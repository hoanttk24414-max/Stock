"""
StockLens - Valuation Analysis

Nguồn đầu vào:
    src/vnstock_data.py
    -> vnstock / KBS

Mục tiêu:
    - Đánh giá mức định giá tương đối của cổ phiếu
    - Tính Valuation Score / 100
    - Không tạo giá mục tiêu khi chưa có mô hình định giá nội tại

Các thành phần:
    1. P/E hiện tại
    2. P/B hiện tại
    3. P/E hiện tại so với median lịch sử
    4. P/B hiện tại so với median lịch sử

Lưu ý:
    Các ngưỡng chấm điểm là heuristic của StockLens.
    Không phải khuyến nghị mua/bán.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Any


# =========================================================
# 1. BASIC HELPERS
# =========================================================

def _num(value) -> float | None:
    """
    Chuyển value về float an toàn.
    """

    try:

        number = float(value)

        if not math.isfinite(number):
            return None

        return number

    except (
        TypeError,
        ValueError,
    ):
        return None


def _multiple_text(
    value: float | None,
) -> str:
    """
    Hiển thị multiple dạng x.
    """

    if value is None:
        return "N/A"

    return f"{value:.2f}x"


# =========================================================
# 2. ABSOLUTE P/E SCORE
# =========================================================

def _score_pe(
    value: float | None,
) -> int | None:
    """
    Chấm P/E tuyệt đối.

    P/E phải > 0 mới có ý nghĩa.

    <= 10x:
        100

    >10 - 15x:
        85

    >15 - 20x:
        70

    >20 - 30x:
        50

    >30x:
        25
    """

    if (
        value is None
        or value <= 0
    ):
        return None

    if value <= 10:
        return 100

    if value <= 15:
        return 85

    if value <= 20:
        return 70

    if value <= 30:
        return 50

    return 25


# =========================================================
# 3. ABSOLUTE P/B SCORE
# =========================================================

def _score_pb(
    value: float | None,
) -> int | None:
    """
    Chấm P/B tuyệt đối.

    <= 1x:
        100

    >1 - 2x:
        85

    >2 - 3x:
        70

    >3 - 5x:
        50

    >5x:
        25
    """

    if (
        value is None
        or value <= 0
    ):
        return None

    if value <= 1:
        return 100

    if value <= 2:
        return 85

    if value <= 3:
        return 70

    if value <= 5:
        return 50

    return 25


# =========================================================
# 4. HISTORICAL RELATIVE SCORE
# =========================================================

def _score_vs_history(
    current: float | None,
    historical_median: float | None,
) -> int | None:
    """
    So sánh multiple hiện tại với median lịch sử.

    current / historical median

    <= 0.85:
        thấp hơn lịch sử ít nhất 15% -> 100

    <= 1.00:
        thấp hơn hoặc bằng median -> 85

    <= 1.15:
        cao hơn không quá 15% -> 65

    > 1.15:
        cao hơn lịch sử đáng kể -> 35
    """

    if (
        current is None
        or historical_median is None
        or current <= 0
        or historical_median <= 0
    ):
        return None

    relative = (
        current
        / historical_median
    )

    if relative <= 0.85:
        return 100

    if relative <= 1.00:
        return 85

    if relative <= 1.15:
        return 65

    return 35


# =========================================================
# 5. CLASSIFICATION
# =========================================================

def _classification(
    score: float | None,
) -> str:
    """
    Phân loại Valuation Score.
    """

    if score is None:
        return "Không đủ dữ liệu"

    if score >= 80:
        return "Định giá tương đối hấp dẫn"

    if score >= 65:
        return "Định giá tương đối hợp lý"

    if score >= 50:
        return "Định giá trung tính"

    return "Định giá tương đối cao"


# =========================================================
# 6. HISTORICAL MULTIPLES
# =========================================================

def _extract_historical_multiples(
    info: dict,
    current_period=None,
):
    """
    Lấy P/E và P/B các năm trước.

    Không đưa năm hiện tại vào median lịch sử
    để tránh tự so sánh với chính nó.
    """

    history = info.get(
        "financialHistory",
        [],
    )

    if not isinstance(
        history,
        list,
    ):
        return {
            "pe_history": [],
            "pb_history": [],
            "pe_median": None,
            "pb_median": None,
        }

    pe_history = []
    pb_history = []

    for row in history:

        if not isinstance(
            row,
            dict,
        ):
            continue

        period = row.get(
            "period"
        )

        # Bỏ kỳ hiện tại
        if (
            current_period is not None
            and str(period)
            == str(current_period)
        ):
            continue

        pe = _num(
            row.get("pe")
        )

        pb = _num(
            row.get("pb")
        )

        if (
            pe is not None
            and pe > 0
        ):
            pe_history.append(
                pe
            )

        if (
            pb is not None
            and pb > 0
        ):
            pb_history.append(
                pb
            )

    pe_median = (
        float(
            median(
                pe_history
            )
        )
        if pe_history
        else None
    )

    pb_median = (
        float(
            median(
                pb_history
            )
        )
        if pb_history
        else None
    )

    return {
        "pe_history": (
            pe_history
        ),

        "pb_history": (
            pb_history
        ),

        "pe_median": (
            pe_median
        ),

        "pb_median": (
            pb_median
        ),
    }


# =========================================================
# 7. MAIN VALUATION ANALYSIS
# =========================================================

def analyze_valuation(
    info: dict,
    ticker: str | None = None,
    current_price: float | None = None,
) -> dict[str, Any]:
    """
    Phân tích định giá.

    Parameters
    ----------
    info:
        Dictionary từ:

            get_financial_data()

        trong src/vnstock_data.py.
    ticker:
        Mã cổ phiếu dùng cho Peer Valuation. Nếu bỏ trống, StockLens thử lấy
        từ ``info["ticker"]``.
    current_price:
        Giá thị trường hiện tại (VND/cp), dùng để tính upside/downside của
        Peer Fair Value. Không dùng để thay đổi Valuation Score lịch sử.

    Returns
    -------
    dict

    Output tương thích với:
        scoring.py
        app.py
        report.py
    """

    info = info or {}

    # Chuẩn hóa input bổ sung nhưng vẫn giữ tương thích với cách gọi cũ:
    #     analyze_valuation(financial_data)
    resolved_ticker = str(ticker or info.get("ticker") or "").strip().upper()
    if resolved_ticker.endswith(".VN"):
        resolved_ticker = resolved_ticker[:-3]

    current_price = _num(current_price)
    if current_price is None:
        current_price = _num(
            info.get("currentPrice")
            or info.get("current_price")
            or info.get("price")
        )

    # =====================================================
    # CURRENT DATA
    # =====================================================

    pe = _num(
        info.get(
            "trailingPE"
        )
    )

    pb = _num(
        info.get(
            "priceToBook"
        )
    )

    forward_pe = _num(
        info.get(
            "forwardPE"
        )
    )

    market_cap = _num(
        info.get(
            "marketCap"
        )
    )

    eps = _num(
        info.get(
            "trailingEps"
        )
    )

    bvps = _num(
        info.get(
            "bookValue"
        )
    )

    current_period = (
        info.get(
            "reportPeriod"
        )
    )

    # =====================================================
    # HISTORICAL DATA
    # =====================================================

    historical = (
        _extract_historical_multiples(
            info=info,
            current_period=current_period,
        )
    )

    pe_median = historical[
        "pe_median"
    ]

    pb_median = historical[
        "pb_median"
    ]

    # =====================================================
    # METRICS
    # =====================================================

    metrics = {

        "pe": pe,

        "pb": pb,

        "forward_pe": (
            forward_pe
        ),

        "market_cap": (
            market_cap
        ),

        "eps": eps,

        "bvps": bvps,

        "historical_pe_median": (
            pe_median
        ),

        "historical_pb_median": (
            pb_median
        ),

        "pe_vs_history": (
            pe / pe_median
            if (
                pe is not None
                and pe_median is not None
                and pe_median > 0
            )
            else None
        ),

        "pb_vs_history": (
            pb / pb_median
            if (
                pb is not None
                and pb_median is not None
                and pb_median > 0
            )
            else None
        ),
    }

    # =====================================================
    # INTERNAL VALUATION WEIGHTS
    # =====================================================
    #
    # Tổng = 100%
    #
    # Đây là trọng số nội bộ của Valuation Score.
    #
    # Sau đó scoring.py mới lấy:
    #
    # Valuation Score × 25%
    #
    # để đưa vào Investment Score.
    # =====================================================

    component_weights = {

        "pe_absolute": 0.30,

        "pb_absolute": 0.25,

        "pe_history": 0.25,

        "pb_history": 0.20,
    }

    # =====================================================
    # COMPONENT SCORES
    # =====================================================

    component_scores = {}

    positives = []
    observations = []
    risks = []

    # =====================================================
    # P/E ABSOLUTE
    # =====================================================

    pe_score = _score_pe(
        pe
    )

    if pe_score is not None:

        component_scores[
            "pe_absolute"
        ] = pe_score

        if pe_score >= 85:

            positives.append(
                f"P/E {_multiple_text(pe)} "
                "ở vùng tương đối thấp theo "
                "ngưỡng tham chiếu của StockLens."
            )

        elif pe_score >= 50:

            observations.append(
                f"P/E {_multiple_text(pe)} "
                "ở vùng trung bình theo "
                "ngưỡng tham chiếu của StockLens."
            )

        else:

            risks.append(
                f"P/E {_multiple_text(pe)} "
                "ở mức tương đối cao."
            )

    elif pe is not None and pe <= 0:

        observations.append(
            "P/E không dương nên không sử dụng "
            "để chấm điểm định giá."
        )

    # =====================================================
    # P/B ABSOLUTE
    # =====================================================

    pb_score = _score_pb(
        pb
    )

    if pb_score is not None:

        component_scores[
            "pb_absolute"
        ] = pb_score

        if pb_score >= 85:

            positives.append(
                f"P/B {_multiple_text(pb)} "
                "ở vùng tương đối thấp."
            )

        elif pb_score >= 50:

            observations.append(
                f"P/B {_multiple_text(pb)} "
                "ở vùng trung bình."
            )

        else:

            risks.append(
                f"P/B {_multiple_text(pb)} "
                "ở mức tương đối cao."
            )

    # =====================================================
    # P/E VS HISTORY
    # =====================================================

    pe_history_score = (
        _score_vs_history(
            current=pe,
            historical_median=pe_median,
        )
    )

    if pe_history_score is not None:

        component_scores[
            "pe_history"
        ] = pe_history_score

        relative = (
            pe
            / pe_median
        )

        difference = (
            relative - 1
        )

        if relative < 1:

            positives.append(
                f"P/E hiện tại {_multiple_text(pe)} "
                f"thấp hơn median lịch sử "
                f"{_multiple_text(pe_median)} "
                f"khoảng {abs(difference):.1%}."
            )

        elif relative <= 1.15:

            observations.append(
                f"P/E hiện tại {_multiple_text(pe)} "
                f"xấp xỉ median lịch sử "
                f"{_multiple_text(pe_median)}."
            )

        else:

            risks.append(
                f"P/E hiện tại {_multiple_text(pe)} "
                f"cao hơn median lịch sử "
                f"{_multiple_text(pe_median)} "
                f"khoảng {difference:.1%}."
            )

    # =====================================================
    # P/B VS HISTORY
    # =====================================================

    pb_history_score = (
        _score_vs_history(
            current=pb,
            historical_median=pb_median,
        )
    )

    if pb_history_score is not None:

        component_scores[
            "pb_history"
        ] = pb_history_score

        relative = (
            pb
            / pb_median
        )

        difference = (
            relative - 1
        )

        if relative < 1:

            positives.append(
                f"P/B hiện tại {_multiple_text(pb)} "
                f"thấp hơn median lịch sử "
                f"{_multiple_text(pb_median)} "
                f"khoảng {abs(difference):.1%}."
            )

        elif relative <= 1.15:

            observations.append(
                f"P/B hiện tại {_multiple_text(pb)} "
                f"xấp xỉ median lịch sử "
                f"{_multiple_text(pb_median)}."
            )

        else:

            risks.append(
                f"P/B hiện tại {_multiple_text(pb)} "
                f"cao hơn median lịch sử "
                f"{_multiple_text(pb_median)} "
                f"khoảng {difference:.1%}."
            )

    # =====================================================
    # WEIGHTED SCORE
    # =====================================================
    #
    # Chỉ tiêu thiếu dữ liệu:
    # - KHÔNG chấm 0
    # - Loại trọng số đó khỏi mẫu số
    # =====================================================

    weighted_points = 0.0
    available_weight = 0.0

    for (
        component,
        score_value,
    ) in component_scores.items():

        weight = (
            component_weights.get(
                component,
                0,
            )
        )

        weighted_points += (
            score_value
            * weight
        )

        available_weight += (
            weight
        )

    if available_weight > 0:

        score = round(
            weighted_points
            / available_weight,
            2,
        )

    else:

        score = None

    # =====================================================
    # COVERAGE
    # =====================================================

    coverage = len(
        component_scores
    )

    total_components = len(
        component_weights
    )

    coverage_ratio = (
        coverage
        / total_components
        if total_components
        else 0
    )

    # =====================================================
    # CLASSIFICATION
    # =====================================================

    classification = (
        _classification(
            score
        )
    )

    # =====================================================
    # COMMENTARY
    # =====================================================

    if score is not None:

        commentary = (
            f"Valuation Score đạt {score:.2f}/100, "
            f"xếp loại '{classification}'. "
            "Điểm định giá được xây dựng từ P/E, P/B "
            "hiện tại và so sánh với median lịch sử "
            "của chính doanh nghiệp. "
            f"Có {coverage}/{total_components} "
            "thành phần đủ dữ liệu."
        )

    else:

        commentary = (
            "Không đủ dữ liệu P/E/P/B hợp lệ "
            "để tính Valuation Score."
        )

    # =====================================================
    # PEER VALUATION - LỚP BỔ SUNG
    # =====================================================
    #
    # Quan trọng:
    # - Peer Score KHÔNG thay thế Valuation Score lịch sử ở trên.
    # - Peer Fair Value là giá trị hàm ý theo multiples của peers,
    #   KHÔNG được gán thành target_price.
    # - Lỗi/rate-limit của nguồn peer không làm hỏng toàn bộ StockLens.
    # =====================================================

    peer_valuation = {
        "data_available": False,
        "score": None,
        "classification": "Chưa đủ dữ liệu peer",
        "peer_fair_value": None,
        "upside_downside": None,
        "peer_median_pe": None,
        "peer_median_pb": None,
        "peers": [],
        "positives": [],
        "risks": [],
        "peer_quality_status": "Chưa đánh giá",
        "peer_quality_warnings": [],
        "commentary": "Chưa chạy Peer Valuation vì thiếu mã cổ phiếu.",
    }

    if resolved_ticker:
        try:
            try:
                # Khi chạy theo cấu trúc package: src.valuation
                from .peer_valuation import analyze_peer_valuation
            except ImportError:
                # Fallback khi chạy file trực tiếp trong một số môi trường test
                from peer_valuation import analyze_peer_valuation

            peer_valuation = analyze_peer_valuation(
                ticker=resolved_ticker,
                current_price=current_price,
                max_peers=5,
                financial_data=info,
                request_delay=2.0,
            ) or peer_valuation

        except BaseException as exc:
            # vnstock Community đôi lúc phát SystemExit khi rate-limit.
            # Không để lỗi peer làm hỏng phần định giá lịch sử/Investment Score.
            peer_valuation = {
                **peer_valuation,
                "commentary": (
                    "Peer Valuation tạm thời chưa khả dụng: "
                    f"{type(exc).__name__}: {exc}"
                ),
                "risks": [
                    "Không lấy được dữ liệu peer trong lần chạy này; "
                    "Valuation Score lịch sử vẫn được giữ nguyên."
                ],
            }

    peer_score = _num(peer_valuation.get("score"))
    peer_fair_value = _num(peer_valuation.get("peer_fair_value"))
    peer_upside_downside = _num(peer_valuation.get("upside_downside"))
    peer_median_pe = _num(peer_valuation.get("peer_median_pe"))
    peer_median_pb = _num(peer_valuation.get("peer_median_pb"))
    peer_implied_price_pe = _num(peer_valuation.get("implied_price_pe"))
    peer_implied_price_pb = _num(peer_valuation.get("implied_price_pb"))

    # =====================================================
    # OUTPUT
    # =====================================================

    return {

        # -----------------------------------------------
        # Main result
        # -----------------------------------------------

        "data_available": (
            score is not None
        ),

        "score": score,

        "classification": (
            classification
        ),

        # -----------------------------------------------
        # Metrics
        # -----------------------------------------------

        "metrics": metrics,

        # -----------------------------------------------
        # Compatibility with old app/report
        # -----------------------------------------------

        "pe": pe,

        "pb": pb,

        "forward_pe": (
            forward_pe
        ),

        "market_cap": (
            market_cap
        ),

        "eps": eps,

        "bvps": bvps,

        # -----------------------------------------------
        # Historical valuation
        # -----------------------------------------------

        "historical_pe": (
            historical[
                "pe_history"
            ]
        ),

        "historical_pb": (
            historical[
                "pb_history"
            ]
        ),

        "historical_pe_median": (
            pe_median
        ),

        "historical_pb_median": (
            pb_median
        ),

        # -----------------------------------------------
        # Peer valuation - bổ sung, không thay score gốc
        # -----------------------------------------------

        "peer_valuation": peer_valuation,

        "peer_score": peer_score,

        "peer_classification": peer_valuation.get("classification"),

        "peer_median_pe": peer_median_pe,

        "peer_median_pb": peer_median_pb,

        "peer_implied_price_pe": peer_implied_price_pe,

        "peer_implied_price_pb": peer_implied_price_pb,

        "peer_fair_value": peer_fair_value,

        "peer_upside_downside": peer_upside_downside,

        "peer_quality_status": peer_valuation.get("peer_quality_status"),

        "peer_quality_warnings": list(
            peer_valuation.get("peer_quality_warnings", []) or []
        ),

        "peer_list": list(
            peer_valuation.get("peers", []) or []
        ),

        "peer_positives": list(
            peer_valuation.get("positives", []) or []
        ),

        "peer_risks": list(
            peer_valuation.get("risks", []) or []
        ),

        "peer_commentary": peer_valuation.get("commentary"),

        # -----------------------------------------------
        # Scoring
        # -----------------------------------------------

        "component_scores": (
            component_scores
        ),

        "component_weights": (
            component_weights
        ),

        # -----------------------------------------------
        # Analysis
        # -----------------------------------------------

        "positives": positives,

        "observations": (
            observations
        ),

        "risks": risks,

        "commentary": (
            commentary
        ),

        # -----------------------------------------------
        # Coverage
        # -----------------------------------------------

        "coverage": coverage,

        "total_components": (
            total_components
        ),

        "coverage_ratio": round(
            coverage_ratio,
            4,
        ),

        # -----------------------------------------------
        # Company
        # -----------------------------------------------

        "ticker": (
            resolved_ticker
            or info.get("ticker")
        ),

        "company_name": (
            info.get(
                "name"
            )
        ),

        "report_period": (
            info.get(
                "reportPeriod"
            )
        ),

        # -----------------------------------------------
        # Không bịa giá mục tiêu
        # -----------------------------------------------

        "fair_value": None,

        "target_price": None,

        # -----------------------------------------------
        # Source
        # -----------------------------------------------

        "source": (
            "vnstock - dữ liệu tài chính KBS"
        ),

        "method_note": (
            "Valuation Score sử dụng P/E hiện tại 30%, "
            "P/B hiện tại 25%, P/E so với median lịch sử "
            "25% và P/B so với median lịch sử 20%. "
            "Các ngưỡng là heuristic do StockLens thiết kế. "
            "Chỉ tiêu thiếu dữ liệu được loại khỏi mẫu số. "
            "Peer Valuation được hiển thị như một lớp định giá tương đối bổ sung "
            "và không thay thế Valuation Score lịch sử. Peer Fair Value chỉ là "
            "giá trị hàm ý theo multiples của doanh nghiệp cùng ngành, không phải "
            "target price hay mô hình giá trị nội tại."
        ),
    }