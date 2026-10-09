# src/report.py
# -*- coding: utf-8 -*-
"""StockLens - 8-page equity research PDF report.

Public API kept compatible with the current Streamlit app::

    generate_pdf(
        ticker,
        period_text,
        results,
        summary,
        sections,
        profile,
        company_info=company,
    ) -> bytes

The full report is designed as an 8-page A4 portrait research note:
    1. Research snapshot
    2. Technical analysis: Price+MA, RSI, MACD, Volume
    3. Market risk & drawdown
    4. Financial performance: Revenue/LNST, ROE/ROA
    5. Balance sheet & financial health: Assets/Equity + history table
    6. Valuation: historical + peer comparison + news sentiment
    7. Investment Score & investor profiles
    8. Financial-statement appendix + methodology / disclaimer

Data sources expected by the project:
    - DNSE OpenAPI: OHLCV
    - vnstock/KBS: financial statements and ratios
    - Google News RSS: news headlines/sentiment
    - StockLens: Technical/Fundamental/Valuation/Risk/Investment Score

Important:
    - No hard-coded ticker/company.
    - Missing values are shown as N/A; the report does not fabricate target price
      or peer multiples. Peer Fair Value / upside-downside are shown only when a
      usable same-industry peer set is available.
    - If ``financial_data`` is not passed, the module attempts to load it from
      ``src.vnstock_data.get_financial_data`` so the existing app.py does not
      need to change.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import math
import os
import urllib.request

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# =============================================================================
# 1. VISUAL SYSTEM
# =============================================================================
PAGE_W, PAGE_H = A4
LEFT = RIGHT = 12 * mm
TOP = 17 * mm
BOTTOM = 13 * mm
CONTENT_W = PAGE_W - LEFT - RIGHT

NAVY = colors.HexColor("#0B2B55")
BLUE = colors.HexColor("#1368D7")
BLUE_2 = colors.HexColor("#2D83E6")
SKY = colors.HexColor("#EAF4FF")
TEAL = colors.HexColor("#13B8A6")
GREEN = colors.HexColor("#13A86B")
GREEN_BG = colors.HexColor("#E9F8F1")
AMBER = colors.HexColor("#E7951A")
AMBER_BG = colors.HexColor("#FFF3DF")
RED = colors.HexColor("#D94F4F")
RED_BG = colors.HexColor("#FDEBEC")
PURPLE = colors.HexColor("#7868D8")
TEXT = colors.HexColor("#1C2E45")
MUTED = colors.HexColor("#64758A")
LINE = colors.HexColor("#DDE6EF")
BG = colors.HexColor("#F6F9FC")
WHITE = colors.white
PAGE_BG = colors.HexColor("#F8FCFF")
PAGE_SKY = colors.HexColor("#EAF5FF")
PAGE_SKY_2 = colors.HexColor("#DCEFFF")
PAGE_MINT = colors.HexColor("#EAFBF7")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
LOGO_DIR = ASSETS_DIR / "logos"
COMPANY_IMAGE_DIR = ASSETS_DIR / "company_images"


def _register_fonts() -> Tuple[str, str]:
    """Prefer Times New Roman on Windows; fall back to a Times-compatible serif."""
    candidates = [
        # Windows - user's target environment
        ("C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/timesbd.ttf"),
        # Linux / container - serif fallbacks for verification only
        ("/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
    ]
    for normal, bold in candidates:
        if os.path.exists(normal):
            try:
                pdfmetrics.registerFont(TTFont("StockLensTimes", normal))
                if os.path.exists(bold):
                    pdfmetrics.registerFont(TTFont("StockLensTimesBold", bold))
                    return "StockLensTimes", "StockLensTimesBold"
                return "StockLensTimes", "StockLensTimes"
            except Exception:
                pass
    return "Times-Roman", "Times-Bold"


FONT, FONT_BOLD = _register_fonts()

styles = getSampleStyleSheet()
STYLE_TITLE = ParagraphStyle(
    "SLTitle", parent=styles["Title"], fontName=FONT_BOLD, fontSize=22,
    leading=25, textColor=NAVY, alignment=TA_LEFT, spaceAfter=1.5 * mm,
)
STYLE_SUBTITLE = ParagraphStyle(
    "SLSubtitle", parent=styles["BodyText"], fontName=FONT, fontSize=10,
    leading=13, textColor=MUTED, alignment=TA_LEFT,
)
STYLE_H1 = ParagraphStyle(
    "SLH1", parent=styles["Heading1"], fontName=FONT_BOLD, fontSize=20,
    leading=23, textColor=NAVY, spaceAfter=1.5 * mm,
)
STYLE_H2 = ParagraphStyle(
    "SLH2", parent=styles["Heading2"], fontName=FONT_BOLD, fontSize=14,
    leading=17, textColor=NAVY, spaceAfter=1 * mm,
)
STYLE_BODY = ParagraphStyle(
    "SLBody", parent=styles["BodyText"], fontName=FONT, fontSize=10.4,
    leading=14.0, textColor=TEXT,
)
STYLE_SMALL = ParagraphStyle(
    "SLSmall", parent=STYLE_BODY, fontSize=9.6, leading=12.6, textColor=MUTED,
)
STYLE_TINY = ParagraphStyle(
    "SLTiny", parent=STYLE_BODY, fontSize=8.8, leading=11.2, textColor=MUTED,
)
STYLE_CENTER = ParagraphStyle(
    "SLCenter", parent=STYLE_BODY, alignment=TA_CENTER, fontSize=9.7, leading=12.2,
)
STYLE_RIGHT = ParagraphStyle(
    "SLRight", parent=STYLE_BODY, alignment=TA_RIGHT, fontSize=9.7, leading=12.2,
)
STYLE_CARD_LABEL = ParagraphStyle(
    "SLCardLabel", parent=STYLE_SMALL, fontName=FONT_BOLD, fontSize=9.2,
    textColor=MUTED, leading=11.0,
)
STYLE_CARD_VALUE = ParagraphStyle(
    "SLCardValue", parent=STYLE_BODY, fontName=FONT_BOLD, fontSize=17,
    leading=19, textColor=NAVY,
)

_MPL_FONT = "Times New Roman" if os.path.exists("C:/Windows/Fonts/times.ttf") else "Liberation Serif"
plt.rcParams.update({
    "font.family": _MPL_FONT,
    "font.size": 11,
    "axes.titlesize": 14,
    "axes.labelsize": 10.5,
    "legend.fontsize": 9.5,
    "xtick.labelsize": 9.5,
    "ytick.labelsize": 9.5,
    "axes.edgecolor": "#DDE6EF",
    "axes.labelcolor": "#5C6F84",
    "xtick.color": "#6A7B91",
    "ytick.color": "#6A7B91",
    "text.color": "#1C2E45",
    "figure.facecolor": "#FBFDFF",
    "axes.facecolor": "#FBFDFF",
})


# =============================================================================
# 2. GENERIC HELPERS
# =============================================================================
def _esc(value: Any) -> str:
    import html
    return html.escape(str("" if value is None else value))


def _finite(value: Any) -> Optional[float]:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _fmt_num(value: Any, digits: int = 1, suffix: str = "") -> str:
    v = _finite(value)
    return "N/A" if v is None else f"{v:,.{digits}f}{suffix}"


def _fmt_price(value: Any) -> str:
    v = _finite(value)
    return "N/A" if v is None else f"{v:,.0f} VND"


def _fmt_money(value: Any) -> str:
    v = _finite(value)
    if v is None:
        return "N/A"
    av = abs(v)
    if av >= 1e12:
        return f"{v / 1e12:,.1f} nghìn tỷ VND"
    if av >= 1e9:
        return f"{v / 1e9:,.1f} tỷ VND"
    if av >= 1e6:
        return f"{v / 1e6:,.1f} triệu VND"
    return f"{v:,.0f} VND"


def _fmt_billion(value: Any, digits: int = 1) -> str:
    v = _finite(value)
    return "N/A" if v is None else f"{v / 1e9:,.{digits}f}"


def _fmt_pct(value: Any, digits: int = 1, ratio: bool = True) -> str:
    v = _finite(value)
    if v is None:
        return "N/A"
    if ratio:
        v *= 100
    return f"{v:.{digits}f}%"


def _fmt_x(value: Any, digits: int = 2) -> str:
    v = _finite(value)
    return "N/A" if v is None else f"{v:.{digits}f}x"


def _P(text: Any, style: ParagraphStyle = STYLE_BODY) -> Paragraph:
    return Paragraph(_esc(text), style)


def _Phtml(text: str, style: ParagraphStyle = STYLE_BODY) -> Paragraph:
    return Paragraph(text, style)


def _score_label(score: Any) -> str:
    v = _finite(score)
    if v is None:
        return "Chưa đủ dữ liệu"
    if v >= 80:
        return "Cơ hội cao"
    if v >= 65:
        return "Tích cực"
    if v >= 50:
        return "Trung lập"
    return "Thận trọng"


def _score_color(score: Any):
    v = _finite(score)
    if v is None:
        return MUTED
    if v >= 65:
        return GREEN
    if v >= 50:
        return AMBER
    return RED


def _get_score(result: Dict[str, Any]) -> Optional[float]:
    if not isinstance(result, dict):
        return None
    return _finite(result.get("score", result.get("investment_score")))


def _company_name(company: Dict[str, Any], financial: Dict[str, Any], ticker: str) -> str:
    return (
        company.get("name")
        or company.get("company_name")
        or financial.get("name")
        or financial.get("companyName")
        or ticker
    )


def _financial_history(financial: Dict[str, Any]) -> List[Dict[str, Any]]:
    history = (
        financial.get("financialHistory")
        or financial.get("financial_history")
        or []
    )
    rows = [x for x in history if isinstance(x, dict)]
    def key(row: Dict[str, Any]) -> int:
        try:
            return int(str(row.get("period", 0))[:4])
        except Exception:
            return 0
    return sorted(rows, key=key)


def _technical_df(results: Dict[str, Any]) -> pd.DataFrame:
    technical = results.get("technical", {}) or {}
    df = technical.get("data")
    if not isinstance(df, pd.DataFrame):
        return pd.DataFrame()
    out = df.copy()
    if "Date" in out.columns:
        out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
        out = out.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    return out


def _latest_market_stats(df: pd.DataFrame) -> Dict[str, Any]:
    if df is None or df.empty or "Close" not in df.columns:
        return {
            "close": None, "change": None, "pct_change": None,
            "volume": None, "high_52w": None, "low_52w": None,
        }
    tmp = df.sort_values("Date").reset_index(drop=True) if "Date" in df.columns else df.reset_index(drop=True)
    close = _finite(tmp.iloc[-1].get("Close"))
    prev = _finite(tmp.iloc[-2].get("Close")) if len(tmp) >= 2 else None
    change = None if close is None or prev is None else close - prev
    pct = None if change is None or prev in (None, 0) else change / prev
    last_252 = tmp.tail(252)
    high = _finite(last_252["High"].max()) if "High" in last_252.columns else _finite(last_252["Close"].max())
    low = _finite(last_252["Low"].min()) if "Low" in last_252.columns else _finite(last_252["Close"].min())
    vol = _finite(tmp.iloc[-1].get("Volume")) if "Volume" in tmp.columns else None
    return {"close": close, "change": change, "pct_change": pct, "volume": vol, "high_52w": high, "low_52w": low}


def _load_financial_data(ticker: str) -> Dict[str, Any]:
    try:
        from src.vnstock_data import get_financial_data
        return get_financial_data(str(ticker).strip().upper(), period="year") or {}
    except Exception:
        return {}


def _normalize_sections(sections: Optional[Iterable[str]]) -> set[str]:
    """Chuẩn hóa các phần người dùng chọn trên giao diện.

    ``sections is None`` nghĩa là tạo báo cáo đầy đủ. Danh sách rỗng nghĩa là
    chỉ giữ trang Research Snapshot. Các key hợp lệ: technical, fundamental,
    valuation, news, score, method.
    """
    allowed = {"technical", "fundamental", "valuation", "news", "score", "method"}
    if sections is None:
        return allowed.copy()
    return {
        str(x).strip().lower()
        for x in sections
        if str(x).strip().lower() in allowed
    }


def _ensure_technical_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Fill chart-only technical columns if an older technical module omitted them."""
    if df is None or df.empty or "Close" not in df.columns:
        return df
    out = df.copy()
    close = pd.to_numeric(out["Close"], errors="coerce")
    if "MA20" not in out.columns:
        out["MA20"] = close.rolling(20).mean()
    if "MA50" not in out.columns:
        out["MA50"] = close.rolling(50).mean()
    if "RSI" not in out.columns:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        out["RSI"] = 100 - 100 / (1 + rs)
    if "MACD" not in out.columns:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        out["MACD"] = ema12 - ema26
    if "MACD_Signal" not in out.columns:
        out["MACD_Signal"] = out["MACD"].ewm(span=9, adjust=False).mean()
    if "MACD_Histogram" not in out.columns:
        out["MACD_Histogram"] = out["MACD"] - out["MACD_Signal"]
    if "AvgVolume20" not in out.columns and "Volume" in out.columns:
        out["AvgVolume20"] = pd.to_numeric(out["Volume"], errors="coerce").rolling(20).mean()
    if "Volatility20" not in out.columns:
        ret = close.pct_change()
        out["Volatility20"] = ret.rolling(20).std() * np.sqrt(252)
    return out


# =============================================================================
# 3. CHART HELPERS
# =============================================================================
def _fig_image(fig, width: float, height: float) -> Image:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=210, bbox_inches="tight", pad_inches=0.08, facecolor="#FBFDFF")
    plt.close(fig)
    buf.seek(0)
    img = Image(buf, width=width, height=height)
    img._stocklens_buffer = buf  # keep BytesIO alive until document build completes
    return img


def _clean_axes(ax, grid_axis: str = "y"):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#DDE6EF")
    ax.spines["bottom"].set_color("#DDE6EF")
    ax.grid(True, axis=grid_axis, alpha=0.20, linewidth=0.7)
    ax.tick_params(labelsize=9)


def _chart_price_volume(df: pd.DataFrame, width: float, height: float) -> Optional[Image]:
    if df is None or df.empty or "Date" not in df.columns or "Close" not in df.columns:
        return None
    d = _ensure_technical_columns(df).tail(252)
    fig, ax = plt.subplots(figsize=(8.1, 3.2))
    ax.plot(d["Date"], d["Close"], linewidth=1.8, label="Giá đóng cửa")
    ax.set_title("Diễn biến giá cổ phiếu", loc="left", fontsize=13, fontweight="bold")
    ax.set_ylabel("VND", fontsize=9)
    _clean_axes(ax)
    ax2 = ax.twinx()
    if "Volume" in d.columns:
        ax2.bar(d["Date"], d["Volume"] / 1e6, alpha=0.16, width=1.0)
        ax2.set_ylabel("Triệu CP", fontsize=9)
        ax2.tick_params(labelsize=7)
        ax2.spines["top"].set_visible(False)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_price_ma(df: pd.DataFrame, width: float, height: float) -> Optional[Image]:
    if df is None or df.empty:
        return None
    d = _ensure_technical_columns(df).tail(252)
    fig, ax = plt.subplots(figsize=(8.1, 3.0))
    ax.plot(d["Date"], d["Close"], linewidth=1.5, label="Close")
    ax.plot(d["Date"], d["MA20"], linewidth=1.2, label="MA20")
    ax.plot(d["Date"], d["MA50"], linewidth=1.2, label="MA50")
    ax.set_title("Giá + MA20 + MA50", loc="left", fontsize=13, fontweight="bold")
    ax.set_ylabel("VND", fontsize=9)
    _clean_axes(ax)
    ax.legend(frameon=False, fontsize=9, ncol=3, loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_rsi(df: pd.DataFrame, width: float, height: float) -> Optional[Image]:
    if df is None or df.empty:
        return None
    d = _ensure_technical_columns(df).tail(180)
    if "RSI" not in d.columns:
        return None
    fig, ax = plt.subplots(figsize=(4.0, 2.25))
    ax.plot(d["Date"], d["RSI"], linewidth=1.3)
    ax.axhline(70, linewidth=0.8, linestyle="--")
    ax.axhline(30, linewidth=0.8, linestyle="--")
    ax.fill_between(d["Date"], 70, 100, alpha=0.06)
    ax.fill_between(d["Date"], 0, 30, alpha=0.06)
    ax.set_ylim(0, 100)
    ax.set_title("RSI (14)", loc="left", fontsize=12, fontweight="bold")
    _clean_axes(ax)
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_macd(df: pd.DataFrame, width: float, height: float) -> Optional[Image]:
    if df is None or df.empty:
        return None
    d = _ensure_technical_columns(df).tail(180)
    if "MACD" not in d.columns:
        return None
    fig, ax = plt.subplots(figsize=(4.0, 2.25))
    ax.plot(d["Date"], d["MACD"], linewidth=1.2, label="MACD")
    ax.plot(d["Date"], d["MACD_Signal"], linewidth=1.1, label="Signal")
    ax.bar(d["Date"], d["MACD_Histogram"], alpha=0.22, width=1.0, label="Hist")
    ax.axhline(0, linewidth=0.7)
    ax.set_title("MACD (12,26,9)", loc="left", fontsize=12, fontweight="bold")
    _clean_axes(ax)
    ax.legend(frameon=False, fontsize=8.5, ncol=3, loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_volume(df: pd.DataFrame, width: float, height: float) -> Optional[Image]:
    if df is None or df.empty or "Volume" not in df.columns:
        return None
    d = _ensure_technical_columns(df).tail(180)
    fig, ax = plt.subplots(figsize=(8.1, 2.35))
    ax.bar(d["Date"], d["Volume"] / 1e6, alpha=0.45, width=1.0, label="Volume")
    if "AvgVolume20" in d.columns:
        ax.plot(d["Date"], d["AvgVolume20"] / 1e6, linewidth=1.2, label="Volume MA20")
    ax.set_title("Thanh khoản: Volume vs MA20", loc="left", fontsize=12.5, fontweight="bold")
    ax.set_ylabel("Triệu CP", fontsize=9)
    _clean_axes(ax)
    ax.legend(frameon=False, fontsize=9, ncol=2, loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_drawdown(df: pd.DataFrame, width: float, height: float) -> Optional[Image]:
    if df is None or df.empty or "Close" not in df.columns:
        return None
    d = _ensure_technical_columns(df).copy()
    close = pd.to_numeric(d["Close"], errors="coerce")
    peak = close.cummax()
    drawdown = close / peak - 1.0
    fig, ax = plt.subplots(figsize=(8.1, 2.8))
    ax.plot(d["Date"], drawdown * 100, linewidth=1.2)
    ax.fill_between(d["Date"], drawdown * 100, 0, alpha=0.15)
    ax.axhline(0, linewidth=0.7)
    ax.set_title("Maximum Drawdown theo thời gian", loc="left", fontsize=13, fontweight="bold")
    ax.set_ylabel("%", fontsize=9)
    _clean_axes(ax)
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_rolling_volatility(df: pd.DataFrame, width: float, height: float) -> Optional[Image]:
    if df is None or df.empty or "Close" not in df.columns:
        return None
    d = _ensure_technical_columns(df).copy()
    vol = d.get("Volatility20")
    if vol is None:
        return None
    fig, ax = plt.subplots(figsize=(8.1, 2.45))
    ax.plot(d["Date"], pd.to_numeric(vol, errors="coerce") * 100, linewidth=1.2)
    ax.set_title("Volatility 20 phiên - thường niên hóa", loc="left", fontsize=12.5, fontweight="bold")
    ax.set_ylabel("%", fontsize=9)
    _clean_axes(ax)
    fig.autofmt_xdate()
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _history_arrays(history: List[Dict[str, Any]], key: str) -> Tuple[List[str], List[float]]:
    periods, values = [], []
    for row in history:
        p = str(row.get("period", ""))
        v = _finite(row.get(key))
        if p and v is not None:
            periods.append(p)
            values.append(v)
    return periods, values


def _chart_revenue_profit(history: List[Dict[str, Any]], width: float, height: float) -> Optional[Image]:
    if not history:
        return None
    periods = [str(x.get("period")) for x in history]
    rev = [(_finite(x.get("revenue")) or np.nan) / 1e12 for x in history]
    net = [(_finite(x.get("net_profit")) or np.nan) / 1e12 for x in history]
    x = np.arange(len(periods))
    bw = 0.36
    fig, ax = plt.subplots(figsize=(8.1, 3.0))
    ax.bar(x - bw / 2, rev, width=bw, label="Doanh thu")
    ax.bar(x + bw / 2, net, width=bw, label="LNST")
    ax.set_xticks(x, periods)
    ax.set_ylabel("Nghìn tỷ VND", fontsize=9)
    ax.set_title("Doanh thu và lợi nhuận sau thuế", loc="left", fontsize=13, fontweight="bold")
    _clean_axes(ax)
    ax.legend(frameon=False, fontsize=9, ncol=2, loc="upper left")
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_roe_roa(history: List[Dict[str, Any]], width: float, height: float) -> Optional[Image]:
    if not history:
        return None
    periods = [str(x.get("period")) for x in history]
    roe = [(_finite(x.get("roe")) or np.nan) * 100 for x in history]
    roa = [(_finite(x.get("roa")) or np.nan) * 100 for x in history]
    fig, ax = plt.subplots(figsize=(8.1, 2.55))
    ax.plot(periods, roe, marker="o", linewidth=1.5, label="ROE")
    ax.plot(periods, roa, marker="o", linewidth=1.5, label="ROA")
    ax.set_ylabel("%", fontsize=9)
    ax.set_title("Hiệu quả sinh lời: ROE & ROA", loc="left", fontsize=12.5, fontweight="bold")
    _clean_axes(ax)
    ax.legend(frameon=False, fontsize=9, ncol=2, loc="upper left")
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_assets_equity(history: List[Dict[str, Any]], width: float, height: float) -> Optional[Image]:
    if not history:
        return None
    periods = [str(x.get("period")) for x in history]
    assets = [(_finite(x.get("total_assets")) or np.nan) / 1e12 for x in history]
    equity = [(_finite(x.get("equity")) or np.nan) / 1e12 for x in history]
    x = np.arange(len(periods))
    bw = 0.36
    fig, ax = plt.subplots(figsize=(8.1, 3.0))
    ax.bar(x - bw / 2, assets, width=bw, label="Tổng tài sản")
    ax.bar(x + bw / 2, equity, width=bw, label="VCSH")
    ax.set_xticks(x, periods)
    ax.set_ylabel("Nghìn tỷ VND", fontsize=9)
    ax.set_title("Quy mô tài sản và vốn chủ sở hữu", loc="left", fontsize=13, fontweight="bold")
    _clean_axes(ax)
    ax.legend(frameon=False, fontsize=9, ncol=2, loc="upper left")
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_leverage_liquidity(financial: Dict[str, Any], width: float, height: float) -> Optional[Image]:
    """Historical Debt/Equity and Current Ratio from raw vnstock/KBS tables."""
    raw = financial.get("_raw", {}) or {}
    ratios = raw.get("ratios")
    balance = raw.get("balance_sheet")
    periods: List[str] = []
    de_map: Dict[str, float] = {}
    cr_map: Dict[str, float] = {}

    if isinstance(ratios, pd.DataFrame) and not ratios.empty and "item_id" in ratios.columns:
        r = ratios[ratios["item_id"].astype(str) == "debt_to_equity"]
        if not r.empty:
            row = r.iloc[0]
            for col in ratios.columns:
                if str(col).isdigit():
                    v = _finite(row.get(col))
                    if v is not None:
                        de_map[str(col)] = v / 100.0 if abs(v) > 5 else v

    if isinstance(balance, pd.DataFrame) and not balance.empty and "item_id" in balance.columns:
        def _row(item_id: str):
            x = balance[balance["item_id"].astype(str) == item_id]
            return None if x.empty else x.iloc[0]
        ca = _row("current_assets")
        cl = _row("current_liabilities")
        if ca is not None and cl is not None:
            for col in balance.columns:
                if str(col).isdigit():
                    a, l = _finite(ca.get(col)), _finite(cl.get(col))
                    if a is not None and l not in (None, 0):
                        cr_map[str(col)] = a / l

    periods = sorted(set(de_map) | set(cr_map))[-4:]
    if not periods:
        return None
    de = [de_map.get(p, np.nan) for p in periods]
    cr = [cr_map.get(p, np.nan) for p in periods]
    fig, ax = plt.subplots(figsize=(8.1, 2.65))
    ax.plot(periods, de, marker="o", linewidth=1.7, label="Debt/Equity")
    ax.plot(periods, cr, marker="o", linewidth=1.7, label="Current Ratio")
    ax.axhline(1.0, linewidth=0.8, linestyle="--", alpha=0.55)
    ax.set_title("Đòn bẩy và khả năng thanh toán theo lịch sử", loc="left", fontsize=12.5, fontweight="bold")
    ax.set_ylabel("Lần", fontsize=9)
    _clean_axes(ax)
    ax.legend(frameon=False, fontsize=9, ncol=2, loc="upper left")
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_valuation(history: List[Dict[str, Any]], width: float, height: float) -> Optional[Image]:
    if not history:
        return None
    periods = [str(x.get("period")) for x in history]
    pe = [_finite(x.get("pe")) for x in history]
    pb = [_finite(x.get("pb")) for x in history]
    if not any(v is not None for v in pe + pb):
        return None
    fig, axes = plt.subplots(1, 2, figsize=(8.1, 2.8))
    axes[0].plot(periods, pe, marker="o", linewidth=1.5)
    axes[0].set_title("P/E lịch sử", loc="left", fontsize=12, fontweight="bold")
    axes[0].set_ylabel("Lần", fontsize=9)
    _clean_axes(axes[0])
    axes[1].plot(periods, pb, marker="o", linewidth=1.5)
    axes[1].set_title("P/B lịch sử", loc="left", fontsize=12, fontweight="bold")
    axes[1].set_ylabel("Lần", fontsize=9)
    _clean_axes(axes[1])
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_news_sentiment(news: Dict[str, Any], width: float, height: float) -> Optional[Image]:
    counts = news.get("sentiment_counts", {}) or {}
    vals = [int(counts.get("Positive", 0) or 0), int(counts.get("Neutral", 0) or 0), int(counts.get("Negative", 0) or 0)]
    if sum(vals) <= 0:
        return None
    fig, ax = plt.subplots(figsize=(3.8, 2.55))
    ax.bar(["Tích cực", "Trung tính", "Tiêu cực"], vals)
    ax.set_title("News Sentiment", loc="left", fontsize=12.5, fontweight="bold")
    ax.set_ylabel("Số tin", fontsize=9)
    _clean_axes(ax)
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_components(summary: Dict[str, Any], width: float, height: float) -> Optional[Image]:
    scores = summary.get("component_scores", {}) or {}
    keys = ["fundamental", "valuation", "technical", "news", "risk"]
    names = ["Fundamental", "Valuation", "Technical", "News", "Risk/Safety"]
    vals = [_finite(scores.get(k)) for k in keys]
    if not any(v is not None for v in vals):
        return None
    plot_vals = [0 if v is None else v for v in vals]
    fig, ax = plt.subplots(figsize=(8.1, 3.0))
    bars = ax.barh(names, plot_vals)
    ax.set_xlim(0, 100)
    ax.set_title("5 thành phần Investment Score", loc="left", fontsize=13, fontweight="bold")
    _clean_axes(ax, grid_axis="x")
    for bar, v in zip(bars, vals):
        if v is not None:
            ax.text(min(v + 1.2, 97), bar.get_y() + bar.get_height()/2, f"{v:.1f}", va="center", fontsize=9)
    ax.invert_yaxis()
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_contributions(summary: Dict[str, Any], width: float, height: float) -> Optional[Image]:
    vals = summary.get("contributions", {}) or {}
    keys = ["fundamental", "valuation", "technical", "news", "risk"]
    names = ["Fundamental", "Valuation", "Technical", "News", "Risk/Safety"]
    points = [_finite(vals.get(k)) for k in keys]
    if not any(v is not None for v in points):
        return None
    p = [0 if v is None else v for v in points]
    fig, ax = plt.subplots(figsize=(3.8, 2.5))
    ax.bar(names, p)
    ax.set_title("Đóng góp vào điểm tổng", loc="left", fontsize=12, fontweight="bold")
    ax.set_ylabel("Điểm", fontsize=9)
    ax.tick_params(axis="x", rotation=30, labelsize=6.2)
    _clean_axes(ax)
    fig.tight_layout()
    return _fig_image(fig, width, height)


def _chart_profiles(summary: Dict[str, Any], width: float, height: float) -> Optional[Image]:
    profiles = summary.get("profile_scores", {}) or {}
    names = ["Thận trọng", "Cân bằng", "Tăng trưởng"]
    vals = [_finite(profiles.get(n)) for n in names]
    if not any(v is not None for v in vals):
        return None
    p = [0 if v is None else v for v in vals]
    fig, ax = plt.subplots(figsize=(3.8, 2.5))
    bars = ax.bar(names, p)
    ax.set_ylim(0, 100)
    ax.set_title("Investor Profiles", loc="left", fontsize=12, fontweight="bold")
    ax.set_ylabel("Điểm", fontsize=9)
    _clean_axes(ax)
    for bar, v in zip(bars, vals):
        if v is not None:
            ax.text(bar.get_x() + bar.get_width()/2, v + 2, f"{v:.1f}", ha="center", fontsize=9)
    fig.tight_layout()
    return _fig_image(fig, width, height)


# =============================================================================
# 4. REPORTLAB COMPONENTS
# =============================================================================
class ScoreDonut(Flowable):
    def __init__(self, score: Optional[float], width: float = 37 * mm, height: float = 37 * mm):
        super().__init__()
        self.score = _finite(score)
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        cx, cy = self.width / 2, self.height / 2
        r = min(self.width, self.height) * 0.35
        c.setLineWidth(9)
        c.setStrokeColor(colors.HexColor("#E6EDF4"))
        c.circle(cx, cy, r, stroke=1, fill=0)
        if self.score is not None:
            score = max(0.0, min(100.0, self.score))
            c.setStrokeColor(_score_color(score))
            # Approximate donut using short line segments around a circle.
            steps = max(1, int(72 * score / 100))
            for i in range(steps):
                a1 = math.radians(90 - i * 5)
                a2 = math.radians(90 - (i + 1) * 5)
                c.line(cx + r * math.cos(a1), cy + r * math.sin(a1), cx + r * math.cos(a2), cy + r * math.sin(a2))
        c.setFont(FONT_BOLD, 22)
        c.setFillColor(NAVY)
        c.drawCentredString(cx, cy + 1, "N/A" if self.score is None else f"{self.score:.0f}")
        c.setFont(FONT, 10)
        c.setFillColor(MUTED)
        c.drawCentredString(cx, cy - 13, "/100")


def _section_title(title: str, subtitle: str = "") -> Table:
    left = [_P(title, STYLE_H1)]
    if subtitle:
        left.append(_P(subtitle, STYLE_SMALL))
    t = Table([[left]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("LINEBELOW", (0, 0), (-1, -1), 1.0, colors.HexColor("#CFE1F2")),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _accent_bg(accent):
    """Return a soft background matching a card accent."""
    if accent == GREEN:
        return colors.HexColor("#EAF9F2")
    if accent == TEAL:
        return colors.HexColor("#EAFBF8")
    if accent == AMBER:
        return colors.HexColor("#FFF6E6")
    if accent == RED:
        return colors.HexColor("#FDEEEE")
    if accent == PURPLE:
        return colors.HexColor("#F1EFFF")
    if accent == BLUE_2:
        return colors.HexColor("#EEF6FF")
    return colors.HexColor("#F2F8FF")


def _card(label: str, value: str, note: str = "", accent=BLUE) -> Table:
    """Professional KPI card with soft fill, accent rail and larger typography."""
    rows = [
        [_P(label, STYLE_CARD_LABEL)],
        [_P(value, STYLE_CARD_VALUE)],
    ]
    if note:
        rows.append([_P(note, STYLE_SMALL)])
    t = Table(rows, colWidths=[34 * mm], rowHeights=None)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _accent_bg(accent)),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#D1E2F1")),
        ("LINEBEFORE", (0, 0), (0, -1), 3.8, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5.5),
    ]))
    return t


def _card_row(cards: Sequence[Table]) -> Table:
    widths = [CONTENT_W / len(cards)] * len(cards)
    t = Table([list(cards)], colWidths=widths)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _translate_signal(value: Any) -> str:
    """Translate internal English signal labels to Vietnamese for the PDF."""
    mapping = {
        "Positive": "Tích cực",
        "Neutral": "Trung tính",
        "Negative": "Tiêu cực",
        "Buy": "Tích cực",
        "Sell": "Tiêu cực",
    }
    text = str(value or "-")
    return mapping.get(text, text)


def _expand_analysis_body(title: str, body: str) -> str:
    """Add useful interpretation when a section would otherwise look visually empty."""
    body = (body or "").strip()
    if len(body) >= 380:
        return body
    low = (title or "").lower()
    extras = []
    if "kỹ thuật" in low or "technical" in low:
        extras.append("Nên ưu tiên sự đồng thuận giữa xu hướng giá, MA20/MA50, RSI, MACD và thanh khoản; tín hiệu đơn lẻ thường dễ nhiễu hơn nhiều tín hiệu cùng chiều.")
    elif "rủi ro" in low or "risk" in low or "thanh khoản" in low:
        extras.append("Với cổ phiếu biến động cao, quy mô vị thế và khả năng chịu drawdown quan trọng không kém kỳ vọng sinh lời; Risk Score nên được xem như lớp kiểm soát bổ sung.")
    elif "kinh doanh" in low or "tài chính" in low or "financial" in low or "sức khỏe" in low:
        extras.append("Chất lượng tăng trưởng cần được kiểm tra qua biên lợi nhuận, ROE/ROA, cấu trúc vốn và dòng tiền, không chỉ qua doanh thu hay lợi nhuận tuyệt đối.")
    elif "định giá" in low or "valuation" in low:
        extras.append("P/E và P/B thấp hơn lịch sử có thể tạo biên an toàn, nhưng cần được đọc cùng chất lượng tăng trưởng và vị thế ngành thay vì dùng như tín hiệu mua độc lập.")
    elif "news" in low or "tin tức" in low:
        extras.append("Sentiment phản ánh tâm lý ngắn hạn; tin tiêu cực dày đặc có thể kéo dài áp lực giá, còn tin tích cực cần được xác nhận bằng kết quả kinh doanh và dòng tiền.")
    elif "score" in low or "kết luận" in low:
        extras.append("Điểm tổng hợp là bản đồ các yếu tố hỗ trợ/cản trở quyết định. Fundamental/Valuation tốt nhưng Technical/News yếu thường phù hợp theo dõi trung hạn hơn là giải ngân vội.")
    else:
        extras.append("Kết quả cần được đọc trong mối liên hệ giữa dữ liệu thị trường, chất lượng doanh nghiệp và mức định giá. StockLens ưu tiên diễn giải đa yếu tố để hạn chế việc kết luận chỉ từ một con số hoặc một biểu đồ riêng lẻ.")
    return (body + " " + " ".join(extras)).strip()


def _analysis_box(title: str, body: str, accent=BLUE, bg=SKY, width: float = CONTENT_W) -> Table:
    """A flexible narrative block used to fill the page with actual interpretation."""
    rows = [
        [_P(title, ParagraphStyle("AnalysisTitle", parent=STYLE_H2, textColor=accent, fontSize=13.5, leading=16))],
        [_P(_expand_analysis_body(title, body or "Chưa có đủ dữ liệu để diễn giải."), STYLE_BODY)],
    ]
    t = Table(rows, colWidths=[width])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#C9DAEA")),
        ("LINEBEFORE", (0, 0), (0, -1), 3.0, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


class TickerBadge(Flowable):
    """Fallback company visual when no company image/logo is available."""
    def __init__(self, ticker: str, width: float = 28 * mm, height: float = 24 * mm):
        super().__init__()
        self.ticker = str(ticker or "STOCK")[:8].upper()
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        c.setFillColor(SKY)
        c.setStrokeColor(colors.HexColor("#BBD5EC"))
        c.roundRect(0, 0, self.width, self.height, 7, fill=1, stroke=1)
        c.setFillColor(NAVY)
        c.setFont(FONT_BOLD, 19)
        c.drawCentredString(self.width / 2, self.height / 2 + 2, self.ticker)
        c.setFont(FONT, 7.5)
        c.setFillColor(MUTED)
        c.drawCentredString(self.width / 2, 4, "STOCKLENS")


def _company_visual(company: Dict[str, Any], ticker: str, width: float = 36 * mm, height: float = 27 * mm) -> Flowable:
    """Resolve a company logo/photo dynamically.

    Priority:
      1. company_info paths/URLs
      2. <project>/assets/logos/<TICKER>.*
      3. <project>/assets/company_images/<TICKER>.*
      4. logo.clearbit.com when company website is available
      5. branded ticker badge fallback
    """
    def make_image(source):
        try:
            img = Image(source)
            img._restrictSize(width, height)
            return img
        except Exception:
            return None

    local_candidates: List[str] = []
    for key in ("logo_path", "image_path", "logo", "company_image_path"):
        value = company.get(key)
        if isinstance(value, str) and value.strip():
            local_candidates.append(value.strip())

    for folder in (LOGO_DIR, COMPANY_IMAGE_DIR, ASSETS_DIR, PROJECT_ROOT / "logos"):
        for ext in ("png", "jpg", "jpeg", "webp"):
            local_candidates.append(str(folder / f"{ticker}.{ext}"))
            local_candidates.append(str(folder / f"{ticker.lower()}.{ext}"))

    for path in local_candidates:
        if os.path.exists(path):
            img = make_image(path)
            if img is not None:
                return img

    urls: List[str] = []
    for key in ("logo_url", "image_url", "company_image_url"):
        value = company.get(key)
        if isinstance(value, str) and value.startswith(("http://", "https://")):
            urls.append(value)

    website = str(company.get("website") or "").strip()
    if website:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(website if "://" in website else "https://" + website)
            domain = parsed.netloc or parsed.path.split("/")[0]
            if domain:
                urls.append(f"https://logo.clearbit.com/{domain}")
        except Exception:
            pass

    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 StockLens/2.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = resp.read()
            buf = BytesIO(data)
            img = make_image(buf)
            if img is not None:
                img._stocklens_buffer = buf
                return img
        except Exception:
            pass

    return TickerBadge(ticker, width=width, height=height)


def _pct_change(new: Any, old: Any) -> Optional[float]:
    n, o = _finite(new), _finite(old)
    if n is None or o in (None, 0):
        return None
    return n / o - 1


def _technical_interpretation(technical: Dict[str, Any], market: Dict[str, Any]) -> str:
    close = _finite(technical.get("close", market.get("close")))
    ma20 = _finite(technical.get("ma20"))
    ma50 = _finite(technical.get("ma50"))
    rsi = _finite(technical.get("rsi"))
    vr = _finite(technical.get("volume_ratio"))
    points = []
    if close is not None and ma20 is not None and ma50 is not None:
        if close > ma20 > ma50:
            points.append("Giá đang nằm trên MA20 và MA50, đồng thời MA20 cao hơn MA50, cho thấy xu hướng ngắn - trung hạn tích cực.")
        elif close < ma20 < ma50:
            points.append("Giá đang dưới MA20 và MA50, trong khi MA20 thấp hơn MA50; xu hướng ngắn - trung hạn vẫn yếu và cần chờ tín hiệu xác nhận đảo chiều.")
        else:
            points.append("Cấu trúc giá - MA20 - MA50 đang đan xen, phản ánh xu hướng chưa thật sự rõ ràng.")
    if rsi is not None:
        if rsi < 30:
            points.append(f"RSI(14) ở {rsi:.1f}, thuộc vùng quá bán; có thể xuất hiện nhịp hồi kỹ thuật nhưng rủi ro xu hướng giảm vẫn cần được theo dõi.")
        elif rsi > 70:
            points.append(f"RSI(14) ở {rsi:.1f}, thuộc vùng quá mua; động lượng mạnh nhưng xác suất rung lắc/chốt lời tăng lên.")
        else:
            points.append(f"RSI(14) ở {rsi:.1f}, nằm trong vùng trung tính 30-70.")
    if vr is not None:
        points.append(f"Khối lượng phiên gần nhất bằng khoảng {vr:.2f} lần trung bình 20 phiên, cho biết mức độ xác nhận của dòng tiền đối với biến động giá hiện tại.")
    return " ".join(points[:3]) or (technical.get("commentary") or "Chưa đủ dữ liệu để diễn giải kỹ thuật.")


def _risk_interpretation(risk: Dict[str, Any], market: Dict[str, Any]) -> str:
    rm = risk.get("metrics", {}) or {}
    vol = _finite(rm.get("volatility_20_annualized"))
    dd = _finite(rm.get("max_drawdown_period"))
    range_pct = None
    hi, lo = _finite(market.get("high_52w")), _finite(market.get("low_52w"))
    if hi not in (None, 0) and lo is not None:
        range_pct = (hi - lo) / hi
    parts = []
    if vol is not None:
        parts.append(f"Volatility 20 phiên thường niên hóa ở {vol:.1%}, phản ánh mức dao động giá ngắn hạn của cổ phiếu.")
    if dd is not None:
        parts.append(f"Maximum Drawdown của kỳ phân tích là {dd:.1%}; mức giảm sâu càng lớn thì yêu cầu kiểm soát vị thế và điểm cắt lỗ càng quan trọng.")
    if range_pct is not None:
        parts.append(f"Biên độ giữa đỉnh và đáy 52 tuần tương đương khoảng {range_pct:.1%} so với đỉnh, cho thấy khoảng dao động mà nhà đầu tư đã phải chịu trong một năm gần nhất.")
    return " ".join(parts) or (risk.get("commentary") or "Chưa đủ dữ liệu để diễn giải rủi ro.")


def _financial_interpretation(history: List[Dict[str, Any]], fundamental: Dict[str, Any]) -> str:
    if len(history) >= 2:
        prev, cur = history[-2], history[-1]
        rg = _pct_change(cur.get("revenue"), prev.get("revenue"))
        pg = _pct_change(cur.get("net_profit"), prev.get("net_profit"))
        roe_cur, roe_prev = _finite(cur.get("roe")), _finite(prev.get("roe"))
        parts = []
        if rg is not None:
            parts.append(f"Doanh thu năm gần nhất {'tăng' if rg >= 0 else 'giảm'} {abs(rg):.1%} so với năm trước.")
        if pg is not None:
            parts.append(f"LNST {'tăng' if pg >= 0 else 'giảm'} {abs(pg):.1%}, cho thấy tốc độ biến động lợi nhuận {'nhanh hơn' if rg is not None and pg > rg else 'không vượt'} tốc độ doanh thu.")
        if roe_cur is not None and roe_prev is not None:
            parts.append(f"ROE thay đổi từ {roe_prev:.1%} lên {roe_cur:.1%}; đây là chỉ báo quan trọng về hiệu quả sử dụng vốn chủ sở hữu.")
        return " ".join(parts)
    return fundamental.get("commentary") or "Chưa đủ lịch sử để so sánh hiệu quả kinh doanh."


def _valuation_interpretation(valuation: Dict[str, Any]) -> str:
    pe = _finite(valuation.get("pe"))
    pb = _finite(valuation.get("pb"))
    pe_med = _finite(valuation.get("historical_pe_median"))
    pb_med = _finite(valuation.get("historical_pb_median"))
    parts = []
    if pe is not None and pe_med not in (None, 0):
        diff = pe / pe_med - 1
        parts.append(f"P/E hiện tại {pe:.2f}x {'thấp hơn' if diff < 0 else 'cao hơn'} median lịch sử {pe_med:.2f}x khoảng {abs(diff):.1%}.")
    if pb is not None and pb_med not in (None, 0):
        diff = pb / pb_med - 1
        parts.append(f"P/B hiện tại {pb:.2f}x {'thấp hơn' if diff < 0 else 'cao hơn'} median lịch sử {pb_med:.2f}x khoảng {abs(diff):.1%}.")
    parts.append("Valuation Score dùng trong Investment Score vẫn dựa trên P/E, P/B hiện tại và lịch sử của chính doanh nghiệp.")
    return " ".join(parts)


def _peer_valuation_interpretation(valuation: Dict[str, Any]) -> str:
    """Diễn giải Peer Valuation nhưng không biến Peer Fair Value thành target price."""
    peer = valuation.get("peer_valuation", {}) or {}
    if not peer.get("data_available"):
        return peer.get("commentary") or "Chưa đủ dữ liệu peer cùng ngành để thực hiện Peer Valuation."

    score = _finite(valuation.get("peer_score", peer.get("score")))
    fair = _finite(valuation.get("peer_fair_value", peer.get("peer_fair_value")))
    upside = _finite(valuation.get("peer_upside_downside", peer.get("upside_downside")))
    med_pe = _finite(valuation.get("peer_median_pe", peer.get("peer_median_pe")))
    med_pb = _finite(valuation.get("peer_median_pb", peer.get("peer_median_pb")))
    implied_pe = _finite(valuation.get("peer_implied_price_pe", peer.get("implied_price_pe")))
    implied_pb = _finite(valuation.get("peer_implied_price_pb", peer.get("implied_price_pb")))
    cur_pe = _finite(valuation.get("pe", peer.get("pe")))
    cur_pb = _finite(valuation.get("pb", peer.get("pb")))
    quality = valuation.get("peer_quality_status") or peer.get("peer_quality_status")

    parts = []
    if score is not None:
        parts.append(f"Peer Score đạt {score:.1f}/100.")
    if cur_pe is not None and med_pe not in (None, 0):
        gap = cur_pe / med_pe - 1
        parts.append(f"P/E hiện tại {'cao hơn' if gap > 0 else 'thấp hơn'} median peer khoảng {abs(gap):.1%}.")
    if cur_pb is not None and med_pb not in (None, 0):
        gap = cur_pb / med_pb - 1
        parts.append(f"P/B hiện tại {'cao hơn' if gap > 0 else 'thấp hơn'} median peer khoảng {abs(gap):.1%}.")
    if fair is not None and upside is not None:
        parts.append(f"Peer Fair Value hàm ý khoảng {fair:,.0f} VND, tương ứng upside/downside {upside:+.1%} so với giá thị trường.")
    if implied_pe is not None and implied_pb is not None:
        parts.append(f"Giá hàm ý riêng theo P/E khoảng {implied_pe:,.0f} VND và theo P/B khoảng {implied_pb:,.0f} VND.")
    if quality:
        parts.append(f"Chất lượng bộ peer: {quality}.")
    warnings = valuation.get("peer_quality_warnings") or peer.get("peer_quality_warnings") or []
    if warnings:
        parts.append("Cảnh báo chính: " + "; ".join(str(x) for x in warnings[:2]) + ".")
    parts.append("Peer Fair Value là giá trị hàm ý tương đối theo multiples cùng ngành, không phải target price hay giá trị nội tại DCF.")
    return " ".join(parts)


def _score_interpretation(summary: Dict[str, Any], profile: str) -> str:
    strongest = summary.get("strongest_component") or {}
    weakest = summary.get("weakest_component") or {}
    base = _finite(summary.get("investment_score", summary.get("score")))
    pscore = _finite((summary.get("profile_scores") or {}).get(profile))
    text = []
    if base is not None:
        text.append(f"Investment Score cơ sở đạt {base:.2f}/100.")
    if strongest:
        text.append(f"Yếu tố hỗ trợ mạnh nhất là {strongest.get('name', 'N/A')} ({_fmt_num(strongest.get('score'), 1)}/100).")
    if weakest:
        text.append(f"Yếu tố kéo điểm xuống nhiều nhất là {weakest.get('name', 'N/A')} ({_fmt_num(weakest.get('score'), 1)}/100).")
    if pscore is not None:
        text.append(f"Với hồ sơ {profile.lower()}, điểm điều chỉnh là {pscore:.2f}/100; khác biệt đến từ việc thay đổi trọng số theo khẩu vị rủi ro.")
    return " ".join(text)


def _snapshot_interpretation(ticker: str, summary: Dict[str, Any], results: Dict[str, Any]) -> str:
    scores = summary.get("component_scores", {}) or {}
    strongest = summary.get("strongest_component") or {}
    weakest = summary.get("weakest_component") or {}
    score = _finite(summary.get("investment_score", summary.get("score")))
    label = summary.get("classification") or summary.get("label") or _score_label(score)
    text = (
        f"{ticker} hiện đạt Investment Score {_fmt_num(score, 2)}/100, xếp loại {label}. "
        f"Nhóm yếu tố mạnh nhất là {strongest.get('name', 'N/A')} với {_fmt_num(strongest.get('score'), 2)}/100, "
        f"trong khi yếu tố thấp nhất là {weakest.get('name', 'N/A')} với {_fmt_num(weakest.get('score'), 2)}/100. "
        "Sự chênh lệch giữa các nhóm điểm cho biết cổ phiếu có thể hấp dẫn về nền tảng hoặc định giá nhưng chưa chắc thuận lợi về thời điểm giao dịch. "
    )
    if scores:
        text += (
            f"Cụ thể, Fundamental {_fmt_num(scores.get('fundamental'), 1)}, Valuation {_fmt_num(scores.get('valuation'), 1)}, "
            f"Technical {_fmt_num(scores.get('technical'), 1)}, News {_fmt_num(scores.get('news'), 1)} và Risk/Safety {_fmt_num(scores.get('risk'), 1)}. "
        )
    text += "Do đó, báo cáo ưu tiên phân tích đồng thời doanh nghiệp, giá thị trường, sentiment và rủi ro trước khi đưa ra kết luận theo từng hồ sơ nhà đầu tư."
    return text


def _news_interpretation(news: Dict[str, Any]) -> str:
    counts = news.get("sentiment_counts", {}) or {}
    pos = int(counts.get("Positive", 0) or 0)
    neu = int(counts.get("Neutral", 0) or 0)
    neg = int(counts.get("Negative", 0) or 0)
    score = _get_score(news)
    classification = news.get("classification") or _score_label(score)
    return (
        f"News Score đạt {_fmt_num(score, 2)}/100, xếp loại {classification}. Tập tin dùng chấm điểm gồm {pos} tin tích cực, {neu} tin trung tính và {neg} tin tiêu cực. "
        "Khi tỷ trọng tin tiêu cực tăng và tập trung trong thời gian ngắn, tâm lý thị trường có thể trở thành lực cản đáng kể đối với giá cổ phiếu, ngay cả khi nền tảng cơ bản chưa xấu đi tương ứng. "
        "Ngược lại, sentiment cải thiện chỉ nên được xem là bền vững khi đi cùng tín hiệu kỹ thuật tốt hơn và thông tin kinh doanh có khả năng kiểm chứng."
    )


def _balance_interpretation(financial: Dict[str, Any], fundamental: Dict[str, Any], history: List[Dict[str, Any]]) -> str:
    fm = fundamental.get("metrics", {}) or {}
    de = _finite(fm.get("debt_to_equity", financial.get("debtToEquity")))
    cr = _finite(fm.get("current_ratio", financial.get("currentRatio")))
    ocf = _finite(financial.get("operatingCashflow"))
    assets = _finite(financial.get("totalAssets"))
    equity = _finite(financial.get("totalStockholderEquity") or financial.get("totalEquity"))
    growth_text = ""
    if len(history) >= 2:
        ag = _pct_change(history[-1].get("total_assets"), history[-2].get("total_assets"))
        eg = _pct_change(history[-1].get("equity"), history[-2].get("equity"))
        if ag is not None and eg is not None:
            growth_text = f" So với năm trước, tổng tài sản {'tăng' if ag >= 0 else 'giảm'} {abs(ag):.1%} và vốn chủ sở hữu {'tăng' if eg >= 0 else 'giảm'} {abs(eg):.1%}."
    return (
        f"Tổng tài sản hiện ở mức {_fmt_money(assets)}, trong khi vốn chủ sở hữu đạt {_fmt_money(equity)}.{growth_text} "
        f"Debt/Equity ở mức {_fmt_x(de)} và Current Ratio ở mức {_fmt_x(cr)}, phản ánh cấu trúc đòn bẩy và khả năng đáp ứng nghĩa vụ ngắn hạn. "
        f"Dòng tiền từ hoạt động kinh doanh đạt {_fmt_money(ocf)}. Một cấu trúc tài chính lành mạnh cần sự cân bằng giữa tăng trưởng tài sản, vốn chủ sở hữu, nợ và dòng tiền; do đó StockLens không đánh giá sức khỏe tài chính chỉ từ một tỷ lệ riêng lẻ."
    )


def _bullet_box(title: str, items: List[str], positive: bool = True) -> Table:
    accent = GREEN if positive else RED
    bg = GREEN_BG if positive else RED_BG
    rows: List[List[Any]] = [[_P(title, ParagraphStyle("BoxTitle", parent=STYLE_H2, textColor=accent))]]
    if not items:
        items = ["Chưa có đủ dữ liệu để tạo nhận xét."]
    for item in items[:5]:
        rows.append([_Phtml(f"<b>•</b> {_esc(item)}", STYLE_SMALL)])
    t = Table(rows, colWidths=[CONTENT_W / 2 - 4 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDE9E4") if positive else colors.HexColor("#F0D7D7")),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _data_table(
    data: List[List[Any]],
    widths: List[float],
    font_size: float = 8.7,
    repeat_rows: int = 1,
    align_numeric_from: int = 1,
) -> Table:
    converted: List[List[Any]] = []
    for r, row in enumerate(data):
        converted_row = []
        for cell in row:
            if isinstance(cell, (Paragraph, Table, Image, Flowable)):
                converted_row.append(cell)
            else:
                style = ParagraphStyle(
                    f"tbl_{r}_{len(converted_row)}",
                    parent=STYLE_TINY,
                    fontName=FONT_BOLD if r == 0 else FONT,
                    fontSize=font_size,
                    leading=font_size + 1.5,
                    textColor=NAVY if r == 0 else TEXT,
                )
                converted_row.append(_P(cell, style))
        converted.append(converted_row)
    t = Table(converted, colWidths=widths, repeatRows=repeat_rows, hAlign="LEFT")
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), SKY),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 5.0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5.0),
    ]
    if align_numeric_from < len(widths):
        style.append(("ALIGN", (align_numeric_from, 1), (-1, -1), "RIGHT"))
    t.setStyle(TableStyle(style))
    return t


def _financial_history_table(history: List[Dict[str, Any]]) -> Optional[Table]:
    if not history:
        return None
    hist = history[-4:]
    periods = [str(x.get("period")) for x in hist]
    rows: List[List[Any]] = [["Chỉ tiêu"] + periods]
    rows.extend([
        ["Doanh thu (tỷ VND)"] + [_fmt_billion(x.get("revenue"), 0) for x in hist],
        ["LNST (tỷ VND)"] + [_fmt_billion(x.get("net_profit"), 0) for x in hist],
        ["Tổng tài sản (tỷ VND)"] + [_fmt_billion(x.get("total_assets"), 0) for x in hist],
        ["VCSH (tỷ VND)"] + [_fmt_billion(x.get("equity"), 0) for x in hist],
        ["ROE"] + [_fmt_pct(x.get("roe"), 1) for x in hist],
        ["ROA"] + [_fmt_pct(x.get("roa"), 1) for x in hist],
        ["P/E"] + [_fmt_x(x.get("pe"), 1) for x in hist],
        ["P/B"] + [_fmt_x(x.get("pb"), 1) for x in hist],
    ])
    first = 48 * mm
    remaining = (CONTENT_W - first) / max(1, len(periods))
    return _data_table(rows, [first] + [remaining] * len(periods), font_size=8.9)


def _financial_performance_table(history: List[Dict[str, Any]]) -> Optional[Table]:
    if not history:
        return None
    hist = history[-4:]
    periods = [str(x.get("period", "")) for x in hist]
    rows: List[List[Any]] = [
        ["Chỉ tiêu"] + periods,
        ["Doanh thu (tỷ VND)"] + [_fmt_billion(x.get("revenue"), 0) for x in hist],
        ["LNST (tỷ VND)"] + [_fmt_billion(x.get("net_profit"), 0) for x in hist],
        ["ROE"] + [_fmt_pct(x.get("roe"), 1) for x in hist],
        ["ROA"] + [_fmt_pct(x.get("roa"), 1) for x in hist],
        ["P/E"] + [_fmt_x(x.get("pe"), 1) for x in hist],
        ["P/B"] + [_fmt_x(x.get("pb"), 1) for x in hist],
    ]
    first = 48 * mm
    remaining = (CONTENT_W - first) / max(1, len(periods))
    return _data_table(rows, [first] + [remaining] * len(periods), font_size=8.5)


def _statement_dataframe(financial: Dict[str, Any], key: str) -> Optional[pd.DataFrame]:
    raw = financial.get("_raw", {}) or {}
    df = raw.get(key)
    return df if isinstance(df, pd.DataFrame) and not df.empty else None


def _latest_statement_period(financial: Dict[str, Any]) -> Optional[str]:
    report_period = financial.get("reportPeriod")
    if report_period is not None:
        return str(report_period)
    periods: List[str] = []
    raw = financial.get("_raw", {}) or {}
    for key in ("income_statement", "balance_sheet", "cash_flow", "ratios"):
        df = raw.get(key)
        if isinstance(df, pd.DataFrame):
            periods.extend([str(c) for c in df.columns if str(c).isdigit()])
    return sorted(set(periods), reverse=True)[0] if periods else None


def _select_statement_rows(financial: Dict[str, Any], key: str, period: str, limit: int) -> List[Tuple[str, Any]]:
    df = _statement_dataframe(financial, key)
    if df is None or period not in df.columns:
        return []
    tmp = df.copy()
    if "item" not in tmp.columns:
        return []
    tmp[period] = pd.to_numeric(tmp[period], errors="coerce")
    tmp = tmp.dropna(subset=[period])
    if tmp.empty:
        return []

    priorities = {
        "income_statement": [
            "revenue", "cost_of_goods_sold", "gross_profit", "financial_income",
            "financial_expenses", "selling_expenses", "general_and_administrative_expenses",
            "operating_profit", "profit_before_tax", "net_profit",
        ],
        "balance_sheet": [
            "cash_and_cash_equivalents", "current_assets", "inventory", "short_term_receivables",
            "fixed_assets", "long_term_assets", "total_assets", "current_liabilities",
            "long_term_liabilities", "total_liabilities", "owners_equity_2", "owners_equity_3",
        ],
        "cash_flow": [
            "net_cash_flow_from_operating_activities", "net_cash_flow_from_investing_activities",
            "net_cash_flow_from_financing_activities", "cash_and_cash_equivalents_at_beginning_of_period",
            "cash_and_cash_equivalents_at_end_of_period",
        ],
        "ratios": [
            "pe_ratio", "pb_ratio", "roe", "roa", "debt_to_equity", "debt_to_assets",
            "current_ratio", "book_value_per_share_bvps", "debt_coverage",
        ],
    }
    priority = priorities.get(key, [])
    rows: List[Tuple[str, Any]] = []
    used = set()
    if "item_id" in tmp.columns:
        for pid in priority:
            matches = tmp[tmp["item_id"].astype(str) == pid]
            for idx, r in matches.iterrows():
                rows.append((str(r.get("item") or pid), r[period]))
                used.add(idx)
                if len(rows) >= limit:
                    return rows
    # Fill remaining slots with non-null rows that have informative labels.
    for idx, r in tmp.iterrows():
        if idx in used:
            continue
        label = str(r.get("item") or "").strip()
        if not label:
            continue
        rows.append((label, r[period]))
        if len(rows) >= limit:
            break
    return rows


def _statement_mini_table(financial: Dict[str, Any], key: str, title: str, period: str, limit: int, ratios: bool = False) -> Table:
    rows = _select_statement_rows(financial, key, period, limit)
    data: List[List[Any]] = [[title, period]]
    if not rows:
        data.append(["Không có dữ liệu", "N/A"])
    else:
        for label, value in rows:
            if ratios:
                # Keep ratio values in the unit returned by KBS, except obvious price multiples.
                value_text = _fmt_num(value, 2)
            else:
                value_text = _fmt_billion(value, 1)
            data.append([label, value_text])
    t = _data_table(data, [63 * mm, 25 * mm], font_size=8.4, align_numeric_from=1)
    return t


def _metric_table(rows: List[Tuple[str, str]], width: float = CONTENT_W) -> Table:
    data = [[_P(k, STYLE_SMALL), _P(v, STYLE_RIGHT)] for k, v in rows]
    t = Table(data, colWidths=[width * 0.62, width * 0.38])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


# =============================================================================
# 5. HEADER / FOOTER
# =============================================================================
def _draw_report_background(canvas):
    """Soft finance-tech background inspired by the approved blue/white demo."""
    canvas.setFillColor(PAGE_BG)
    canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

    # translucent atmospheric circles
    try:
        canvas.setFillAlpha(0.32)
    except Exception:
        pass
    canvas.setFillColor(PAGE_SKY_2)
    canvas.circle(18 * mm, PAGE_H - 12 * mm, 31 * mm, fill=1, stroke=0)
    canvas.setFillColor(PAGE_SKY)
    canvas.circle(PAGE_W - 20 * mm, PAGE_H - 24 * mm, 24 * mm, fill=1, stroke=0)
    canvas.setFillColor(PAGE_MINT)
    canvas.circle(PAGE_W - 8 * mm, 35 * mm, 32 * mm, fill=1, stroke=0)

    try:
        canvas.setFillAlpha(1)
        canvas.setStrokeAlpha(0.42)
    except Exception:
        pass

    # elegant wave lines at bottom / left
    for i in range(7):
        canvas.setStrokeColor(colors.HexColor("#9DCAF3"))
        canvas.setLineWidth(0.45)
        p = canvas.beginPath()
        y0 = 22 * mm + i * 2.1 * mm
        p.moveTo(-8 * mm, y0)
        p.curveTo(38 * mm, y0 + 27 * mm, 92 * mm, y0 - 10 * mm, PAGE_W + 8 * mm, y0 + 18 * mm)
        canvas.drawPath(p, stroke=1, fill=0)

    # subtle candlestick motif, top-right and lower-left
    candle_color = colors.HexColor("#A8CFF2")
    canvas.setStrokeColor(candle_color)
    canvas.setFillColor(colors.HexColor("#DCEEFF"))
    for base_x, base_y, scale in [(PAGE_W - 48 * mm, PAGE_H - 61 * mm, 1.0), (6 * mm, 42 * mm, 0.72)]:
        for j, h in enumerate([10, 16, 12, 22, 18, 28]):
            x = base_x + j * 5.2 * mm * scale
            y = base_y + j * 2.1 * mm * scale
            canvas.setLineWidth(0.7)
            canvas.line(x + 1.6 * mm, y - 4 * mm * scale, x + 1.6 * mm, y + (h + 5) * mm * scale)
            canvas.rect(x, y, 3.2 * mm * scale, h * mm * scale, fill=1, stroke=1)

    try:
        canvas.setStrokeAlpha(1)
    except Exception:
        pass


def _on_page(canvas, doc):
    canvas.saveState()
    _draw_report_background(canvas)
    page_no = canvas.getPageNumber()
    total_pages = getattr(doc, "_stocklens_total_pages", 8)

    # semi-transparent header bar
    canvas.setFillColor(colors.HexColor("#FFFFFF"))
    canvas.roundRect(LEFT - 2 * mm, PAGE_H - 13 * mm, CONTENT_W + 4 * mm, 8 * mm, 3 * mm, fill=1, stroke=0)
    canvas.setStrokeColor(colors.HexColor("#CFE2F3"))
    canvas.setLineWidth(0.7)
    canvas.line(LEFT, PAGE_H - 10.5 * mm, PAGE_W - RIGHT, PAGE_H - 10.5 * mm)
    canvas.setFont(FONT_BOLD, 11)
    canvas.setFillColor(NAVY)
    canvas.drawString(LEFT, PAGE_H - 8.1 * mm, "STOCKLENS")
    canvas.setFont(FONT, 8.2)
    canvas.setFillColor(MUTED)
    canvas.drawString(LEFT + 31 * mm, PAGE_H - 8.1 * mm, "Investment Intelligence Platform")
    canvas.setFont(FONT_BOLD, 8.6)
    canvas.drawRightString(
        PAGE_W - RIGHT,
        PAGE_H - 8.1 * mm,
        f"BÁO CÁO PHÂN TÍCH CỔ PHIẾU  |  Trang {page_no}/{total_pages}",
    )

    # footer ribbon
    canvas.setFillColor(colors.HexColor("#F1F8FE"))
    canvas.roundRect(LEFT - 2 * mm, 4.2 * mm, CONTENT_W + 4 * mm, 8 * mm, 3 * mm, fill=1, stroke=0)
    canvas.setStrokeColor(colors.HexColor("#CFE2F3"))
    canvas.line(LEFT, 10.1 * mm, PAGE_W - RIGHT, 10.1 * mm)
    canvas.setFont(FONT, 7.8)
    canvas.setFillColor(MUTED)
    canvas.drawString(LEFT, 6.8 * mm, "Nguồn: DNSE OpenAPI | vnstock/KBS | Google News RSS | StockLens")
    canvas.drawRightString(PAGE_W - RIGHT, 6.8 * mm, "Học tập - Không phải khuyến nghị đầu tư")
    canvas.restoreState()


# =============================================================================
# 6. 8-PAGE STORY BUILDER
# =============================================================================
def _collect_insights(results: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    positives: List[str] = []
    risks: List[str] = []
    for key in ("fundamental", "valuation", "technical", "news", "risk"):
        res = results.get(key, {}) or {}
        positives.extend([str(x) for x in (res.get("positives") or [])[:2]])
        risks.extend([str(x) for x in (res.get("risks") or [])[:2]])
        if key == "valuation":
            positives.extend([str(x) for x in (res.get("peer_positives") or [])[:1]])
            risks.extend([str(x) for x in (res.get("peer_risks") or [])[:1]])
    news = results.get("news", {}) or {}
    if len(risks) < 4:
        for item in news.get("items", []) or []:
            if item.get("sentiment") == "Negative" and item.get("title"):
                risks.append(str(item["title"]))
            if len(risks) >= 5:
                break
    return positives[:5], risks[:5]


def _build_story(
    ticker: str,
    period_text: str,
    results: Dict[str, Any],
    summary: Dict[str, Any],
    sections: set[str],
    profile: str,
    company: Dict[str, Any],
    financial: Dict[str, Any],
) -> List[Any]:
    story: List[Any] = []
    technical = results.get("technical", {}) or {}
    fundamental = results.get("fundamental", {}) or {}
    valuation = results.get("valuation", {}) or {}
    news = results.get("news", {}) or {}
    risk = results.get("risk", {}) or {}
    tech_df = _ensure_technical_columns(_technical_df(results))
    market = _latest_market_stats(tech_df)
    history = _financial_history(financial)

    name = _company_name(company, financial, ticker)
    display_name = ticker if str(name).strip().upper() == ticker.upper() else f"{ticker} - {name}"
    exchange = company.get("exchange") or financial.get("exchange") or "N/A"
    sector = company.get("sector") or financial.get("sector") or "Chưa có dữ liệu ngành"
    report_period = financial.get("reportPeriod") or company.get("report_period") or "N/A"
    score = _finite(summary.get("investment_score", summary.get("score")))
    label = summary.get("classification") or summary.get("label") or _score_label(score)
    positives, risks = _collect_insights(results)

    # -------------------------------------------------------------------------
    # PAGE 1 - RESEARCH SNAPSHOT
    # -------------------------------------------------------------------------
    story.append(Spacer(1, 1.5 * mm))
    company_visual = _company_visual({**financial, **company}, ticker, width=38 * mm, height=28 * mm)
    hero_text = [
        _P(display_name, STYLE_TITLE),
        _P(f"Báo cáo phân tích cổ phiếu | Khoảng dữ liệu: {period_text} | Hồ sơ: {profile}", STYLE_SUBTITLE),
    ]
    hero = Table([[hero_text, company_visual]], colWidths=[CONTENT_W - 42 * mm, 42 * mm])
    hero.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(hero)
    story.append(Spacer(1, 2.5 * mm))

    company_strip = Table([[ 
        _Phtml(f"<b>Mã</b><br/>{_esc(ticker)}", STYLE_CENTER),
        _Phtml(f"<b>Sàn</b><br/>{_esc(exchange)}", STYLE_CENTER),
        _Phtml(f"<b>Ngành</b><br/>{_esc(sector)}", STYLE_CENTER),
        _Phtml(f"<b>Kỳ BCTC</b><br/>{_esc(report_period)}", STYLE_CENTER),
        _Phtml(f"<b>Giá gần nhất</b><br/>{_esc(_fmt_price(market.get('close')))}", STYLE_CENTER),
    ]], colWidths=[CONTENT_W / 5] * 5)
    company_strip.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(company_strip)
    story.append(Spacer(1, 3 * mm))

    donut = ScoreDonut(score)
    score_box = Table([
        [_P("Đánh giá tổng hợp", STYLE_CARD_LABEL)],
        [_P(label.upper(), ParagraphStyle("Overall", parent=STYLE_CARD_VALUE, fontSize=14, textColor=_score_color(score)))],
        [_P(summary.get("commentary") or "Điểm tổng hợp từ 5 nhóm yếu tố StockLens.", STYLE_SMALL)],
    ], colWidths=[47 * mm])
    score_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GREEN_BG if (score or 0) >= 65 else AMBER_BG if (score or 0) >= 50 else RED_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    thesis = []
    thesis.extend((fundamental.get("positives") or [])[:2])
    thesis.extend((valuation.get("positives") or [])[:1])
    if len(thesis) < 3:
        thesis.extend((valuation.get("peer_positives") or [])[:1])
    if len(thesis) < 3:
        thesis.extend((technical.get("positives") or [])[: 3 - len(thesis)])
    if not thesis:
        thesis = ["Chưa có đủ dữ liệu để tạo luận điểm đầu tư."]
    thesis_data = [[_P("TÓM TẮT ĐẦU TƯ", STYLE_H2)]]
    thesis_data += [[_Phtml(f"<b>{i}.</b> {_esc(x)}", STYLE_SMALL)] for i, x in enumerate(thesis[:2], 1)]
    if risks:
        thesis_data.append([_P("RỦI RO CHÍNH", ParagraphStyle("SnapRisk", parent=STYLE_H2, fontSize=11.5, leading=13.5, textColor=RED, spaceBefore=1 * mm))])
        thesis_data += [[_Phtml(f"• {_esc(x)}", STYLE_SMALL)] for x in risks[:2]]
    thesis_box = Table(thesis_data, colWidths=[75 * mm])
    thesis_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    snap_top = Table([[[donut, score_box], thesis_box]], colWidths=[CONTENT_W - 77 * mm, 77 * mm])
    snap_top.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(snap_top)
    story.append(Spacer(1, 3 * mm))

    price_chart = _chart_price_volume(tech_df, 116 * mm, 40 * mm)
    info_rows = [
        ("Giá đóng cửa", _fmt_price(market.get("close"))),
        ("Biến động phiên", "N/A" if market.get("pct_change") is None else f"{market['pct_change']:+.2%}"),
        ("Khối lượng", _fmt_num(market.get("volume"), 0)),
        ("Đỉnh 52 tuần", _fmt_price(market.get("high_52w"))),
        ("Đáy 52 tuần", _fmt_price(market.get("low_52w"))),
        ("P/E", _fmt_x(valuation.get("pe", financial.get("trailingPE")))),
        ("P/B", _fmt_x(valuation.get("pb", financial.get("priceToBook")))),
    ]
    info = _metric_table(info_rows, width=CONTENT_W - 119 * mm)
    chart_row = Table([[price_chart or _P("Không đủ dữ liệu giá để vẽ biểu đồ.", STYLE_SMALL), info]], colWidths=[119 * mm, CONTENT_W - 119 * mm])
    chart_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(chart_row)
    story.append(Spacer(1, 3 * mm))

    story.append(_card_row([
        _card("Technical", "N/A" if _get_score(technical) is None else f"{_get_score(technical):.1f}/100", _translate_signal(technical.get("label") or technical.get("classification") or ""), BLUE),
        _card("Fundamental", "N/A" if _get_score(fundamental) is None else f"{_get_score(fundamental):.1f}/100", fundamental.get("classification") or "", TEAL),
        _card("Valuation", "N/A" if _get_score(valuation) is None else f"{_get_score(valuation):.1f}/100", valuation.get("classification") or "", PURPLE),
        _card("News", "N/A" if _get_score(news) is None else f"{_get_score(news):.1f}/100", news.get("classification") or "", AMBER),
        _card("Risk/Safety", "N/A" if _get_score(risk) is None else f"{_get_score(risk):.1f}/100", risk.get("classification") or "", RED),
    ]))
    # The key investment thesis and main risks are already integrated into the
    # snapshot summary box above. Keeping them there prevents the first page
    # from overflowing into an unintended extra page.

    # -------------------------------------------------------------------------
    # PAGE 2 - TECHNICAL ANALYSIS
    # -------------------------------------------------------------------------
    story.append(PageBreak())
    story.append(_section_title("Phân tích kỹ thuật", "Giá + MA, RSI, MACD và thanh khoản"))
    story.append(Spacer(1, 2 * mm))
    story.append(_card_row([
        _card("Close", _fmt_price(technical.get("close", market.get("close"))), "Giá gần nhất", BLUE),
        _card("MA20", _fmt_price(technical.get("ma20")), "20 phiên", BLUE_2),
        _card("MA50", _fmt_price(technical.get("ma50")), "50 phiên", PURPLE),
        _card("RSI(14)", _fmt_num(technical.get("rsi"), 1), "Động lượng", AMBER),
        _card("Volume Ratio", _fmt_x(technical.get("volume_ratio")), "So với MA20", TEAL),
    ]))
    story.append(Spacer(1, 3 * mm))
    price_ma = _chart_price_ma(tech_df, CONTENT_W, 49 * mm)
    if price_ma:
        story.append(price_ma)
    story.append(Spacer(1, 2 * mm))
    rsi = _chart_rsi(tech_df, CONTENT_W / 2 - 2 * mm, 33 * mm)
    macd = _chart_macd(tech_df, CONTENT_W / 2 - 2 * mm, 33 * mm)
    twin = Table([[rsi or _P("Không có RSI", STYLE_SMALL), macd or _P("Không có MACD", STYLE_SMALL)]], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    twin.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1)]))
    story.append(twin)
    story.append(Spacer(1, 2 * mm))
    volume = _chart_volume(tech_df, CONTENT_W, 26 * mm)
    if volume:
        story.append(volume)
    story.append(Spacer(1, 2 * mm))
    sigs = technical.get("signals", {}) or {}
    tech_rows: List[List[Any]] = [["Chỉ báo", "Tín hiệu"]]
    for key in ("MA", "RSI", "MACD", "Volume"):
        sig = sigs.get(key)
        if isinstance(sig, dict):
            tech_rows.append([key, _translate_signal(sig.get("signal"))])
    if len(tech_rows) > 1:
        story.append(_data_table(tech_rows, [CONTENT_W * 0.55, CONTENT_W * 0.45], font_size=8.2, align_numeric_from=2))
        story.append(Spacer(1, 2 * mm))
    story.append(_analysis_box(
        "Phân tích kỹ thuật",
        _technical_interpretation(technical, market),
        accent=BLUE,
        bg=colors.HexColor("#EEF6FF"),
    ))

    # -------------------------------------------------------------------------
    # PAGE 3 - RISK & DRAWDOWN
    # -------------------------------------------------------------------------
    story.append(PageBreak())
    story.append(_section_title("Rủi ro thị trường & thanh khoản", "Drawdown, volatility và tín hiệu rủi ro"))
    story.append(Spacer(1, 2 * mm))
    rm = risk.get("metrics", {}) or {}
    story.append(_card_row([
        _card("Risk/Safety Score", "N/A" if _get_score(risk) is None else f"{_get_score(risk):.1f}/100", risk.get("classification") or "", RED),
        _card("Volatility 20", _fmt_pct(rm.get("volatility_20_annualized", technical.get("volatility")), 1), "Thường niên hóa", AMBER),
        _card("Maximum Drawdown", _fmt_pct(rm.get("max_drawdown_period"), 1), "Kỳ phân tích", RED),
        _card("Volume Ratio", _fmt_x(technical.get("volume_ratio")), "Thanh khoản", TEAL),
        _card("Quan sát", _fmt_num(rm.get("observations", len(tech_df)), 0), "Phiên dữ liệu", BLUE),
    ]))
    story.append(Spacer(1, 3 * mm))
    dd = _chart_drawdown(tech_df, CONTENT_W / 2 - 2 * mm, 67 * mm)
    vol_chart = _chart_rolling_volatility(tech_df, CONTENT_W / 2 - 2 * mm, 67 * mm)
    risk_charts = Table([[
        dd or _P("Không có Drawdown", STYLE_SMALL),
        vol_chart or _P("Không có Volatility", STYLE_SMALL),
    ]], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    risk_charts.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(risk_charts)
    story.append(Spacer(1, 3 * mm))

    range_text = (
        f"Đỉnh 52 tuần: {_fmt_price(market.get('high_52w'))} | "
        f"Đáy 52 tuần: {_fmt_price(market.get('low_52w'))} | "
        f"Giá hiện tại: {_fmt_price(market.get('close'))}"
    )
    story.append(_analysis_box("Biên độ 52 tuần & thanh khoản", range_text, accent=TEAL, bg=colors.HexColor("#ECFAF7")))
    story.append(Spacer(1, 2 * mm))

    signals = technical.get("signals", {}) or {}
    signal_rows: List[List[Any]] = [["Chỉ báo", "Tín hiệu", "Giá trị / ghi chú"]]
    for key in ("MA", "RSI", "MACD", "Volume", "Volatility"):
        sig = signals.get(key)
        if not isinstance(sig, dict):
            continue
        value = sig.get("value")
        if isinstance(value, dict):
            value_text = ", ".join(f"{k}: {_fmt_num(v, 2)}" for k, v in value.items())
        else:
            value_text = _fmt_num(value, 2) if _finite(value) is not None else str(value or "-")
        signal_rows.append([key, _translate_signal(sig.get("signal") or "-"), value_text])
    if len(signal_rows) > 1:
        story.append(_data_table(signal_rows, [34 * mm, 34 * mm, CONTENT_W - 68 * mm], font_size=8.7, align_numeric_from=3))
    story.append(Spacer(1, 2 * mm))
    story.append(_analysis_box(
        "Nhận định rủi ro",
        _risk_interpretation(risk, market),
        accent=RED,
        bg=RED_BG,
    ))

    # -------------------------------------------------------------------------
    # PAGE 4 - FINANCIAL PERFORMANCE
    # -------------------------------------------------------------------------
    story.append(PageBreak())
    story.append(_section_title("Kết quả kinh doanh & hiệu quả sinh lời", "Revenue/LNST và ROE/ROA theo lịch sử"))
    story.append(Spacer(1, 2 * mm))
    fm = fundamental.get("metrics", {}) or {}
    story.append(_card_row([
        _card("Fundamental Score", "N/A" if _get_score(fundamental) is None else f"{_get_score(fundamental):.1f}/100", fundamental.get("classification") or "", TEAL),
        _card("Doanh thu", _fmt_money(financial.get("totalRevenue")), f"Kỳ {report_period}", BLUE),
        _card("LNST", _fmt_money(financial.get("netIncomeToCommon")), f"Kỳ {report_period}", GREEN),
        _card("ROE", _fmt_pct(fm.get("roe", financial.get("returnOnEquity")), 1), "Sinh lời VCSH", PURPLE),
        _card("ROA", _fmt_pct(fm.get("roa", financial.get("returnOnAssets")), 1), "Sinh lời tài sản", AMBER),
    ]))
    story.append(Spacer(1, 3 * mm))
    rp = _chart_revenue_profit(history, CONTENT_W, 46 * mm)
    if rp:
        story.append(rp)
    story.append(Spacer(1, 2 * mm))
    rr = _chart_roe_roa(history, CONTENT_W, 31 * mm)
    if rr:
        story.append(rr)
    story.append(Spacer(1, 2 * mm))
    ht = _financial_performance_table(history)
    if ht:
        story.append(ht)
    story.append(Spacer(1, 2 * mm))
    story.append(_analysis_box(
        "Phân tích kết quả kinh doanh",
        _financial_interpretation(history, fundamental) + " " + (fundamental.get("commentary") or ""),
        accent=TEAL,
        bg=colors.HexColor("#ECFAF7"),
    ))

    # -------------------------------------------------------------------------
    # PAGE 5 - BALANCE SHEET / FINANCIAL HEALTH
    # -------------------------------------------------------------------------
    story.append(PageBreak())
    story.append(_section_title("Bảng cân đối & sức khỏe tài chính", "Tài sản, vốn chủ, đòn bẩy và dòng tiền"))
    story.append(Spacer(1, 2 * mm))
    story.append(_card_row([
        _card("Tổng tài sản", _fmt_money(financial.get("totalAssets")), f"Kỳ {report_period}", BLUE),
        _card("Vốn chủ sở hữu", _fmt_money(financial.get("totalStockholderEquity") or financial.get("totalEquity")), f"Kỳ {report_period}", TEAL),
        _card("Debt/Equity", _fmt_x(fm.get("debt_to_equity", financial.get("debtToEquity"))), "Đòn bẩy", RED),
        _card("Current Ratio", _fmt_x(fm.get("current_ratio", financial.get("currentRatio"))), "Thanh khoản", AMBER),
        _card("Operating CF", _fmt_money(financial.get("operatingCashflow")), "Dòng tiền HĐKD", GREEN),
    ]))
    story.append(Spacer(1, 3 * mm))
    ae = _chart_assets_equity(history, CONTENT_W / 2 - 2 * mm, 58 * mm)
    health_chart = _chart_leverage_liquidity(financial, CONTENT_W / 2 - 2 * mm, 58 * mm)
    health_row = Table([[
        ae or _P("Không đủ dữ liệu tài sản/VCSH.", STYLE_SMALL),
        health_chart or _P("Chưa có đủ lịch sử Debt/Equity - Current Ratio.", STYLE_SMALL),
    ]], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    health_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(health_row)
    story.append(Spacer(1, 3 * mm))

    period = _latest_statement_period(financial) or str(report_period)
    income_rows = _select_statement_rows(financial, "income_statement", period, 8)
    balance_rows = _select_statement_rows(financial, "balance_sheet", period, 10)
    left_data = [["KQKD - chỉ tiêu chính", period]] + [[x, _fmt_billion(v, 1)] for x, v in income_rows]
    right_data = [["BCĐKT - chỉ tiêu chính", period]] + [[x, _fmt_billion(v, 1)] for x, v in balance_rows]
    left_table = _data_table(left_data if len(left_data) > 1 else [["KQKD", period], ["Không có dữ liệu", "N/A"]], [61 * mm, 26 * mm], font_size=7.8)
    right_table = _data_table(right_data if len(right_data) > 1 else [["BCĐKT", period], ["Không có dữ liệu", "N/A"]], [61 * mm, 26 * mm], font_size=7.8)
    bst = Table([[left_table, right_table]], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    bst.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1)]))
    story.append(bst)
    story.append(Spacer(1, 2 * mm))
    balance_text = _balance_interpretation(financial, fundamental, history)
    story.append(_analysis_box("Phân tích sức khỏe tài chính", balance_text, accent=TEAL, bg=colors.HexColor("#ECFAF7")))

    # -------------------------------------------------------------------------
    # PAGE 6 - HISTORICAL VALUATION + PEER VALUATION + NEWS
    # -------------------------------------------------------------------------
    story.append(PageBreak())
    story.append(_section_title(
        "Định giá, Peer Valuation & News",
        "So sánh lịch sử doanh nghiệp, doanh nghiệp cùng ngành và bối cảnh tin tức gần đây",
    ))
    story.append(Spacer(1, 1.5 * mm))

    vm = valuation.get("metrics", {}) or {}
    story.append(_card_row([
        _card("Valuation Score", "N/A" if _get_score(valuation) is None else f"{_get_score(valuation):.1f}/100", valuation.get("classification") or "", PURPLE),
        _card("P/E hiện tại", _fmt_x(valuation.get("pe", financial.get("trailingPE"))), "Current", BLUE),
        _card("Median P/E", _fmt_x(valuation.get("historical_pe_median", vm.get("historical_pe_median"))), "Lịch sử", BLUE_2),
        _card("P/B hiện tại", _fmt_x(valuation.get("pb", financial.get("priceToBook"))), "Current", TEAL),
        _card("Median P/B", _fmt_x(valuation.get("historical_pb_median", vm.get("historical_pb_median"))), "Lịch sử", AMBER),
    ]))
    story.append(Spacer(1, 2 * mm))

    val_chart = _chart_valuation(history, CONTENT_W, 31 * mm)
    if val_chart:
        story.append(val_chart)
        story.append(Spacer(1, 1.5 * mm))

    # Peer Valuation is supplementary. It does NOT replace the historical
    # Valuation Score used by scoring.py / Investment Score.
    peer = valuation.get("peer_valuation", {}) or {}
    peer_available = bool(peer.get("data_available"))

    if peer_available:
        peer_score = _finite(valuation.get("peer_score", peer.get("score")))
        peer_fair = _finite(valuation.get("peer_fair_value", peer.get("peer_fair_value")))
        peer_upside = _finite(valuation.get("peer_upside_downside", peer.get("upside_downside")))
        peer_med_pe = _finite(valuation.get("peer_median_pe", peer.get("peer_median_pe")))
        peer_med_pb = _finite(valuation.get("peer_median_pb", peer.get("peer_median_pb")))
        peer_quality = valuation.get("peer_quality_status") or peer.get("peer_quality_status") or "N/A"

        peer_accent = GREEN if (peer_score is not None and peer_score >= 65) else AMBER if (peer_score is not None and peer_score >= 50) else RED
        upside_accent = GREEN if (peer_upside is not None and peer_upside >= 0) else RED if peer_upside is not None else BLUE
        story.append(_card_row([
            _card("Peer Score", "N/A" if peer_score is None else f"{peer_score:.1f}/100", peer.get("classification") or "Peer comparison", peer_accent),
            _card("Peer Fair Value", _fmt_price(peer_fair), "Giá trị hàm ý", PURPLE),
            _card("Upside / Downside", "N/A" if peer_upside is None else f"{peer_upside:+.1%}", "So với giá hiện tại", upside_accent),
            _card("Median P/E peers", _fmt_x(peer_med_pe), "Cùng ngành", BLUE_2),
            _card("Median P/B peers", _fmt_x(peer_med_pb), "Cùng ngành", TEAL),
        ]))
        story.append(Spacer(1, 1.2 * mm))

        weights = peer.get("valuation_weights", {}) or {}
        industry_name = peer.get("industry") or sector or "N/A"
        icb_level = peer.get("industry_icb_level")
        icb_code = peer.get("industry_icb_code")
        requested = peer.get("requested_peers", []) or []
        peers = [x for x in (peer.get("peers", []) or []) if isinstance(x, dict)]
        valid_count = peer.get("peer_count")
        if valid_count is None:
            valid_count = len(peers)
        meta = [f"Ngành: {industry_name}"]
        if icb_level is not None:
            meta.append(f"ICB cấp {icb_level}")
        if icb_code:
            meta.append(f"mã {icb_code}")
        meta.append(f"{valid_count}/{len(requested)} peer hợp lệ" if requested else f"{valid_count} peer hợp lệ")
        if weights.get("label"):
            meta.append(str(weights.get("label")))
        meta.append(f"Quality: {peer_quality}")
        story.append(_P(" • ".join(meta), STYLE_TINY))
        quality_warnings = valuation.get("peer_quality_warnings") or peer.get("peer_quality_warnings") or []
        if quality_warnings:
            warning_line = "Cảnh báo peer: " + "; ".join(str(x) for x in quality_warnings[:3])
            story.append(_P(warning_line, ParagraphStyle("PeerWarnings", parent=STYLE_TINY, fontSize=7.6, leading=9.0, textColor=RED)))
        story.append(Spacer(1, 1.0 * mm))

        quality_map: Dict[str, Dict[str, Any]] = {}
        for q in peer.get("peer_quality", []) or []:
            if isinstance(q, dict):
                quality_map[str(q.get("symbol") or "").upper()] = q

        peer_rows: List[List[Any]] = [["Mã", "P/E", "P/B", "ROE", "Quality"]]
        for row in peers[:5]:
            sym = str(row.get("symbol") or "-").upper()
            q = quality_map.get(sym, {})
            roe = _finite(row.get("roe"))
            peer_rows.append([
                sym,
                _fmt_x(row.get("pe")),
                _fmt_x(row.get("pb")),
                "N/A" if roe is None else f"{roe:.2f}%",
                q.get("status") or "OK",
            ])
        peer_table = _data_table(
            peer_rows if len(peer_rows) > 1 else [["Mã", "P/E", "P/B", "ROE", "Quality"], ["-", "N/A", "N/A", "N/A", "N/A"]],
            [15 * mm, 18 * mm, 18 * mm, 20 * mm, 28 * mm],
            font_size=7.4,
            align_numeric_from=1,
        )
    else:
        peer_table = _analysis_box(
            "Peer Valuation",
            peer.get("commentary") or "Chưa đủ dữ liệu doanh nghiệp cùng ngành để thực hiện Peer Valuation.",
            accent=AMBER,
            bg=AMBER_BG,
            width=99 * mm,
        )

    right_panel_w = CONTENT_W - 101 * mm
    sentiment_w = 31 * mm
    metrics_w = right_panel_w - sentiment_w - 2 * mm
    sentiment = _chart_news_sentiment(news, sentiment_w, 27 * mm)
    news_metrics = _metric_table([
        ("News Score", "N/A" if _get_score(news) is None else f"{_get_score(news):.1f}/100"),
        ("Phân loại", news.get("classification") or "N/A"),
        ("Số bài", str(news.get("article_count", len(news.get("items", []) or [])))),
        ("Nguồn", news.get("source") or "Google News RSS"),
    ], width=metrics_w)
    news_panel = Table([[sentiment or _P("Chưa đủ tin để vẽ sentiment.", STYLE_TINY), news_metrics]], colWidths=[sentiment_w, metrics_w])
    news_panel.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]))

    peer_news = Table([[peer_table, news_panel]], colWidths=[101 * mm, CONTENT_W - 101 * mm])
    peer_news.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(peer_news)
    story.append(Spacer(1, 1.5 * mm))

    article_rows: List[List[Any]] = [["Ngày", "Sentiment", "Nguồn", "Tiêu đề"]]
    for item in (news.get("items", []) or [])[:3]:
        article_rows.append([
            item.get("published") or "-",
            _translate_signal(item.get("sentiment") or "Neutral"),
            item.get("source_name") or "-",
            item.get("title") or "-",
        ])
    if len(article_rows) > 1:
        story.append(_data_table(article_rows, [22 * mm, 24 * mm, 28 * mm, CONTENT_W - 74 * mm], font_size=7.1, align_numeric_from=4))
        story.append(Spacer(1, 1.2 * mm))

    valuation_text = _valuation_interpretation(valuation)
    peer_text = _peer_valuation_interpretation(valuation)
    news_text = _news_interpretation(news)

    def _compact_analysis(title, body, accent, bg, width):
        body = (body or "").strip()
        if len(body) > 360:
            body = body[:357].rsplit(" ", 1)[0] + "..."
        t = Table([
            [_P(title, ParagraphStyle(f"Compact_{title}", parent=STYLE_H2, textColor=accent, fontSize=10.8, leading=12.2))],
            [_P(body or "Chưa có đủ dữ liệu để diễn giải.", ParagraphStyle(f"CompactBody_{title}", parent=STYLE_TINY, fontSize=8.0, leading=9.7, textColor=TEXT))],
        ], colWidths=[width])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#C9DAEA")),
            ("LINEBEFORE", (0, 0), (0, -1), 2.5, accent),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    box_w = CONTENT_W / 3 - 1.2 * mm
    analysis_row = Table([[
        _compact_analysis("Định giá lịch sử", valuation_text, PURPLE, colors.HexColor("#F3F0FF"), box_w),
        _compact_analysis("Peer Valuation", peer_text, BLUE, colors.HexColor("#EEF6FF"), box_w),
        _compact_analysis("News Sentiment", news_text, AMBER, AMBER_BG, box_w),
    ]], colWidths=[CONTENT_W / 3] * 3)
    analysis_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(analysis_row)

    # -------------------------------------------------------------------------
    # PAGE 7 - INVESTMENT SCORE / PROFILES
    # -------------------------------------------------------------------------
    story.append(PageBreak())
    story.append(_section_title("Investment Score & Investor Profiles", "Cấu trúc điểm, mức đóng góp và góc nhìn theo khẩu vị rủi ro"))
    story.append(Spacer(1, 2 * mm))
    comp = _chart_components(summary, CONTENT_W, 52 * mm)
    if comp:
        story.append(comp)
    story.append(Spacer(1, 2 * mm))
    contrib = _chart_contributions(summary, CONTENT_W / 2 - 2 * mm, 38 * mm)
    profiles = _chart_profiles(summary, CONTENT_W / 2 - 2 * mm, 38 * mm)
    cp = Table([[contrib or _P("Không có dữ liệu đóng góp.", STYLE_SMALL), profiles or _P("Không có dữ liệu hồ sơ.", STYLE_SMALL)]], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    cp.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1)]))
    story.append(cp)
    story.append(Spacer(1, 3 * mm))

    story.append(Spacer(1, 1 * mm))
    strongest = summary.get("strongest_component") or {}
    weakest = summary.get("weakest_component") or {}
    driver_text = (
        f"Yếu tố mạnh nhất: {strongest.get('name', 'N/A')} ({_fmt_num(strongest.get('score'), 2)}/100). "
        f"Yếu tố thấp nhất: {weakest.get('name', 'N/A')} ({_fmt_num(weakest.get('score'), 2)}/100). "
        f"{summary.get('commentary') or ''}"
    )
    story.append(_analysis_box("Why This Score?", _score_interpretation(summary, profile), accent=BLUE, bg=colors.HexColor("#EEF6FF")))
    story.append(Spacer(1, 2 * mm))
    score_insights = Table([[
        _bullet_box("Yếu tố hỗ trợ", positives[:3], True),
        _bullet_box("Yếu tố kéo điểm xuống", risks[:3], False),
    ]], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    score_insights.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.append(score_insights)
    story.append(Spacer(1, 2 * mm))
    profile_score = _finite((summary.get("profile_scores") or {}).get(profile))
    profile_label = (summary.get("profile_labels") or {}).get(profile) or _score_label(profile_score)
    conclusion_text = (
        f"Theo hồ sơ {profile.lower()}, StockLens ghi nhận điểm { _fmt_num(profile_score, 2) }/100, "
        f"xếp loại {profile_label}. {summary.get('commentary') or driver_text} "
        "Điểm số là công cụ tổng hợp dữ liệu và không thay thế quyết định đầu tư độc lập."
    )
    story.append(_analysis_box("Kết luận theo hồ sơ nhà đầu tư", conclusion_text, accent=NAVY, bg=colors.HexColor("#F4F8FC")))

    # -------------------------------------------------------------------------
    # PAGE 8 - FINANCIAL STATEMENT APPENDIX + METHOD
    # -------------------------------------------------------------------------
    story.append(PageBreak())
    period = _latest_statement_period(financial) or str(report_period)
    story.append(_section_title(f"Phụ lục BCTC - kỳ {period}", "Trích các chỉ tiêu trọng yếu từ vnstock/KBS"))
    story.append(Spacer(1, 2 * mm))

    income = _statement_mini_table(financial, "income_statement", "KẾT QUẢ KINH DOANH", period, 11, ratios=False)
    balance = _statement_mini_table(financial, "balance_sheet", "BẢNG CÂN ĐỐI KẾ TOÁN", period, 12, ratios=False)
    cash = _statement_mini_table(financial, "cash_flow", "LƯU CHUYỂN TIỀN TỆ", period, 10, ratios=False)
    ratios = _statement_mini_table(financial, "ratios", "CHỈ SỐ TÀI CHÍNH", period, 11, ratios=True)
    grid = Table([[income, balance], [cash, ratios]], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1.2),
        ("TOPPADDING", (0, 0), (-1, -1), 1.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2),
    ]))
    story.append(grid)
    story.append(Spacer(1, 3 * mm))

    method_rows = [
        ["Khối", "Nguồn / phương pháp"],
        ["Giá & kỹ thuật", "DNSE OpenAPI; MA20, MA50, RSI(14), MACD(12,26,9), Volume/MA20, Volatility và Drawdown."],
        ["BCTC & cơ bản", "vnstock/KBS; ROE, ROA, biên lợi nhuận, tăng trưởng, Debt/Equity, Current Ratio; không tự điền dữ liệu thiếu."],
        ["Định giá & News", "P/E, P/B so với lịch sử doanh nghiệp; Peer Valuation theo median P/E/P/B cùng ngành khi đủ dữ liệu; Google News RSS và sentiment heuristic."],
        ["Investment Score", "25% Fundamental + 25% Valuation + 25% Technical + 15% News + 10% Risk/Safety."],
    ]
    story.append(_data_table(method_rows, [39 * mm, CONTENT_W - 39 * mm], font_size=8.2, align_numeric_from=2))
    story.append(Spacer(1, 2 * mm))
    story.append(_Phtml(
        "<b>Giới hạn & disclaimer:</b> Investment Score là mô hình heuristic phục vụ học tập. "
        "StockLens không tạo target price hoặc peer multiples khi dữ liệu không đủ. Peer Fair Value và upside/downside chỉ được hiển thị khi có bộ peer cùng ngành khả dụng và là giá trị hàm ý tương đối, không phải giá mục tiêu. "
        "News Score không phải NLP toàn văn. Dữ liệu bên thứ ba có thể thay đổi hoặc thiếu; báo cáo hiển thị N/A thay vì bịa số liệu. "
        "Nội dung không cấu thành khuyến nghị mua, bán, nắm giữ chứng khoán hoặc tư vấn đầu tư cá nhân.",
        STYLE_TINY,
    ))

    return story


def _filter_story_by_sections(
    full_story: List[Any],
    sections: set[str],
) -> Tuple[List[Any], int]:
    """Lọc báo cáo theo lựa chọn trên giao diện.

    Mapping trang của báo cáo đầy đủ:
      0 Research Snapshot (luôn giữ)
      1 Technical Dashboard
      2 Risk & Liquidity
      3 Financial Performance
      4 Balance Sheet & Financial Health
      5 Valuation & News
      6 Investment Score
      7 Financial Appendix & Method
    """
    pages: List[List[Any]] = [[]]
    for item in full_story:
        if isinstance(item, PageBreak):
            if pages[-1]:
                pages.append([])
        else:
            pages[-1].append(item)

    pages = [page for page in pages if page]
    if not pages:
        return full_story, 1

    selected_page_indexes = {0}
    if "technical" in sections:
        selected_page_indexes.update({1, 2})
    if "fundamental" in sections:
        selected_page_indexes.update({3, 4})
    if "valuation" in sections or "news" in sections:
        selected_page_indexes.add(5)
    if "score" in sections:
        selected_page_indexes.add(6)
    if "method" in sections:
        selected_page_indexes.add(7)

    selected_page_indexes = sorted(
        i for i in selected_page_indexes if 0 <= i < len(pages)
    )

    filtered_story: List[Any] = []
    for pos, page_index in enumerate(selected_page_indexes):
        filtered_story.extend(pages[page_index])
        if pos < len(selected_page_indexes) - 1:
            filtered_story.append(PageBreak())

    return filtered_story, max(1, len(selected_page_indexes))


# =============================================================================
# 7. PUBLIC API - COMPATIBLE WITH APP.PY
# =============================================================================
def generate_pdf(
    ticker: str,
    period_text: str,
    results: Dict[str, Any],
    summary: Dict[str, Any],
    sections: Optional[Iterable[str]] = None,
    profile: str = "Cân bằng",
    company_info: Optional[Dict[str, Any]] = None,
    financial_data: Optional[Dict[str, Any]] = None,
) -> bytes:
    """Tạo PDF StockLens theo đúng các mục người dùng đã chọn.

    Research Snapshot luôn được giữ. Nếu ``sections`` là ``None`` thì tạo
    báo cáo đầy đủ; nếu là danh sách rỗng thì chỉ tạo Research Snapshot.
    """
    ticker = str(ticker or "").strip().upper().split(".")[0]
    if not ticker:
        raise ValueError("Ticker không được để trống.")

    results = results or {}
    summary = summary or {}
    company = company_info or {}
    financial = financial_data or _load_financial_data(ticker) or {}
    selected = _normalize_sections(sections)

    full_story = _build_story(
        ticker=ticker,
        period_text=period_text,
        results=results,
        summary=summary,
        sections=selected,
        profile=profile,
        company=company,
        financial=financial,
    )
    story, total_pages = _filter_story_by_sections(full_story, selected)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=LEFT,
        rightMargin=RIGHT,
        topMargin=TOP,
        bottomMargin=BOTTOM,
        title=f"StockLens - {ticker}",
        author="StockLens",
        subject="Báo cáo phân tích cổ phiếu",
    )
    doc._stocklens_total_pages = total_pages
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    pdf = buf.getvalue()
    buf.close()
    return pdf


def generate_report(
    output_path: str,
    ticker: str,
    period_text: str,
    results: Dict[str, Any],
    summary: Dict[str, Any],
    sections: Optional[Iterable[str]] = None,
    profile: str = "Cân bằng",
    company_info: Optional[Dict[str, Any]] = None,
    financial_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Convenience wrapper that writes ``generate_pdf`` bytes to disk."""
    pdf = generate_pdf(
        ticker=ticker,
        period_text=period_text,
        results=results,
        summary=summary,
        sections=sections,
        profile=profile,
        company_info=company_info,
        financial_data=financial_data,
    )
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf)
    return str(path)


# =============================================================================
# 8. DIRECT DEMO TEST
# =============================================================================
if __name__ == "__main__":
    rng = np.random.default_rng(42)
    dates = pd.date_range("2026-01-02", periods=190, freq="B")
    close = 82_000 + np.cumsum(rng.normal(0, 700, len(dates)))
    df = pd.DataFrame({
        "Date": dates,
        "Open": close + rng.normal(0, 250, len(dates)),
        "High": close + rng.uniform(250, 900, len(dates)),
        "Low": close - rng.uniform(250, 900, len(dates)),
        "Close": close,
        "Volume": rng.integers(2_000_000, 10_000_000, len(dates)),
    })
    df = _ensure_technical_columns(df)

    # Minimal fake raw BCTC tables to verify the appendix layout.
    income_raw = pd.DataFrame({
        "item": ["Doanh thu thuần", "Lợi nhuận gộp", "Lợi nhuận trước thuế", "Lợi nhuận sau thuế"],
        "item_id": ["revenue", "gross_profit", "profit_before_tax", "net_profit"],
        "2025": [70e12, 26e12, 14e12, 11.2e12],
    })
    balance_raw = pd.DataFrame({
        "item": ["Tài sản ngắn hạn", "Tài sản dài hạn", "Tổng cộng tài sản", "Nợ ngắn hạn", "Nợ dài hạn", "Nợ phải trả", "Vốn chủ sở hữu"],
        "item_id": ["current_assets", "long_term_assets", "total_assets", "current_liabilities", "long_term_liabilities", "total_liabilities", "owners_equity_2"],
        "2025": [58e12, 30e12, 88e12, 41e12, 3e12, 44e12, 44e12],
    })
    cash_raw = pd.DataFrame({
        "item": ["Lưu chuyển tiền thuần từ HĐKD", "Lưu chuyển tiền thuần từ HĐĐT", "Lưu chuyển tiền thuần từ HĐTC"],
        "item_id": ["net_cash_flow_from_operating_activities", "net_cash_flow_from_investing_activities", "net_cash_flow_from_financing_activities"],
        "2025": [10.1e12, -5.2e12, -1.1e12],
    })
    ratios_raw = pd.DataFrame({
        "item": ["P/E", "P/B", "ROE", "ROA", "Nợ/VCSH"],
        "item_id": ["pe_ratio", "pb_ratio", "roe", "roa", "debt_to_equity"],
        "2025": [14.64, 3.33, 27.24, 10.08, 48.84],
    })

    financial_demo = {
        "name": "Doanh nghiệp Demo",
        "exchange": "HOSE",
        "sector": "Demo",
        "reportPeriod": "2025",
        "totalRevenue": 70e12,
        "netIncomeToCommon": 11.2e12,
        "totalAssets": 88e12,
        "totalStockholderEquity": 44e12,
        "returnOnEquity": 0.2724,
        "returnOnAssets": 0.1008,
        "debtToEquity": 0.4884,
        "currentRatio": 1.40,
        "trailingPE": 14.64,
        "priceToBook": 3.33,
        "operatingCashflow": 10.1e12,
        "financialHistory": [
            {"period": "2022", "revenue": 44e12, "gross_profit": 17e12, "net_profit": 6.5e12, "total_assets": 51e12, "equity": 25e12, "roe": 0.283, "roa": 0.117, "pe": 15.91, "pb": 3.73},
            {"period": "2023", "revenue": 52e12, "gross_profit": 20e12, "net_profit": 7.8e12, "total_assets": 60e12, "equity": 30e12, "roe": 0.287, "roa": 0.119, "pe": 26.74, "pb": 6.28},
            {"period": "2024", "revenue": 63e12, "gross_profit": 24e12, "net_profit": 9.4e12, "total_assets": 72e12, "equity": 36e12, "roe": 0.281, "roa": 0.116, "pe": 17.56, "pb": 4.08},
            {"period": "2025", "revenue": 70e12, "gross_profit": 26e12, "net_profit": 11.2e12, "total_assets": 88e12, "equity": 44e12, "roe": 0.2724, "roa": 0.1008, "pe": 14.64, "pb": 3.33},
        ],
        "_raw": {
            "income_statement": income_raw,
            "balance_sheet": balance_raw,
            "cash_flow": cash_raw,
            "ratios": ratios_raw,
        },
    }

    technical_demo = {
        "data_available": True,
        "score": 37.5,
        "label": "Thận trọng",
        "data": df,
        "close": float(df.iloc[-1]["Close"]),
        "ma20": float(df.iloc[-1]["MA20"]),
        "ma50": float(df.iloc[-1]["MA50"]),
        "rsi": float(df.iloc[-1]["RSI"]),
        "volume_ratio": float(df.iloc[-1]["Volume"] / df.iloc[-1]["AvgVolume20"]),
        "volatility": float(df.iloc[-1]["Volatility20"]),
        "signals": {
            "MA": {"signal": "Negative", "value": {"close": float(df.iloc[-1]["Close"]), "ma20": float(df.iloc[-1]["MA20"]), "ma50": float(df.iloc[-1]["MA50"])}},
            "RSI": {"signal": "Positive", "value": float(df.iloc[-1]["RSI"])},
            "MACD": {"signal": "Negative", "value": float(df.iloc[-1]["MACD"])},
            "Volume": {"signal": "Neutral", "value": float(df.iloc[-1]["Volume"])},
            "Volatility": {"signal": "Neutral", "value": float(df.iloc[-1]["Volatility20"])},
        },
        "positives": ["RSI chưa nằm trong vùng quá mua hoặc quá bán."],
        "risks": ["Xu hướng giá và MACD đang yếu."],
        "commentary": "Technical Score thấp cho thấy động lượng ngắn hạn chưa thuận lợi.",
    }
    fundamental_demo = {
        "data_available": True,
        "score": 94.0,
        "classification": "Nền tảng cơ bản mạnh",
        "metrics": {"roe": 0.2724, "roa": 0.1008, "profit_margin": 0.1475, "revenue_growth": 0.1156, "debt_to_equity": 0.4884, "current_ratio": 1.40},
        "positives": ["ROE cao và hiệu quả sử dụng vốn tốt.", "Doanh thu duy trì tăng trưởng tích cực."],
        "risks": [],
        "commentary": "Nền tảng tài chính mạnh và khả năng sinh lời tích cực.",
    }
    valuation_demo = {
        "data_available": True,
        "score": 83.0,
        "classification": "Định giá tương đối hấp dẫn",
        "pe": 14.64,
        "pb": 3.33,
        "historical_pe_median": 17.56,
        "historical_pb_median": 4.08,
        "positives": ["P/E và P/B hiện tại thấp hơn median lịch sử."],
        "risks": [],
        "commentary": "Định giá hiện tại tương đối hấp dẫn so với lịch sử của chính doanh nghiệp.",
        "peer_score": 37.5,
        "peer_fair_value": 50812.96,
        "peer_upside_downside": -0.1224,
        "peer_median_pe": 12.69,
        "peer_median_pb": 0.60,
        "peer_quality_status": "Cần thận trọng",
        "peer_quality_warnings": [
            "Chỉ có 3 peer hợp lệ.",
            "2/5 peer thiếu P/E hoặc P/B.",
            "HIG có ROE âm.",
        ],
        "peer_risks": ["P/E và đặc biệt P/B của cổ phiếu đang cao hơn median peer cùng ngành."],
        "peer_positives": [],
        "peer_valuation": {
            "data_available": True,
            "score": 37.5,
            "classification": "Định giá cao so với peers",
            "peer_fair_value": 50812.96,
            "upside_downside": -0.1224,
            "peer_median_pe": 12.69,
            "peer_median_pb": 0.60,
            "eps": 5251.94,
            "bvps": 23110.99,
            "implied_price_pe": 66647.12,
            "implied_price_pb": 13866.59,
            "industry": "Phần mềm",
            "industry_icb_level": 4,
            "industry_icb_code": "9537",
            "requested_peers": ["CMT", "CNX", "HIG", "HPT", "ICT"],
            "peer_count": 3,
            "valuation_weights": {"pe": 0.7, "pb": 0.3, "label": "P/E 70% + P/B 30% (ngành Phần mềm)"},
            "peer_quality_status": "Cần thận trọng",
            "peer_quality_warnings": ["Chỉ có 3 peer hợp lệ.", "2/5 peer thiếu P/E/P/B.", "HIG có ROE âm."],
            "peer_quality": [
                {"symbol": "CMT", "status": "OK", "flags": []},
                {"symbol": "HIG", "status": "Cảnh báo", "flags": ["ROE âm"]},
                {"symbol": "ICT", "status": "OK", "flags": []},
            ],
            "peers": [
                {"symbol": "CMT", "name": "CMT", "pe": 4.54, "pb": 0.50, "roe": 2.07},
                {"symbol": "HIG", "name": "HIG", "pe": 29.80, "pb": 0.60, "roe": -1.18},
                {"symbol": "ICT", "name": "ICT", "pe": 12.69, "pb": 0.66, "roe": 0.71},
            ],
            "commentary": "Peer Valuation cho thấy định giá hiện tại cao hơn median peer, nhưng bộ peer còn nhỏ nên cần thận trọng khi diễn giải.",
        },
    }
    news_demo = {
        "data_available": True,
        "score": 40.56,
        "classification": "Tin tức cần thận trọng",
        "sentiment_counts": {"Positive": 2, "Neutral": 2, "Negative": 6},
        "article_count": 10,
        "source": "Google News RSS",
        "items": [
            {"published": "2026-10-09", "sentiment": "Negative", "source_name": "MoneyF", "title": "Cổ phiếu chịu áp lực ngắn hạn và nguy cơ rời rổ chỉ số"},
            {"published": "2026-10-08", "sentiment": "Positive", "source_name": "Index.vn", "title": "Cổ phiếu được khuyến nghị theo dõi"},
            {"published": "2026-10-07", "sentiment": "Negative", "source_name": "CafeF", "title": "Giá giảm nhiều phiên liên tiếp"},
        ],
        "positives": ["Có một số khuyến nghị tích cực."],
        "risks": ["Tin tức ngắn hạn đang thiên về tiêu cực."],
        "commentary": "Sentiment gần đây ở mức thận trọng.",
    }
    risk_demo = {
        "data_available": True,
        "score": 50.0,
        "classification": "Rủi ro thị trường trung bình",
        "metrics": {"volatility_20_annualized": float(df.iloc[-1]["Volatility20"]), "max_drawdown_period": -0.4057, "observations": len(df)},
        "positives": [],
        "risks": ["Maximum Drawdown của kỳ phân tích ở mức cao."],
        "commentary": "Rủi ro thị trường ở mức trung bình, cần theo dõi drawdown và volatility.",
    }
    results_demo = {"technical": technical_demo, "fundamental": fundamental_demo, "valuation": valuation_demo, "news": news_demo, "risk": risk_demo}
    summary_demo = {
        "score": 64.71,
        "investment_score": 64.71,
        "label": "Trung lập",
        "classification": "Trung lập",
        "component_scores": {"fundamental": 94, "valuation": 83, "technical": 37.5, "news": 40.56, "risk": 50},
        "contributions": {"fundamental": 23.5, "valuation": 20.75, "technical": 9.38, "news": 6.08, "risk": 5.0},
        "weights": {"fundamental": 0.25, "valuation": 0.25, "technical": 0.25, "news": 0.15, "risk": 0.10},
        "profile_scores": {"Thận trọng": 64.78, "Cân bằng": 64.71, "Tăng trưởng": 65.18},
        "profile_labels": {"Thận trọng": "Trung lập", "Cân bằng": "Trung lập", "Tăng trưởng": "Tích cực"},
        "strongest_component": {"name": "Fundamental", "score": 94},
        "weakest_component": {"name": "Technical", "score": 37.5},
        "commentary": "Fundamental và Valuation hỗ trợ điểm số, trong khi Technical và News kéo giảm Investment Score.",
    }

    path = generate_report(
        output_path="StockLens_report_peer_demo.pdf",
        ticker="DEMO",
        period_text="2026-01-01 -> 2026-10-09",
        results=results_demo,
        summary=summary_demo,
        sections=["technical", "fundamental", "valuation", "news", "score", "method"],
        profile="Cân bằng",
        company_info={"name": "Doanh nghiệp Demo", "exchange": "HOSE", "sector": "Demo"},
        financial_data=financial_demo,
    )
    print(path)
