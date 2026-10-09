"""StockLens - Market data loader using DNSE OpenAPI.

Public contract kept compatible with the existing StockLens project:
    get_market_data(ticker, start_date, end_date) -> pandas.DataFrame

Returned columns:
    Date, Open, High, Low, Close, Volume

The module does NOT hard-code a stock code and does NOT fall back to synthetic data.
Credentials are read from environment variables / .env:
    DNSE_API_KEY=...
    DNSE_API_SECRET=...

Optional:
    DNSE_API_BASE_URL=https://openapi.dnse.com.vn
    DNSE_API_VERSION=2026-07-23
    DNSE_RESOLUTION=1D

Notes
-----
- DNSE OHLC endpoint: GET /price/ohlc
- For stocks, DNSE market-data prices are commonly returned in display units
  (thousand VND). This module auto-detects that format and converts OHLC to VND
  so the rest of StockLens can continue displaying prices like 58,200 VND.
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
    # The module still works if credentials are supplied as OS environment vars.
    pass


REQUIRED = ["Date", "Open", "High", "Low", "Close", "Volume"]
BASE_URL = os.getenv("DNSE_API_BASE_URL", "https://openapi.dnse.com.vn").rstrip("/")
API_VERSION = os.getenv("DNSE_API_VERSION", "2026-07-23")
DEFAULT_RESOLUTION = os.getenv("DNSE_RESOLUTION", "1D")
TIMEOUT_SECONDS = 30


def candidate_symbols(ticker: str) -> list[str]:
    """Normalize a user-entered Vietnam stock ticker for DNSE.

    Examples
    --------
    FPT -> ["FPT"]
    fpt -> ["FPT"]
    FPT.VN -> ["FPT"]  # convenient when users paste a Yahoo-style symbol
    """
    symbol = (ticker or "").strip().upper()
    if not symbol:
        return []
    if symbol.endswith(".VN"):
        symbol = symbol[:-3]
    return [symbol]


def _format_dnse_date_header() -> str:
    """Return DNSE's UTC Date header format, e.g. Thu, 09 Oct 2026 06:30:00 +0000."""
    now = datetime.now(timezone.utc)
    return now.strftime("%a, %d %b %Y %H:%M:%S +0000")


def _build_auth_headers(method: str, path: str, api_key: str, api_secret: str) -> dict[str, str]:
    """Build HMAC headers compatible with DNSE OpenAPI's request-signing scheme."""
    date_value = _format_dnse_date_header()
    nonce = uuid.uuid4().hex
    algorithm = "hmac-sha256"

    # DNSE signs the request path only (query string is not included).
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

    # DNSE's SDK URL-encodes the Base64 signature.
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
    """Convert an analysis date to Unix seconds using Vietnam local time."""
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
    """Parse DNSE timestamps whether they arrive as epoch seconds/ms or strings."""
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
    """Accept common DNSE OHLC response shapes and return standardized columns."""
    if payload is None:
        return pd.DataFrame(columns=REQUIRED)

    # Some APIs wrap the OHLC payload inside "data".
    if isinstance(payload, dict) and "data" in payload:
        nested = payload.get("data")
        if nested is not None:
            payload = nested

    # Shape A: parallel arrays, e.g. {t:[...], o:[...], h:[...], l:[...], c:[...], v:[...]}
    if isinstance(payload, dict):
        t = _pick(payload, "t", "time", "timestamp", "timestamps", "date", "dates")
        o = _pick(payload, "o", "open", "opens")
        h = _pick(payload, "h", "high", "highs")
        l = _pick(payload, "l", "low", "lows")
        c = _pick(payload, "c", "close", "closes")
        v = _pick(payload, "v", "volume", "volumes")

        if all(isinstance(x, (list, tuple)) for x in (t, o, h, l, c, v)):
            n = min(len(t), len(o), len(h), len(l), len(c), len(v))
            return pd.DataFrame(
                {
                    "Date": list(t)[:n],
                    "Open": list(o)[:n],
                    "High": list(h)[:n],
                    "Low": list(l)[:n],
                    "Close": list(c)[:n],
                    "Volume": list(v)[:n],
                }
            )

        # Shape B: records may be nested under another conventional key.
        for key in ("items", "rows", "candles", "bars", "result"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break

    # Shape C: list of candle dictionaries.
    if isinstance(payload, list):
        rows: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "Date": _pick(item, "t", "time", "timestamp", "date", "tradingDate", "Date"),
                    "Open": _pick(item, "o", "open", "Open"),
                    "High": _pick(item, "h", "high", "High"),
                    "Low": _pick(item, "l", "low", "Low"),
                    "Close": _pick(item, "c", "close", "Close"),
                    "Volume": _pick(item, "v", "volume", "Volume"),
                }
            )
        return pd.DataFrame(rows, columns=REQUIRED)

    return pd.DataFrame(columns=REQUIRED)


def _normalize(raw: pd.DataFrame | None, symbol: str) -> pd.DataFrame:
    """Clean DNSE candles and convert stock prices to VND when needed."""
    if raw is None or raw.empty:
        empty = pd.DataFrame(columns=REQUIRED)
        empty.attrs["symbol"] = symbol
        empty.attrs["source"] = "DNSE OpenAPI /price/ohlc"
        return empty

    df = raw.copy()
    if not all(col in df.columns for col in REQUIRED):
        return pd.DataFrame(columns=REQUIRED)

    df = df[REQUIRED].copy()
    df["Date"] = _parse_timestamp_series(df["Date"])

    for col in REQUIRED[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = (
        df.dropna(subset=REQUIRED)
        .query("High >= Low and Close > 0 and Volume >= 0")
        .sort_values("Date")
        .drop_duplicates("Date", keep="last")
        .reset_index(drop=True)
    )

    # DNSE stock market-data normally uses display prices in thousand VND
    # (e.g. 58.2 means 58,200 VND). Auto-detect instead of blindly multiplying.
    if not df.empty:
        median_close = float(df["Close"].median())
        if 0 < median_close < 1000:
            for col in ("Open", "High", "Low", "Close"):
                df[col] = df[col] * 1000.0
            df.attrs["dnse_raw_price_unit"] = "thousand VND"
        else:
            df.attrs["dnse_raw_price_unit"] = "VND or provider-native"

    df.attrs["symbol"] = symbol
    df.attrs["source"] = "DNSE OpenAPI /price/ohlc"
    df.attrs["price_unit"] = "VND"
    df.attrs["resolution"] = DEFAULT_RESOLUTION
    return df


def get_market_data(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch historical daily OHLCV from DNSE for one Vietnam stock ticker.

    Parameters
    ----------
    ticker:
        Stock symbol such as FPT, HPG, MWG. ``FPT.VN`` is also accepted and
        automatically normalized to ``FPT`` for DNSE.
    start_date, end_date:
        Inclusive analysis window, e.g. ``2025-01-01`` and ``2026-10-09``.

    Returns
    -------
    pandas.DataFrame
        Standardized columns: Date, Open, High, Low, Close, Volume.
        If DNSE returns no candles, an empty DataFrame is returned.

    Raises
    ------
    ValueError
        Invalid ticker/date input or missing credentials.
    RuntimeError
        DNSE authentication/network/API errors.
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

    api_key = (os.getenv("DNSE_API_KEY") or os.getenv("api-key") or "").strip()
    api_secret = (os.getenv("DNSE_API_SECRET") or os.getenv("secret-key") or "").strip()
    if not api_key or not api_secret:
        raise ValueError(
            "Chưa cấu hình DNSE API. Hãy tạo file .env với DNSE_API_KEY và DNSE_API_SECRET."
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
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Không kết nối được DNSE OpenAPI: {exc}") from exc

    if response.status_code in (401, 403):
        raise RuntimeError(
            "DNSE từ chối xác thực (HTTP "
            f"{response.status_code}). Kiểm tra API Key/API Secret, trạng thái key và thời gian hệ thống Windows."
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
    df = _normalize(raw_df, symbol)

    if df.empty:
        df.attrs["request_params"] = {
            "symbol": symbol,
            "resolution": DEFAULT_RESOLUTION,
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
        }
        return df

    # Final defensive filter to the user's inclusive analysis window.
    start_day = start.normalize().tz_localize(None) if start.tzinfo else start.normalize()
    end_day = end.normalize().tz_localize(None) if end.tzinfo else end.normalize()
    mask = (df["Date"].dt.normalize() >= start_day) & (df["Date"].dt.normalize() <= end_day)
    df = df.loc[mask].reset_index(drop=True)

    df.attrs["symbol"] = symbol
    df.attrs["source"] = "DNSE OpenAPI /price/ohlc"
    df.attrs["price_unit"] = "VND"
    df.attrs["resolution"] = DEFAULT_RESOLUTION
    return df


if __name__ == "__main__":
    # Smoke test only. It uses credentials from .env and never prints secrets.
    test_symbol = os.getenv("DNSE_TEST_SYMBOL", "FPT")
    test_start = os.getenv("DNSE_TEST_START", "2026-01-01")
    test_end = os.getenv("DNSE_TEST_END", "2026-10-09")

    try:
        data = get_market_data(test_symbol, test_start, test_end)
        print(f"DNSE market data: {test_symbol} | rows={len(data)}")
        if not data.empty:
            print(data.tail())
            print("Source:", data.attrs.get("source"))
    except Exception as exc:
        print(f"ERROR: {exc}")
