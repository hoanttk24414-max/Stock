"""
StockLens - News & Sentiment Analysis

Nguồn:
    Google News RSS

Mục tiêu:
    - Tìm tin liên quan trực tiếp đến cổ phiếu/doanh nghiệp
    - Loại tin trùng và false positive
    - Phân loại:
        Positive
        Neutral
        Negative
    - Tin mới có trọng số cao hơn
    - Tính News Score / 100

News Score chiếm:
    15% Investment Score

Lưu ý:
    Sentiment được suy ra từ tiêu đề bằng bộ từ khóa
    heuristic của StockLens.
    Không phải phân tích toàn văn bài báo.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import quote

import feedparser


# =========================================================
# 1. POSITIVE KEYWORDS
# =========================================================

POSITIVE_TERMS = (
    # -----------------------------------------------------
    # Kết quả kinh doanh
    # -----------------------------------------------------

    "lợi nhuận tăng",
    "lãi tăng",
    "lãi lớn",
    "lợi nhuận cao",
    "tăng trưởng",
    "tăng mạnh",
    "tăng tốc",
    "bứt phá",
    "khởi sắc",
    "phục hồi",
    "hồi phục",
    "hồi phục mạnh",
    "vượt kế hoạch",
    "vượt kỳ vọng",
    "vượt dự báo",
    "kỷ lục",
    "cao kỷ lục","được khuyến nghị", 
    "khuyến nghị tích cực",
    "khuyến nghị khả quan",

    # -----------------------------------------------------
    # Doanh nghiệp
    # -----------------------------------------------------

    "mở rộng",
    "ký hợp đồng",
    "hợp đồng lớn",
    "trúng thầu",
    "đơn hàng mới",
    "tăng công suất",
    "mở nhà máy",
    "hợp tác chiến lược",

    # -----------------------------------------------------
    # Chứng khoán
    # -----------------------------------------------------

    "mua ròng",
    "được mua ròng",
    "khuyến nghị mua",
    "nâng khuyến nghị",
    "nâng giá mục tiêu",
    "nâng hạng",
    "tăng giá",
    "tăng trần",
    "dòng tiền vào",

    "hấp dẫn",
    "định giá hấp dẫn",

    "chấm dứt chuỗi ngày giảm",
    "chấm dứt chuỗi giảm",
    "chấm dứt chuỗi phiên giảm",

    "tăng trở lại",
    "đảo chiều tăng",

    # -----------------------------------------------------
    # English
    # -----------------------------------------------------

    "record profit",
    "profit rises",
    "profit growth",
    "revenue growth",
    "strong growth",
    "upgrade",
    "buy rating",
)


# =========================================================
# 2. NEGATIVE KEYWORDS
# =========================================================

NEGATIVE_TERMS = (
    # -----------------------------------------------------
    # Kết quả kinh doanh
    # -----------------------------------------------------

    "thua lỗ",
    "báo lỗ",
    "lỗ lớn",
    "lợi nhuận giảm",
    "lãi giảm",
    "sụt giảm",
    "doanh thu giảm",
    "tạm lỗ", 
    "đang lỗ", 
    "lỗ gần", 
    "lỗ hơn",
    "quay lưng",
    "nhà đầu tư quay lưng",

    # -----------------------------------------------------
    # Diễn biến giá
    # -----------------------------------------------------

    "giảm mạnh",
    "giảm điểm",
    "giảm giá",
    "lao dốc",
    "tụt giảm",
    "giảm liên tiếp",
    "giảm nhiều phiên",
    "giảm 10 phiên",
    "chuỗi ngày giảm",
    "chuỗi phiên giảm",
    "chuỗi giảm",

    "giảm sàn",
    "bán tháo",
    "bị bán tháo",
    "mất giá",

    "bốc hơi",
    "mất vốn hóa",
    "thủng mốc",

    # -----------------------------------------------------
    # Chỉ số / rổ cổ phiếu
    # -----------------------------------------------------

    "rơi khỏi",
    "rời rổ",
    "nguy cơ rời",
    "nguy cơ bị loại",

    # -----------------------------------------------------
    # Dòng tiền
    # -----------------------------------------------------

    "bán ròng",
    "bị bán mạnh",
    "áp lực bán",
    "chịu áp lực",

    # -----------------------------------------------------
    # Doanh nghiệp / pháp lý
    # -----------------------------------------------------

    "nợ xấu",
    "rủi ro",
    "vi phạm",
    "xử phạt",
    "bị phạt",
    "điều tra",
    "khởi tố",
    "gian lận",
    "chậm thanh toán",
    "mất khả năng thanh toán",
    "vỡ nợ",

    # -----------------------------------------------------
    # Khuyến nghị
    # -----------------------------------------------------

    "hạ khuyến nghị",
    "hạ giá mục tiêu",
    "hạ dự báo",
    "cảnh báo",

    # -----------------------------------------------------
    # English
    # -----------------------------------------------------

    "loss",
    "profit falls",
    "profit decline",
    "downgrade",
    "fraud",
    "investigation",
)


# =========================================================
# 3. COMPANY NAME FILTER
# =========================================================

STOP_WORDS = {
    "cong",
    "ty",
    "co",
    "phan",
    "tap",
    "doan",
    "tong",
    "ctcp",
    "tnhh",

    "corporation",
    "joint",
    "stock",
    "company",
    "group",
    "holdings",
    "holding",
    "jsc",
    "ltd",
    "limited",
}


def normalize_ticker(
    ticker: str,
) -> str:
    """
    Chuẩn hóa mã cổ phiếu.

    FPT
    fpt
    FPT.VN

    -> FPT
    """

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


def _company_tokens(
    company_name: str,
) -> set[str]:

    raw = re.findall(
        r"[A-Za-zÀ-ỹ0-9]+",
        company_name or "",
        flags=re.UNICODE,
    )

    result = set()

    for token in raw:

        value = (
            token
            .strip()
            .lower()
        )

        if (
            len(value) >= 3
            and value not in STOP_WORDS
        ):
            result.add(value)

    return result


# =========================================================
# 4. TEXT HELPERS
# =========================================================

def _normalize_text(
    text: str,
) -> str:

    text = str(
        text or ""
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def _normalize_title_key(
    title: str,
) -> str:

    title = (
        _normalize_text(
            title
        )
        .lower()
    )

    title = re.sub(
        r"[^\wÀ-ỹ]+",
        " ",
        title,
        flags=re.UNICODE,
    )

    return re.sub(
        r"\s+",
        " ",
        title,
    ).strip()


# =========================================================
# 5. FALSE POSITIVE FILTER
# =========================================================

def _is_false_positive(
    ticker: str,
    title: str,
) -> bool:
    """
    Loại các tiêu đề có ticker nhưng thực chất
    đang nói về một pháp nhân khác.

    Có thể mở rộng thêm khi nhóm test mã khác.
    """

    text = (
        title.lower()
    )

    # -----------------------------------------------------
    # FPT Corporation != FPT Securities
    # -----------------------------------------------------

    if ticker == "FPT":

        exclusion_terms = (
            "fpt securities",
            "chứng khoán fpt",
            "ctcp chứng khoán fpt",
            "công ty chứng khoán fpt",
            "fpts",
        )

        if any(
            term in text
            for term in exclusion_terms
        ):
            return True

    return False


# =========================================================
# 6. RELEVANCE
# =========================================================

def _contains_exact_token(
    text: str,
    token: str,
) -> bool:

    pattern = (
        rf"(?<![A-Za-z0-9])"
        rf"{re.escape(token)}"
        rf"(?![A-Za-z0-9])"
    )

    return bool(
        re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )
    )


def _relevance_score(
    title: str,
    ticker: str,
    company_name: str,
) -> int:
    """
    3:
        Có ticker trực tiếp.

    2:
        Match >= 2 token tên doanh nghiệp.

    1:
        Match 1 token.

    0:
        Không đủ liên quan.
    """

    text = (
        title.lower()
    )

    if _contains_exact_token(
        text,
        ticker.lower(),
    ):
        return 3

    tokens = _company_tokens(
        company_name
    )

    matched = 0

    for token in tokens:

        if _contains_exact_token(
            text,
            token,
        ):
            matched += 1

    if matched >= 2:
        return 2

    if matched == 1:
        return 1

    return 0


# =========================================================
# 7. SENTIMENT
# =========================================================

def _term_count(
    text: str,
    terms,
) -> int:

    text = (
        text.lower()
    )

    count = 0

    for term in terms:

        if term.lower() in text:
            count += 1

    return count


def _find_terms(
    text: str,
    terms,
) -> list[str]:

    text = (
        text.lower()
    )

    found = []

    for term in terms:

        if term.lower() in text:
            found.append(term)

    return found


def _classify_sentiment(
    title: str,
) -> dict[str, Any]:
    """
    Nếu tiêu đề chứa cả tín hiệu tích cực và tiêu cực:
        -> Neutral / Mixed

    Ví dụ:
        "FPT hấp dẫn nhưng đối mặt rủi ro..."
        -> Neutral
    """

    text = (
        _normalize_text(
            title
        )
        .lower()
    )

    positive_terms = _find_terms(
        text,
        POSITIVE_TERMS,
    )

    negative_terms = _find_terms(
        text,
        NEGATIVE_TERMS,
    )

    positive_hits = len(
        positive_terms
    )

    negative_hits = len(
        negative_terms
    )

    # =====================================================
    # MIXED
    # =====================================================

    if (
        positive_hits > 0
        and negative_hits > 0
    ):

        sentiment = "Neutral"

        base_score = 50

        sentiment_reason = (
            "mixed"
        )

    # =====================================================
    # POSITIVE
    # =====================================================

    elif positive_hits > 0:

        sentiment = "Positive"

        base_score = 75

        sentiment_reason = (
            "positive_keywords"
        )

    # =====================================================
    # NEGATIVE
    # =====================================================

    elif negative_hits > 0:

        sentiment = "Negative"

        base_score = 25

        sentiment_reason = (
            "negative_keywords"
        )

    # =====================================================
    # NO SIGNAL
    # =====================================================

    else:

        sentiment = "Neutral"

        base_score = 50

        sentiment_reason = (
            "no_clear_signal"
        )

    return {
        "sentiment": (
            sentiment
        ),

        "score": (
            base_score
        ),

        "positive_hits": (
            positive_hits
        ),

        "negative_hits": (
            negative_hits
        ),

        "positive_terms": (
            positive_terms
        ),

        "negative_terms": (
            negative_terms
        ),

        "reason": (
            sentiment_reason
        ),
    }


# =========================================================
# 8. DATE
# =========================================================

def _parse_published(
    value: str,
) -> datetime | None:

    if not value:
        return None

    try:

        dt = (
            parsedate_to_datetime(
                value
            )
        )

        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:
        return None


def _days_old(
    published_dt: datetime | None,
) -> float | None:

    if published_dt is None:
        return None

    now = datetime.now(
        timezone.utc
    )

    delta = (
        now - published_dt
    )

    return max(
        0.0,
        delta.total_seconds()
        / 86400,
    )


def _recency_weight(
    days: float | None,
) -> float:
    """
    Tin càng mới -> trọng số càng cao.
    """

    if days is None:
        return 0.50

    if days <= 7:
        return 1.00

    if days <= 30:
        return 0.85

    if days <= 60:
        return 0.70

    if days <= 120:
        return 0.55

    return 0.40


# =========================================================
# 9. GOOGLE NEWS QUERY
# =========================================================

def _build_query(
    ticker: str,
    company_name: str,
) -> str:

    if (
        company_name
        and company_name.strip()
        and company_name.strip().upper()
        != ticker
    ):

        return (
            f'("{ticker}" OR '
            f'"{company_name.strip()}") '
            f'(cổ phiếu OR chứng khoán '
            f'OR doanh nghiệp OR đầu tư)'
        )

    return (
        f'"{ticker}" '
        f'(cổ phiếu OR chứng khoán '
        f'OR doanh nghiệp OR đầu tư)'
    )


def _google_news_url(
    query: str,
) -> str:

    return (
        "https://news.google.com/"
        "rss/search?q="
        + quote(query)
        + "&hl=vi"
        + "&gl=VN"
        + "&ceid=VN:vi"
    )


# =========================================================
# 10. SOURCE
# =========================================================

def _get_source_name(
    entry,
) -> str:

    source = entry.get(
        "source"
    )

    if isinstance(
        source,
        dict,
    ):

        title = source.get(
            "title"
        )

        if title:

            return (
                _normalize_text(
                    title
                )
            )

    return ""


# =========================================================
# 11. NEWS CLASSIFICATION
# =========================================================

def _classification(
    score: float | None,
) -> str:

    if score is None:
        return "Không đủ dữ liệu"

    if score >= 65:
        return "Tin tức tương đối tích cực"

    if score >= 45:
        return "Tin tức trung tính"

    return "Tin tức cần thận trọng"


# =========================================================
# 12. EMPTY RESULT
# =========================================================

def _empty_result(
    ticker: str,
    query: str,
    message: str,
) -> dict[str, Any]:

    return {

        "ticker": ticker,

        "data_available": False,

        "score": None,

        "classification": (
            "Không đủ dữ liệu"
        ),

        "items": [],

        "positives": [],

        "observations": [],

        "risks": [],

        "sentiment_counts": {
            "Positive": 0,
            "Neutral": 0,
            "Negative": 0,
        },

        "article_count": 0,

        "query": query,

        "commentary": message,

        "source": (
            "Google News RSS"
        ),

        "method_note": (
            "Không nội suy News Score khi "
            "không có đủ tin liên quan."
        ),
    }


# =========================================================
# 13. MAIN
# =========================================================

def analyze_news(
    ticker: str,
    company_name: str = "",
    max_items: int = 10,
    max_age_days: int = 120,
) -> dict[str, Any]:

    ticker = normalize_ticker(
        ticker
    )

    company_name = (
        company_name
        or ""
    ).strip()

    max_items = max(
        1,
        min(
            int(max_items),
            20,
        ),
    )

    max_age_days = max(
        1,
        int(max_age_days),
    )

    # =====================================================
    # QUERY
    # =====================================================

    query = _build_query(
        ticker=ticker,
        company_name=company_name,
    )

    url = _google_news_url(
        query
    )

    # =====================================================
    # FETCH RSS
    # =====================================================

    try:

        feed = feedparser.parse(
            url,

            request_headers={
                "User-Agent": (
                    "StockLens/3.0 "
                    "Educational Equity Research"
                )
            },
        )

    except Exception as exc:

        return _empty_result(
            ticker=ticker,
            query=query,
            message=(
                "Không truy cập được "
                "Google News RSS: "
                f"{type(exc).__name__}."
            ),
        )

    entries = getattr(
        feed,
        "entries",
        [],
    )

    if not entries:

        return _empty_result(
            ticker=ticker,
            query=query,
            message=(
                f"Không tìm thấy tin phù hợp "
                f"cho {ticker}."
            ),
        )

    # =====================================================
    # FILTER
    # =====================================================

    items = []

    seen_titles = set()

    for entry in entries[:100]:

        title = _normalize_text(
            entry.get(
                "title",
                ""
            )
        )

        if not title:
            continue

        # -------------------------------------------------
        # Duplicate
        # -------------------------------------------------

        title_key = (
            _normalize_title_key(
                title
            )
        )

        if (
            not title_key
            or title_key in seen_titles
        ):
            continue

        # -------------------------------------------------
        # False positive
        # -------------------------------------------------

        if _is_false_positive(
            ticker=ticker,
            title=title,
        ):
            continue

        # -------------------------------------------------
        # Relevance
        # -------------------------------------------------

        relevance = (
            _relevance_score(
                title=title,
                ticker=ticker,
                company_name=company_name,
            )
        )

        if relevance <= 0:
            continue

        # -------------------------------------------------
        # Date
        # -------------------------------------------------

        published_raw = (
            entry.get(
                "published",
                ""
            )
            or entry.get(
                "updated",
                ""
            )
        )

        published_dt = (
            _parse_published(
                published_raw
            )
        )

        days = _days_old(
            published_dt
        )

        if (
            days is not None
            and days > max_age_days
        ):
            continue

        # -------------------------------------------------
        # Sentiment
        # -------------------------------------------------

        sentiment_data = (
            _classify_sentiment(
                title
            )
        )

        sentiment = (
            sentiment_data[
                "sentiment"
            ]
        )

        sentiment_score = (
            sentiment_data[
                "score"
            ]
        )

        # -------------------------------------------------
        # Recency
        # -------------------------------------------------

        recency_weight = (
            _recency_weight(
                days
            )
        )

        # -------------------------------------------------
        # Relevance weight
        # -------------------------------------------------

        if relevance >= 3:

            relevance_weight = 1.00

        elif relevance == 2:

            relevance_weight = 0.90

        else:

            relevance_weight = 0.80

        final_weight = (
            recency_weight
            * relevance_weight
        )

        # -------------------------------------------------
        # Published
        # -------------------------------------------------

        if published_dt is not None:

            published_iso = (
                published_dt
                .date()
                .isoformat()
            )

        else:

            published_iso = None

        # -------------------------------------------------
        # Save
        # -------------------------------------------------

        seen_titles.add(
            title_key
        )

        items.append(
            {
                "title": title,

                "link": (
                    entry.get(
                        "link",
                        ""
                    )
                ),

                "published": (
                    published_iso
                    or published_raw
                    or "Không rõ ngày"
                ),

                "published_raw": (
                    published_raw
                ),

                "published_iso": (
                    published_iso
                ),

                "source_name": (
                    _get_source_name(
                        entry
                    )
                ),

                "sentiment": (
                    sentiment
                ),

                "sentiment_score": (
                    sentiment_score
                ),

                "positive_hits": (
                    sentiment_data[
                        "positive_hits"
                    ]
                ),

                "negative_hits": (
                    sentiment_data[
                        "negative_hits"
                    ]
                ),

                "positive_terms": (
                    sentiment_data[
                        "positive_terms"
                    ]
                ),

                "negative_terms": (
                    sentiment_data[
                        "negative_terms"
                    ]
                ),

                "sentiment_reason": (
                    sentiment_data[
                        "reason"
                    ]
                ),

                "relevance_score": (
                    relevance
                ),

                "days_old": (
                    None
                    if days is None
                    else round(
                        days,
                        1,
                    )
                ),

                "weight": round(
                    final_weight,
                    4,
                ),
            }
        )

        if len(items) >= max_items:
            break

    # =====================================================
    # NO NEWS
    # =====================================================

    if not items:

        return _empty_result(
            ticker=ticker,
            query=query,
            message=(
                f"Không có đủ tiêu đề tin tức "
                f"liên quan trực tiếp đến {ticker} "
                f"trong {max_age_days} ngày."
            ),
        )

    # =====================================================
    # CALCULATE SCORE
    # =====================================================

    weighted_score = 0.0

    total_weight = 0.0

    for item in items:

        weight = float(
            item[
                "weight"
            ]
        )

        weighted_score += (
            item[
                "sentiment_score"
            ]
            * weight
        )

        total_weight += weight

    if total_weight > 0:

        score = round(
            weighted_score
            / total_weight,
            2,
        )

    else:

        score = None

    # =====================================================
    # SENTIMENT COUNTS
    # =====================================================

    counts = {
        "Positive": 0,
        "Neutral": 0,
        "Negative": 0,
    }

    for item in items:

        sentiment = (
            item.get(
                "sentiment"
            )
        )

        if sentiment in counts:

            counts[
                sentiment
            ] += 1

    # =====================================================
    # INSIGHTS
    # =====================================================

    positives = [
        item["title"]
        for item in items
        if item["sentiment"]
        == "Positive"
    ][:3]

    risks = [
        item["title"]
        for item in items
        if item["sentiment"]
        == "Negative"
    ][:3]

    observations = [
        item["title"]
        for item in items
        if item["sentiment"]
        == "Neutral"
    ][:3]

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
            f"News Score đạt {score:.2f}/100 từ "
            f"{len(items)} tiêu đề liên quan đến {ticker}. "
            f"Trong đó có "
            f"{counts['Positive']} tin tích cực, "
            f"{counts['Neutral']} tin trung tính và "
            f"{counts['Negative']} tin tiêu cực. "
            "Tin mới và tin có mã cổ phiếu xuất hiện "
            "trực tiếp trong tiêu đề được ưu tiên trọng số. "
            "Tiêu đề đồng thời chứa tín hiệu tốt và xấu "
            "được xếp Neutral."
        )

    else:

        commentary = (
            "Không đủ dữ liệu để tính News Score."
        )

    # =====================================================
    # OUTPUT
    # =====================================================

    return {

        "ticker": ticker,

        "data_available": (
            score is not None
        ),

        "score": score,

        "classification": (
            classification
        ),

        "items": items,

        "positives": (
            positives
        ),

        "observations": (
            observations
        ),

        "risks": risks,

        "sentiment_counts": (
            counts
        ),

        "article_count": (
            len(items)
        ),

        "query": query,

        "max_age_days": (
            max_age_days
        ),

        "commentary": (
            commentary
        ),

        "source": (
            "Google News RSS"
        ),

        "method_note": (
            "News Score là sentiment heuristic dựa trên "
            "tiêu đề. Positive = 75 điểm, Neutral = 50 điểm, "
            "Negative = 25 điểm. Tin mới và tin liên quan "
            "trực tiếp được đặt trọng số cao hơn. "
            "Tiêu đề chứa đồng thời tín hiệu tích cực và "
            "tiêu cực được xếp Neutral. "
            "StockLens không giả định đã phân tích toàn văn "
            "bài báo."
        ),
    }


# =========================================================
# 14. TEST
# =========================================================

if __name__ == "__main__":

    print(
        "===== STOCKLENS - NEWS ANALYSIS TEST ====="
    )

    try:

        result = analyze_news(
            ticker="FPT",
            company_name="FPT",
            max_items=10,
            max_age_days=120,
        )

        print()
        print(
            "Ticker:",
            result.get(
                "ticker"
            ),
        )

        print(
            "Source:",
            result.get(
                "source"
            ),
        )

        print(
            "News Score:",
            result.get(
                "score"
            ),
        )

        print(
            "Classification:",
            result.get(
                "classification"
            ),
        )

        print(
            "Article Count:",
            result.get(
                "article_count",
                0,
            ),
        )

        print(
            "Sentiment Counts:",
            result.get(
                "sentiment_counts"
            ),
        )

        print()

        print(
            "Commentary:"
        )

        print(
            result.get(
                "commentary"
            )
        )

        print()

        print(
            "NEWS:"
        )

        for index, item in enumerate(
            result.get(
                "items",
                []
            ),
            start=1,
        ):

            print()

            print(
                f"{index}. "
                f"[{item.get('sentiment')}] "
                f"{item.get('title')}"
            )

            print(
                "   Date:",
                item.get(
                    "published"
                ),
            )

            print(
                "   Source:",
                item.get(
                    "source_name"
                )
                or "N/A",
            )

            print(
                "   Positive terms:",
                item.get(
                    "positive_terms"
                ),
            )

            print(
                "   Negative terms:",
                item.get(
                    "negative_terms"
                ),
            )

            print(
                "   Weight:",
                item.get(
                    "weight"
                ),
            )

        print()

        if result.get(
            "data_available"
        ):

            print(
                "news analysis test: OK"
            )

        else:

            print(
                "WARNING: "
                "Không đủ dữ liệu để tính News Score."
            )

    except Exception as exc:

        print()

        print(
            "ERROR:"
        )

        print(exc)