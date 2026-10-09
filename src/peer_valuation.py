# -*- coding: utf-8 -*-
"""StockLens - Peer Valuation

Peer valuation for Vietnamese equities, optimized for vnstock Community/Guest.

Main public function
--------------------
    analyze_peer_valuation(
        ticker,
        current_price=None,
        max_peers=5,
        financial_data=None,
        peer_symbols=None,
        request_delay=2.0,
    )

Design goals
------------
1. Select peers using the deepest available ICB level first (prefer level 4).
2. Load only P/E, P/B and ROE for peers to keep API usage low.
3. Recover target EPS/BVPS from StockLens financial_data, including the raw
   ratio table where KBS commonly exposes "EPS" and "BVPS" rows.
4. Use sector-aware weighting: Software uses P/E 70% + P/B 30%.\n5. Add peer-quality warnings for small samples, missing ratios, negative ROE,\n   and highly dispersed multiples.\n6. Keep the existing StockLens-friendly output keys so integration is simple.
"""

from __future__ import annotations

import re
import time
from functools import lru_cache
from statistics import median
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd


# =============================================================================
# Helpers
# =============================================================================


def _compact_ticker(ticker: str) -> str:
    symbol = str(ticker or "").strip().upper()
    if symbol.endswith(".VN"):
        symbol = symbol[:-3]
    return symbol


def _finite(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        number = float(value)
        if pd.isna(number):
            return None
        return number
    except Exception:
        return None


def _positive(value: Any) -> Optional[float]:
    number = _finite(value)
    if number is None or number <= 0:
        return None
    return number


def _first_value(data: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)
    return None


def _safe_median(values: Iterable[Any]) -> Optional[float]:
    cleaned = [_positive(v) for v in values]
    cleaned = [v for v in cleaned if v is not None]
    if not cleaned:
        return None
    return float(median(cleaned))


def _pct_diff(value: Optional[float], benchmark: Optional[float]) -> Optional[float]:
    if value is None or benchmark in (None, 0):
        return None
    return value / benchmark - 1.0


def _score_multiple(relative_multiple: Optional[float]) -> Optional[float]:
    """Convert target multiple / peer median into a 0-100 heuristic score."""
    if relative_multiple is None or relative_multiple <= 0:
        return None
    if relative_multiple <= 0.70:
        return 100.0
    if relative_multiple <= 0.85:
        return 90.0
    if relative_multiple <= 1.00:
        return 75.0
    if relative_multiple <= 1.15:
        return 60.0
    if relative_multiple <= 1.30:
        return 45.0
    if relative_multiple <= 1.50:
        return 30.0
    return 20.0


def _classification(score: Optional[float]) -> str:
    if score is None:
        return "Chưa đủ dữ liệu"
    if score >= 80:
        return "Định giá peer hấp dẫn"
    if score >= 65:
        return "Tương đối hấp dẫn so với peers"
    if score >= 50:
        return "Định giá gần mức peers"
    return "Định giá cao so với peers"


def _valuation_weights(
    industry_name: Optional[str],
    icb_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Return sector-aware P/E-P/B weights.

    Software companies use 70% P/E + 30% P/B because earnings multiples
    are usually more informative than book-value multiples for asset-light
    businesses. Other sectors keep a neutral 50/50 default until a dedicated
    rule is defined.
    """
    name = str(industry_name or "").strip().casefold()
    code = str(icb_code or "").strip()

    is_software = (
        "phần mềm" in name
        or "phan mem" in name
        or "software" in name
        or code == "9537"
    )

    if is_software:
        return {
            "pe": 0.70,
            "pb": 0.30,
            "label": "P/E 70% + P/B 30% (ngành Phần mềm)",
            "sector_rule": "software",
        }

    return {
        "pe": 0.50,
        "pb": 0.50,
        "label": "P/E 50% + P/B 50% (mặc định)",
        "sector_rule": "default",
    }


def _weighted_available(
    values: Dict[str, Optional[float]],
    weights: Dict[str, float],
) -> Optional[float]:
    """Weighted average using only available finite inputs."""
    numerator = 0.0
    denominator = 0.0

    for key, value in values.items():
        number = _finite(value)
        weight = float(weights.get(key, 0.0) or 0.0)
        if number is None or weight <= 0:
            continue
        numerator += number * weight
        denominator += weight

    if denominator <= 0:
        return None
    return numerator / denominator


def _peer_quality_review(
    peer_rows: Sequence[Dict[str, Any]],
    cleaned_peers: Sequence[Dict[str, Any]],
) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    """Generate explicit quality warnings for the selected peer set."""
    warnings: List[str] = []
    peer_quality: List[Dict[str, Any]] = []

    for row in peer_rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        pe = _positive(row.get("pe"))
        pb = _positive(row.get("pb"))
        roe = _finite(row.get("roe"))
        flags: List[str] = []

        if pe is None:
            flags.append("Thiếu P/E")
        if pb is None:
            flags.append("Thiếu P/B")
        if roe is None:
            flags.append("Thiếu ROE")
        elif roe < 0:
            flags.append("ROE âm")

        if pe is not None and (pe < 3 or pe > 60):
            flags.append("P/E cực trị")
        if pb is not None and pb > 10:
            flags.append("P/B cực trị")
        if row.get("error"):
            flags.append("Lỗi/thiếu dữ liệu API")

        peer_quality.append({
            "symbol": symbol,
            "status": "OK" if not flags else "Cảnh báo",
            "flags": flags,
        })

    valid_count = len(cleaned_peers)
    total_count = len(peer_rows)
    failed_count = max(total_count - valid_count, 0)

    if valid_count < 3:
        warnings.append(
            f"Mẫu peer rất nhỏ: chỉ có {valid_count} doanh nghiệp đủ dữ liệu; median có độ tin cậy thấp."
        )
    elif valid_count == 3:
        warnings.append(
            "Chỉ có 3 peer đủ dữ liệu; kết quả median có thể nhạy với từng doanh nghiệp."
        )

    if failed_count > 0:
        warnings.append(
            f"{failed_count}/{total_count} peer được chọn thiếu P/E/P/B hợp lệ và không được dùng để tính median."
        )

    negative_roe = [
        p for p in cleaned_peers
        if _finite(p.get("roe")) is not None and _finite(p.get("roe")) < 0
    ]
    if negative_roe:
        symbols = ", ".join(str(p.get("symbol")) for p in negative_roe)
        warnings.append(
            f"Có peer ROE âm ({symbols}); mức định giá của các doanh nghiệp này có thể kém đại diện cho doanh nghiệp mục tiêu."
        )

    pe_values = sorted(
        v for v in (_positive(p.get("pe")) for p in cleaned_peers) if v is not None
    )
    if len(pe_values) >= 3 and pe_values[0] > 0:
        dispersion = pe_values[-1] / pe_values[0]
        if dispersion >= 4:
            warnings.append(
                f"P/E giữa các peer phân tán mạnh (max/min ≈ {dispersion:.1f}x); nên đọc median cùng với bảng từng peer."
            )

    pb_values = sorted(
        v for v in (_positive(p.get("pb")) for p in cleaned_peers) if v is not None
    )
    if len(pb_values) >= 3 and pb_values[0] > 0:
        dispersion = pb_values[-1] / pb_values[0]
        if dispersion >= 4:
            warnings.append(
                f"P/B giữa các peer phân tán mạnh (max/min ≈ {dispersion:.1f}x)."
            )

    if not warnings:
        status = "Tốt"
    elif len(warnings) == 1:
        status = "Khá"
    else:
        status = "Cần thận trọng"

    return status, warnings, peer_quality


def _norm(value: Any) -> str:
    """Normalize text for flexible column/metric matching."""
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _find_column(df: pd.DataFrame, candidates: Sequence[str]) -> Optional[Any]:
    lookup = {_norm(c): c for c in df.columns}
    for candidate in candidates:
        key = _norm(candidate)
        if key in lookup:
            return lookup[key]
    return None


def _latest_period_column(df: pd.DataFrame) -> Optional[Any]:
    candidates: List[Tuple[int, int, str, Any]] = []
    for col in df.columns:
        text = str(col).strip()
        m = re.search(r"(20\d{2})(?:[^0-9]*q?([1-4]))?", text, flags=re.I)
        if not m:
            continue
        year = int(m.group(1))
        quarter = int(m.group(2) or 0)
        candidates.append((year, quarter, text, col))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][3]


def _latest_history_record(history: Any) -> Dict[str, Any]:
    if not isinstance(history, list):
        return {}
    rows = [x for x in history if isinstance(x, dict)]
    if not rows:
        return {}

    def key(row: Dict[str, Any]) -> Tuple[int, int]:
        text = str(row.get("period") or row.get("year") or "")
        m = re.search(r"(20\d{2})(?:[^0-9]*q?([1-4]))?", text, flags=re.I)
        if not m:
            return (0, 0)
        return (int(m.group(1)), int(m.group(2) or 0))

    return max(rows, key=key)


# =============================================================================
# Target company financial data
# =============================================================================


def _load_financial_data(ticker: str) -> Dict[str, Any]:
    """Use StockLens' existing vnstock/KBS financial loader."""
    try:
        from .vnstock_data import get_financial_data  # type: ignore
    except Exception:
        from vnstock_data import get_financial_data  # type: ignore

    return get_financial_data(ticker, period="year") or {}


def _extract_raw_ratio_metric(
    financial_data: Dict[str, Any],
    *,
    exact_ids: Sequence[str] = (),
    contains_tokens: Sequence[str] = (),
) -> Optional[float]:
    """Extract one metric from financial_data['_raw']['ratios'].

    This handles the KBS report-style table used by StockLens, including labels
    such as:
      - "Giá trị sổ sách của cổ phiếu (BVPS)"
      - "Thu nhập trên mỗi cổ phần của 4 quý gần nhất (EPS)"
    """
    raw = financial_data.get("_raw") or {}
    ratios = raw.get("ratios")

    if ratios is None or not isinstance(ratios, pd.DataFrame) or ratios.empty:
        return None

    work = ratios.copy()
    period_col = _latest_period_column(work)
    if period_col is None:
        return None

    id_col = _find_column(work, ["item_id", "id"])
    item_col = _find_column(work, ["item", "item_en", "name"])

    exact_norm = {_norm(x) for x in exact_ids}
    token_norm = [_norm(x) for x in contains_tokens if _norm(x)]

    # Exact taxonomy IDs first.
    if id_col is not None and exact_norm:
        for _, row in work.iterrows():
            if _norm(row.get(id_col)) in exact_norm:
                value = _positive(row.get(period_col))
                if value is not None:
                    return value

    # Then search item_id + item labels with robust token matching.
    for _, row in work.iterrows():
        haystack = " ".join(
            str(row.get(col) or "")
            for col in (id_col, item_col)
            if col is not None
        )
        normalized = _norm(haystack)
        if any(token in normalized for token in token_norm):
            value = _positive(row.get(period_col))
            if value is not None:
                return value

    return None


def _financial_row(symbol: str, preloaded: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Build target-company valuation inputs, including EPS and BVPS fallbacks."""
    data = preloaded if preloaded is not None else _load_financial_data(symbol)

    pe = _positive(
        _first_value(
            data,
            ["trailingPE", "pe", "pe_ratio", "priceToEarning", "price_to_earning"],
        )
    )
    pb = _positive(
        _first_value(
            data,
            ["priceToBook", "pb", "pb_ratio", "price_to_book"],
        )
    )
    eps = _positive(
        _first_value(
            data,
            [
                "eps",
                "EPS",
                "earningsPerShare",
                "earningPerShare",
                "earnings_per_share",
                "earning_per_share",
                "basicEPS",
            ],
        )
    )
    bvps = _positive(
        _first_value(
            data,
            [
                "bvps",
                "BVPS",
                "bookValuePerShare",
                "book_value_per_share",
                "bookValue",
            ],
        )
    )

    roe = _finite(_first_value(data, ["returnOnEquity", "roe"]))
    roa = _finite(_first_value(data, ["returnOnAssets", "roa"]))
    market_cap = _finite(_first_value(data, ["marketCap", "market_cap"]))

    # Latest history fallback. The StockLens history is often ascending, so do
    # not assume history[0] is the newest period.
    history = data.get("financialHistory") or data.get("financial_history") or []
    latest = _latest_history_record(history)
    if latest:
        if pe is None:
            pe = _positive(latest.get("pe"))
        if pb is None:
            pb = _positive(latest.get("pb"))
        if eps is None:
            eps = _positive(latest.get("eps"))
        if bvps is None:
            bvps = _positive(latest.get("bvps"))
        if roe is None:
            roe = _finite(latest.get("roe"))
        if roa is None:
            roa = _finite(latest.get("roa"))

    # Raw KBS ratio table fallback. These are the important fixes for the
    # current StockLens data where EPS/BVPS are visible in the PDF appendix but
    # were not exposed at the top level of financial_data.
    if pe is None:
        pe = _extract_raw_ratio_metric(
            data,
            exact_ids=["pe_ratio"],
            contains_tokens=["p/e", "price to earning", "priceToEarning"],
        )
    if pb is None:
        pb = _extract_raw_ratio_metric(
            data,
            exact_ids=["pb_ratio"],
            contains_tokens=["p/b", "price to book", "priceToBook"],
        )
    if eps is None:
        eps = _extract_raw_ratio_metric(
            data,
            exact_ids=[
                "eps",
                "earnings_per_share_eps",
                "earnings_per_share",
                "earning_per_share",
                "basic_eps",
            ],
            contains_tokens=[
                "(EPS)",
                "EPS",
                "thu nhập trên mỗi cổ phần",
                "earnings per share",
            ],
        )
    if bvps is None:
        bvps = _extract_raw_ratio_metric(
            data,
            exact_ids=[
                "bvps",
                "book_value_per_share_bvps",
                "book_value_per_share",
            ],
            contains_tokens=[
                "(BVPS)",
                "BVPS",
                "giá trị sổ sách của cổ phiếu",
                "book value per share",
            ],
        )

    return {
        "symbol": symbol,
        "name": data.get("name") or data.get("company") or symbol,
        "exchange": data.get("exchange"),
        "sector": data.get("sector"),
        "pe": pe,
        "pb": pb,
        "eps": eps,
        "bvps": bvps,
        "roe": roe,
        "roa": roa,
        "market_cap": market_cap,
    }


# =============================================================================
# ICB peer discovery
# =============================================================================


@lru_cache(maxsize=1)
def _community_industry_table() -> pd.DataFrame:
    """Fetch the community ICB classification once per Python process."""
    from vnstock import Reference  # type: ignore

    ref = Reference()
    try:
        df = ref.equity.list_by_industry()
    except TypeError:
        df = ref.equity.list_by_industry(lang="vi")

    if df is None or not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    return df.copy()


def _select_icb_peers_from_table(
    industry_df: pd.DataFrame,
    ticker: str,
    max_peers: int,
    min_candidates: int = 3,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Pure helper: select peers from the deepest available ICB level.

    If the deepest level has fewer than ``min_candidates`` companies, the helper
    broadens one level at a time until enough candidates exist. This prevents the
    previous behavior where FPT could accidentally stop at broad ICB code 9000.
    """
    if industry_df is None or industry_df.empty:
        return {}, []

    symbol_col = _find_column(industry_df, ["symbol", "ticker", "code"])
    if symbol_col is None:
        return {}, []

    level_col = _find_column(industry_df, ["icb_level", "icblevel", "level"])
    code_col = _find_column(industry_df, ["icb_code", "icbcode", "industry_code"])
    name_col = _find_column(industry_df, ["icb_name", "icbname", "industry_name", "industry"])
    organ_col = _find_column(industry_df, ["organ_name", "name", "company_name"])

    work = industry_df.copy()
    work[symbol_col] = work[symbol_col].astype(str).str.upper().str.strip()

    target_rows = work[work[symbol_col] == ticker].copy()
    if target_rows.empty:
        return {}, []

    # Best case: table explicitly provides ICB level and code.
    if level_col is not None and code_col is not None:
        work["__icb_level_num"] = pd.to_numeric(work[level_col], errors="coerce")
        target_rows["__icb_level_num"] = pd.to_numeric(target_rows[level_col], errors="coerce")

        target_rows = target_rows.dropna(subset=["__icb_level_num"])
        if not target_rows.empty:
            available_levels = sorted(
                {int(v) for v in target_rows["__icb_level_num"].tolist()},
                reverse=True,
            )

            chosen = None
            chosen_peers = pd.DataFrame()

            for idx, level in enumerate(available_levels):
                level_targets = target_rows[target_rows["__icb_level_num"] == level]
                if level_targets.empty:
                    continue

                # A ticker normally has one code per level. Use the first valid one.
                code_values = [
                    str(v).strip()
                    for v in level_targets[code_col].tolist()
                    if str(v).strip() and str(v).strip().lower() != "nan"
                ]
                if not code_values:
                    continue

                code = code_values[0]
                peers = work[
                    (work["__icb_level_num"] == level)
                    & (work[code_col].astype(str).str.strip() == code)
                    & (work[symbol_col] != ticker)
                ].copy()

                # Prefer the deepest level. Only broaden if there are too few candidates.
                is_last_level = idx == len(available_levels) - 1
                if len(peers) >= min(min_candidates, max_peers) or is_last_level:
                    chosen = level_targets.iloc[0]
                    chosen_peers = peers
                    break

            if chosen is not None:
                metadata = {
                    "icb_level": int(chosen.get("__icb_level_num")),
                    "icb_code": str(chosen.get(code_col) or "").strip() or None,
                    "icb_name": (
                        str(chosen.get(name_col) or "").strip() or None
                        if name_col is not None
                        else None
                    ),
                }

                peers_out: List[Dict[str, Any]] = []
                seen = set()
                for _, row in chosen_peers.iterrows():
                    symbol = _compact_ticker(row.get(symbol_col))
                    if not symbol or symbol == ticker or symbol in seen:
                        continue
                    seen.add(symbol)
                    peers_out.append(
                        {
                            "symbol": symbol,
                            "name": (
                                str(row.get(organ_col) or "").strip() or None
                                if organ_col is not None
                                else None
                            ),
                            "icb_level": metadata["icb_level"],
                            "icb_code": metadata["icb_code"],
                            "icb_name": metadata["icb_name"],
                        }
                    )
                    if len(peers_out) >= max_peers:
                        break

                metadata["available_peer_candidates"] = int(len(chosen_peers))
                return metadata, peers_out

    # Fallback for a simplified community table without icb_level.
    # Choose the most specific industry-looking column available.
    fallback_candidates = [
        "icb_code_lv4",
        "icb_code4",
        "icb_code_4",
        "icb_code",
        "icb_name_lv4",
        "icb_name4",
        "icb_name",
        "industry_code",
        "industry",
        "industry_name",
        "sector",
    ]

    target = target_rows.iloc[0]
    industry_col = None
    target_value = None
    for candidate in fallback_candidates:
        col = _find_column(work, [candidate])
        if col is None:
            continue
        value = target.get(col)
        if value is None or str(value).strip().lower() in {"", "nan", "none"}:
            continue
        industry_col = col
        target_value = str(value).strip()
        break

    if industry_col is None or target_value is None:
        return {}, []

    peer_df = work[
        (work[industry_col].astype(str).str.strip() == target_value)
        & (work[symbol_col] != ticker)
    ].copy()

    peers_out = []
    seen = set()
    for _, row in peer_df.iterrows():
        symbol = _compact_ticker(row.get(symbol_col))
        if not symbol or symbol == ticker or symbol in seen:
            continue
        seen.add(symbol)
        peers_out.append(
            {
                "symbol": symbol,
                "name": (
                    str(row.get(organ_col) or "").strip() or None
                    if organ_col is not None
                    else None
                ),
                "icb_level": None,
                "icb_code": target_value if "code" in _norm(industry_col) else None,
                "icb_name": target_value if "name" in _norm(industry_col) or "industry" in _norm(industry_col) else None,
            }
        )
        if len(peers_out) >= max_peers:
            break

    return {
        "icb_level": None,
        "icb_code": target_value if "code" in _norm(industry_col) else None,
        "icb_name": target_value if "name" in _norm(industry_col) or "industry" in _norm(industry_col) else None,
        "available_peer_candidates": int(len(peer_df)),
    }, peers_out


def _discover_with_community_reference(
    ticker: str,
    max_peers: int,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    try:
        industry_df = _community_industry_table()
    except BaseException:
        return {}, []

    return _select_icb_peers_from_table(
        industry_df,
        ticker,
        max_peers=max_peers,
        min_candidates=3,
    )


# =============================================================================
# Lightweight peer ratio loader
# =============================================================================


def _parse_ratio_dataframe(df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
    empty = {"symbol": symbol, "pe": None, "pb": None, "roe": None}
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return empty

    work = df.copy()

    if isinstance(work.columns, pd.MultiIndex):
        work.columns = [
            "_".join(
                str(part).strip()
                for part in col
                if str(part).strip() and str(part).strip().lower() != "nan"
            )
            for col in work.columns
        ]

    year_col = _find_column(work, ["year", "nam"])
    quarter_col = _find_column(work, ["quarter", "quy"])
    sort_cols = []
    if year_col is not None:
        work[year_col] = pd.to_numeric(work[year_col], errors="coerce")
        sort_cols.append(year_col)
    if quarter_col is not None:
        work[quarter_col] = pd.to_numeric(work[quarter_col], errors="coerce")
        sort_cols.append(quarter_col)
    if sort_cols:
        work = work.sort_values(sort_cols, ascending=False, na_position="last")

    pe_col = _find_column(work, ["priceToEarning", "price_to_earning", "pe", "p/e", "pe_ratio"])
    pb_col = _find_column(work, ["priceToBook", "price_to_book", "pb", "p/b", "pb_ratio"])
    roe_col = _find_column(work, ["roe", "returnOnEquity", "return_on_equity"])

    if pe_col is not None or pb_col is not None:
        latest = work.iloc[0]
        return {
            "symbol": symbol,
            "pe": _positive(latest.get(pe_col)) if pe_col is not None else None,
            "pb": _positive(latest.get(pb_col)) if pb_col is not None else None,
            "roe": _finite(latest.get(roe_col)) if roe_col is not None else None,
        }

    # Report-style fallback.
    period_col = _latest_period_column(work)
    item_col = _find_column(work, ["item", "item_en", "name"])
    id_col = _find_column(work, ["item_id", "id"])
    if period_col is None or (item_col is None and id_col is None):
        return empty

    def find_metric(exact_ids: Sequence[str], tokens: Sequence[str], positive: bool) -> Optional[float]:
        exact_norm = {_norm(x) for x in exact_ids}
        token_norm = [_norm(x) for x in tokens]
        for _, row in work.iterrows():
            id_text = _norm(row.get(id_col)) if id_col is not None else ""
            item_text = _norm(row.get(item_col)) if item_col is not None else ""
            if id_text in exact_norm or any(tok and tok in item_text for tok in token_norm):
                value = row.get(period_col)
                return _positive(value) if positive else _finite(value)
        return None

    return {
        "symbol": symbol,
        "pe": find_metric(["pe_ratio"], ["p/e", "price to earning"], True),
        "pb": find_metric(["pb_ratio"], ["p/b", "price to book"], True),
        "roe": find_metric(["roe"], ["roe", "return on equity"], False),
    }


@lru_cache(maxsize=128)
def _peer_ratio_row_cached(symbol: str) -> Tuple[Any, Any, Any, Any, Optional[str]]:
    symbol = _compact_ticker(symbol)

    try:
        from vnstock import Fundamental  # type: ignore

        fun = Fundamental()
        try:
            df = fun.equity(symbol).ratio(orient="time_series")
        except TypeError:
            df = fun.equity(symbol).ratio()

        parsed = _parse_ratio_dataframe(df, symbol)
        return (
            symbol,
            parsed.get("pe"),
            parsed.get("pb"),
            parsed.get("roe"),
            None,
        )
    except SystemExit as exc:
        return symbol, None, None, None, f"Rate limit/SystemExit: {exc}"
    except BaseException as exc:
        return symbol, None, None, None, str(exc)


def _peer_ratio_row(symbol: str) -> Dict[str, Any]:
    data = _peer_ratio_row_cached(_compact_ticker(symbol))
    return {
        "symbol": data[0],
        "pe": data[1],
        "pb": data[2],
        "roe": data[3],
        "error": data[4],
    }


# =============================================================================
# Public analysis function
# =============================================================================


def analyze_peer_valuation(
    ticker: str,
    current_price: Optional[float] = None,
    max_peers: int = 5,
    financial_data: Optional[Dict[str, Any]] = None,
    peer_symbols: Optional[Sequence[str]] = None,
    request_delay: float = 2.0,
) -> Dict[str, Any]:
    """Run peer-relative valuation for one Vietnam stock."""
    symbol = _compact_ticker(ticker)
    if not symbol:
        raise ValueError("Ticker không được để trống.")

    max_peers = max(2, min(int(max_peers), 8))
    current_price = _positive(current_price)
    target = _financial_row(symbol, preloaded=financial_data)

    source = ""
    industry_meta: Dict[str, Any] = {}
    peer_descriptors: List[Dict[str, Any]] = []

    # Manual peers.
    if peer_symbols:
        source = "Manual peer list + vnstock Fundamental.ratio"
        seen = set()
        for raw in peer_symbols:
            peer = _compact_ticker(raw)
            if not peer or peer == symbol or peer in seen:
                continue
            seen.add(peer)
            peer_descriptors.append({"symbol": peer, "name": None})
            if len(peer_descriptors) >= max_peers:
                break
    else:
        industry_meta, peer_descriptors = _discover_with_community_reference(symbol, max_peers)
        source = "vnstock Reference.list_by_industry (ICB) + Fundamental.ratio"

    if not peer_descriptors:
        return {
            "ticker": symbol,
            "data_available": False,
            "score": None,
            "classification": "Chưa đủ dữ liệu peer",
            "source": source or "vnstock",
            "industry": industry_meta.get("icb_name") or target.get("sector"),
            "industry_icb_level": industry_meta.get("icb_level"),
            "industry_icb_code": industry_meta.get("icb_code"),
            "peer_count": 0,
            "pe": target.get("pe"),
            "pb": target.get("pb"),
            "eps": target.get("eps"),
            "bvps": target.get("bvps"),
            "current_price": current_price,
            "peer_median_pe": None,
            "peer_median_pb": None,
            "implied_price_pe": None,
            "implied_price_pb": None,
            "peer_fair_value": None,
            "upside_downside": None,
            "peers": [],
            "positives": [],
            "risks": ["Không tìm được doanh nghiệp cùng phân ngành ICB phù hợp."],
            "commentary": "Peer valuation chưa được tính vì không tìm được nhóm doanh nghiệp so sánh.",
        }

    # Load only lightweight ratios for peers.
    peer_rows: List[Dict[str, Any]] = []
    for idx, descriptor in enumerate(peer_descriptors):
        peer = descriptor["symbol"]

        hits_before = _peer_ratio_row_cached.cache_info().hits
        ratio_row = _peer_ratio_row(peer)
        hits_after = _peer_ratio_row_cached.cache_info().hits

        ratio_row["name"] = descriptor.get("name")
        ratio_row["icb_level"] = descriptor.get("icb_level", industry_meta.get("icb_level"))
        ratio_row["icb_code"] = descriptor.get("icb_code", industry_meta.get("icb_code"))
        ratio_row["icb_name"] = descriptor.get("icb_name", industry_meta.get("icb_name"))
        peer_rows.append(ratio_row)

        used_cache = hits_after > hits_before
        if not used_cache and request_delay > 0 and idx < len(peer_descriptors) - 1:
            time.sleep(float(request_delay))

    cleaned_peers: List[Dict[str, Any]] = []
    for row in peer_rows:
        pe = _positive(row.get("pe"))
        pb = _positive(row.get("pb"))
        if pe is None and pb is None:
            continue
        cleaned_peers.append(
            {
                "symbol": row.get("symbol"),
                "name": row.get("name"),
                "pe": pe,
                "pb": pb,
                "roe": row.get("roe"),
                "icb_level": row.get("icb_level"),
                "icb_code": row.get("icb_code"),
                "icb_name": row.get("icb_name"),
            }
        )

    peer_median_pe = _safe_median(row.get("pe") for row in cleaned_peers)
    peer_median_pb = _safe_median(row.get("pb") for row in cleaned_peers)

    target_pe = _positive(target.get("pe"))
    target_pb = _positive(target.get("pb"))
    target_eps = _positive(target.get("eps"))
    target_bvps = _positive(target.get("bvps"))

    implied_pe = (
        target_eps * peer_median_pe
        if target_eps is not None and peer_median_pe is not None
        else None
    )
    implied_pb = (
        target_bvps * peer_median_pb
        if target_bvps is not None and peer_median_pb is not None
        else None
    )

    industry_name = industry_meta.get("icb_name") or target.get("sector")
    valuation_weights = _valuation_weights(
        industry_name=industry_name,
        icb_code=industry_meta.get("icb_code"),
    )

    peer_fair_value = _weighted_available(
        {"pe": implied_pe, "pb": implied_pb},
        {"pe": valuation_weights["pe"], "pb": valuation_weights["pb"]},
    )

    upside_downside = (
        peer_fair_value / current_price - 1.0
        if peer_fair_value is not None and current_price not in (None, 0)
        else None
    )

    pe_relative = (
        target_pe / peer_median_pe
        if target_pe is not None and peer_median_pe not in (None, 0)
        else None
    )
    pb_relative = (
        target_pb / peer_median_pb
        if target_pb is not None and peer_median_pb not in (None, 0)
        else None
    )

    components = {
        "pe_vs_peers": _score_multiple(pe_relative),
        "pb_vs_peers": _score_multiple(pb_relative),
    }
    valid_scores = [v for v in components.values() if v is not None]
    score = _weighted_available(
        {
            "pe": components.get("pe_vs_peers"),
            "pb": components.get("pb_vs_peers"),
        },
        {
            "pe": valuation_weights["pe"],
            "pb": valuation_weights["pb"],
        },
    )
    score = round(score, 2) if score is not None else None
    classification = _classification(score)

    positives: List[str] = []
    risks: List[str] = []

    pe_diff = _pct_diff(target_pe, peer_median_pe)
    if pe_diff is not None:
        if pe_diff < 0:
            positives.append(
                f"P/E {target_pe:.2f}x thấp hơn median peers {peer_median_pe:.2f}x khoảng {abs(pe_diff):.1%}."
            )
        elif pe_diff > 0:
            risks.append(
                f"P/E {target_pe:.2f}x cao hơn median peers {peer_median_pe:.2f}x khoảng {abs(pe_diff):.1%}."
            )

    pb_diff = _pct_diff(target_pb, peer_median_pb)
    if pb_diff is not None:
        if pb_diff < 0:
            positives.append(
                f"P/B {target_pb:.2f}x thấp hơn median peers {peer_median_pb:.2f}x khoảng {abs(pb_diff):.1%}."
            )
        elif pb_diff > 0:
            risks.append(
                f"P/B {target_pb:.2f}x cao hơn median peers {peer_median_pb:.2f}x khoảng {abs(pb_diff):.1%}."
            )

    if upside_downside is not None:
        if upside_downside > 0:
            positives.append(f"Giá trị hàm ý theo peers cao hơn giá hiện tại khoảng {upside_downside:.1%}.")
        elif upside_downside < 0:
            risks.append(f"Giá trị hàm ý theo peers thấp hơn giá hiện tại khoảng {abs(upside_downside):.1%}.")

    failed_peer_count = len(peer_rows) - len(cleaned_peers)
    if failed_peer_count > 0:
        risks.append(f"{failed_peer_count} peer thiếu P/E/P/B hợp lệ và đã bị loại khỏi median.")

    if not cleaned_peers:
        risks.append("Không có peer nào trả về P/E/P/B hợp lệ; có thể API đang rate limit hoặc dữ liệu ngành thiếu.")

    peer_quality_status, peer_quality_warnings, peer_quality = _peer_quality_review(
        peer_rows,
        cleaned_peers,
    )

    comparison_parts = []
    if target_pe is not None and peer_median_pe is not None:
        comparison_parts.append(f"P/E {target_pe:.2f}x vs median {peer_median_pe:.2f}x")
    if target_pb is not None and peer_median_pb is not None:
        comparison_parts.append(f"P/B {target_pb:.2f}x vs median {peer_median_pb:.2f}x")
    comparison_text = "; ".join(comparison_parts) if comparison_parts else "chưa đủ P/E/P/B để so sánh"

    fair_value_text = (
        (
            f" Giá trị hàm ý tổng hợp theo peers khoảng {peer_fair_value:,.0f} VND/cp, "
            f"sử dụng {valuation_weights['label']}."
        )
        if peer_fair_value is not None
        else " Chưa đủ EPS/BVPS để quy đổi multiples của peers thành giá trị hàm ý."
    )

    icb_text = ""
    if industry_meta.get("icb_code"):
        icb_text = (
            f" Nhóm peer được chọn theo ICB cấp {industry_meta.get('icb_level') or 'N/A'} "
            f"({industry_meta.get('icb_code')} - {industry_meta.get('icb_name') or 'N/A'})."
        )

    commentary = (
        f"Peer Valuation Score đạt {score:.2f}/100, xếp loại '{classification}'. "
        if score is not None
        else "Peer Valuation chưa đủ dữ liệu để chấm điểm. "
    )
    quality_text = ""
    if peer_quality_warnings:
        quality_text = (
            f" Chất lượng peer: {peer_quality_status}. "
            + " ".join(peer_quality_warnings[:2])
        )

    commentary += (
        f"StockLens sử dụng {len(cleaned_peers)} peer hợp lệ; {comparison_text}."
        + fair_value_text
        + icb_text
        + quality_text
        + " Peer valuation là định giá tương đối; mức chiết khấu so với peers không tự động đồng nghĩa cổ phiếu bị định giá thấp nếu tăng trưởng, ROE hoặc rủi ro doanh nghiệp khác biệt."
    )

    return {
        "ticker": symbol,
        "data_available": bool(valid_scores),
        "source": source,
        "industry": industry_meta.get("icb_name") or target.get("sector"),
        "industry_icb_level": industry_meta.get("icb_level"),
        "industry_icb_code": industry_meta.get("icb_code"),
        "industry_peer_candidates": industry_meta.get("available_peer_candidates"),
        "peer_count": len(cleaned_peers),
        "score": score,
        "classification": classification,
        "components": components,
        "pe": target_pe,
        "pb": target_pb,
        "eps": target_eps,
        "bvps": target_bvps,
        "current_price": current_price,
        "peer_median_pe": peer_median_pe,
        "peer_median_pb": peer_median_pb,
        "pe_relative": pe_relative,
        "pb_relative": pb_relative,
        "implied_price_pe": implied_pe,
        "implied_price_pb": implied_pb,
        "peer_fair_value": peer_fair_value,
        "upside_downside": upside_downside,
        "valuation_weights": {
            "pe": valuation_weights["pe"],
            "pb": valuation_weights["pb"],
            "label": valuation_weights["label"],
            "sector_rule": valuation_weights["sector_rule"],
        },
        "peer_quality_status": peer_quality_status,
        "peer_quality_warnings": peer_quality_warnings,
        "peer_quality": peer_quality,
        "peers": cleaned_peers,
        "positives": positives,
        "risks": risks,
        "commentary": commentary,
        "requested_peers": [p.get("symbol") for p in peer_descriptors],
        "failed_peer_count": failed_peer_count,
    }


peer_valuation = analyze_peer_valuation


# =============================================================================
# Standalone FPT test
# =============================================================================


def _fmt(value: Any, suffix: str = "") -> str:
    number = _finite(value)
    if number is None:
        return "N/A"
    return f"{number:,.2f}{suffix}"


if __name__ == "__main__":
    test_ticker = "FPT"

    print("=" * 60)
    print("STOCKLENS - PEER VALUATION TEST")
    print("=" * 60)
    print()

    # Try to reuse StockLens/DNSE for the latest close. If unavailable, peer
    # valuation still works; only upside/downside will be N/A.
    latest_price = None
    try:
        from datetime import date, timedelta
        try:
            from market_data import get_market_data
        except Exception:
            from ..market_data import get_market_data  # type: ignore

        end = date.today()
        start = end - timedelta(days=30)
        market_df = get_market_data(test_ticker, str(start), str(end))
        if isinstance(market_df, pd.DataFrame) and not market_df.empty:
            latest_price = _positive(market_df.iloc[-1].get("Close"))
    except BaseException:
        latest_price = None

    result = analyze_peer_valuation(
        ticker=test_ticker,
        current_price=latest_price,
        max_peers=5,
        request_delay=2.0,
    )

    print("Ticker:", result.get("ticker"))
    print("Source:", result.get("source"))
    print("Industry:", result.get("industry"))
    print("ICB Level:", result.get("industry_icb_level"))
    print("ICB Code:", result.get("industry_icb_code"))
    print("Requested Peers:", result.get("requested_peers"))
    print("Valid Peer Count:", result.get("peer_count"))
    print()
    print("Current Price:", _fmt(result.get("current_price"), " VND"))
    print("P/E:", _fmt(result.get("pe"), "x"))
    print("Peer Median P/E:", _fmt(result.get("peer_median_pe"), "x"))
    print("P/B:", _fmt(result.get("pb"), "x"))
    print("Peer Median P/B:", _fmt(result.get("peer_median_pb"), "x"))
    print("EPS:", _fmt(result.get("eps"), " VND"))
    print("BVPS:", _fmt(result.get("bvps"), " VND"))
    print()
    print("Implied Price by P/E:", _fmt(result.get("implied_price_pe"), " VND"))
    print("Implied Price by P/B:", _fmt(result.get("implied_price_pb"), " VND"))
    print("Peer Fair Value:", _fmt(result.get("peer_fair_value"), " VND"))
    print("Valuation Weights:", result.get("valuation_weights"))
    if result.get("upside_downside") is None:
        print("Upside/Downside: N/A")
    else:
        print("Upside/Downside:", f"{result['upside_downside']:+.2%}")
    print()
    print("Peer Valuation Score:", result.get("score"))
    print("Classification:", result.get("classification"))
    print("Components:", result.get("components"))
    print()
    print("Peers:")
    for peer in result.get("peers", []):
        print(peer)
    print()
    print("Positive:", result.get("positives"))
    print("Risks:", result.get("risks"))
    print("Peer Quality Status:", result.get("peer_quality_status"))
    print("Peer Quality Warnings:", result.get("peer_quality_warnings"))
    print("Peer Quality Detail:", result.get("peer_quality"))
    print("Commentary:", result.get("commentary"))
    print()
    print("peer valuation test: OK")
