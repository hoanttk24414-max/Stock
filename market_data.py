"""StockLens - Market data loader.

Priority:
    1. DNSE OpenAPI
    2. vnstock Market fallback ONLY when DNSE cannot be reached (timeout/connection error)

Public contract:
    get_market_data(ticker, start_date, end_date) -> pandas.DataFrame

Returned columns:
    Date, Open, High, Low, Close, Volume

No synthetic prices are generated.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import pandas as pd
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


REQUIRED = ["Date", "Open", "High", "Low", "Close", "Volume"]
BASE_URL = os.getenv("DNSE_API_BASE_URL", "https://openapi.dnse.com.vn").rstrip("/")
API_VERSION = os.getenv("DNSE_API_VERSION", "2026-07-23")
DEFAULT_RESOLUTION = os.getenv("DNSE_RESOLUTION", "1D")

# Cloud should not wait 30+ seconds before switching to fallback.
CONNECT_TIMEOUT_SECONDS = float(os.getenv("DNSE_CONNECT_TIMEOUT", "8"))
READ_TIMEOUT_SECONDS = float(os.getenv("DNSE_READ_TIMEOUT", "30"))


class DNSEConnectionError(RuntimeError):
    """Raised only when DNSE cannot be reached at network level."""


def candidate_symbols(ticker: str) -> list[str]:
    symbol = (ticker or "").strip().upper()
    if not symbol:
        return []
    if symbol.endswith(".VN"):
        symbol = symbol[:-3]
    return [symbol]


def _format_dnse_date_header() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%a, %d %b %Y %H:%M:%S +0000")


def _build_auth_headers(method: str, path: str, api_key: str, api_secret: str) -> dict[str, str]:
    date_value = _format_dnse_date_header()
    nonce = uuid.uuid4().hex
    algorithm = "hmac-sha256"

    signing_text = (
        f"(request-target): {method.lower()} {path}\n"
        f"date: {date_value}\n"
        f"nonce: {nonce}"
    )

    digest = hmac.new(
        api_secret.encode("utf-8"),
        signing_text.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    signature = quote(base64.b64encode(digest).decode("ascii"), safe="")

    signature_header = (
        f'Signature keyId="{api_key}",'
        f'algorithm="{algorithm}",'
        f'headers="(request-target) date",'
        f'signature="{signature}",'
        f'nonce="{nonce}"'
    )

    headers = {
        "Date": date_value,
        "X-Signature": signature_header,
        "x-api-key": api_key,
        "Accept": "application/json",
    }
    if API_VERSION:
        headers["version"] = API_VERSION
    return headers


def _to_epoch_seconds(value: pd.Timestamp, end_of_day: bool = False) -> int:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("Asia/Ho_Chi_Minh")
    else:
        ts = ts.tz_convert("Asia/Ho_Chi_Minh")

    ts = ts.normalize()
    if end_of_day:
        ts = ts + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return int(ts.timestamp())


def _pick(d: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in d:
            return d[name]
    return None


def _parse_timestamp_series(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    numeric_non_na = numeric.dropna()

    if not numeric_non_na.empty:
        median_abs = float(numeric_non_na.abs().median())
        unit = "ms" if median_abs >= 1e11 else "s"
        out = pd.to_datetime(numeric, unit=unit, errors="coerce", utc=True)
        return out.dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)

    out = pd.to_datetime(values, errors="coerce", utc=True)
    try:
        return out.dt.tz_convert("Asia/Ho_Chi_Minh").dt.tz_localize(None)
    except (TypeError, AttributeError):
        return pd.to_datetime(values, errors="coerce")


def _payload_to_frame(payload: Any) -> pd.DataFrame:
    if payload is None:
        return pd.DataFrame(columns=REQUIRED)

    if isinstance(payload, dict) and "data" in payload:
        nested = payload.get("data")
        if nested is not None:
            payload = nested

    if isinstance(payload, dict):
        t = _pick(payload, "t", "time", "timestamp", "timestamps", "date", "dates")
        o = _pick(payload, "o", "open", "opens")
        h = _pick(payload, "h", "high", "highs")
        l = _pick(payload, "l", "low", "lows")
        c = _pick(payload, "c", "close", "closes")
        v = _pick(payload, "v", "volume", "volumes")

        if all(isinstance(x, (list, tuple)) for x in (t, o, h, l, c, v)):
            n = min(len(t), len(o), len(h), len(l), len(c), len(v))
            return pd.DataFrame({
                "Date": list(t)[:n],
                "Open": list(o)[:n],
                "High": list(h)[:n],
                "Low": list(l)[:n],
                "Close": list(c)[:n],
                "Volume": list(v)[:n],
            })

        for key in ("items", "rows", "candles", "bars", "result"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break

    if isinstance(payload, list):
        rows: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            rows.append({
                "Date": _pick(item, "t", "time", "timestamp", "date", "tradingDate", "Date"),
                "Open": _pick(item, "o", "open", "Open"),
                "High": _pick(item, "h", "high", "High"),
                "Low": _pick(item, "l", "low", "Low"),
                "Close": _pick(item, "c", "close", "Close"),
                "Volume": _pick(item, "v", "volume", "Volume"),
            })
        return pd.DataFrame(rows, columns=REQUIRED)

    return pd.DataFrame(columns=REQUIRED)


def _normalize_ohlcv(
    raw: pd.DataFrame | None,
    symbol: str,
    source_name: str,
) -> pd.DataFrame:
    """Normalize DNSE/vnstock OHLCV to StockLens format and VND prices."""
    if raw is None or raw.empty:
        empty = pd.DataFrame(columns=REQUIRED)
        empty.attrs["symbol"] = symbol
        empty.attrs["source"] = source_name
        return empty

    df = raw.copy()

    # vnstock Market returns lower-case columns such as:
    # time, open, high, low, close, volume
    rename_map = {}
    for col in df.columns:
        key = str(col).strip().lower()
        if key in ("time", "date", "datetime", "timestamp", "tradingdate"):
            rename_map[col] = "Date"
        elif key == "open":
            rename_map[col] = "Open"
        elif key == "high":
            rename_map[col] = "High"
        elif key == "low":
            rename_map[col] = "Low"
        elif key == "close":
            rename_map[col] = "Close"
        elif key == "volume":
            rename_map[col] = "Volume"

    df = df.rename(columns=rename_map)

    if not all(col in df.columns for col in REQUIRED):
        empty = pd.DataFrame(columns=REQUIRED)
        empty.attrs["symbol"] = symbol
        empty.attrs["source"] = source_name
        return empty

    df = df[REQUIRED].copy()

    # DNSE may return epochs; vnstock normally returns datetime-like strings.
    if pd.api.types.is_numeric_dtype(df["Date"]):
        df["Date"] = _parse_timestamp_series(df["Date"])
    else:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        try:
            if df["Date"].dt.tz is not None:
                df["Date"] = (
                    df["Date"]
                    .dt.tz_convert("Asia/Ho_Chi_Minh")
                    .dt.tz_localize(None)
                )
        except (AttributeError, TypeError):
            pass

    for col in REQUIRED[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = (
        df.dropna(subset=REQUIRED)
        .query("High >= Low and Close > 0 and Volume >= 0")
        .sort_values("Date")
        .drop_duplicates("Date", keep="last")
        .reset_index(drop=True)
    )

    # Both DNSE and vnstock/KBS commonly expose VN stock prices in thousand VND.
    # Detect instead of blindly multiplying.
    if not df.empty:
        median_close = float(df["Close"].median())
        if 0 < median_close < 1000:
            for col in ("Open", "High", "Low", "Close"):
                df[col] = df[col] * 1000.0
            df.attrs["raw_price_unit"] = "thousand VND"
        else:
            df.attrs["raw_price_unit"] = "VND or provider-native"

    df.attrs["symbol"] = symbol
    df.attrs["source"] = source_name
    df.attrs["price_unit"] = "VND"
    df.attrs["resolution"] = DEFAULT_RESOLUTION
    return df


def _filter_window(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if df.empty:
        return df

    start_day = start.normalize().tz_localize(None) if start.tzinfo else start.normalize()
    end_day = end.normalize().tz_localize(None) if end.tzinfo else end.normalize()

    out = df.loc[
        (df["Date"].dt.normalize() >= start_day)
        & (df["Date"].dt.normalize() <= end_day)
    ].reset_index(drop=True)

    # Preserve metadata after slicing/reset_index.
    out.attrs.update(df.attrs)
    return out


def _get_dnse_market_data(
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Primary source. Network failure is distinguishable from API/auth errors."""
    api_key = (os.getenv("DNSE_API_KEY") or os.getenv("api-key") or "").strip()
    api_secret = (os.getenv("DNSE_API_SECRET") or os.getenv("secret-key") or "").strip()

    if not api_key or not api_secret:
        raise ValueError(
            "Chưa cấu hình DNSE API. Hãy cấu hình DNSE_API_KEY và DNSE_API_SECRET."
        )

    path = "/price/ohlc"
    params = {
        "symbol": symbol,
        "resolution": DEFAULT_RESOLUTION,
        "from": _to_epoch_seconds(start, end_of_day=False),
        "to": _to_epoch_seconds(end, end_of_day=True),
        "type": "STOCK",
    }
    headers = _build_auth_headers("GET", path, api_key, api_secret)

    try:
        response = requests.get(
            f"{BASE_URL}{path}",
            params=params,
            headers=headers,
            timeout=(CONNECT_TIMEOUT_SECONDS, READ_TIMEOUT_SECONDS),
        )
    except (requests.Timeout, requests.ConnectionError) as exc:
        raise DNSEConnectionError(f"Không kết nối được DNSE OpenAPI: {exc}") from exc
    except requests.RequestException as exc:
        # Other request-level transport errors are also suitable for fallback.
        raise DNSEConnectionError(f"Lỗi kết nối DNSE OpenAPI: {exc}") from exc

    # Authentication/configuration errors are NOT hidden by fallback.
    if response.status_code in (401, 403):
        raise RuntimeError(
            "DNSE từ chối xác thực (HTTP "
            f"{response.status_code}). Kiểm tra API Key/API Secret và trạng thái key."
        )
    if response.status_code == 429:
        raise RuntimeError("DNSE giới hạn tần suất gọi API (HTTP 429). Hãy thử lại sau.")
    if response.status_code >= 400:
        detail = response.text[:500].replace("\n", " ")
        raise RuntimeError(f"DNSE OpenAPI lỗi HTTP {response.status_code}: {detail}")

    try:
        payload = response.json()
    except ValueError:
        try:
            payload = json.loads(response.text)
        except Exception as exc:
            raise RuntimeError("DNSE trả về dữ liệu không phải JSON hợp lệ.") from exc

    raw_df = _payload_to_frame(payload)
    df = _normalize_ohlcv(
        raw_df,
        symbol,
        source_name="DNSE OpenAPI /price/ohlc",
    )
    return _filter_window(df, start, end)


def _get_vnstock_market_data(
    symbol: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """Fallback source used only after a DNSE network failure."""
    from vnstock import Market

    start_text = start.strftime("%Y-%m-%d")
    end_text = end.strftime("%Y-%m-%d")

    market = Market()
    raw = market.equity(symbol).ohlcv(
        start=start_text,
        end=end_text,
        interval="1D",
    )

    if raw is None:
        raw = pd.DataFrame()
    elif not isinstance(raw, pd.DataFrame):
        raw = pd.DataFrame(raw)

    df = _normalize_ohlcv(
        raw,
        symbol,
        source_name="vnstock Market fallback",
    )
    df = _filter_window(df, start, end)

    if df.empty:
        raise RuntimeError(
            f"vnstock không trả dữ liệu OHLCV hợp lệ cho {symbol} "
            f"trong khoảng {start_text} → {end_text}."
        )

    df.attrs["fallback_used"] = True
    df.attrs["primary_source"] = "DNSE OpenAPI"
    return df


def get_market_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Get StockLens OHLCV with DNSE -> vnstock fallback.

    Logic
    -----
    DNSE OK:
        Return DNSE data.

    DNSE timeout / connection failure:
        Automatically use vnstock Market.

    DNSE auth/API error:
        Raise the DNSE error directly. This prevents bad credentials or API
        configuration from being silently hidden by fallback.

    DNSE network failure + vnstock failure:
        Raise one combined error containing both causes.
    """
    symbols = candidate_symbols(ticker)
    if not symbols:
        raise ValueError("Mã cổ phiếu không được để trống.")
    symbol = symbols[0]

    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)

    if pd.isna(start) or pd.isna(end):
        raise ValueError("Ngày bắt đầu/kết thúc không hợp lệ.")
    if start > end:
        raise ValueError("Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.")

    try:
        df = _get_dnse_market_data(symbol, start, end)

        if df.empty:
            # DNSE connected successfully but returned no candles.
            # Do not silently substitute another provider in this case.
            df.attrs["request_params"] = {
                "symbol": symbol,
                "resolution": DEFAULT_RESOLUTION,
                "from": start.strftime("%Y-%m-%d"),
                "to": end.strftime("%Y-%m-%d"),
            }

        df.attrs["fallback_used"] = False
        return df

    except DNSEConnectionError as dnse_error:
        try:
            df = _get_vnstock_market_data(symbol, start, end)
            df.attrs["fallback_reason"] = str(dnse_error)
            return df
        except Exception as vnstock_error:
            raise RuntimeError(
                "Không lấy được dữ liệu thị trường từ cả hai nguồn. "
                f"DNSE: {dnse_error} | "
                f"vnstock fallback: {vnstock_error}"
            ) from vnstock_error


if __name__ == "__main__":
    test_symbol = os.getenv("DNSE_TEST_SYMBOL", "FPT")
    test_start = os.getenv("DNSE_TEST_START", "2026-01-01")
    test_end = os.getenv("DNSE_TEST_END", "2026-10-09")

    try:
        data = get_market_data(test_symbol, test_start, test_end)
        print(f"StockLens market data: {test_symbol} | rows={len(data)}")
        print("Source:", data.attrs.get("source"))
        print("Fallback used:", data.attrs.get("fallback_used"))
        if not data.empty:
            print(data.tail())
    except Exception as exc:
        print(f"ERROR: {exc}")
