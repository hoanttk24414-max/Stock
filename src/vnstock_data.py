from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd


# =========================================================
# STOCKLENS - VNSTOCK FINANCIAL DATA
#
# Market price:
#   DNSE OpenAPI
#
# Financial statements:
#   vnstock -> KBS
#
# IMPORTANT:
# Current KBS/vnstock output on this machine returns annual
# values in reverse order relative to year-column labels.
# We normalize that below.
# =========================================================


REPAIR_KBS_REVERSED_PERIODS = True


# =========================================================
# BASIC
# =========================================================

def normalize_ticker(ticker: str) -> str:

    if ticker is None:
        raise ValueError(
            "Mã cổ phiếu không được để trống."
        )

    ticker = str(
        ticker
    ).strip().upper()

    if not ticker:
        raise ValueError(
            "Mã cổ phiếu không được để trống."
        )

    if ticker.endswith(".VN"):
        ticker = ticker[:-3]

    return ticker


def _safe_float(value):

    if value is None:
        return None

    try:

        value = float(value)

        if pd.isna(value):
            return None

        return value

    except (
        TypeError,
        ValueError,
    ):
        return None


def _safe_divide(
    numerator,
    denominator,
):

    numerator = _safe_float(
        numerator
    )

    denominator = _safe_float(
        denominator
    )

    if (
        numerator is None
        or denominator is None
        or denominator == 0
    ):
        return None

    return (
        numerator
        / denominator
    )


def _normalize_percent(value):
    """
    28.30 -> 0.2830
    0.283 -> 0.283
    """

    value = _safe_float(
        value
    )

    if value is None:
        return None

    if abs(value) > 1.5:
        return value / 100

    return value


def _ensure_dataframe(
    value,
):

    if isinstance(
        value,
        pd.DataFrame,
    ):
        return value.copy()

    if value is None:
        return pd.DataFrame()

    try:
        return pd.DataFrame(
            value
        )

    except Exception:
        return pd.DataFrame()


# =========================================================
# PERIOD
# =========================================================

_METADATA_COLUMNS = {
    "item",
    "item_id",
    "item_en",
    "unit",
    "levels",
    "row_number",
    "code",
    "name",
}


def _period_sort_key(
    value: str,
):

    text = str(
        value
    ).strip()

    # 2026-Q3
    q = re.fullmatch(
        r"(\d{4})-Q([1-4])(?:_\d+)?",
        text,
    )

    if q:

        return (
            int(q.group(1)),
            int(q.group(2)),
        )

    # 2025
    y = re.fullmatch(
        r"\d{4}",
        text,
    )

    if y:

        return (
            int(text),
            5,
        )

    return (
        -1,
        -1,
    )


def _get_period_columns(
    df: pd.DataFrame,
) -> list[str]:

    if (
        df is None
        or df.empty
    ):
        return []

    result = []

    for column in df.columns:

        text = str(column)

        if (
            _period_sort_key(text)
            != (-1, -1)
        ):
            result.append(text)

    result.sort(
        key=_period_sort_key,
        reverse=True,
    )

    return result


def _latest_period(
    df: pd.DataFrame,
):

    periods = (
        _get_period_columns(df)
    )

    if not periods:
        return None

    return periods[0]


# =========================================================
# FIX KBS PERIOD ORDER
# =========================================================

def _repair_period_values(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Dữ liệu thực tế máy hiện tại:

        column 2025 -> value năm 2022
        column 2024 -> value năm 2023
        column 2023 -> value năm 2024
        column 2022 -> value năm 2025

    Vì vậy đảo VALUES giữa các cột năm,
    giữ nguyên tên cột.

    Ví dụ:
        trước:
        2025 = 44,009
        2024 = 52,618
        2023 = 62,849
        2022 = 70,113

        sau:
        2025 = 70,113
        2024 = 62,849
        2023 = 52,618
        2022 = 44,009
    """

    if (
        df is None
        or df.empty
        or not REPAIR_KBS_REVERSED_PERIODS
    ):
        return df

    df = df.copy()

    period_columns = (
        _get_period_columns(df)
    )

    if len(period_columns) <= 1:
        return df

    reversed_values = (
        df[
            list(
                reversed(
                    period_columns
                )
            )
        ]
        .to_numpy(
            copy=True
        )
    )

    df.loc[
        :,
        period_columns
    ] = reversed_values

    return df


# =========================================================
# ITEM VALUE
# =========================================================

def _get_item_value(
    df: pd.DataFrame,
    item_ids: list[str],
    period: str | None = None,
):
    """
    Lấy giá trị theo item_id.

    Có trường hợp KBS trả nhiều row cùng item_id, trong đó row đầu tiên
    là NaN nhưng row sau có giá trị thật. Vì vậy luôn duyệt toàn bộ
    các row khớp trước khi kết luận thiếu dữ liệu.
    """

    if (
        df is None
        or df.empty
        or "item_id" not in df.columns
    ):
        return None

    normalized = (
        df["item_id"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    for item_id in item_ids:

        target = (
            str(item_id)
            .strip()
            .lower()
        )

        matches = df[
            normalized == target
        ]

        if matches.empty:
            continue

        if (
            period is not None
            and period in matches.columns
        ):

            for _, row in matches.iterrows():

                value = _safe_float(
                    row[period]
                )

                if value is not None:
                    return value

        periods = (
            _get_period_columns(
                matches
            )
        )

        for p in periods:

            for _, row in matches.iterrows():

                value = _safe_float(
                    row[p]
                )

                if value is not None:
                    return value

    return None


def _normalize_search_text(value) -> str:
    """
    Chuẩn hóa text để fallback theo nhãn KBS.

    Ví dụ:
        "Vốn chủ sở hữu" -> "von chu so huu"
        "Tổng thu nhập hoạt động" -> "tong thu nhap hoat dong"
    """

    if value is None:
        return ""

    text = str(value).strip().lower()

    text = unicodedata.normalize(
        "NFKD",
        text,
    )

    text = "".join(
        ch for ch in text
        if not unicodedata.combining(ch)
    )

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _get_item_value_flexible(
    df: pd.DataFrame,
    item_ids: list[str],
    period: str | None = None,
    label_keywords: list[str] | None = None,
):
    """
    Ưu tiên item_id chuẩn; nếu vnstock/KBS đổi item_id giữa nhóm ngành
    thì fallback theo item/item_en/name.

    Fallback chỉ dùng khi exact item_id không tìm thấy để tránh làm thay
    đổi kết quả của các mã đang chạy ổn như FPT.
    """

    value = _get_item_value(
        df=df,
        item_ids=item_ids,
        period=period,
    )

    if value is not None:
        return value

    if (
        df is None
        or df.empty
        or not label_keywords
    ):
        return None

    search_columns = [
        column
        for column in [
            "item_id",
            "item",
            "item_en",
            "name",
        ]
        if column in df.columns
    ]

    if not search_columns:
        return None

    normalized_keywords = [
        _normalize_search_text(keyword)
        for keyword in label_keywords
        if keyword
    ]

    for keyword in normalized_keywords:

        if not keyword:
            continue

        for _, row in df.iterrows():

            row_text = " | ".join(
                _normalize_search_text(
                    row.get(column)
                )
                for column in search_columns
            )

            if keyword not in row_text:
                continue

            if (
                period is not None
                and period in df.columns
            ):

                value = _safe_float(
                    row.get(period)
                )

                if value is not None:
                    return value

            for p in _get_period_columns(df):

                value = _safe_float(
                    row.get(p)
                )

                if value is not None:
                    return value

    return None


def _statement_text_blob(
    *frames: pd.DataFrame,
) -> str:

    parts = []

    for df in frames:

        if (
            df is None
            or df.empty
        ):
            continue

        for column in [
            "item_id",
            "item",
            "item_en",
            "name",
        ]:

            if column not in df.columns:
                continue

            parts.extend(
                _normalize_search_text(value)
                for value in df[column].dropna().astype(str).tolist()
            )

    return " | ".join(parts)


def _detect_business_type(
    profile: dict[str, Any],
    income: pd.DataFrame,
    balance: pd.DataFrame,
) -> str:
    """
    Chỉ tách riêng ngân hàng khi có tín hiệu đủ rõ.

    Không gộp toàn bộ ngành tài chính vào ngân hàng vì CTCK/bảo hiểm có
    cấu trúc BCTC khác.
    """

    profile_text = _normalize_search_text(
        " ".join(
            str(profile.get(key) or "")
            for key in [
                "industry",
                "name",
            ]
        )
    )

    statement_text = _statement_text_blob(
        income,
        balance,
    )

    bank_markers = [
        "ngan hang",
        "commercial bank",
        "banking",
        "net interest income",
        "thu nhap lai thuan",
        "customer deposits",
        "tien gui cua khach hang",
        "loans to customers",
        "cho vay khach hang",
    ]

    if any(
        marker in profile_text
        or marker in statement_text
        for marker in bank_markers
    ):
        return "bank"

    return "corporate"


# =========================================================
# VNSTOCK
# =========================================================

def _call_ratio(
    equity,
    ticker: str | None,
    period: str,
):

    for name in [
        "ratios",
        "ratio",
    ]:

        method = getattr(
            equity,
            name,
            None,
        )

        if method is None:
            continue

        try:

            if ticker is None:

                return method(
                    period=period
                )

            return method(
                symbol=ticker,
                period=period,
            )

        except Exception:
            continue

    return pd.DataFrame()


def _load_vnstock(
    ticker: str,
    period: str,
):

    from vnstock import Fundamental

    fa = Fundamental()

    # =====================================================
    # Unified API
    # =====================================================

    try:

        equity = fa.equity

        income = (
            equity.income_statement(
                symbol=ticker,
                period=period,
            )
        )

        balance = (
            equity.balance_sheet(
                symbol=ticker,
                period=period,
            )
        )

        cashflow = (
            equity.cash_flow(
                symbol=ticker,
                period=period,
            )
        )

        ratios = _call_ratio(
            equity=equity,
            ticker=ticker,
            period=period,
        )

    except Exception:

        # =================================================
        # Alternate vnstock build
        # =================================================

        equity = fa.equity(
            ticker
        )

        income = (
            equity.income_statement(
                period=period
            )
        )

        balance = (
            equity.balance_sheet(
                period=period
            )
        )

        cashflow = (
            equity.cash_flow(
                period=period
            )
        )

        ratios = _call_ratio(
            equity=equity,
            ticker=None,
            period=period,
        )

    income = _ensure_dataframe(
        income
    )

    balance = _ensure_dataframe(
        balance
    )

    cashflow = _ensure_dataframe(
        cashflow
    )

    ratios = _ensure_dataframe(
        ratios
    )

    # =====================================================
    # FIX YEAR MAPPING
    # =====================================================

    income = _repair_period_values(
        income
    )

    balance = _repair_period_values(
        balance
    )

    cashflow = _repair_period_values(
        cashflow
    )

    ratios = _repair_period_values(
        ratios
    )

    return (
        income,
        balance,
        cashflow,
        ratios,
    )


# =========================================================
# COMPANY PROFILE
# =========================================================

def _get_company_profile(
    ticker: str,
) -> dict[str, Any]:

    result = {
        "name": ticker,
        "exchange": None,
        "industry": None,
        "business_model": None,
    }

    try:

        from vnstock import Reference

        ref = Reference()

        try:

            df = ref.company.info(
                symbol=ticker
            )

        except Exception:

            company = ref.company(
                ticker
            )

            try:
                df = company.info()

            except Exception:
                df = company.overview()

        df = _ensure_dataframe(
            df
        )

        if df.empty:
            return result

        row = df.iloc[0]

        # Company name
        for key in [
            "company_name",
            "organ_name",
            "organName",
            "short_name",
            "shortName",
            "name",
        ]:

            if (
                key in row.index
                and pd.notna(
                    row[key]
                )
            ):

                result["name"] = str(
                    row[key]
                )

                break

        # Exchange
        for key in [
            "exchange",
            "exchange_code",
            "exchangeCode",
            "comGroupCode",
        ]:

            if (
                key in row.index
                and pd.notna(
                    row[key]
                )
            ):

                result[
                    "exchange"
                ] = str(
                    row[key]
                )

                break

        # Industry
        for key in [
            "industry",
            "industry_name",
            "industryName",
            "icb_name",
            "icbName",
            "icbName3",
            "sector",
        ]:

            if (
                key in row.index
                and pd.notna(
                    row[key]
                )
            ):

                result[
                    "industry"
                ] = str(
                    row[key]
                )

                break

        # Description
        for key in [
            "business_model",
            "business",
            "company_profile",
            "companyProfile",
            "businessDescription",
        ]:

            if (
                key in row.index
                and pd.notna(
                    row[key]
                )
            ):

                result[
                    "business_model"
                ] = str(
                    row[key]
                )

                break

    except Exception:
        pass

    return result


# =========================================================
# HISTORY
# =========================================================

def _build_history(
    income,
    balance,
    ratios,
    business_type: str = "corporate",
):

    periods = (
        _get_period_columns(
            income
        )
    )

    history = []

    revenue_ids = [
        "revenue",
        "net_revenue",
        "operating_income",
        "total_operating_income",
        "total_income",
        "operating_revenue",
    ]

    revenue_labels = [
        "revenue",
        "net revenue",
        "doanh thu thuan",
        "tong doanh thu",
        "total operating income",
        "tong thu nhap hoat dong",
    ]

    equity_ids = [
        "owners_equity_2",
        "owners_equity_3",
        "owners_equity",
        "equity",
        "total_equity",
        "shareholders_equity",
        "shareholder_equity",
        "total_shareholders_equity",
        "equity_attributable_to_owners",
    ]

    for period in periods:

        revenue = _get_item_value_flexible(
            income,
            revenue_ids,
            period,
            revenue_labels,
        )

        gross_profit = None

        if business_type != "bank":
            gross_profit = _get_item_value_flexible(
                income,
                [
                    "gross_profit",
                ],
                period,
                [
                    "gross profit",
                    "loi nhuan gop",
                ],
            )

        history.append(
            {
                "period": period,

                "revenue": revenue,

                "gross_profit": gross_profit,

                "net_profit": (
                    _get_item_value_flexible(
                        income,
                        [
                            "net_profit",
                            "net_profit_after_tax",
                            "profit_after_tax",
                            "net_income",
                            "net_income_after_tax",
                        ],
                        period,
                        [
                            "net profit after tax",
                            "profit after tax",
                            "net income",
                            "loi nhuan sau thue",
                        ],
                    )
                ),

                "total_assets": (
                    _get_item_value_flexible(
                        balance,
                        [
                            "total_assets",
                            "assets",
                        ],
                        period,
                        [
                            "total assets",
                            "tong tai san",
                        ],
                    )
                ),

                "equity": (
                    _get_item_value_flexible(
                        balance,
                        equity_ids,
                        period,
                        [
                            "total equity",
                            "shareholders equity",
                            "owners equity",
                            "von chu so huu",
                        ],
                    )
                ),

                "roe": (
                    _normalize_percent(
                        _get_item_value(
                            ratios,
                            [
                                "roe",
                                "return_on_equity",
                            ],
                            period,
                        )
                    )
                ),

                "roa": (
                    _normalize_percent(
                        _get_item_value(
                            ratios,
                            [
                                "roa",
                                "return_on_assets",
                            ],
                            period,
                        )
                    )
                ),

                "pe": (
                    _get_item_value(
                        ratios,
                        [
                            "pe_ratio",
                            "p_e",
                            "pe",
                        ],
                        period,
                    )
                ),

                "pb": (
                    _get_item_value(
                        ratios,
                        [
                            "pb_ratio",
                            "p_b",
                            "pb",
                        ],
                        period,
                    )
                ),
            }
        )

    return history


# =========================================================
# MAIN
# =========================================================

def get_financial_data(
    ticker: str,
    period: str = "year",
) -> dict[str, Any]:

    ticker = normalize_ticker(
        ticker
    )

    if period not in {
        "year",
        "quarter",
    }:

        raise ValueError(
            "period chỉ nhận 'year' hoặc 'quarter'."
        )

    (
        income,
        balance,
        cashflow,
        ratios,
    ) = _load_vnstock(
        ticker=ticker,
        period=period,
    )

    if income.empty:

        raise RuntimeError(
            f"Không lấy được BCTC "
            f"cho {ticker} từ vnstock."
        )

    # =====================================================
    # PERIOD
    # =====================================================

    income_period = (
        _latest_period(
            income
        )
    )

    balance_period = (
        _latest_period(
            balance
        )
    )

    ratio_period = (
        _latest_period(
            ratios
        )
    )

    cashflow_period = (
        _latest_period(
            cashflow
        )
    )

    # =====================================================
    # PROFILE / BUSINESS TYPE
    # =====================================================

    profile = (
        _get_company_profile(
            ticker
        )
    )

    business_type = (
        _detect_business_type(
            profile=profile,
            income=income,
            balance=balance,
        )
    )

    # =====================================================
    # INCOME STATEMENT
    # =====================================================

    revenue_ids = [
        "revenue",
        "net_revenue",
        "operating_income",
        "total_operating_income",
        "total_income",
        "operating_revenue",
    ]

    revenue_labels = [
        "revenue",
        "net revenue",
        "doanh thu thuan",
        "tong doanh thu",
        "total operating income",
        "tong thu nhap hoat dong",
    ]

    revenue = (
        _get_item_value_flexible(
            income,
            revenue_ids,
            income_period,
            revenue_labels,
        )
    )

    gross_profit = None

    if business_type != "bank":
        gross_profit = (
            _get_item_value_flexible(
                income,
                [
                    "gross_profit",
                ],
                income_period,
                [
                    "gross profit",
                    "loi nhuan gop",
                ],
            )
        )

    net_profit = (
        _get_item_value_flexible(
            income,
            [
                "net_profit",
                "net_profit_after_tax",
                "profit_after_tax",
                "net_income",
                "net_income_after_tax",
            ],
            income_period,
            [
                "net profit after tax",
                "profit after tax",
                "net income",
                "loi nhuan sau thue",
            ],
        )
    )

    eps_income = (
        _get_item_value(
            income,
            [
                "eps",
                "earnings_per_share",
            ],
            income_period,
        )
    )

    # =====================================================
    # REVENUE / OPERATING INCOME GROWTH
    # =====================================================

    revenue_growth = None

    income_periods = (
        _get_period_columns(
            income
        )
    )

    if len(income_periods) >= 2:

        current_revenue = (
            _get_item_value_flexible(
                income,
                revenue_ids,
                income_periods[0],
                revenue_labels,
            )
        )

        previous_revenue = (
            _get_item_value_flexible(
                income,
                revenue_ids,
                income_periods[1],
                revenue_labels,
            )
        )

        if (
            current_revenue is not None
            and previous_revenue
            not in (
                None,
                0,
            )
        ):

            revenue_growth = (
                current_revenue
                / previous_revenue
                - 1
            )

    # =====================================================
    # BALANCE SHEET
    # =====================================================

    total_assets = (
        _get_item_value_flexible(
            balance,
            [
                "total_assets",
                "assets",
            ],
            balance_period,
            [
                "total assets",
                "tong tai san",
            ],
        )
    )

    current_assets = (
        _get_item_value_flexible(
            balance,
            [
                "current_assets",
                "short_term_assets",
            ],
            balance_period,
            [
                "current assets",
                "short term assets",
                "tai san ngan han",
            ],
        )
    )

    total_liabilities = (
        _get_item_value_flexible(
            balance,
            [
                "total_liabilities",
                "liabilities",
                "total_debt_and_liabilities",
            ],
            balance_period,
            [
                "total liabilities",
                "liabilities",
                "no phai tra",
            ],
        )
    )

    current_liabilities = (
        _get_item_value_flexible(
            balance,
            [
                "current_liabilities",
                "short_term_liabilities",
            ],
            balance_period,
            [
                "current liabilities",
                "short term liabilities",
                "no ngan han",
            ],
        )
    )

    equity = (
        _get_item_value_flexible(
            balance,
            [
                "owners_equity_2",
                "owners_equity_3",
                "owners_equity",
                "equity",
                "total_equity",
                "shareholders_equity",
                "shareholder_equity",
                "total_shareholders_equity",
                "equity_attributable_to_owners",
            ],
            balance_period,
            [
                "total equity",
                "shareholders equity",
                "owners equity",
                "von chu so huu",
            ],
        )
    )

    # =====================================================
    # CASH FLOW
    # =====================================================

    operating_cash_flow = (
        _get_item_value_flexible(
            cashflow,
            [
                "operating_cash_flow",
                "net_cash_flows_from_operating_activities",
                "net_cash_flow_from_operating_activities",
            ],
            cashflow_period,
            [
                "net cash flows from operating activities",
                "cash flow from operating activities",
                "luu chuyen tien thuan tu hoat dong kinh doanh",
            ],
        )
    )

    # =====================================================
    # RATIOS
    # =====================================================

    roe = _normalize_percent(
        _get_item_value(
            ratios,
            [
                "roe",
                "return_on_equity",
            ],
            ratio_period,
        )
    )

    roa = _normalize_percent(
        _get_item_value(
            ratios,
            [
                "roa",
                "return_on_assets",
            ],
            ratio_period,
        )
    )

    net_margin = (
        _normalize_percent(
            _get_item_value(
                ratios,
                [
                    "net_margin",
                    "net_profit_margin",
                    "profit_margin",
                ],
                ratio_period,
            )
        )
    )

    # Với doanh nghiệp thông thường có thể fallback LNST / doanh thu.
    # Với ngân hàng không ép tỷ lệ này vì "doanh thu" được thay bằng
    # tổng thu nhập hoạt động và không hoàn toàn tương đương net margin
    # của doanh nghiệp sản xuất/dịch vụ.
    if (
        net_margin is None
        and business_type != "bank"
    ):

        net_margin = (
            _safe_divide(
                net_profit,
                revenue,
            )
        )

    # --------------------------
    # P/E
    # --------------------------

    pe = _get_item_value(
        ratios,
        [
            "pe_ratio",
            "p_e",
            "pe",
        ],
        ratio_period,
    )

    # --------------------------
    # P/B
    # --------------------------

    pb = _get_item_value(
        ratios,
        [
            "pb_ratio",
            "p_b",
            "pb",
        ],
        ratio_period,
    )

    # --------------------------
    # BVPS
    # --------------------------

    book_value = (
        _get_item_value(
            ratios,
            [
                "book_value_per_share_bvps",
                "book_value_per_share",
                "bvps",
            ],
            ratio_period,
        )
    )

    # --------------------------
    # EPS
    # --------------------------

    eps_ratio = (
        _get_item_value(
            ratios,
            [
                "earnings_per_share",
                "earnings_per_share_eps",
                "eps",
            ],
            ratio_period,
        )
    )

    eps = (
        eps_ratio
        if eps_ratio is not None
        else eps_income
    )

    # =====================================================
    # DEBT / EQUITY
    # =====================================================

    if business_type == "bank":

        # Không dùng D/E kiểu doanh nghiệp thông thường cho ngân hàng.
        # Tiền gửi và các nguồn vốn huy động là cấu phần hoạt động cốt lõi,
        # nên đưa D/E vào cùng thang điểm với FPT/HPG có thể gây sai lệch.
        debt_to_equity = None

    else:

        debt_to_equity_raw = (
            _get_item_value(
                ratios,
                [
                    "debt_to_equity",
                    "debt_equity",
                ],
                ratio_period,
            )
        )

        # KBS có thể trả 48.84 tức 48.84%.
        # StockLens chuẩn hóa về decimal = 0.4884.
        debt_to_equity = (
            _normalize_percent(
                debt_to_equity_raw
            )
        )

        if debt_to_equity is None:

            debt_to_equity = (
                _safe_divide(
                    total_liabilities,
                    equity,
                )
            )

    # =====================================================
    # CURRENT RATIO
    # =====================================================

    if business_type == "bank":

        # Current Ratio không phải chỉ tiêu thanh khoản chuẩn để đánh giá
        # ngân hàng theo cùng cách với doanh nghiệp thông thường.
        current_ratio = None

    else:

        current_ratio = (
            _safe_divide(
                current_assets,
                current_liabilities,
            )
        )

        if current_ratio is None:

            current_ratio = (
                _safe_float(
                    _get_item_value(
                        ratios,
                        [
                            "current_ratio",
                        ],
                        ratio_period,
                    )
                )
            )

    # =====================================================
    # HISTORY
    # =====================================================

    history = (
        _build_history(
            income,
            balance,
            ratios,
            business_type=business_type,
        )
    )

    # =====================================================
    # OUTPUT
    # =====================================================

    return {

        # Company
        "ticker": ticker,

        "name": (
            profile.get("name")
            or ticker
        ),

        "exchange": (
            profile.get(
                "exchange"
            )
        ),

        "sector": (
            profile.get(
                "industry"
            )
        ),

        "business_model": (
            profile.get(
                "business_model"
            )
        ),

        "financialBusinessType": (
            business_type
        ),

        "revenueMetricLabel": (
            "Tổng thu nhập hoạt động"
            if business_type == "bank"
            else "Doanh thu"
        ),

        "notApplicableMetrics": (
            [
                "grossProfit",
                "debtToEquity",
                "currentRatio",
            ]
            if business_type == "bank"
            else []
        ),

        # Fundamental
        "returnOnEquity": roe,

        "returnOnAssets": roa,

        "profitMargins": (
            net_margin
        ),

        "revenueGrowth": (
            revenue_growth
        ),

        "debtToEquity": (
            debt_to_equity
        ),

        "currentRatio": (
            current_ratio
        ),

        "totalRevenue": (
            revenue
        ),

        "netIncomeToCommon": (
            net_profit
        ),

        "grossProfit": (
            gross_profit
        ),

        "operatingCashFlow": (
            operating_cash_flow
        ),

        # Balance sheet
        "totalAssets": (
            total_assets
        ),

        "currentAssets": (
            current_assets
        ),

        "totalLiabilities": (
            total_liabilities
        ),

        "currentLiabilities": (
            current_liabilities
        ),

        "totalEquity": (
            equity
        ),

        # Valuation
        "trailingPE": pe,

        "priceToBook": pb,

        "forwardPE": None,

        "marketCap": None,

        "trailingEps": eps,

        "bookValue": (
            book_value
        ),

        # Period
        "reportPeriod": (
            income_period
        ),

        "financialStatementPeriod": (
            income_period
        ),

        "balanceSheetPeriod": (
            balance_period
        ),

        "ratioPeriod": (
            ratio_period
        ),

        "cashFlowPeriod": (
            cashflow_period
        ),

        "periodType": period,

        # Source
        "source": (
            "vnstock - KBS"
        ),

        "dataAvailable": True,

        # History
        "financialHistory": (
            history
        ),

        # Raw
        "_raw": {
            "income_statement": (
                income
            ),
            "balance_sheet": (
                balance
            ),
            "cash_flow": (
                cashflow
            ),
            "ratios": (
                ratios
            ),
        },
    }


# =========================================================
# TEST
# =========================================================

if __name__ == "__main__":

    print(
        "===== STOCKLENS - VNSTOCK FINANCIAL TEST ====="
    )

    try:

        data = get_financial_data(
            ticker="FPT",
            period="year",
        )

        print()
        print(
            "Ticker:",
            data.get("ticker"),
        )

        print(
            "Company:",
            data.get("name"),
        )

        print(
            "Exchange:",
            data.get("exchange"),
        )

        print(
            "Sector:",
            data.get("sector"),
        )

        print()

        print(
            "Report Period:",
            data.get(
                "reportPeriod"
            ),
        )

        print(
            "Source:",
            data.get(
                "source"
            ),
        )

        print()

        print(
            "Revenue:",
            data.get(
                "totalRevenue"
            ),
        )

        print(
            "Net Income:",
            data.get(
                "netIncomeToCommon"
            ),
        )

        print(
            "Revenue Growth:",
            data.get(
                "revenueGrowth"
            ),
        )

        print(
            "Total Assets:",
            data.get(
                "totalAssets"
            ),
        )

        print(
            "Total Equity:",
            data.get(
                "totalEquity"
            ),
        )

        print(
            "ROE:",
            data.get(
                "returnOnEquity"
            ),
        )

        print(
            "ROA:",
            data.get(
                "returnOnAssets"
            ),
        )

        print(
            "Profit Margin:",
            data.get(
                "profitMargins"
            ),
        )

        print(
            "Debt / Equity:",
            data.get(
                "debtToEquity"
            ),
        )

        print(
            "Current Ratio:",
            data.get(
                "currentRatio"
            ),
        )

        print(
            "P/E:",
            data.get(
                "trailingPE"
            ),
        )

        print(
            "P/B:",
            data.get(
                "priceToBook"
            ),
        )

        print(
            "BVPS:",
            data.get(
                "bookValue"
            ),
        )

        print(
            "EPS:",
            data.get(
                "trailingEps"
            ),
        )

        print(
            "Operating Cash Flow:",
            data.get(
                "operatingCashFlow"
            ),
        )

        print()

        print(
            "Financial History:"
        )

        for row in (
            data.get(
                "financialHistory",
                []
            )[:5]
        ):

            print(row)

        print()
        print(
            "vnstock financial test: OK"
        )

    except Exception as exc:

        print()
        print(
            "ERROR:"
        )
        print(exc)