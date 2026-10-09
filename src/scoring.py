"""
StockLens - Investment Scoring

Mục tiêu:
    1. Tính Market Risk / Safety Score
    2. Tổng hợp 5 nhóm điểm thành Investment Score
    3. Tính điểm điều chỉnh theo hồ sơ nhà đầu tư

Investment Score cơ sở:
    Fundamental : 25%
    Valuation   : 25%
    Technical   : 25%
    News        : 15%
    Risk/Safety : 10%

Lưu ý:
    - Investment Score là heuristic của StockLens.
    - Không phải xác suất sinh lời.
    - Không phải khuyến nghị mua/bán.
    - Nếu thiếu một thành phần chính, StockLens không
      tự nội suy Investment Score cơ sở.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


# =========================================================
# 1. BASE INVESTMENT WEIGHTS
# =========================================================

WEIGHTS = {
    "fundamental": 0.25,
    "valuation": 0.25,
    "technical": 0.25,
    "news": 0.15,
    "risk": 0.10,
}


# =========================================================
# 2. INVESTOR PROFILES
# =========================================================
#
# Cân bằng:
#     đúng bằng Investment Score cơ sở
#
# Thận trọng:
#     tăng mạnh trọng số Risk/Safety
#
# Tăng trưởng:
#     tăng Fundamental + Technical,
#     giảm Risk/Safety và Valuation
# =========================================================

PROFILES = {

    "Thận trọng": {
        "fundamental": 0.25,
        "valuation": 0.20,
        "technical": 0.15,
        "news": 0.10,
        "risk": 0.30,
    },

    "Cân bằng": {
        "fundamental": 0.25,
        "valuation": 0.25,
        "technical": 0.25,
        "news": 0.15,
        "risk": 0.10,
    },

    "Tăng trưởng": {
        "fundamental": 0.35,
        "valuation": 0.15,
        "technical": 0.30,
        "news": 0.15,
        "risk": 0.05,
    },
}


# =========================================================
# 3. DISPLAY NAMES
# =========================================================

COMPONENT_NAMES = {
    "fundamental": "Fundamental",
    "valuation": "Valuation",
    "technical": "Technical",
    "news": "News/Sentiment",
    "risk": "Risk/Safety",
}


# =========================================================
# 4. BASIC HELPERS
# =========================================================

def _num(
    value,
) -> float | None:
    """
    Chuyển về float an toàn.
    """

    try:

        number = float(
            value
        )

        if not math.isfinite(
            number
        ):
            return None

        return number

    except (
        TypeError,
        ValueError,
    ):
        return None


def _clamp_score(
    value,
) -> float | None:
    """
    Đảm bảo score nằm trong 0 -> 100.
    """

    value = _num(
        value
    )

    if value is None:
        return None

    return max(
        0.0,
        min(
            100.0,
            value,
        ),
    )


# =========================================================
# 5. INVESTMENT CLASSIFICATION
# =========================================================

def investment_label(
    score: float | None,
) -> str | None:
    """
    Phân loại chính thức của StockLens.

    80 - 100:
        Cơ hội cao

    65 - <80:
        Tích cực

    50 - <65:
        Trung lập

    <50:
        Thận trọng
    """

    score = _num(
        score
    )

    if score is None:
        return None

    if score >= 80:
        return "Cơ hội cao"

    if score >= 65:
        return "Tích cực"

    if score >= 50:
        return "Trung lập"

    return "Thận trọng"


# =========================================================
# 6. RISK CLASSIFICATION
# =========================================================

def _risk_classification(
    score: float | None,
) -> str:
    """
    Risk/Safety Score càng cao
    -> rủi ro thị trường càng thấp.
    """

    if score is None:
        return "Không đủ dữ liệu"

    if score >= 80:
        return "Rủi ro thị trường thấp"

    if score >= 65:
        return "Rủi ro tương đối kiểm soát"

    if score >= 50:
        return "Rủi ro thị trường trung bình"

    return "Rủi ro thị trường cao"


# =========================================================
# 7. VOLATILITY SCORE
# =========================================================

def _volatility_score(
    volatility: float | None,
) -> int | None:
    """
    Annualized volatility.

    < 20%:
        100

    20% - 30%:
        75

    >30% - 40%:
        50

    >40%:
        25

    Điểm cao = biến động thấp hơn.
    """

    volatility = _num(
        volatility
    )

    if (
        volatility is None
        or volatility < 0
    ):
        return None

    if volatility < 0.20:
        return 100

    if volatility <= 0.30:
        return 75

    if volatility <= 0.40:
        return 50

    return 25


# =========================================================
# 8. MAX DRAWDOWN SCORE
# =========================================================

def _drawdown_score(
    max_drawdown: float | None,
) -> int | None:
    """
    max_drawdown thường là số âm.

    Ví dụ:
        -0.12 = giảm tối đa 12%

    Absolute drawdown:

    < 10%:
        100

    10% - 20%:
        75

    >20% - 35%:
        50

    >35%:
        25
    """

    max_drawdown = _num(
        max_drawdown
    )

    if max_drawdown is None:
        return None

    dd = abs(
        max_drawdown
    )

    if dd < 0.10:
        return 100

    if dd <= 0.20:
        return 75

    if dd <= 0.35:
        return 50

    return 25


# =========================================================
# 9. MARKET RISK / SAFETY SCORE
# =========================================================

def market_risk(
    technical: dict,
) -> dict[str, Any]:
    """
    Tính Market Risk / Safety Score.

    Input:
        output từ analyze_technical()

    Công thức:
        50% Volatility Score
        50% Maximum Drawdown Score

    Điểm càng cao:
        rủi ro thị trường càng thấp.
    """

    technical = (
        technical
        or {}
    )

    # =====================================================
    # CHECK TECHNICAL DATA
    # =====================================================

    if not technical.get(
        "data_available",
        False,
    ):

        return {
            "data_available": False,

            "score": None,

            "classification": (
                "Không đủ dữ liệu"
            ),

            "metrics": {},

            "positives": [],

            "observations": [],

            "risks": [],

            "commentary": (
                "Thiếu dữ liệu kỹ thuật để đo "
                "Market Risk/Safety Score."
            ),

            "source": (
                "DNSE OpenAPI + StockLens"
            ),
        }

    # =====================================================
    # GET DATA
    # =====================================================

    df = technical.get(
        "data"
    )

    volatility = _num(
        technical.get(
            "volatility"
        )
    )

    if (
        not isinstance(
            df,
            pd.DataFrame,
        )
        or df.empty
    ):

        return {
            "data_available": False,

            "score": None,

            "classification": (
                "Không đủ dữ liệu"
            ),

            "metrics": {},

            "positives": [],

            "observations": [],

            "risks": [],

            "commentary": (
                "Không có chuỗi giá hợp lệ "
                "để tính Maximum Drawdown."
            ),

            "source": (
                "DNSE OpenAPI + StockLens"
            ),
        }

    if (
        "Close"
        not in df.columns
    ):

        return {
            "data_available": False,

            "score": None,

            "classification": (
                "Không đủ dữ liệu"
            ),

            "metrics": {},

            "positives": [],

            "observations": [],

            "risks": [],

            "commentary": (
                "Dữ liệu kỹ thuật thiếu cột Close."
            ),

            "source": (
                "DNSE OpenAPI + StockLens"
            ),
        }

    # =====================================================
    # CLEAN CLOSE
    # =====================================================

    close = pd.to_numeric(
        df["Close"],
        errors="coerce",
    ).dropna()

    close = close[
        close > 0
    ]

    if close.empty:

        return {
            "data_available": False,

            "score": None,

            "classification": (
                "Không đủ dữ liệu"
            ),

            "metrics": {},

            "positives": [],

            "observations": [],

            "risks": [],

            "commentary": (
                "Không có giá đóng cửa hợp lệ "
                "để tính rủi ro."
            ),

            "source": (
                "DNSE OpenAPI + StockLens"
            ),
        }

    # =====================================================
    # MAXIMUM DRAWDOWN
    # =====================================================

    running_peak = (
        close.cummax()
    )

    drawdown_series = (
        close
        / running_peak
        - 1.0
    )

    max_drawdown = float(
        drawdown_series.min()
    )

    # =====================================================
    # COMPONENT SCORES
    # =====================================================

    vol_score = (
        _volatility_score(
            volatility
        )
    )

    dd_score = (
        _drawdown_score(
            max_drawdown
        )
    )

    component_scores = {}

    component_weights = {
        "volatility": 0.50,
        "max_drawdown": 0.50,
    }

    if vol_score is not None:

        component_scores[
            "volatility"
        ] = vol_score

    if dd_score is not None:

        component_scores[
            "max_drawdown"
        ] = dd_score

    # =====================================================
    # WEIGHTED RISK SCORE
    # =====================================================

    weighted_points = 0.0
    available_weight = 0.0

    for (
        key,
        component_score,
    ) in component_scores.items():

        weight = (
            component_weights[
                key
            ]
        )

        weighted_points += (
            component_score
            * weight
        )

        available_weight += weight

    if available_weight > 0:

        score = round(
            weighted_points
            / available_weight,
            2,
        )

    else:

        score = None

    # =====================================================
    # POSITIVES / RISKS
    # =====================================================

    positives = []
    observations = []
    risks = []

    # Volatility
    if volatility is not None:

        if vol_score == 100:

            positives.append(
                f"Biến động thường niên hóa "
                f"{volatility:.1%}, ở mức thấp "
                "theo ngưỡng StockLens."
            )

        elif vol_score in {
            75,
            50,
        }:

            observations.append(
                f"Biến động thường niên hóa "
                f"{volatility:.1%}, ở mức cần theo dõi."
            )

        else:

            risks.append(
                f"Biến động thường niên hóa "
                f"{volatility:.1%}, tương đối cao."
            )

    # Drawdown
    dd_abs = abs(
        max_drawdown
    )

    if dd_score == 100:

        positives.append(
            f"Maximum Drawdown trong kỳ "
            f"{max_drawdown:.1%}, ở mức thấp."
        )

    elif dd_score in {
        75,
        50,
    }:

        observations.append(
            f"Maximum Drawdown trong kỳ "
            f"{max_drawdown:.1%}, cần được theo dõi."
        )

    else:

        risks.append(
            f"Maximum Drawdown trong kỳ "
            f"{max_drawdown:.1%}, cho thấy "
            "mức giảm sâu đáng kể trong giai đoạn phân tích."
        )

    # =====================================================
    # CLASSIFICATION
    # =====================================================

    classification = (
        _risk_classification(
            score
        )
    )

    # =====================================================
    # COMMENTARY
    # =====================================================

    if score is not None:

        commentary = (
            f"Market Risk/Safety Score đạt "
            f"{score:.2f}/100, xếp loại "
            f"'{classification}'. "
            "Điểm được tính từ 50% mức biến động "
            "20 phiên thường niên hóa và 50% "
            "Maximum Drawdown của toàn kỳ phân tích. "
            "Điểm càng cao phản ánh mức rủi ro "
            "thị trường tương đối thấp hơn."
        )

    else:

        commentary = (
            "Không đủ dữ liệu để tính "
            "Market Risk/Safety Score."
        )

    # =====================================================
    # OUTPUT
    # =====================================================

    return {

        "data_available": (
            score is not None
        ),

        "score": score,

        "classification": (
            classification
        ),

        "metrics": {

            "volatility_20_annualized": (
                volatility
            ),

            "max_drawdown_period": (
                max_drawdown
            ),

            "volatility_score": (
                vol_score
            ),

            "drawdown_score": (
                dd_score
            ),

            "observations": (
                len(close)
            ),
        },

        "component_scores": (
            component_scores
        ),

        "component_weights": (
            component_weights
        ),

        "positives": (
            positives
        ),

        "observations": (
            observations
        ),

        "risks": risks,

        "commentary": (
            commentary
        ),

        "source": (
            "DNSE OpenAPI + StockLens"
        ),

        "method_note": (
            "Risk/Safety Score sử dụng 50% "
            "annualized volatility 20 phiên và "
            "50% Maximum Drawdown của kỳ phân tích. "
            "Đây là thước đo rủi ro thị trường, "
            "không phản ánh toàn bộ rủi ro doanh nghiệp."
        ),
    }


# =========================================================
# 10. EXTRACT COMPONENT SCORE
# =========================================================

def _extract_score(
    component: dict | None,
) -> float | None:
    """
    Lấy score từ một module.

    Module phải có:
        data_available = True
        score = số
    """

    if not isinstance(
        component,
        dict,
    ):
        return None

    if not component.get(
        "data_available",
        False,
    ):
        return None

    return _clamp_score(
        component.get(
            "score"
        )
    )


# =========================================================
# 11. WEIGHTED SCORE
# =========================================================

def _weighted_score(
    scores: dict[str, float | None],
    weights: dict[str, float],
    require_all: bool = True,
) -> float | None:
    """
    Tính weighted score.

    Investment Score cơ sở dùng:
        require_all=True

    Nghĩa là thiếu 1/5 thành phần:
        -> không tính điểm tổng hợp.

    Điều này tránh tự nội suy dữ liệu.
    """

    weighted_points = 0.0
    available_weight = 0.0

    for key, weight in (
        weights.items()
    ):

        score = scores.get(
            key
        )

        if score is None:

            if require_all:
                return None

            continue

        weighted_points += (
            score
            * weight
        )

        available_weight += (
            weight
        )

    if available_weight <= 0:
        return None

    # Trong trường hợp require_all=False,
    # chuẩn hóa theo phần trọng số có dữ liệu.
    return round(
        weighted_points
        / available_weight,
        2,
    )


# =========================================================
# 12. CONTRIBUTIONS
# =========================================================

def _contributions(
    scores: dict[str, float | None],
    weights: dict[str, float],
) -> dict[str, float | None]:
    """
    Ví dụ:

        Fundamental 94 × 25%
        = đóng góp 23.5 điểm.
    """

    result = {}

    for key, weight in (
        weights.items()
    ):

        score = scores.get(
            key
        )

        if score is None:

            result[key] = None

        else:

            result[key] = round(
                score * weight,
                2,
            )

    return result


# =========================================================
# 13. PROFILE SCORES
# =========================================================

def _profile_scores(
    scores: dict[str, float | None],
) -> dict[str, float | None]:
    """
    Điểm theo từng hồ sơ.

    Vẫn yêu cầu đủ cả 5 thành phần.
    """

    result = {}

    for (
        profile_name,
        weights,
    ) in PROFILES.items():

        result[
            profile_name
        ] = _weighted_score(
            scores=scores,
            weights=weights,
            require_all=True,
        )

    return result


# =========================================================
# 14. SCORE ALL
# =========================================================

def score_all(
    results: dict,
) -> dict[str, Any]:
    """
    Ghép 5 module thành Investment Score.

    results phải có dạng:

        {
            "fundamental": fundamental_result,
            "valuation": valuation_result,
            "technical": technical_result,
            "news": news_result,
            "risk": risk_result
        }

    Trong đó mỗi module có:

        data_available
        score
    """

    results = (
        results
        or {}
    )

    # =====================================================
    # EXTRACT SCORES
    # =====================================================

    scores = {

        "fundamental": (
            _extract_score(
                results.get(
                    "fundamental"
                )
            )
        ),

        "valuation": (
            _extract_score(
                results.get(
                    "valuation"
                )
            )
        ),

        "technical": (
            _extract_score(
                results.get(
                    "technical"
                )
            )
        ),

        "news": (
            _extract_score(
                results.get(
                    "news"
                )
            )
        ),

        "risk": (
            _extract_score(
                results.get(
                    "risk"
                )
            )
        ),
    }

    # =====================================================
    # MISSING COMPONENTS
    # =====================================================

    missing = [
        key
        for key, value
        in scores.items()
        if value is None
    ]

    # =====================================================
    # BASE INVESTMENT SCORE
    # =====================================================

    base_score = (
        _weighted_score(
            scores=scores,
            weights=WEIGHTS,
            require_all=True,
        )
    )

    # =====================================================
    # LABEL
    # =====================================================

    label = (
        investment_label(
            base_score
        )
    )

    # =====================================================
    # CONTRIBUTIONS
    # =====================================================

    contributions = (
        _contributions(
            scores=scores,
            weights=WEIGHTS,
        )
    )

    # =====================================================
    # PROFILE SCORES
    # =====================================================

    profile_scores = (
        _profile_scores(
            scores
        )
    )

    # =====================================================
    # PROFILE LABELS
    # =====================================================

    profile_labels = {

        profile: (
            investment_label(
                score
            )
        )

        for (
            profile,
            score,
        ) in profile_scores.items()
    }

    # =====================================================
    # AVAILABLE COMPONENTS
    # =====================================================

    available = [
        key
        for key, value
        in scores.items()
        if value is not None
    ]

    coverage = len(
        available
    )

    coverage_ratio = (
        coverage
        / len(WEIGHTS)
    )

    # =====================================================
    # POSITIVE / WEAK COMPONENTS
    # =====================================================

    strongest_component = None
    weakest_component = None

    available_scores = {
        key: value
        for key, value
        in scores.items()
        if value is not None
    }

    if available_scores:

        strongest_key = max(
            available_scores,
            key=available_scores.get,
        )

        weakest_key = min(
            available_scores,
            key=available_scores.get,
        )

        strongest_component = {
            "key": strongest_key,

            "name": (
                COMPONENT_NAMES[
                    strongest_key
                ]
            ),

            "score": (
                available_scores[
                    strongest_key
                ]
            ),
        }

        weakest_component = {
            "key": weakest_key,

            "name": (
                COMPONENT_NAMES[
                    weakest_key
                ]
            ),

            "score": (
                available_scores[
                    weakest_key
                ]
            ),
        }

    # =====================================================
    # COMMENTARY
    # =====================================================

    if base_score is None:

        missing_text = ", ".join(
            COMPONENT_NAMES.get(
                key,
                key,
            )
            for key in missing
        )

        commentary = (
            "Investment Score chưa được tính "
            "vì thiếu thành phần: "
            f"{missing_text}. "
            "StockLens giữ trạng thái thiếu dữ liệu "
            "thay vì tự nội suy điểm."
        )

    else:

        strongest_text = ""

        weakest_text = ""

        if strongest_component:

            strongest_text = (
                f" Thành phần mạnh nhất là "
                f"{strongest_component['name']} "
                f"({strongest_component['score']:.2f}/100)."
            )

        if weakest_component:

            weakest_text = (
                f" Thành phần thấp nhất là "
                f"{weakest_component['name']} "
                f"({weakest_component['score']:.2f}/100)."
            )

        commentary = (
            f"Investment Score đạt "
            f"{base_score:.2f}/100, "
            f"xếp loại '{label}'. "
            "Điểm cơ sở sử dụng trọng số cố định: "
            "25% Fundamental, 25% Valuation, "
            "25% Technical, 15% News/Sentiment "
            "và 10% Risk/Safety."
            + strongest_text
            + weakest_text
        )

    # =====================================================
    # FORMULA TEXT
    # =====================================================

    formula = (
        "Investment Score = "
        "25% Fundamental "
        "+ 25% Valuation "
        "+ 25% Technical "
        "+ 15% News/Sentiment "
        "+ 10% Risk/Safety"
    )

    # =====================================================
    # OUTPUT
    # =====================================================

    return {

        # -----------------------------------------------
        # Base score
        # -----------------------------------------------

        "score": (
            base_score
        ),

        "investment_score": (
            base_score
        ),

        "label": label,

        "classification": (
            label
        ),

        # -----------------------------------------------
        # Component scores
        # -----------------------------------------------

        "component_scores": (
            scores
        ),

        # -----------------------------------------------
        # Fixed weights
        # -----------------------------------------------

        "weights": (
            WEIGHTS.copy()
        ),

        # -----------------------------------------------
        # Contribution to 100-point score
        # -----------------------------------------------

        "contributions": (
            contributions
        ),

        # -----------------------------------------------
        # Profiles
        # -----------------------------------------------

        "profile_scores": (
            profile_scores
        ),

        "profile_labels": (
            profile_labels
        ),

        "profile_weights": {
            name: weights.copy()
            for name, weights
            in PROFILES.items()
        },

        # -----------------------------------------------
        # Missing data
        # -----------------------------------------------

        "missing": (
            missing
        ),

        "available": (
            available
        ),

        "coverage": (
            coverage
        ),

        "total_components": (
            len(WEIGHTS)
        ),

        "coverage_ratio": round(
            coverage_ratio,
            4,
        ),

        "data_available": (
            base_score is not None
        ),

        # -----------------------------------------------
        # Main drivers
        # -----------------------------------------------

        "strongest_component": (
            strongest_component
        ),

        "weakest_component": (
            weakest_component
        ),

        # -----------------------------------------------
        # Description
        # -----------------------------------------------

        "formula": (
            formula
        ),

        "commentary": (
            commentary
        ),

        "method_note": (
            "Investment Score là mô hình tổng hợp "
            "heuristic của StockLens. Điểm cơ sở dùng "
            "trọng số cố định 25/25/25/15/10. "
            "Điểm hồ sơ nhà đầu tư được tính riêng "
            "và không thay thế Investment Score cơ sở. "
            "Nếu thiếu một trong năm thành phần, "
            "StockLens không tự nội suy Investment Score."
        ),
    }



# =========================================================
# 15. FULL PIPELINE TEST
# =========================================================

if __name__ == "__main__":

    import sys
    from pathlib import Path

    # Cho phép scoring.py gọi market_data.py
    # nằm ở thư mục cha của src/
    PROJECT_ROOT = Path(
        __file__
    ).resolve().parent.parent

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(
            0,
            str(PROJECT_ROOT),
        )

    from market_data import get_market_data

    from src.technical_analysis import (
        analyze_technical,
    )

    from src.vnstock_data import (
        get_financial_data,
    )

    from src.fundamental_analysis import (
        analyze_fundamental,
    )

    from src.valuation import (
        analyze_valuation,
    )

    from src.news_analysis import (
        analyze_news,
    )

    print(
        "=" * 70
    )

    print(
        "STOCKLENS - FULL SCORING PIPELINE TEST"
    )

    print(
        "=" * 70
    )

    ticker = "FPT"

    try:

        # =================================================
        # 1. MARKET DATA - DNSE
        # =================================================

        print()
        print(
            "[1/7] DNSE Market Data..."
        )

        market_df = get_market_data(
            ticker=ticker,
            start_date="2026-01-01",
            end_date="2026-10-08",
        )

        print(
            "Market Data:",
            len(market_df),
            "phiên",
        )

        print(
            "Latest Close:",
            f"{market_df['Close'].iloc[-1]:,.0f} VND",
        )

        # =================================================
        # 2. TECHNICAL
        # =================================================

        print()
        print(
            "[2/7] Technical Analysis..."
        )

        technical = (
            analyze_technical(
                market_df
            )
        )

        print(
            "Technical Score:",
            technical.get(
                "score"
            ),
        )

        print(
            "Technical Label:",
            technical.get(
                "label"
            )
            or technical.get(
                "classification"
            ),
        )

        print(
            "RSI:",
            technical.get(
                "rsi"
            ),
        )

        print(
            "Volatility:",
            technical.get(
                "volatility"
            ),
        )

        # =================================================
        # 3. VNSTOCK / KBS
        # =================================================

        print()
        print(
            "[3/7] vnstock / KBS Financial Data..."
        )

        financial_data = (
            get_financial_data(
                ticker=ticker,
                period="year",
            )
        )

        print(
            "Report Period:",
            financial_data.get(
                "reportPeriod"
            ),
        )

        print(
            "Revenue:",
            financial_data.get(
                "totalRevenue"
            ),
        )

        print(
            "Net Income:",
            financial_data.get(
                "netIncomeToCommon"
            ),
        )

        # =================================================
        # 4. FUNDAMENTAL
        # =================================================

        print()
        print(
            "[4/7] Fundamental Analysis..."
        )

        fundamental = (
            analyze_fundamental(
                financial_data
            )
        )

        print(
            "Fundamental Score:",
            fundamental.get(
                "score"
            ),
        )

        print(
            "Fundamental:",
            fundamental.get(
                "classification"
            ),
        )

        # =================================================
        # 5. VALUATION
        # =================================================

        print()
        print(
            "[5/7] Valuation Analysis..."
        )

        valuation = (
            analyze_valuation(
                financial_data
            )
        )

        print(
            "Valuation Score:",
            valuation.get(
                "score"
            ),
        )

        print(
            "Valuation:",
            valuation.get(
                "classification"
            ),
        )

        print(
            "P/E:",
            valuation.get(
                "pe"
            ),
        )

        print(
            "P/B:",
            valuation.get(
                "pb"
            ),
        )

        # =================================================
        # 6. NEWS
        # =================================================

        print()
        print(
            "[6/7] News Analysis..."
        )

        news = analyze_news(
            ticker=ticker,

            company_name=(
                financial_data.get(
                    "name"
                )
                or ticker
            ),

            max_items=10,

            max_age_days=120,
        )

        print(
            "News Score:",
            news.get(
                "score"
            ),
        )

        print(
            "News:",
            news.get(
                "classification"
            ),
        )

        print(
            "Article Count:",
            news.get(
                "article_count"
            ),
        )

        # =================================================
        # 7. RISK / SAFETY
        # =================================================

        print()
        print(
            "[7/7] Risk / Safety Analysis..."
        )

        risk = market_risk(
            technical
        )

        print(
            "Risk/Safety Score:",
            risk.get(
                "score"
            ),
        )

        print(
            "Risk:",
            risk.get(
                "classification"
            ),
        )

        print(
            "Maximum Drawdown:",
            risk.get(
                "metrics",
                {},
            ).get(
                "max_drawdown_period"
            ),
        )

        # =================================================
        # FINAL INVESTMENT SCORE
        # =================================================

        results = {

            "fundamental": (
                fundamental
            ),

            "valuation": (
                valuation
            ),

            "technical": (
                technical
            ),

            "news": (
                news
            ),

            "risk": (
                risk
            ),
        }

        summary = score_all(
            results
        )

        # =================================================
        # RESULT
        # =================================================

        print()
        print(
            "=" * 70
        )

        print(
            "STOCKLENS INVESTMENT SCORE"
        )

        print(
            "=" * 70
        )

        print()

        print(
            "Ticker:",
            ticker,
        )

        print(
            "Investment Score:",
            summary.get(
                "investment_score"
            ),
        )

        print(
            "Classification:",
            summary.get(
                "classification"
            ),
        )

        # =================================================
        # COMPONENT SCORES
        # =================================================

        print()
        print(
            "Component Scores:"
        )

        for key, value in (
            summary.get(
                "component_scores",
                {}
            ).items()
        ):

            print(
                f"  {key}: {value}"
            )

        # =================================================
        # CONTRIBUTIONS
        # =================================================

        print()
        print(
            "Contributions:"
        )

        for key, value in (
            summary.get(
                "contributions",
                {}
            ).items()
        ):

            print(
                f"  {key}: {value}"
            )

        # =================================================
        # VERIFY SUM
        # =================================================

        contributions = (
            summary.get(
                "contributions",
                {}
            )
        )

        contribution_sum = sum(
            value
            for value in contributions.values()
            if value is not None
        )

        print()
        print(
            "Contribution Sum:",
            round(
                contribution_sum,
                2,
            ),
        )

        # =================================================
        # INVESTOR PROFILES
        # =================================================

        print()
        print(
            "Investor Profiles:"
        )

        profile_scores = (
            summary.get(
                "profile_scores",
                {}
            )
        )

        profile_labels = (
            summary.get(
                "profile_labels",
                {}
            )
        )

        for (
            profile,
            value,
        ) in profile_scores.items():

            print(
                f"  {profile}: "
                f"{value} "
                f"({profile_labels.get(profile)})"
            )

        # =================================================
        # STRONGEST / WEAKEST
        # =================================================

        print()

        print(
            "Strongest:",
            summary.get(
                "strongest_component"
            ),
        )

        print(
            "Weakest:",
            summary.get(
                "weakest_component"
            ),
        )

        # =================================================
        # COMMENTARY
        # =================================================

        print()

        print(
            "Commentary:"
        )

        print(
            summary.get(
                "commentary"
            )
        )

        # =================================================
        # FINAL STATUS
        # =================================================

        print()
        print(
            "=" * 70
        )

        if summary.get(
            "data_available"
        ):

            print(
                "FULL PIPELINE TEST: OK"
            )

        else:

            print(
                "FULL PIPELINE TEST: "
                "CHƯA ĐỦ DỮ LIỆU"
            )

            print(
                "Missing:",
                summary.get(
                    "missing"
                ),
            )

    except Exception as exc:

        print()
        print(
            "=" * 70
        )

        print(
            "PIPELINE ERROR"
        )

        print(
            "=" * 70
        )

        print(
            type(exc).__name__,
            ":",
            exc,
        )