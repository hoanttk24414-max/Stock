from __future__ import annotations

import os
import json
from datetime import datetime, time, timezone, timedelta

import pandas as pd
from dotenv import load_dotenv
from dnse import DNSEClient


# =========================================================
# STOCKLENS - MARKET DATA
# Data source: DNSE OpenAPI
#
# Output chuẩn:
# Date | Open | High | Low | Close | Volume
# =========================================================


# =========================================================
# 1. LOAD CONFIG
# =========================================================

load_dotenv()

DNSE_API_KEY = os.getenv("DNSE_API_KEY", "").strip()
DNSE_API_SECRET = os.getenv("DNSE_API_SECRET", "").strip()

DNSE_API_BASE_URL = os.getenv(
    "DNSE_API_BASE_URL",
    "https://openapi.dnse.com.vn",
).strip()

# Nếu để trống, SDK sẽ dùng API version mặc định.
DNSE_API_VERSION = os.getenv(
    "DNSE_API_VERSION",
    "",
).strip()

# Dữ liệu ngày
DNSE_RESOLUTION = os.getenv(
    "DNSE_RESOLUTION",
    "1D",
).strip()

# Response DNSE của em đang trả giá dạng:
# 85.19, 59.70...
# StockLens cần hiển thị 85,190 VND; 59,700 VND.
# Nếu sau này DNSE trả thẳng VND, đổi thành 1.
DNSE_PRICE_MULTIPLIER = float(
    os.getenv(
        "DNSE_PRICE_MULTIPLIER",
        "1000",
    )
)

VN_TZ = timezone(timedelta(hours=7))


# =========================================================
# 2. TICKER
# =========================================================

def normalize_ticker(ticker: str) -> str:
    """
    Chuẩn hóa mã cổ phiếu cho DNSE.

    FPT      -> FPT
    fpt      -> FPT
    FPT.VN   -> FPT
    HPG.VN   -> HPG
    """

    if ticker is None:
        raise ValueError(
            "Mã cổ phiếu không được để trống."
        )

    ticker = str(ticker).strip().upper()

    if not ticker:
        raise ValueError(
            "Mã cổ phiếu không được để trống."
        )

    if ticker.endswith(".VN"):
        ticker = ticker[:-3]

    return ticker


# =========================================================
# 3. DATE FUNCTIONS
# =========================================================

def _parse_date(value) -> datetime:
    """
    Chuyển chuỗi/ngày về datetime.
    """

    if isinstance(value, datetime):
        return value

    try:
        return pd.to_datetime(
            value
        ).to_pydatetime()

    except Exception as exc:
        raise ValueError(
            f"Ngày không hợp lệ: {value}. "
            "Hãy dùng định dạng YYYY-MM-DD."
        ) from exc


def _date_to_timestamp(
    value,
    end_of_day: bool = False,
) -> int:
    """
    Chuyển ngày sang Unix timestamp,
    sử dụng múi giờ Việt Nam.
    """

    dt = _parse_date(value)

    if end_of_day:
        target_time = time(
            23,
            59,
            59,
        )
    else:
        target_time = time(
            0,
            0,
            0,
        )

    dt = datetime.combine(
        dt.date(),
        target_time,
        tzinfo=VN_TZ,
    )

    return int(dt.timestamp())


# =========================================================
# 4. CREATE DNSE CLIENT
# =========================================================

def _create_dnse_client() -> DNSEClient:
    """
    Tạo DNSE API client.
    """

    if not DNSE_API_KEY:
        raise ValueError(
            "Không tìm thấy DNSE_API_KEY.\n"
            "Kiểm tra file .env."
        )

    if not DNSE_API_SECRET:
        raise ValueError(
            "Không tìm thấy DNSE_API_SECRET.\n"
            "Kiểm tra file .env."
        )

    config = {
        "api_key": DNSE_API_KEY,
        "api_secret": DNSE_API_SECRET,
        "base_url": DNSE_API_BASE_URL,
    }

    # Chỉ truyền API version khi .env có khai báo
    if DNSE_API_VERSION:
        config["api_version"] = DNSE_API_VERSION

    return DNSEClient(**config)


# =========================================================
# 5. PARSE DNSE RESPONSE
# =========================================================

def _parse_response_body(body):
    """
    DNSE SDK có thể trả body dưới dạng:
    - dict
    - str chứa JSON
    - bytes chứa JSON

    Hàm này chuẩn hóa về dict/list.
    """

    if body is None:
        return None

    if isinstance(body, bytes):
        body = body.decode(
            "utf-8",
            errors="replace",
        )

    if isinstance(body, str):

        try:
            return json.loads(body)

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "DNSE trả dữ liệu không phải JSON hợp lệ.\n"
                f"Chi tiết: {exc}"
            ) from exc

    return body


# =========================================================
# 6. FIND OHLC DATA
# =========================================================

def _find_ohlc_dict(body):
    """
    Tìm dictionary chứa các mảng:
    t, o, h, l, c, v

    Hỗ trợ cả trường hợp response nằm trong
    data/items/result...
    """

    if not isinstance(body, dict):
        return None

    required_keys = {
        "t",
        "o",
        "h",
        "l",
        "c",
    }

    if required_keys.issubset(
        body.keys()
    ):
        return body

    for key in [
        "data",
        "result",
        "results",
        "items",
        "ohlc",
        "bars",
        "candles",
    ]:

        value = body.get(key)

        if isinstance(value, dict):

            found = _find_ohlc_dict(
                value
            )

            if found is not None:
                return found

    return None


# =========================================================
# 7. CONVERT DNSE -> STOCKLENS DATAFRAME
# =========================================================

def _convert_to_dataframe(body) -> pd.DataFrame:
    """
    Chuyển response OHLC của DNSE:

    {
        "t": [...],
        "o": [...],
        "h": [...],
        "l": [...],
        "c": [...],
        "v": [...]
    }

    thành:

    Date
    Open
    High
    Low
    Close
    Volume
    """

    empty_df = pd.DataFrame(
        columns=[
            "Date",
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]
    )

    if body is None:
        return empty_df

    # -----------------------------------------------------
    # Trường hợp DNSE trả list records
    # -----------------------------------------------------

    if isinstance(body, list):

        if not body:
            return empty_df

        df = pd.DataFrame(body)

        rename_map = {
            "timestamp": "Date",
            "time": "Date",
            "t": "Date",
            "date": "Date",

            "open": "Open",
            "o": "Open",

            "high": "High",
            "h": "High",

            "low": "Low",
            "l": "Low",

            "close": "Close",
            "c": "Close",

            "volume": "Volume",
            "v": "Volume",
        }

        df = df.rename(
            columns=rename_map
        )

    # -----------------------------------------------------
    # Response thực tế của DNSE:
    # {"t": [...], "o": [...], ...}
    # -----------------------------------------------------

    elif isinstance(body, dict):

        ohlc = _find_ohlc_dict(
            body
        )

        if ohlc is None:
            return empty_df

        timestamps = ohlc.get(
            "t",
            [],
        )

        opens = ohlc.get(
            "o",
            [],
        )

        highs = ohlc.get(
            "h",
            [],
        )

        lows = ohlc.get(
            "l",
            [],
        )

        closes = ohlc.get(
            "c",
            [],
        )

        volumes = ohlc.get(
            "v",
            [],
        )

        # Bắt buộc phải có OHLC + timestamp
        lengths = [
            len(timestamps),
            len(opens),
            len(highs),
            len(lows),
            len(closes),
        ]

        if (
            not all(
                isinstance(x, list)
                for x in [
                    timestamps,
                    opens,
                    highs,
                    lows,
                    closes,
                ]
            )
            or min(lengths) == 0
        ):
            return empty_df

        length = min(lengths)

        # Nếu volume thiếu hoặc ngắn hơn thì bổ sung 0
        volume_values = []

        for i in range(length):

            if (
                isinstance(volumes, list)
                and i < len(volumes)
            ):
                volume_values.append(
                    volumes[i]
                )
            else:
                volume_values.append(
                    0
                )

        df = pd.DataFrame(
            {
                "Date": timestamps[:length],
                "Open": opens[:length],
                "High": highs[:length],
                "Low": lows[:length],
                "Close": closes[:length],
                "Volume": volume_values,
            }
        )

    else:
        return empty_df

    # =====================================================
    # Validate required columns
    # =====================================================

    required = [
        "Date",
        "Open",
        "High",
        "Low",
        "Close",
    ]

    for column in required:

        if column not in df.columns:
            return empty_df

    if "Volume" not in df.columns:
        df["Volume"] = 0

    # =====================================================
    # CONVERT DATE
    # =====================================================

    def convert_timestamp(value):

        try:

            if isinstance(
                value,
                (int, float),
            ):

                # Milliseconds
                if value > 10_000_000_000:

                    dt = datetime.fromtimestamp(
                        value / 1000,
                        tz=timezone.utc,
                    )

                # Seconds
                else:

                    dt = datetime.fromtimestamp(
                        value,
                        tz=timezone.utc,
                    )

                dt = dt.astimezone(
                    VN_TZ
                )

                # Bỏ timezone để tương thích
                # với phần còn lại StockLens.
                return pd.Timestamp(
                    dt.replace(
                        tzinfo=None
                    )
                )

            return pd.to_datetime(
                value,
                errors="coerce",
            )

        except Exception:
            return pd.NaT

    df["Date"] = df[
        "Date"
    ].apply(
        convert_timestamp
    )

    # Chỉ cần ngày giao dịch,
    # không cần giờ 09:00.
    df["Date"] = pd.to_datetime(
        df["Date"]
    ).dt.normalize()

    # =====================================================
    # NUMERIC
    # =====================================================

    for column in [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # =====================================================
    # PRICE UNIT
    # =====================================================

    for column in [
        "Open",
        "High",
        "Low",
        "Close",
    ]:

        df[column] = (
            df[column]
            * DNSE_PRICE_MULTIPLIER
        )

    # =====================================================
    # CLEAN DATA
    # =====================================================

    df = df.dropna(
        subset=[
            "Date",
            "Open",
            "High",
            "Low",
            "Close",
        ]
    )

    # Giá phải dương
    df = df[
        (df["Open"] > 0)
        & (df["High"] > 0)
        & (df["Low"] > 0)
        & (df["Close"] > 0)
    ]

    # Logic OHLC
    df = df[
        (df["High"] >= df["Low"])
        & (df["High"] >= df["Open"])
        & (df["High"] >= df["Close"])
        & (df["Low"] <= df["Open"])
        & (df["Low"] <= df["Close"])
    ]

    df["Volume"] = (
        df["Volume"]
        .fillna(0)
        .clip(lower=0)
    )

    df["Volume"] = df[
        "Volume"
    ].astype("int64")

    df = (
        df[
            [
                "Date",
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
            ]
        ]
        .sort_values("Date")
        .drop_duplicates(
            subset=["Date"],
            keep="last",
        )
        .reset_index(drop=True)
    )

    return df


# =========================================================
# 8. MAIN FUNCTION USED BY STOCKLENS
# =========================================================

def get_market_data(
    ticker: str,
    start_date,
    end_date,
    resolution: str | None = None,
) -> pd.DataFrame:
    """
    Lấy OHLCV lịch sử từ DNSE OpenAPI.

    Parameters
    ----------
    ticker:
        FPT, HPG, MWG, VNM, ACB...

    start_date:
        YYYY-MM-DD

    end_date:
        YYYY-MM-DD

    resolution:
        Mặc định lấy từ DNSE_RESOLUTION.
        StockLens hiện sử dụng 1D.

    Returns
    -------
    pd.DataFrame

    Columns:
        Date
        Open
        High
        Low
        Close
        Volume
    """

    ticker = normalize_ticker(
        ticker
    )

    start_dt = _parse_date(
        start_date
    )

    end_dt = _parse_date(
        end_date
    )

    if (
        start_dt.date()
        > end_dt.date()
    ):
        raise ValueError(
            "Ngày bắt đầu phải nhỏ hơn "
            "hoặc bằng ngày kết thúc."
        )

    if resolution is None:
        resolution = DNSE_RESOLUTION

    from_timestamp = (
        _date_to_timestamp(
            start_date,
            end_of_day=False,
        )
    )

    to_timestamp = (
        _date_to_timestamp(
            end_date,
            end_of_day=True,
        )
    )

    client = _create_dnse_client()

    query = {
        "symbol": ticker,
        "resolution": str(
            resolution
        ),
        "from": from_timestamp,
        "to": to_timestamp,
    }

    # =====================================================
    # CALL DNSE
    # =====================================================

    try:

        status, body = (
            client.get_ohlc(
                bar_type="STOCK",
                query=query,
                dry_run=False,
            )
        )

    except TypeError:

        # Hỗ trợ SDK version không có
        # tham số dry_run.
        try:

            status, body = (
                client.get_ohlc(
                    bar_type="STOCK",
                    query=query,
                )
            )

        except Exception as exc:

            raise RuntimeError(
                "Không thể gọi DNSE OpenAPI.\n"
                f"Chi tiết: {exc}"
            ) from exc

    except Exception as exc:

        raise RuntimeError(
            "Không thể gọi DNSE OpenAPI.\n"
            f"Chi tiết: {exc}"
        ) from exc

    # =====================================================
    # HTTP STATUS
    # =====================================================

    if status == 401:

        raise RuntimeError(
            "DNSE trả HTTP 401 - Unauthorized.\n"
            "Kiểm tra API Key và API Secret."
        )

    if status == 403:

        raise RuntimeError(
            "DNSE trả HTTP 403 - Forbidden.\n"
            "API Key không có quyền truy cập "
            "hoặc chữ ký không hợp lệ."
        )

    if status != 200:

        raise RuntimeError(
            f"DNSE OpenAPI trả HTTP {status}.\n"
            f"Response: {body}"
        )

    # =====================================================
    # BODY: STR -> DICT
    # =====================================================

    body = _parse_response_body(
        body
    )

    # =====================================================
    # CONVERT TO DATAFRAME
    # =====================================================

    df = _convert_to_dataframe(
        body
    )

    if df.empty:

        raise ValueError(
            f"DNSE không trả dữ liệu OHLC hợp lệ "
            f"cho mã {ticker} trong khoảng "
            f"{start_date} → {end_date}."
        )

    # =====================================================
    # FILTER DATE
    # =====================================================

    start_filter = pd.Timestamp(
        start_dt.date()
    )

    end_filter = pd.Timestamp(
        end_dt.date()
    )

    df = df[
        (df["Date"] >= start_filter)
        & (df["Date"] <= end_filter)
    ].copy()

    df.reset_index(
        drop=True,
        inplace=True,
    )

    if df.empty:

        raise ValueError(
            f"Không có phiên giao dịch của "
            f"{ticker} trong khoảng ngày đã chọn."
        )

    # =====================================================
    # METADATA
    # =====================================================

    df.attrs["ticker"] = ticker
    df.attrs["source"] = (
        "DNSE OpenAPI"
    )
    df.attrs["resolution"] = str(
        resolution
    )

    df.attrs["price_unit"] = "VND"

    return df


# =========================================================
# 9. TEST MARKET_DATA.PY
# =========================================================

if __name__ == "__main__":

    print(
        "===== STOCKLENS - DNSE MARKET DATA TEST ====="
    )

    try:

        data = get_market_data(
            ticker="FPT",
            start_date="2026-01-01",
            end_date="2026-10-08",
        )

        print()
        print(
            "Ticker:",
            data.attrs.get(
                "ticker"
            ),
        )

        print(
            "Source:",
            data.attrs.get(
                "source"
            ),
        )

        print(
            "Resolution:",
            data.attrs.get(
                "resolution"
            ),
        )

        print(
            "Price unit:",
            data.attrs.get(
                "price_unit"
            ),
        )

        print(
            "Rows:",
            len(data),
        )

        print()
        print(
            "5 dòng đầu:"
        )

        print(
            data.head().to_string(
                index=False
            )
        )

        print()
        print(
            "5 dòng cuối:"
        )

        print(
            data.tail().to_string(
                index=False
            )
        )

        print()
        print(
            "Latest Close:",
            f"{data['Close'].iloc[-1]:,.0f} VND",
        )

        print()
        print(
            "DNSE market data test: OK"
        )

    except Exception as exc:

        print()
        print(
            "ERROR:"
        )
        print(exc)