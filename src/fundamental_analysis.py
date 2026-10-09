"""
StockLens - Fundamental Analysis

Nguồn đầu vào:
    src/vnstock_data.py -> vnstock / KBS

Thiết kế:
    - Doanh nghiệp thông thường: giữ nguyên bộ 6 chỉ tiêu cũ để không làm thay đổi
      cách chấm FPT/HPG/MWG...
    - Ngân hàng: dùng bộ chỉ tiêu riêng phù hợp hơn với mô hình ngân hàng; không
      ép Debt/Equity, Current Ratio hay Net Margin vào cùng thang điểm doanh nghiệp.

Các ngưỡng là heuristic của StockLens, phục vụ học tập và nghiên cứu.
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any


# =========================================================
# 1. BASIC HELPERS
# =========================================================

def _num(value) -> float | None:
    try:
        number = float(value)
        if not math.isfinite(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def _pct_text(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2%}"


def _ratio_text(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2f}x"


def _normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"\s+", " ", text)
    return text


def _detect_business_type(info: dict) -> str:
    explicit = _normalize_text(info.get("financialBusinessType"))
    if explicit == "bank":
        return "bank"
    if explicit == "corporate":
        return "corporate"

    blob = _normalize_text(
        " ".join(
            str(info.get(k) or "")
            for k in ("sector", "industry", "name", "business_model")
        )
    )

    bank_markers = (
        "ngan hang",
        "commercial bank",
        "banking",
        "bank ",
    )
    if any(marker in blob for marker in bank_markers):
        return "bank"

    return "corporate"


def _period_key(value: Any) -> tuple[int, int]:
    text = str(value or "")
    q = re.search(r"(\d{4}).*?q([1-4])", text, flags=re.I)
    if q:
        return int(q.group(1)), int(q.group(2))
    y = re.search(r"(\d{4})", text)
    if y:
        return int(y.group(1)), 5
    return -1, -1


def _history_rows(info: dict) -> list[dict]:
    history = info.get("financialHistory", []) or []
    rows = [row for row in history if isinstance(row, dict)]
    return sorted(rows, key=lambda row: _period_key(row.get("period")), reverse=True)


def _history_growth(info: dict, field: str) -> float | None:
    values: list[float] = []
    for row in _history_rows(info):
        value = _num(row.get(field))
        if value is not None:
            values.append(value)
        if len(values) >= 2:
            break

    if len(values) < 2 or values[1] == 0:
        return None
    return values[0] / values[1] - 1


def _safe_divide(a, b) -> float | None:
    a = _num(a)
    b = _num(b)
    if a is None or b in (None, 0):
        return None
    return a / b


# =========================================================
# 2. SCORING HELPERS
# =========================================================

def _score_higher(value: float | None, strong: float, acceptable: float) -> int | None:
    if value is None:
        return None
    if value >= strong:
        return 100
    if value >= acceptable:
        return 60
    return 20


def _score_lower(value: float | None, strong: float, acceptable: float) -> int | None:
    if value is None:
        return None
    if value <= strong:
        return 100
    if value <= acceptable:
        return 60
    return 20


def _score_current_ratio(value: float | None) -> int | None:
    if value is None or value < 0:
        return None
    if value >= 1.5:
        return 100
    if value >= 1.0:
        return 60
    return 20


def _classification(score: float | None) -> str:
    if score is None:
        return "Không đủ dữ liệu"
    if score >= 80:
        return "Nền tảng cơ bản mạnh"
    if score >= 65:
        return "Nền tảng cơ bản tích cực"
    if score >= 50:
        return "Nền tảng cơ bản trung lập"
    return "Nền tảng cơ bản cần thận trọng"


def _weighted_score(component_scores: dict[str, float], weights: dict[str, float]):
    weighted_points = 0.0
    available_weight = 0.0

    for key, score_value in component_scores.items():
        weight = weights.get(key, 0.0)
        weighted_points += score_value * weight
        available_weight += weight

    score = round(weighted_points / available_weight, 2) if available_weight > 0 else None
    return score, available_weight


# =========================================================
# 3. CORPORATE ANALYSIS - GIỮ LOGIC CŨ
# =========================================================

def _analyze_corporate(info: dict, metrics: dict[str, float | None]) -> dict[str, Any]:
    component_weights = {
        "roe": 0.20,
        "roa": 0.15,
        "profit_margin": 0.20,
        "revenue_growth": 0.15,
        "debt_to_equity": 0.15,
        "current_ratio": 0.15,
    }

    component_scores: dict[str, int] = {}
    positives: list[str] = []
    risks: list[str] = []
    observations: list[str] = []

    roe = metrics["roe"]
    s = _score_higher(roe, 0.15, 0.08)
    if s is not None:
        component_scores["roe"] = s
        if s == 100:
            positives.append(f"ROE {_pct_text(roe)} cho thấy khả năng sinh lời trên vốn chủ sở hữu tốt.")
        elif s == 60:
            observations.append(f"ROE {_pct_text(roe)} ở mức chấp nhận được.")
        else:
            risks.append(f"ROE {_pct_text(roe)} tương đối thấp.")

    roa = metrics["roa"]
    s = _score_higher(roa, 0.07, 0.03)
    if s is not None:
        component_scores["roa"] = s
        if s == 100:
            positives.append(f"ROA {_pct_text(roa)} phản ánh hiệu quả sử dụng tài sản tốt.")
        elif s == 60:
            observations.append(f"ROA {_pct_text(roa)} ở mức trung bình.")
        else:
            risks.append(f"ROA {_pct_text(roa)} còn thấp.")

    margin = metrics["profit_margin"]
    s = _score_higher(margin, 0.12, 0.05)
    if s is not None:
        component_scores["profit_margin"] = s
        if s == 100:
            positives.append(f"Biên lợi nhuận ròng {_pct_text(margin)} ở mức tốt.")
        elif s == 60:
            observations.append(f"Biên lợi nhuận ròng {_pct_text(margin)} ở mức chấp nhận được.")
        else:
            risks.append(f"Biên lợi nhuận ròng {_pct_text(margin)} còn thấp.")

    growth = metrics["revenue_growth"]
    s = _score_higher(growth, 0.10, 0.00)
    if s is not None:
        component_scores["revenue_growth"] = s
        if s == 100:
            positives.append(f"Doanh thu tăng {_pct_text(growth)} so với kỳ trước.")
        elif s == 60:
            observations.append(f"Tăng trưởng doanh thu {_pct_text(growth)} ở mức dương nhưng chưa cao.")
        else:
            risks.append(f"Doanh thu giảm {_pct_text(abs(growth))} so với kỳ trước.")

    de = metrics["debt_to_equity"]
    s = _score_lower(de, 0.80, 1.50) if de is not None and de >= 0 else None
    if s is not None:
        component_scores["debt_to_equity"] = s
        if s == 100:
            positives.append(f"Debt/Equity {_ratio_text(de)} cho thấy đòn bẩy ở mức tương đối an toàn theo tiêu chí StockLens.")
        elif s == 60:
            observations.append(f"Debt/Equity {_ratio_text(de)} ở mức cần theo dõi.")
        else:
            risks.append(f"Debt/Equity {_ratio_text(de)} khá cao.")

    cr = metrics["current_ratio"]
    s = _score_current_ratio(cr)
    if s is not None:
        component_scores["current_ratio"] = s
        if s == 100:
            positives.append(f"Current Ratio {_ratio_text(cr)} cho thấy khả năng thanh toán ngắn hạn tốt.")
        elif s == 60:
            observations.append(f"Current Ratio {_ratio_text(cr)} ở mức chấp nhận được.")
        else:
            risks.append(f"Current Ratio {_ratio_text(cr)} dưới 1, cần lưu ý thanh khoản ngắn hạn.")

    score, available_weight = _weighted_score(component_scores, component_weights)

    return {
        "component_weights": component_weights,
        "component_scores": component_scores,
        "positives": positives,
        "risks": risks,
        "observations": observations,
        "score": score,
        "available_weight": available_weight,
        "total_components": len(component_weights),
        "method_note": (
            "Doanh nghiệp thông thường: ROE 20%, ROA 15%, biên lợi nhuận ròng 20%, "
            "tăng trưởng doanh thu 15%, Debt/Equity 15% và Current Ratio 15%. "
            "Chỉ tiêu thiếu dữ liệu được loại khỏi mẫu số thay vì chấm 0."
        ),
    }


# =========================================================
# 4. BANK ANALYSIS - BỘ CHỈ TIÊU RIÊNG
# =========================================================

def _analyze_bank(info: dict, metrics: dict[str, float | None]) -> dict[str, Any]:
    # Không dùng D/E, Current Ratio và Net Margin của doanh nghiệp thường cho ngân hàng.
    # Chỉ sử dụng các biến có thể lấy/derive minh bạch từ KBS hiện tại.
    component_weights = {
        "roe": 0.25,
        "roa": 0.20,
        "net_income_growth": 0.20,
        "asset_growth": 0.15,
        "equity_to_assets": 0.10,
        "operating_income_growth": 0.10,
    }

    component_scores: dict[str, int] = {}
    positives: list[str] = []
    risks: list[str] = []
    observations: list[str] = []

    roe = metrics["roe"]
    s = _score_higher(roe, 0.15, 0.10)
    if s is not None:
        component_scores["roe"] = s
        if s == 100:
            positives.append(f"ROE {_pct_text(roe)} ở mức mạnh đối với ngân hàng.")
        elif s == 60:
            observations.append(f"ROE {_pct_text(roe)} ở mức chấp nhận được đối với ngân hàng.")
        else:
            risks.append(f"ROE {_pct_text(roe)} còn thấp so với ngưỡng StockLens dành cho ngân hàng.")

    roa = metrics["roa"]
    s = _score_higher(roa, 0.015, 0.008)
    if s is not None:
        component_scores["roa"] = s
        if s == 100:
            positives.append(f"ROA {_pct_text(roa)} cho thấy hiệu quả sử dụng tài sản tốt trong mô hình ngân hàng.")
        elif s == 60:
            observations.append(f"ROA {_pct_text(roa)} ở mức chấp nhận được đối với ngân hàng.")
        else:
            risks.append(f"ROA {_pct_text(roa)} còn thấp.")

    growth = metrics["net_income_growth"]
    s = _score_higher(growth, 0.15, 0.00)
    if s is not None:
        component_scores["net_income_growth"] = s
        if s == 100:
            positives.append(f"LNST tăng {_pct_text(growth)} so với năm trước.")
        elif s == 60:
            observations.append(f"LNST tăng {_pct_text(growth)}, nhưng tốc độ chưa cao.")
        else:
            risks.append(f"LNST giảm {_pct_text(abs(growth))} so với năm trước.")

    asset_growth = metrics["asset_growth"]
    s = _score_higher(asset_growth, 0.12, 0.05)
    if s is not None:
        component_scores["asset_growth"] = s
        if s == 100:
            positives.append(f"Tổng tài sản tăng {_pct_text(asset_growth)}, cho thấy quy mô hoạt động mở rộng mạnh.")
        elif s == 60:
            observations.append(f"Tổng tài sản tăng {_pct_text(asset_growth)} ở mức vừa phải.")
        else:
            risks.append(f"Tăng trưởng tổng tài sản {_pct_text(asset_growth)} còn yếu hoặc âm.")

    equity_to_assets = metrics["equity_to_assets"]
    s = _score_higher(equity_to_assets, 0.08, 0.05)
    if s is not None:
        component_scores["equity_to_assets"] = s
        if s == 100:
            positives.append(f"VCSH/Tổng tài sản {_pct_text(equity_to_assets)} cho thấy lớp vốn kế toán tương đối tốt.")
        elif s == 60:
            observations.append(f"VCSH/Tổng tài sản {_pct_text(equity_to_assets)} ở mức trung bình.")
        else:
            risks.append(f"VCSH/Tổng tài sản {_pct_text(equity_to_assets)} tương đối thấp.")

    income_growth = metrics["operating_income_growth"]
    s = _score_higher(income_growth, 0.10, 0.00)
    if s is not None:
        component_scores["operating_income_growth"] = s
        if s == 100:
            positives.append(f"Thu nhập hoạt động tăng {_pct_text(income_growth)} so với năm trước.")
        elif s == 60:
            observations.append(f"Thu nhập hoạt động tăng {_pct_text(income_growth)} nhưng chưa mạnh.")
        else:
            risks.append(f"Thu nhập hoạt động giảm {_pct_text(abs(income_growth))} so với năm trước.")

    score, available_weight = _weighted_score(component_scores, component_weights)

    observations.append(
        "StockLens không dùng Debt/Equity, Current Ratio và Net Profit Margin theo thang doanh nghiệp thông thường cho ngân hàng."
    )

    return {
        "component_weights": component_weights,
        "component_scores": component_scores,
        "positives": positives,
        "risks": risks,
        "observations": observations,
        "score": score,
        "available_weight": available_weight,
        "total_components": len(component_weights),
        "method_note": (
            "Ngân hàng: ROE 25%, ROA 20%, tăng trưởng LNST 20%, tăng trưởng tổng tài sản 15%, "
            "VCSH/Tổng tài sản 10% và tăng trưởng thu nhập hoạt động 10%. Chỉ tiêu thiếu dữ liệu "
            "được loại khỏi mẫu số. VCSH/Tổng tài sản là tỷ lệ vốn kế toán, không phải CAR."
        ),
    }


# =========================================================
# 5. PUBLIC API
# =========================================================

def analyze_fundamental(info: dict) -> dict[str, Any]:
    info = info or {}
    business_type = _detect_business_type(info)

    history = _history_rows(info)

    total_assets = _num(info.get("totalAssets"))
    total_equity = _num(info.get("totalEquity"))

    metrics = {
        "roe": _num(info.get("returnOnEquity")),
        "roa": _num(info.get("returnOnAssets")),
        "profit_margin": _num(info.get("profitMargins")),
        "revenue_growth": _num(info.get("revenueGrowth")),
        "debt_to_equity": _num(info.get("debtToEquity")),
        "current_ratio": _num(info.get("currentRatio")),
        "total_revenue": _num(info.get("totalRevenue")),
        "net_income": _num(info.get("netIncomeToCommon")),
        "gross_profit": _num(info.get("grossProfit")),
        "operating_cash_flow": _num(info.get("operatingCashFlow")),
        "total_assets": total_assets,
        "total_equity": total_equity,
        # Bank-oriented metrics derived only from actual historical values.
        "net_income_growth": _history_growth(info, "net_profit"),
        "asset_growth": _history_growth(info, "total_assets"),
        "equity_growth": _history_growth(info, "equity"),
        "operating_income_growth": _history_growth(info, "revenue"),
        "equity_to_assets": _safe_divide(total_equity, total_assets),
    }

    if business_type == "bank":
        result = _analyze_bank(info, metrics)
    else:
        result = _analyze_corporate(info, metrics)

    score = result["score"]
    component_scores = result["component_scores"]
    component_weights = result["component_weights"]
    available_weight = result["available_weight"]
    total_components = result["total_components"]
    coverage = len(component_scores)
    coverage_ratio = coverage / total_components if total_components else 0
    classification = _classification(score)

    if score is None:
        commentary = "Không đủ dữ liệu tài chính để tính Fundamental Score."
    elif business_type == "bank":
        commentary = (
            f"Fundamental Score ngân hàng đạt {score:.2f}/100, xếp loại '{classification}'. "
            f"Điểm được tính từ {coverage}/{total_components} chỉ tiêu ngân hàng có dữ liệu. "
            "Debt/Equity, Current Ratio và biên lợi nhuận doanh nghiệp không bị ép vào mô hình ngân hàng."
        )
    else:
        commentary = (
            f"Fundamental Score đạt {score:.2f}/100, xếp loại '{classification}'. "
            f"Điểm được tính từ {coverage}/{total_components} chỉ tiêu tài chính có dữ liệu. "
            "Chỉ tiêu thiếu dữ liệu không bị quy thành 0."
        )

    return {
        "data_available": score is not None,
        "score": score,
        "classification": classification,
        "metrics": metrics,
        "component_scores": component_scores,
        "component_weights": component_weights,
        "positives": result["positives"],
        "observations": result["observations"],
        "risks": result["risks"],
        "commentary": commentary,
        "coverage": coverage,
        "total_components": total_components,
        "coverage_ratio": round(coverage_ratio, 4),
        "coverage_weight": round(available_weight * 100, 2),
        "business_type": business_type,
        "is_bank": business_type == "bank",
        "not_applicable_metrics": (
            ["profit_margin", "debt_to_equity", "current_ratio"]
            if business_type == "bank"
            else []
        ),
        "ticker": info.get("ticker"),
        "company_name": info.get("name"),
        "sector": info.get("sector"),
        "report_period": info.get("reportPeriod"),
        "financial_history": history,
        "source": "vnstock - dữ liệu tài chính KBS",
        "method_note": result["method_note"],
    }
