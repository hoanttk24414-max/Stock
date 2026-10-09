"""StockLens - multi-ticker investment research dashboard.

UI direction: a clean securities-research portal inspired by the supplied visual
reference, while keeping an original StockLens identity and the existing analysis
modules. One run analyzes one ticker; users can immediately switch to another.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import html
import math
import base64
import mimetypes

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from market_data import get_market_data
from src.technical_analysis import analyze_technical
from src.vnstock_data import get_financial_data
from src.fundamental_analysis import analyze_fundamental
from src.valuation import analyze_valuation
from src.news_analysis import analyze_news
from src.scoring import market_risk, score_all
from src.report import generate_pdf


# -----------------------------------------------------------------------------
# Page + visual system
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="StockLens | Investment Intelligence",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
<style>
:root{
  --navy:#0B2B55;
  --blue:#176FD1;
  --blue2:#2A8BEB;
  --teal:#11B7AE;
  --purple:#8B7CF6;
  --pink:#E98AB8;
  --amber:#E99A19;
  --red:#E05262;
  --green:#16A36F;
  --text:#173150;
  --muted:#6B7F99;
  --line:#D7E5F3;
  --surface:rgba(255,255,255,.91);
  --surface-strong:#FFFFFF;
  --shadow:0 14px 34px rgba(35,75,125,.09);
}

html,body,[class*="css"]{font-family:Inter,"Segoe UI",Arial,sans-serif}
.stApp{
  color:var(--text);
  background:
    radial-gradient(circle at 8% 5%, rgba(83,174,255,.22), transparent 25%),
    radial-gradient(circle at 92% 10%, rgba(151,126,246,.17), transparent 27%),
    radial-gradient(circle at 83% 82%, rgba(234,129,184,.12), transparent 30%),
    radial-gradient(circle at 10% 88%, rgba(17,183,174,.10), transparent 28%),
    linear-gradient(135deg,#F3F9FF 0%,#F8F7FF 53%,#FFF8FC 100%);
  background-attachment:fixed;
}
.block-container{max-width:1540px;padding-top:.4rem;padding-bottom:2.4rem}
#MainMenu,footer,header{visibility:hidden}

/* glass top navigation */
.st-key-stocklens_topbar{
  position:sticky;top:0;z-index:999;
  background:rgba(255,255,255,.92);
  backdrop-filter:blur(18px);
  border:1px solid rgba(210,227,244,.92);
  border-radius:0 0 18px 18px;
  box-shadow:0 10px 30px rgba(32,72,118,.08);
  padding:8px 16px 7px;margin-bottom:12px;
}
.st-key-stocklens_topbar div[data-testid="stHorizontalBlock"]{align-items:center}
.sl-brand-wrap{display:flex;align-items:center;gap:10px;min-width:220px;padding-top:2px}
.sl-logo-bars{width:30px;height:29px;display:flex;gap:3px;align-items:flex-end}
.sl-logo-bars i{display:block;width:5px;border-radius:3px 3px 0 0;background:linear-gradient(180deg,#28B9B2 0%,#1A83D7 58%,#0B2B55 100%)}
.sl-logo-bars i:nth-child(1){height:10px}.sl-logo-bars i:nth-child(2){height:17px}.sl-logo-bars i:nth-child(3){height:24px}.sl-logo-bars i:nth-child(4){height:29px}
.sl-brand{font-size:1.45rem;font-weight:900;color:var(--navy);letter-spacing:-.03em;line-height:1}.sl-brand span{color:#1874CC}
.sl-tag{font-size:.60rem;color:#74869C;margin-top:3px}

.st-key-nav_overview button,.st-key-nav_analysis button,.st-key-nav_report button,.st-key-nav_about button{
  min-height:42px!important;border:none!important;border-radius:0!important;
  background:transparent!important;color:#38506E!important;box-shadow:none!important;
  font-size:.80rem!important;font-weight:730!important;padding-left:.45rem!important;padding-right:.45rem!important;
  border-bottom:3px solid transparent!important;
}
.st-key-nav_overview button:hover,.st-key-nav_analysis button:hover,.st-key-nav_report button:hover,.st-key-nav_about button:hover{
  color:#1067C5!important;background:rgba(231,244,255,.58)!important;
}
.st-key-stocklens_topbar div[data-testid="stForm"]{background:transparent!important;border:none!important;box-shadow:none!important;padding:0!important;margin:0!important}
.sl-top-search [data-testid="stTextInput"] input{background:#FAFDFF!important;border:1px solid #D4E3F2!important;border-radius:12px!important;min-height:40px!important}
.sl-top-search button{min-height:40px!important;border-radius:11px!important;background:linear-gradient(110deg,#176FD1,#1597CA)!important;color:#fff!important;border:none!important}

/* analysis toolbar */
div[data-testid="stForm"]{
  background:rgba(255,255,255,.88);
  backdrop-filter:blur(12px);
  border:1px solid rgba(210,227,244,.95)!important;
  border-radius:16px;padding:12px 16px 7px;
  box-shadow:var(--shadow);margin-bottom:12px;
}
.sl-search-title{font-size:.90rem;font-weight:850;color:var(--navy);margin-bottom:2px}.sl-search-sub{font-size:.72rem;color:var(--muted);margin-bottom:7px}
.stTextInput input,.stDateInput input,[data-baseweb="select"]>div{border-radius:10px!important;background:rgba(249,252,255,.96)!important}
.stButton>button,.stDownloadButton>button{border-radius:10px!important;font-weight:760!important;min-height:40px}
.stButton>button[kind="primary"],.stDownloadButton>button[kind="primary"]{
  background:linear-gradient(110deg,#176FD1 0%,#1493CC 60%,#11B7AE 100%)!important;
  border:none!important;color:#fff!important;box-shadow:0 8px 18px rgba(23,111,209,.18)!important;
}

/* company hero */
.sl-company{
  background:
    radial-gradient(circle at 82% 20%,rgba(255,255,255,.86),transparent 36%),
    linear-gradient(112deg,rgba(219,239,255,.96) 0%,rgba(234,241,255,.96) 47%,rgba(247,232,249,.90) 100%);
  border:1px solid #CFE0F1;border-radius:18px;padding:15px 18px;box-shadow:var(--shadow);
  margin:3px 0 11px;display:flex;align-items:center;gap:15px;position:relative;overflow:hidden;
}
.sl-company:after{content:"";position:absolute;right:-35px;bottom:-54px;width:190px;height:120px;border-radius:50%;background:rgba(65,176,218,.09)}
.sl-company-logo{height:66px;width:66px;min-width:66px;border-radius:16px;background:#fff;border:1px solid rgba(255,255,255,.95);box-shadow:0 8px 20px rgba(32,75,122,.12);display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative;z-index:2}
.sl-company-logo img{width:50px;height:50px;object-fit:contain}.sl-ticker-logo{height:66px;width:66px;border-radius:16px;background:linear-gradient(145deg,#0B4B8B,#1A87DF);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:900;font-size:1.15rem}
.sl-company-main{flex:1;position:relative;z-index:2}.sl-company-title{font-size:1.36rem;font-weight:900;color:var(--navy);letter-spacing:-.02em}.sl-company-name{font-size:.82rem;font-weight:680;color:#385576;margin-top:2px}.sl-meta{font-size:.69rem;color:#637992;margin-top:6px}
.sl-price-panel{min-width:255px;display:grid;grid-template-columns:1.05fr .95fr;gap:10px;position:relative;z-index:2}
.sl-price-card{background:rgba(255,255,255,.84);border:1px solid rgba(204,221,239,.92);border-radius:13px;padding:10px 12px}.sl-price-label{font-size:.62rem;color:#70849B;font-weight:700}.sl-price-value{font-size:1.45rem;font-weight:900;color:#0C3C73;margin-top:3px}.sl-price-change{font-size:.68rem;margin-top:3px;font-weight:730}.sl-mini-stats{font-size:.64rem;color:#61758D;line-height:1.75}.sl-mini-stats b{float:right;color:#183D68}

/* secondary nav appearance */
.stTabs [data-baseweb="tab-list"]{gap:1px;background:rgba(255,255,255,.88);border:1px solid #D7E5F3;border-radius:13px;padding:4px 7px;box-shadow:0 8px 22px rgba(35,75,125,.06)}
.stTabs [data-baseweb="tab"]{height:42px;border-radius:9px;padding:0 16px;font-size:.78rem;color:#536982}
.stTabs [aria-selected="true"]{background:linear-gradient(110deg,#E7F3FF,#F1EBFF)!important;color:#0F67C0!important;border-bottom:2px solid #176FD1!important}

/* cards */
.sl-kpi{background:rgba(255,255,255,.91);border:1px solid #D8E5F2;border-radius:16px;padding:13px 14px;min-height:106px;box-shadow:0 10px 26px rgba(35,75,125,.07);position:relative;overflow:hidden}
.sl-kpi:after{content:"";position:absolute;right:-20px;top:-22px;width:72px;height:72px;border-radius:50%;background:linear-gradient(145deg,rgba(203,232,255,.65),rgba(244,226,249,.45))}
.sl-kpi:nth-child(2n):after{background:linear-gradient(145deg,rgba(234,225,255,.65),rgba(255,224,239,.42))}
.sl-kpi-label{font-size:.69rem;color:#526B87;font-weight:760}.sl-kpi-value{font-size:1.48rem;color:var(--navy);font-weight:900;margin-top:8px;line-height:1.05}.sl-kpi-sub{font-size:.68rem;color:#71839A;margin-top:6px}.sl-kpi-good{color:var(--green)}.sl-kpi-warn{color:var(--amber)}.sl-kpi-bad{color:var(--red)}
.sl-kpi-blue{background:linear-gradient(125deg,rgba(239,248,255,.96),rgba(217,237,255,.92))}.sl-kpi-purple{background:linear-gradient(125deg,rgba(248,244,255,.96),rgba(230,219,255,.90))}.sl-kpi-pink{background:linear-gradient(125deg,rgba(255,246,250,.96),rgba(251,224,238,.90))}.sl-kpi-mint{background:linear-gradient(125deg,rgba(240,255,251,.96),rgba(215,247,238,.90))}.sl-kpi-amber{background:linear-gradient(125deg,rgba(255,250,239,.96),rgba(255,237,204,.90))}

.sl-panel,.sl-report-rail{background:rgba(255,255,255,.91);border:1px solid #D6E4F2;border-radius:16px;padding:15px 16px;box-shadow:var(--shadow);backdrop-filter:blur(8px)}
.sl-panel-title{font-weight:880;font-size:.97rem;color:var(--navy);margin-bottom:8px}.sl-section-title{font-weight:880;font-size:1.08rem;color:var(--navy);margin:6px 0 11px;border-left:4px solid #1777D1;padding-left:9px}
.sl-score-note{background:linear-gradient(110deg,#EDF7FF,#F6F0FF);border:1px solid #D8E8F6;border-radius:11px;padding:10px 12px;text-align:center;color:#385A7D;font-size:.74rem;line-height:1.45}
.sl-chip{display:inline-block;font-size:.64rem;font-weight:760;padding:4px 8px;border-radius:999px}.sl-chip-green{background:#E4F8EF;color:#0C8858}.sl-chip-amber{background:#FFF2DD;color:#B66B00}.sl-chip-red{background:#FCE8EC;color:#C93F56}.sl-chip-blue{background:#E7F3FF;color:#0D67C6}

/* plotly/dataframe framing */
[data-testid="stPlotlyChart"]{background:linear-gradient(#FFFFFF,#FFFFFF) padding-box,linear-gradient(135deg,#8CC9FF,#A995F7,#E793BD,#62D5C4) border-box;border:1.5px solid transparent;border-radius:18px;padding:8px 8px 14px;box-shadow:0 12px 28px rgba(56,92,145,.10);overflow:visible}
.sl-chart-caption{text-align:center;margin:-2px 0 12px;color:#526C88;font-size:.73rem;font-weight:720;letter-spacing:.01em}
.sl-chart-caption b{color:#173F70}
div[data-testid="stMetric"]{background:rgba(255,255,255,.92);border:1px solid #D6E4F2;padding:10px 12px;border-radius:13px;box-shadow:0 8px 22px rgba(35,75,125,.06)}
div[data-testid="stDataFrame"]{border:1px solid #D7E5F3;border-radius:12px;overflow:hidden;box-shadow:0 7px 18px rgba(35,75,125,.05)}


/* colored metric cards */
.sl-metric-card{
  position:relative;
  overflow:hidden;
  min-height:104px;
  border-radius:15px;
  padding:12px 14px 11px;
  border:1px solid rgba(197,216,236,.82);
  box-shadow:0 9px 24px rgba(35,75,125,.07);
  display:flex;
  flex-direction:column;
  justify-content:center;
}
.sl-metric-card:after{
  content:"";
  position:absolute;
  width:74px;height:74px;
  border-radius:50%;
  right:-24px;top:-28px;
  background:rgba(255,255,255,.42);
}
.sl-metric-label{position:relative;z-index:2;font-size:.66rem;font-weight:780;color:#58708B;letter-spacing:.01em}
.sl-metric-value{position:relative;z-index:2;font-size:1.27rem;font-weight:900;line-height:1.12;margin-top:7px;letter-spacing:-.015em}
.sl-metric-sub{position:relative;z-index:2;font-size:.62rem;line-height:1.35;color:#6C8097;margin-top:5px;min-height:1.1em}

.sl-metric-blue{background:linear-gradient(128deg,#F1F8FF 0%,#DCEEFF 100%);border-color:#C9E2FA}
.sl-metric-blue .sl-metric-value{color:#0E63B7}
.sl-metric-teal{background:linear-gradient(128deg,#F0FFFC 0%,#D8F7F1 100%);border-color:#C5EEE7}
.sl-metric-teal .sl-metric-value{color:#087E78}
.sl-metric-green{background:linear-gradient(128deg,#F0FCF6 0%,#DDF7E9 100%);border-color:#C8EDD9}
.sl-metric-green .sl-metric-value{color:#0E8758}
.sl-metric-purple{background:linear-gradient(128deg,#F8F5FF 0%,#E8E0FF 100%);border-color:#DDD1FB}
.sl-metric-purple .sl-metric-value{color:#6750C7}
.sl-metric-pink{background:linear-gradient(128deg,#FFF7FB 0%,#FBE2EF 100%);border-color:#F2D4E3}
.sl-metric-pink .sl-metric-value{color:#B94C83}
.sl-metric-amber{background:linear-gradient(128deg,#FFF9EF 0%,#FFECCB 100%);border-color:#F5DEB1}
.sl-metric-amber .sl-metric-value{color:#B56B04}
.sl-metric-red{background:linear-gradient(128deg,#FFF5F6 0%,#FCE1E5 100%);border-color:#F2CED4}
.sl-metric-red .sl-metric-value{color:#C53F55}
.sl-metric-slate{background:linear-gradient(128deg,#F7F9FC 0%,#E9EEF5 100%);border-color:#D7E0EA}
.sl-metric-slate .sl-metric-value{color:#40566F}

/* keep cards readable on narrow screens */
@media(max-width:1000px){.sl-metric-card{min-height:92px}.sl-metric-value{font-size:1.12rem}}

/* report page */
.sl-report-shell{background:rgba(255,255,255,.88);border:1px solid #D3E3F1;border-radius:18px;padding:15px;box-shadow:var(--shadow)}
.sl-report-heading{font-size:1.25rem;font-weight:900;color:var(--navy)}.sl-report-sub{font-size:.72rem;color:#72849A;margin-top:3px}
.sl-report-menu{background:rgba(255,255,255,.90);border:1px solid #D6E5F2;border-radius:14px;padding:8px;box-shadow:0 8px 20px rgba(35,75,125,.06)}
.sl-report-menu-item{display:flex;align-items:center;gap:9px;padding:10px 11px;border-radius:10px;font-size:.74rem;font-weight:730;color:#426080;margin-bottom:5px}.sl-report-menu-item.active{background:linear-gradient(110deg,#176FD1,#0E4A8A);color:white}.sl-report-menu-item span:first-child{font-size:1.1rem}
.sl-pdf-frame{background:#29313B;border-radius:13px;padding:8px;box-shadow:0 12px 30px rgba(22,45,75,.14);overflow:hidden}
.sl-report-download-note{font-size:.67rem;color:#7A899B;text-align:center;margin-top:4px}

/* insights */
.sl-insight-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}.sl-insight{background:rgba(255,255,255,.91);border:1px solid #D7E5F3;border-radius:14px;padding:13px;min-height:155px;box-shadow:0 8px 20px rgba(35,75,125,.05)}.sl-insight h4{margin:0 0 9px;color:var(--navy);font-size:.85rem}.sl-insight ul{margin:0;padding-left:17px}.sl-insight li{margin:0 0 5px;font-size:.72rem;color:#44556B;line-height:1.38}.sl-insight-conclusion{background:linear-gradient(120deg,#EDF7FF,#F7F0FF)}

@media(max-width:1000px){.sl-price-panel{display:none}.sl-insight-grid{grid-template-columns:1fr}.st-key-stocklens_topbar{position:static}.sl-brand-wrap{min-width:auto}}
</style>
""",
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def finite(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def fmt_num(value, decimals=2, suffix=""):
    v = finite(value)
    return "N/A" if v is None else f"{v:,.{decimals}f}{suffix}"


def fmt_money(value, currency="VND"):
    v = finite(value)
    if v is None:
        return "N/A"
    if currency == "VND":
        if abs(v) >= 1e12:
            return f"{v/1e12:,.1f} nghìn tỷ VND"
        if abs(v) >= 1e9:
            return f"{v/1e9:,.1f} tỷ VND"
        return f"{v:,.0f} VND"
    if abs(v) >= 1e9:
        return f"{v/1e9:,.2f}B {currency}"
    if abs(v) >= 1e6:
        return f"{v/1e6:,.2f}M {currency}"
    return f"{v:,.2f} {currency}"


def fmt_price(value, currency="VND"):
    v = finite(value)
    if v is None:
        return "N/A"
    return f"{v:,.0f} {currency}" if currency == "VND" else f"{v:,.2f} {currency}"


def fmt_pct(value, digits=1):
    v = finite(value)
    return "N/A" if v is None else f"{v:.{digits}%}"


def ui_score_label(score):
    v = finite(score)
    if v is None:
        return "Chưa đủ dữ liệu", "sl-chip-blue"
    if v >= 80:
        return "Cơ hội cao", "sl-chip-green"
    if v >= 65:
        return "Tích cực", "sl-chip-green"
    if v >= 50:
        return "Trung lập", "sl-chip-amber"
    return "Thận trọng", "sl-chip-red"


def score_class(score):
    v = finite(score)
    if v is None:
        return ""
    if v >= 65:
        return "sl-kpi-good"
    if v >= 50:
        return "sl-kpi-warn"
    return "sl-kpi-bad"


def kpi(label, value, sub="", css_class=""):
    label_text = str(label or "").lower()
    if "technical" in label_text:
        tone = "sl-kpi-purple"
    elif "risk" in label_text or "an toàn" in label_text:
        tone = "sl-kpi-mint"
    elif "đánh giá" in label_text:
        tone = "sl-kpi-amber"
    elif "giá" in label_text:
        tone = "sl-kpi-pink"
    else:
        tone = "sl-kpi-blue"
    return (
        f'<div class="sl-kpi {tone}">'
        f'<div class="sl-kpi-label">{esc(label)}</div>'
        f'<div class="sl-kpi-value {css_class}">{esc(value)}</div>'
        f'<div class="sl-kpi-sub">{esc(sub)}</div>'
        "</div>"
    )


def metric_card(label, value, sub="", tone="blue"):
    """Pastel finance metric card used across analysis tabs."""
    allowed = {"blue", "teal", "green", "purple", "pink", "amber", "red", "slate"}
    tone = tone if tone in allowed else "blue"
    return (
        f'<div class="sl-metric-card sl-metric-{tone}">'
        f'<div class="sl-metric-label">{esc(label)}</div>'
        f'<div class="sl-metric-value">{esc(value)}</div>'
        f'<div class="sl-metric-sub">{esc(sub)}</div>'
        '</div>'
    )


def score_tone(score):
    """Color score cards without changing any scoring formula."""
    value = finite(score)
    if value is None:
        return "slate"
    if value >= 80:
        return "green"
    if value >= 65:
        return "teal"
    if value >= 50:
        return "amber"
    return "red"


def change_tone(value, neutral="blue"):
    """Positive -> green, negative -> red, missing/zero -> neutral."""
    number = finite(value)
    if number is None or abs(number) < 1e-12:
        return neutral
    return "green" if number > 0 else "red"


def quick_row(label, value):
    return f'<div class="sl-quick-row"><span>{esc(label)}</span><span>{esc(value)}</span></div>'


def compact_ticker(user_ticker: str) -> str:
    return (user_ticker or "").strip().upper().split(".")[0]



COMPANY_DOMAINS = {
    "FPT": "fpt.com", "HPG": "hoaphat.com.vn", "MWG": "mwg.vn", "VNM": "vinamilk.com.vn",
    "VCB": "vietcombank.com.vn", "TCB": "techcombank.com", "MBB": "mbbank.com.vn", "ACB": "acb.com.vn",
    "BID": "bidv.com.vn", "CTG": "vietinbank.vn", "VPB": "vpbank.com.vn", "STB": "sacombank.com.vn",
    "HDB": "hdbank.com.vn", "TPB": "tpb.vn", "VIB": "vib.com.vn", "SSI": "ssi.com.vn", "PNJ": "pnj.com.vn",
}


def _local_logo_data_uri(ticker: str):
    base = Path(__file__).resolve().parent
    for folder in (base / "assets" / "logos", base / "assets" / "company_images", base / "logos"):
        for ext in ("png", "jpg", "jpeg", "webp"):
            path = folder / f"{ticker.upper()}.{ext}"
            if path.exists():
                mime = mimetypes.guess_type(path.name)[0] or "image/png"
                encoded = base64.b64encode(path.read_bytes()).decode("ascii")
                return f"data:{mime};base64,{encoded}"
    return None


def company_logo_src(ticker: str, company: dict):
    local = _local_logo_data_uri(ticker)
    if local:
        return local
    website = (company or {}).get("website") or ""
    domain = COMPANY_DOMAINS.get(ticker.upper())
    if not domain and website:
        domain = website.replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")
    if domain:
        return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
    return None


NAV_PAGES = {
    "overview": "Tổng quan",
    "analysis": "Phân tích cổ phiếu",
    "report": "Báo cáo đầu tư",
    "about": "Giới thiệu hệ thống",
}


def get_current_page() -> str:
    page = st.session_state.get("nav_page", "overview")
    if page not in NAV_PAGES:
        page = "overview"
        st.session_state["nav_page"] = page
    return page


def go_to(page: str):
    if page not in NAV_PAGES:
        page = "overview"
    st.session_state["nav_page"] = page
    st.rerun()


def topbar() -> str:
    """Clickable top navigation + real ticker search, preserving session state."""
    current_page = get_current_page()
    active_key = {
        "overview": "nav_overview", "analysis": "nav_analysis",
        "report": "nav_report", "about": "nav_about",
    }.get(current_page, "nav_overview")

    st.markdown(
        f"""
<style>
.st-key-{active_key} button{{
  color:#0F67C0!important;
  border-bottom:3px solid #176FD1!important;
  background:rgba(232,244,255,.62)!important;
}}
</style>
""",
        unsafe_allow_html=True,
    )

    with st.container(key="stocklens_topbar"):
        brand, n1, n2, n3, n4, search_col = st.columns(
            [2.7, 1.05, 1.45, 1.25, 1.50, 3.1], gap="small"
        )
        with brand:
            st.markdown(
                """
<div class="sl-brand-wrap">
  <div class="sl-logo-bars"><i></i><i></i><i></i><i></i></div>
  <div><div class="sl-brand">STOCK<span>LENS</span></div><div class="sl-tag">Investment Intelligence Platform</div></div>
</div>
""",
                unsafe_allow_html=True,
            )

        nav_specs = [
            (n1, "overview", "Tổng quan", "nav_overview"),
            (n2, "analysis", "Phân tích cổ phiếu", "nav_analysis"),
            (n3, "report", "Báo cáo đầu tư", "nav_report"),
            (n4, "about", "Giới thiệu hệ thống", "nav_about"),
        ]
        for col, page_key, label, key in nav_specs:
            with col:
                if st.button(label, key=key, use_container_width=True):
                    go_to(page_key)

        with search_col:
            st.markdown('<div class="sl-top-search">', unsafe_allow_html=True)
            with st.form("topbar_ticker_search", border=False):
                q1, q2 = st.columns([4.4, .8], gap="small")
                with q1:
                    query = st.text_input(
                        "Tìm mã cổ phiếu",
                        value="",
                        placeholder="Tìm mã cổ phiếu (FPT, HPG, MWG...)",
                        label_visibility="collapsed",
                        key="topbar_ticker_query",
                    )
                with q2:
                    search_go = st.form_submit_button("⌕", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)
            if search_go and query.strip():
                st.session_state["ticker_input"] = compact_ticker(query)
                st.session_state["nav_page"] = "analysis"
                st.rerun()
    return current_page


@st.cache_data(ttl=1800, show_spinner=False)
def load_market(ticker: str, start_date: str, end_date: str):
    return get_market_data(ticker, start_date, end_date)


@st.cache_data(ttl=3600, show_spinner=False)
def load_financial(ticker: str):
    return get_financial_data(compact_ticker(ticker), period="year")


def build_company(display_ticker, financial_data, df):
    domain = COMPANY_DOMAINS.get(display_ticker.upper())
    website = f"https://{domain}" if domain else (financial_data.get("website") or "")
    return {
        "name": financial_data.get("name") or display_ticker,
        "sector": financial_data.get("sector") or "Chưa có dữ liệu ngành",
        "industry": financial_data.get("sector") or "Chưa có dữ liệu",
        "exchange": financial_data.get("exchange") or "HOSE/HNX/UPCoM",
        "currency": "VND",
        "website": website,
        "description": financial_data.get("business_model") or "",
        "symbol": display_ticker,
        "last_date": str(pd.to_datetime(df["Date"].max()).date()),
        "market_cap": finite(financial_data.get("marketCap")),
        "shares": finite(financial_data.get("sharesOutstanding")),
        "eps": finite(financial_data.get("trailingEps")),
        "pe": finite(financial_data.get("trailingPE")),
        "pb": finite(financial_data.get("priceToBook")),
        "roe": finite(financial_data.get("returnOnEquity")),
        "dividend_yield": finite(financial_data.get("dividendYield")),
        "report_period": financial_data.get("reportPeriod"),
        "data_sources": "DNSE OpenAPI • vnstock/KBS • Google News RSS",
    }


def financial_periods(financial_data):
    history = financial_data.get("financialHistory", []) or []
    periods = [str(row.get("period")) for row in history if isinstance(row, dict) and row.get("period") is not None]
    return sorted(set(periods), reverse=True)


def financial_history_table(financial_data):
    history = financial_data.get("financialHistory", []) or []
    is_bank = str(financial_data.get("financialBusinessType") or "").lower() == "bank"
    revenue_label = "Thu nhập HĐ (tỷ VND)" if is_bank else "Doanh thu (tỷ VND)"

    rows = []
    for row in history:
        if not isinstance(row, dict):
            continue
        item = {
            "Năm": str(row.get("period", "")),
            revenue_label: None if finite(row.get("revenue")) is None else round(float(row.get("revenue"))/1e9, 1),
            "LNST (tỷ VND)": None if finite(row.get("net_profit")) is None else round(float(row.get("net_profit"))/1e9, 1),
            "Tổng tài sản (tỷ VND)": None if finite(row.get("total_assets")) is None else round(float(row.get("total_assets"))/1e9, 1),
            "VCSH (tỷ VND)": None if finite(row.get("equity")) is None else round(float(row.get("equity"))/1e9, 1),
            "ROE": None if finite(row.get("roe")) is None else float(row.get("roe")),
            "ROA": None if finite(row.get("roa")) is None else float(row.get("roa")),
            "P/E": finite(row.get("pe")),
            "P/B": finite(row.get("pb")),
        }
        if not is_bank:
            item["Lợi nhuận gộp (tỷ VND)"] = None if finite(row.get("gross_profit")) is None else round(float(row.get("gross_profit"))/1e9, 1)
        rows.append(item)

    table = pd.DataFrame(rows)
    if table.empty:
        return table

    # Với ngân hàng, không giữ cột hoàn toàn trống chỉ để tạo N/A trên UI.
    if is_bank:
        keep = ["Năm"] + [c for c in table.columns if c != "Năm" and table[c].notna().any()]
        table = table[keep]

    return table


def financial_trend_chart(financial_data):
    table = financial_history_table(financial_data)
    if table.empty:
        return None

    table = table.sort_values("Năm")
    fig = go.Figure()
    is_bank = str(financial_data.get("financialBusinessType") or "").lower() == "bank"
    revenue_col = "Thu nhập HĐ (tỷ VND)" if is_bank else "Doanh thu (tỷ VND)"

    if revenue_col in table.columns and table[revenue_col].notna().any():
        fig.add_trace(go.Bar(x=table["Năm"], y=table[revenue_col], name="Thu nhập HĐ" if is_bank else "Doanh thu"))
    if "LNST (tỷ VND)" in table.columns and table["LNST (tỷ VND)"].notna().any():
        fig.add_trace(go.Bar(x=table["Năm"], y=table["LNST (tỷ VND)"], name="LNST"))

    if not fig.data:
        return None

    fig.update_layout(
        barmode="group", height=330, margin=dict(l=10,r=10,t=20,b=5),
        paper_bgcolor="white", plot_bgcolor="white",
        legend=dict(orientation="h", y=1.08), yaxis_title="Tỷ VND",
    )
    fig.update_yaxes(gridcolor="#EDF1F6")
    return fig


def statement_table(financial_data, statement_key: str, period: str, scale_to_billion: bool = True):
    raw = (financial_data.get("_raw", {}) or {}).get(statement_key)
    if not isinstance(raw, pd.DataFrame) or raw.empty or period not in raw.columns:
        return pd.DataFrame()
    cols = [c for c in ["item", "item_id", "unit", period] if c in raw.columns]
    out = raw[cols].copy()
    out = out.dropna(subset=[period])
    if out.empty:
        return out
    value_col = "Giá trị"
    out = out.rename(columns={"item": "Chỉ tiêu", "item_id": "Mã chỉ tiêu", period: value_col, "unit": "Đơn vị"})
    out[value_col] = pd.to_numeric(out[value_col], errors="coerce")
    out = out.dropna(subset=[value_col])
    if scale_to_billion:
        out[value_col] = (out[value_col] / 1e9).round(2)
        value_col_new = "Giá trị (tỷ VND)"
        out = out.rename(columns={value_col: value_col_new})
    else:
        out[value_col] = out[value_col].round(4)
    return out.reset_index(drop=True)


def price_chart(df: pd.DataFrame, currency: str):
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.035,
        row_heights=[0.76, 0.24],
    )
    fig.add_trace(
        go.Scatter(
            x=df["Date"], y=df["Close"], name="Giá đóng cửa",
            mode="lines", line=dict(color="#1675E5", width=2.2),
            fill="tozeroy", fillcolor="rgba(22,117,229,.07)",
            hovertemplate=f"%{{x|%d/%m/%Y}}<br>Giá: %{{y:,.2f}} {currency}<extra></extra>",
        ), row=1, col=1,
    )
    fig.add_trace(
        go.Bar(
            x=df["Date"], y=df["Volume"], name="Khối lượng",
            marker_color="rgba(78,174,224,.55)",
            hovertemplate="%{x|%d/%m/%Y}<br>KL: %{y:,.0f}<extra></extra>",
        ), row=2, col=1,
    )
    fig.update_xaxes(
        rangeselector=dict(
            buttons=[
                dict(count=1, label="1M", step="month", stepmode="backward"),
                dict(count=3, label="3M", step="month", stepmode="backward"),
                dict(count=6, label="6M", step="month", stepmode="backward"),
                dict(count=1, label="1Y", step="year", stepmode="backward"),
                dict(count=3, label="3Y", step="year", stepmode="backward"),
                dict(step="all", label="All"),
            ],
            bgcolor="#F4F8FC", activecolor="#DCEEFF", font=dict(size=10),
        ), row=1, col=1,
    )
    fig.update_layout(
        height=380, margin=dict(l=55, r=18, t=28, b=58),
        paper_bgcolor="white", plot_bgcolor="white", showlegend=False,
        font=dict(family="Inter, Segoe UI, Arial", color="#42566E", size=10),
        hovermode="x unified",
    )
    fig.update_yaxes(title_text=f"Giá ({currency})", gridcolor="#E8EEF5", zeroline=False, row=1, col=1)
    fig.update_yaxes(title_text="Khối lượng", gridcolor="#F0F3F7", zeroline=False, row=2, col=1)
    fig.update_xaxes(title_text="Ngày giao dịch", row=2, col=1, automargin=True)
    return fig


def score_donut(score):
    v = finite(score)
    if v is None:
        v = 0
        colors_ = ["#DDE5ED", "#F2F5F8"]
        center = "N/A"
    else:
        col = "#13A86B" if v >= 65 else "#E7941E" if v >= 50 else "#E05252"
        colors_ = [col, "#E8EDF2"]
        center = f"{v:.0f}"
    fig = go.Figure(go.Pie(values=[v, max(0, 100-v)], hole=.72, marker_colors=colors_, textinfo="none", hoverinfo="skip", sort=False))
    fig.add_annotation(text=f"<b>{center}</b><br><span style='font-size:12px'>/100</span>", x=.5, y=.5, showarrow=False, font=dict(size=29, color="#0B2B55"))
    fig.update_layout(height=245, margin=dict(l=2,r=2,t=2,b=2), showlegend=False, paper_bgcolor="white")
    return fig


def technical_plot(df: pd.DataFrame):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["Date"], y=df["Close"], name="Close", line=dict(color="#146FD1", width=2)))
    fig.add_trace(go.Scatter(x=df["Date"], y=df["MA20"], name="MA20", line=dict(color="#15A988", width=1.5)))
    fig.add_trace(go.Scatter(x=df["Date"], y=df["MA50"], name="MA50", line=dict(color="#E69422", width=1.5)))
    fig.update_layout(height=410, margin=dict(l=58,r=18,t=35,b=55), paper_bgcolor="white", plot_bgcolor="white", hovermode="x unified", legend=dict(orientation="h", y=1.08))
    fig.update_xaxes(title_text="Ngày giao dịch", automargin=True)
    fig.update_yaxes(title_text="Giá (VND)", gridcolor="#E7EDF4", automargin=True)
    return fig


def rsi_plot(df: pd.DataFrame):
    fig = go.Figure(go.Scatter(x=df["Date"], y=df["RSI"], name="RSI(14)", line=dict(color="#7A5AF8", width=2)))
    fig.add_hline(y=70, line_dash="dash", line_color="#E05252", annotation_text="Quá mua 70")
    fig.add_hline(y=30, line_dash="dash", line_color="#13A86B", annotation_text="Quá bán 30")
    fig.update_layout(height=300, margin=dict(l=54,r=18,t=28,b=55), paper_bgcolor="white", plot_bgcolor="white", showlegend=False)
    fig.update_xaxes(title_text="Ngày giao dịch", automargin=True)
    fig.update_yaxes(title_text="RSI(14)", range=[0,100], gridcolor="#EDF1F6", automargin=True)
    return fig


def macd_plot(df: pd.DataFrame):
    hist_colors = ["#5BC4A6" if x >= 0 else "#EF8A8A" for x in df["MACD_Histogram"].fillna(0)]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["Date"], y=df["MACD_Histogram"], name="Histogram", marker_color=hist_colors, opacity=.6))
    fig.add_trace(go.Scatter(x=df["Date"], y=df["MACD"], name="MACD", line=dict(color="#146FD1", width=1.8)))
    fig.add_trace(go.Scatter(x=df["Date"], y=df["MACD_Signal"], name="Signal", line=dict(color="#E69422", width=1.6)))
    fig.update_layout(height=300, margin=dict(l=58,r=18,t=28,b=55), paper_bgcolor="white", plot_bgcolor="white", legend=dict(orientation="h", y=1.1))
    fig.update_xaxes(title_text="Ngày giao dịch", automargin=True)
    fig.update_yaxes(title_text="Giá trị MACD", gridcolor="#EDF1F6", automargin=True)
    return fig


def component_chart(summary):
    names = ["Fundamental", "Valuation", "Technical", "News", "Risk/Safety"]
    keys = ["fundamental", "valuation", "technical", "news", "risk"]
    vals = [summary.get("component_scores", {}).get(k) for k in keys]
    plot_vals = [0 if v is None else v for v in vals]
    fig = go.Figure(go.Bar(x=plot_vals, y=names, orientation="h", marker_color=["#2E86DE","#5C7AEA","#18A999","#F0A52B","#E16A6A"], text=["N/A" if v is None else f"{v:.1f}" for v in vals], textposition="auto"))
    fig.update_layout(height=280, margin=dict(l=10,r=10,t=5,b=5), paper_bgcolor="white", plot_bgcolor="white", xaxis=dict(range=[0,100], gridcolor="#EDF1F6"), yaxis=dict(autorange="reversed"), showlegend=False)
    return fig


def collect_insights(results):
    positives, risks = [], []
    names = {"technical":"Kỹ thuật", "fundamental":"Tài chính", "valuation":"Định giá", "news":"Tin tức", "risk":"Rủi ro"}
    for key in ["fundamental", "valuation", "technical", "news", "risk"]:
        res = results.get(key, {}) or {}

        positive_items = list(res.get("positives", []) or [])
        risk_items = list(res.get("risks", []) or [])

        # Peer Valuation là lớp bổ sung của Valuation. Đưa một phần insight
        # peer lên trang tổng quan nhưng KHÔNG thay Valuation Score gốc.
        if key == "valuation":
            positive_items += list(res.get("peer_positives", []) or [])
            risk_items += list(res.get("peer_risks", []) or [])

        for item in positive_items[:2]:
            positives.append(f"{names[key]}: {item}")
        for item in risk_items[:2]:
            risks.append(f"{names[key]}: {item}")
    return positives[:5], risks[:5]


def insight_html(title, items, extra_class=""):
    if not items:
        items = ["Chưa có đủ dữ liệu để tạo nhận xét cho nhóm yếu tố này."]
    lis = "".join(f"<li>{esc(x)}</li>" for x in items)
    return f'<div class="sl-insight {extra_class}"><h4>{esc(title)}</h4><ul>{lis}</ul></div>'


def preliminary_conclusion(summary, profile):
    score = finite(summary.get("score"))
    label = summary.get("label") or "Chưa đủ dữ liệu"
    pscore = finite(summary.get("profile_scores", {}).get(profile))
    if score is None:
        return "Chưa đủ các thành phần để kết luận điểm tổng hợp. StockLens giữ trạng thái thiếu dữ liệu thay vì tự nội suy số liệu."
    tail = f" Điểm theo hồ sơ {profile.lower()} là {pscore:.1f}/100." if pscore is not None else ""
    return f"Mô hình tổng hợp xếp cổ phiếu ở mức {label.upper()} với Investment Score {score:.1f}/100.{tail} Đây là công cụ hỗ trợ phân tích, không phải khuyến nghị mua/bán."


# -----------------------------------------------------------------------------
# Navigation + analysis form
# -----------------------------------------------------------------------------
current_page = topbar()


def render_analysis_form():
    with st.form("analysis_form", clear_on_submit=False):
        st.markdown(
            '<div class="sl-search-title">Khám phá cơ hội đầu tư cùng StockLens</div>'
            '<div class="sl-search-sub">Phân tích dữ liệu thị trường, sức khỏe tài chính, định giá, tin tức và rủi ro để hỗ trợ quá trình đánh giá cổ phiếu.</div>',
            unsafe_allow_html=True,
        )
        c1, c2, c3, c4, c5 = st.columns([1.15, 1.15, 1.15, 1.2, 1.55], gap="small")
        with c1:
            ticker_input = st.text_input(
                "Mã cổ phiếu",
                value=st.session_state.get("ticker_input", "FPT"),
                placeholder="FPT, HPG, MWG...",
            )
        with c2:
            start = st.date_input(
                "Ngày bắt đầu",
                value=st.session_state.get("start_date", date.today() - timedelta(days=900)),
            )
        with c3:
            end = st.date_input(
                "Ngày kết thúc",
                value=st.session_state.get("end_date", date.today()),
            )
        with c4:
            profiles = ["Cân bằng", "Thận trọng", "Tăng trưởng"]
            saved_profile = st.session_state.get("profile", "Cân bằng")
            if saved_profile not in profiles:
                saved_profile = "Cân bằng"
            profile = st.selectbox(
                "Phong cách nhà đầu tư",
                profiles,
                index=profiles.index(saved_profile),
            )
        with c5:
            st.write("")
            run = st.form_submit_button(
                "Phân tích cổ phiếu",
                type="primary",
                use_container_width=True,
            )

    if not run:
        return

    ticker_input = ticker_input.strip().upper()
    st.session_state["ticker_input"] = ticker_input
    st.session_state["start_date"] = start
    st.session_state["end_date"] = end
    st.session_state["profile"] = profile

    if not ticker_input:
        st.error("Vui lòng nhập mã cổ phiếu.")
        return
    if start > end:
        st.error("Ngày bắt đầu phải trước ngày kết thúc.")
        return

    progress = st.progress(0, text="Đang lấy dữ liệu giá từ DNSE...")
    try:
        df = load_market(ticker_input, str(start), str(end))
        if df.empty:
            raise ValueError(f"Không có dữ liệu giá từ DNSE cho mã {ticker_input}.")

        display_ticker = compact_ticker(ticker_input)
        progress.progress(18, text="Đang lấy BCTC và chỉ số tài chính từ vnstock/KBS...")
        financial_data = load_financial(display_ticker)
        company = build_company(display_ticker, financial_data, df)

        progress.progress(35, text="Đang tính chỉ báo kỹ thuật...")
        tech = analyze_technical(df, chart_dir=str(Path("charts") / display_ticker))

        progress.progress(53, text="Đang phân tích tài chính, định giá lịch sử và peer valuation...")
        fund = analyze_fundamental(financial_data)
        current_price = float(df.iloc[-1]["Close"])

        value = analyze_valuation(
            financial_data,
            ticker=display_ticker,
            current_price=current_price,
        )

        progress.progress(67, text="Đang tổng hợp tin tức...")
        news = analyze_news(display_ticker, company["name"])

        progress.progress(78, text="Đang đánh giá rủi ro và Investment Score...")
        risk = market_risk(tech)
        results = {
            "technical": tech,
            "fundamental": fund,
            "valuation": value,
            "news": news,
            "risk": risk,
        }
        summary = score_all(results)

        full_sections = ["technical", "fundamental", "valuation", "news", "score", "method"]
        default_pdf = None
        pdf_error = None
        progress.progress(90, text="Đang dựng báo cáo nghiên cứu PDF...")
        try:
            default_pdf = generate_pdf(
                display_ticker,
                f"{start} → {end}",
                results,
                summary,
                full_sections,
                profile,
                company_info=company,
                financial_data=financial_data,
            )
        except Exception as exc:
            pdf_error = str(exc)

        st.session_state["analysis"] = {
            "ticker": display_ticker,
            "input_ticker": ticker_input,
            "start": start,
            "end": end,
            "profile": profile,
            "df": df,
            "results": results,
            "summary": summary,
            "company": company,
            "financial_data": financial_data,
            "pdf": default_pdf,
            "pdf_error": pdf_error,
        }
        st.session_state.pop("custom_pdf", None)
        progress.progress(100, text="Hoàn tất phân tích.")
        progress.empty()
        st.rerun()

    except Exception as exc:
        progress.empty()
        st.error(f"Không hoàn thành phân tích: {exc}")


def render_empty_state(page: str):
    if page == "report":
        title = "Chưa có báo cáo để hiển thị"
        detail = "Hãy phân tích một mã cổ phiếu trước, sau đó quay lại mục Báo cáo đầu tư để tạo hoặc tải PDF."
    else:
        title = "Bắt đầu với một mã cổ phiếu"
        detail = "Nhập FPT, HPG, MWG, VNM, ACB… chọn khoảng thời gian và nhấn Phân tích cổ phiếu. Giá lấy từ DNSE; BCTC/chỉ số tài chính lấy qua vnstock/KBS."

    st.markdown(
        f"""
<div class="sl-panel" style="padding:24px;text-align:center;margin-top:12px">
  <div style="font-size:1.15rem;font-weight:850;color:#0B2B55">{esc(title)}</div>
  <div style="margin-top:6px;color:#6A7B91;font-size:.85rem">{esc(detail)}</div>
</div>
""",
        unsafe_allow_html=True,
    )

    if page == "report":
        c1, c2, c3 = st.columns([1, 1.2, 1])
        with c2:
            if st.button("Sang Phân tích cổ phiếu", type="primary", use_container_width=True, key="empty_go_analysis"):
                go_to("analysis")


def render_company_strip(ticker, company, df=None, results=None):
    logo = company_logo_src(ticker, company)
    if logo:
        logo_html = f'<div class="sl-company-logo"><img src="{esc(logo)}" alt="{esc(ticker)} logo"></div>'
    else:
        logo_html = f'<div class="sl-ticker-logo">{esc(ticker[:4])}</div>'

    close = None
    change = None
    high = None
    low = None
    volume = None
    if isinstance(df, pd.DataFrame) and not df.empty:
        close = finite(df.iloc[-1].get("Close"))
        if len(df) >= 2:
            prev = finite(df.iloc[-2].get("Close"))
            if close is not None and prev not in (None, 0):
                change = close / prev - 1
        recent = df.tail(252)
        high = finite(recent["High"].max()) if "High" in recent else None
        low = finite(recent["Low"].min()) if "Low" in recent else None
        volume = finite(df.iloc[-1].get("Volume"))

    change_text = "N/A" if change is None else f"{change:+.2%}"
    change_color = "#15986B" if (change or 0) >= 0 else "#D84F61"
    price_panel = ""
    if close is not None:
        price_panel = f"""
<div class="sl-price-panel">
  <div class="sl-price-card">
    <div class="sl-price-label">Giá cổ phiếu (VND)</div>
    <div class="sl-price-value">{close:,.0f}</div>
    <div class="sl-price-change" style="color:{change_color}">{change_text} so với phiên trước</div>
  </div>
  <div class="sl-price-card sl-mini-stats">
    Cao nhất 52W <b>{'N/A' if high is None else f'{high:,.0f}'}</b><br>
    Thấp nhất 52W <b>{'N/A' if low is None else f'{low:,.0f}'}</b><br>
    Khối lượng <b>{'N/A' if volume is None else f'{volume:,.0f}'}</b>
  </div>
</div>"""

    st.markdown(
        f"""
<div class="sl-company">
  {logo_html}
  <div class="sl-company-main">
    <div class="sl-company-title">{esc(ticker)}</div>
    <div class="sl-company-name">{esc(company['name'])}</div>
    <div class="sl-meta">Sàn: {esc(company['exchange'])} &nbsp; | &nbsp; Ngành: {esc(company['sector'])} &nbsp; | &nbsp; BCTC: {esc(company.get('report_period') or 'N/A')} &nbsp; | &nbsp; Cập nhật: {esc(company['last_date'])}</div>
  </div>
  {price_panel}
</div>
""",
        unsafe_allow_html=True,
    )


def render_overview_page(a, ticker, start, end, profile, df, results, summary, company, financial_data):
    t = results["technical"]
    rsk = results["risk"]
    currency = company["currency"]

    render_company_strip(ticker, company, df=df, results=results)

    main_col, report_col = st.columns([4.25, 1.15], gap="small")
    with main_col:
        last_close = finite(t.get("close"))
        prev_close = finite(df.iloc[-2]["Close"]) if len(df) >= 2 else None
        change = None if last_close is None or prev_close in (None, 0) else last_close / prev_close - 1
        change_text = "Phiên mới nhất" if change is None else f"{change:+.2%} so với phiên trước"
        overall_label, _ = ui_score_label(summary.get("score"))

        kcols = st.columns(5, gap="small")
        cards = [
            ("Giá cổ phiếu", fmt_price(last_close, currency), change_text, change_tone(change, "blue")),
            ("Investment Score", "N/A" if summary.get("score") is None else f"{summary['score']:.1f}/100", overall_label, score_tone(summary.get("score"))),
            ("Technical Score", "N/A" if t.get("score") is None else f"{t['score']:.1f}/100", t.get("label") or t.get("classification", ""), score_tone(t.get("score"))),
            ("Market Risk/Safety", "N/A" if rsk.get("score") is None else f"{rsk['score']:.1f}/100", "Điểm cao = an toàn hơn", score_tone(rsk.get("score"))),
            ("Đánh giá tổng hợp", overall_label.upper(), "Theo mô hình StockLens", score_tone(summary.get("score"))),
        ]
        for col, (lab, val, sub, tone) in zip(kcols, cards):
            col.markdown(metric_card(lab, val, sub, tone), unsafe_allow_html=True)

        chart_col, score_col = st.columns([2.3, 1], gap="small")
        with chart_col:
            st.markdown('<div class="sl-panel-title" style="margin-top:12px">Diễn biến giá cổ phiếu</div>', unsafe_allow_html=True)
            st.plotly_chart(price_chart(df, currency), use_container_width=True, config={"displayModeBar": False})
            st.markdown('<div class="sl-chart-caption"><b>Biểu đồ 1.</b> Diễn biến giá đóng cửa và khối lượng giao dịch theo thời gian</div>', unsafe_allow_html=True)
        with score_col:
            st.markdown('<div class="sl-panel-title" style="margin-top:12px">Investment Score</div>', unsafe_allow_html=True)
            st.plotly_chart(score_donut(summary.get("score")), use_container_width=True, config={"displayModeBar": False})
            label, chip = ui_score_label(summary.get("score"))
            st.markdown(
                f'<div style="text-align:center;margin-top:-13px"><span class="sl-chip {chip}">{esc(label)}</span></div>'
                '<div class="sl-score-note" style="margin-top:8px">80–100: Cơ hội cao &nbsp;•&nbsp; 65–&lt;80: Tích cực<br>50–&lt;65: Trung lập &nbsp;•&nbsp; &lt;50: Thận trọng</div>',
                unsafe_allow_html=True,
            )

    with report_col:
        st.markdown('<div class="sl-report-rail"><div class="sl-panel-title">Báo cáo phân tích</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
<div class="sl-cover">
  <div class="sl-cover-brand">▥ STOCKLENS</div>
  <div class="sl-cover-kicker">BÁO CÁO PHÂN TÍCH<br>DOANH NGHIỆP</div>
  <div class="sl-cover-ticker">{esc(ticker)}</div>
  <div class="sl-cover-name">{esc(company['name'])}</div>
  <div class="sl-cover-meta">Hồ sơ: {esc(profile)}<br>Sàn: {esc(company['exchange'])}<br>Cập nhật: {esc(company['last_date'])}</div>
  <div class="sl-cover-wave"></div>
</div>
""",
            unsafe_allow_html=True,
        )
        if a.get("pdf"):
            st.download_button(
                "Tải báo cáo phân tích PDF",
                data=a["pdf"],
                file_name=f"StockLens_{ticker}_{end}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
                key="top_pdf_download",
            )
            st.caption("Báo cáo nghiên cứu 8 trang • PDF")
        else:
            st.warning("PDF chưa tạo được trong lần chạy này.")

        st.markdown('<div class="sl-panel-title" style="margin-top:14px">Thông tin nhanh</div>', unsafe_allow_html=True)
        is_bank = str(financial_data.get("financialBusinessType") or "").lower() == "bank"
        quick_rows = [
            quick_row("Kỳ BCTC", company.get("report_period") or "N/A"),
            quick_row("LNST", fmt_money(financial_data.get("netIncomeToCommon"), currency)),
            quick_row("P/E", "N/A" if company.get("pe") is None else f"{company['pe']:.2f}x"),
            quick_row("P/B", "N/A" if company.get("pb") is None else f"{company['pb']:.2f}x"),
            quick_row("ROE", fmt_pct(company.get("roe"), 2)),
        ]
        if is_bank:
            quick_rows.insert(1, quick_row("Tổng tài sản", fmt_money(financial_data.get("totalAssets"), currency)))
            if financial_data.get("totalEquity") is not None:
                quick_rows.append(quick_row("VCSH", fmt_money(financial_data.get("totalEquity"), currency)))
        else:
            quick_rows.insert(1, quick_row("Doanh thu", fmt_money(financial_data.get("totalRevenue"), currency)))
            quick_rows.append(quick_row("Debt/Equity", "N/A" if financial_data.get("debtToEquity") is None else f"{financial_data['debtToEquity']:.2f}x"))
        quick = "".join(quick_rows)
        st.markdown(quick + '</div>', unsafe_allow_html=True)

    positives, risks = collect_insights(results)
    conclusion = preliminary_conclusion(summary, profile)
    st.markdown('<div class="sl-section-title">Tổng quan đầu tư</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sl-insight-grid">'
        + insight_html("Điểm nổi bật", positives)
        + insight_html("Rủi ro cần lưu ý", risks)
        + insight_html("Kết luận sơ bộ", [conclusion], "sl-insight-conclusion")
        + '</div>',
        unsafe_allow_html=True,
    )

    if summary.get("missing"):
        st.warning("Investment Score chưa thể tính đầy đủ vì thiếu: " + ", ".join(summary["missing"]) + ". StockLens không tự nội suy thành phần bị thiếu.")


def render_analysis_page(ticker, profile, results, summary, company, financial_data):
    t = results["technical"]
    f = results["fundamental"]
    v = results["valuation"]
    n = results["news"]
    currency = company["currency"]

    render_company_strip(ticker, company)
    positives, risks = collect_insights(results)

    st.markdown('<div class="sl-section-title">Phân tích cổ phiếu</div>', unsafe_allow_html=True)
    tabs = st.tabs([
        "Tổng quan đầu tư",
        "Phân tích kỹ thuật",
        "Phân tích tài chính",
        "Phân tích định giá",
        "Tin tức & triển vọng",
    ])

    with tabs[0]:
        st.markdown('<div class="sl-section-title">Cấu trúc Investment Score</div>', unsafe_allow_html=True)
        c1, c2 = st.columns([1.25, 1], gap="medium")
        with c1:
            st.plotly_chart(component_chart(summary), use_container_width=True, config={"displayModeBar": False})
        with c2:
            rows = []
            weight_map = {"fundamental": 25, "valuation": 25, "technical": 25, "news": 15, "risk": 10}
            label_map = {"fundamental": "Fundamental", "valuation": "Valuation", "technical": "Technical", "news": "News", "risk": "Risk/Safety"}
            for key in ["fundamental", "valuation", "technical", "news", "risk"]:
                value_ = summary.get("component_scores", {}).get(key)
                rows.append({
                    "Thành phần": label_map[key],
                    "Điểm": value_,
                    "Trọng số": f"{weight_map[key]}%",
                    "Đóng góp": summary.get("contributions", {}).get(key),
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption("Investment Score cơ sở: 25% Fundamental + 25% Valuation + 25% Technical + 15% News + 10% Risk/Safety.")

        st.markdown('<div class="sl-section-title">Góc nhìn theo hồ sơ nhà đầu tư</div>', unsafe_allow_html=True)
        pc = st.columns(3)
        for col, name in zip(pc, ["Thận trọng", "Cân bằng", "Tăng trưởng"]):
            val = summary.get("profile_scores", {}).get(name)
            lab, _ = ui_score_label(val)
            with col:
                st.markdown(kpi(name, "N/A" if val is None else f"{val:.1f}/100", lab, score_class(val)), unsafe_allow_html=True)

        st.markdown('<div class="sl-section-title">Why This Score?</div>', unsafe_allow_html=True)
        pcol, rcol = st.columns(2)
        with pcol:
            st.success("\n".join([f"• {x}" for x in positives]) if positives else "Chưa có tín hiệu hỗ trợ nổi bật.")
        with rcol:
            st.error("\n".join([f"• {x}" for x in risks]) if risks else "Chưa ghi nhận cảnh báo nổi bật từ dữ liệu hiện có.")

    with tabs[1]:
        st.markdown('<div class="sl-section-title">Phân tích kỹ thuật</div>', unsafe_allow_html=True)
        if not t.get("data_available"):
            st.warning(t.get("error") or "Không đủ dữ liệu kỹ thuật.")
        else:
            mc = st.columns(6)
            rsi_value = finite(t.get("rsi"))
            rsi_tone = "amber" if rsi_value is not None and (rsi_value >= 70 or rsi_value <= 30) else "purple"
            metrics = [
                ("Close", fmt_price(t.get("close"), currency), "Giá đóng cửa", "blue"),
                ("MA20", fmt_price(t.get("ma20"), currency), "Trung bình 20 phiên", "teal"),
                ("MA50", fmt_price(t.get("ma50"), currency), "Trung bình 50 phiên", "purple"),
                ("RSI(14)", fmt_num(t.get("rsi"), 1), "Quá bán <30 • Quá mua >70", rsi_tone),
                ("Volatility 20", fmt_pct(t.get("volatility")), "Biến động 20 phiên", "pink"),
                ("Volume Ratio", "N/A" if t.get("volume_ratio") is None else f"{t['volume_ratio']:.2f}x", "KL hiện tại / MA20", "amber"),
            ]
            for col, (lab, val, sub, tone) in zip(mc, metrics):
                col.markdown(metric_card(lab, val, sub, tone), unsafe_allow_html=True)
            st.plotly_chart(technical_plot(t["data"]), use_container_width=True, config={"displayModeBar": False})
            st.markdown('<div class="sl-chart-caption"><b>Biểu đồ 2.</b> Giá đóng cửa cùng đường trung bình động MA20 và MA50</div>', unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                st.plotly_chart(rsi_plot(t["data"]), use_container_width=True, config={"displayModeBar": False})
                st.markdown('<div class="sl-chart-caption"><b>Biểu đồ 3.</b> Chỉ số sức mạnh tương đối RSI(14)</div>', unsafe_allow_html=True)
            with c2:
                st.plotly_chart(macd_plot(t["data"]), use_container_width=True, config={"displayModeBar": False})
                st.markdown('<div class="sl-chart-caption"><b>Biểu đồ 4.</b> MACD, Signal và Histogram</div>', unsafe_allow_html=True)
            signal_rows = []
            for key, sig in t.get("signals", {}).items():
                signal_rows.append({"Chỉ báo": key, "Tín hiệu": sig.get("signal"), "Điểm": sig.get("score")})
            st.dataframe(pd.DataFrame(signal_rows), use_container_width=True, hide_index=True)
            st.info(t.get("commentary", ""))
            with st.expander("Xem 30 phiên OHLCV và chỉ báo gần nhất"):
                st.dataframe(t["data"].tail(30), use_container_width=True, hide_index=True)

    with tabs[2]:
        st.markdown('<div class="sl-section-title">Sức khỏe tài chính</div>', unsafe_allow_html=True)
        fm = f.get("metrics", {}) or {}
        is_bank = bool(f.get("is_bank")) or str(financial_data.get("financialBusinessType") or "").lower() == "bank"

        if is_bank:
            # ----------------------------------------------------------
            # NGÂN HÀNG: không ép Net Margin, D/E, Current Ratio vào UI.
            # Chỉ hiển thị KPI phù hợp và có dữ liệu thực tế.
            # ----------------------------------------------------------
            bank_cards = [
                ("ROE", fmt_pct(fm.get("roe"), 2), "Hiệu quả vốn chủ", "green"),
                ("ROA", fmt_pct(fm.get("roa"), 2), "Hiệu quả tài sản", "teal"),
                ("Tăng trưởng LNST", fmt_pct(fm.get("net_income_growth"), 2), "So với năm trước", change_tone(fm.get("net_income_growth"), "green")),
                ("Tăng trưởng tài sản", fmt_pct(fm.get("asset_growth"), 2), "So với năm trước", change_tone(fm.get("asset_growth"), "blue")),
                ("VCSH / Tổng tài sản", fmt_pct(fm.get("equity_to_assets"), 2), "Tỷ lệ vốn kế toán", "purple"),
                ("Tổng tài sản", fmt_money(fm.get("total_assets"), currency), "Quy mô bảng cân đối", "purple"),
                ("VCSH", fmt_money(fm.get("total_equity"), currency), "Vốn chủ sở hữu", "pink"),
                ("LNST", fmt_money(fm.get("net_income"), currency), "Lợi nhuận sau thuế", change_tone(fm.get("net_income"), "teal")),
            ]

            # Nếu KBS có Tổng thu nhập hoạt động và tăng trưởng thì thêm vào,
            # còn thiếu thì không tạo một ô N/A không cần thiết.
            if finite(fm.get("total_revenue")) is not None:
                bank_cards.append(("Tổng thu nhập hoạt động", fmt_money(fm.get("total_revenue"), currency), "Quy mô thu nhập", "blue"))
            if finite(fm.get("operating_income_growth")) is not None:
                bank_cards.append(("Tăng trưởng thu nhập HĐ", fmt_pct(fm.get("operating_income_growth"), 2), "So với năm trước", change_tone(fm.get("operating_income_growth"), "blue")))

            # Không hiển thị card có giá trị N/A ở ngân hàng.
            visible_cards = [card for card in bank_cards if card[1] != "N/A"]
            for i in range(0, len(visible_cards), 4):
                row_cards = visible_cards[i:i+4]
                cols = st.columns(len(row_cards))
                for col, (lab, val, sub, tone) in zip(cols, row_cards):
                    col.markdown(metric_card(lab, val, sub, tone), unsafe_allow_html=True)

            st.caption(
                "Ngân hàng dùng bộ KPI riêng. StockLens không áp dụng Debt/Equity, Current Ratio và Biên lợi nhuận ròng "
                "theo cùng thang với doanh nghiệp sản xuất/dịch vụ."
            )
        else:
            c1, c2, c3, c4 = st.columns(4)
            fund_cards_1 = [
                ("ROE", fmt_pct(fm.get("roe"), 2), "Hiệu quả vốn chủ", "green" if (finite(fm.get("roe")) or 0) > 0 else "red"),
                ("ROA", fmt_pct(fm.get("roa"), 2), "Hiệu quả tài sản", "teal" if (finite(fm.get("roa")) or 0) > 0 else "red"),
                ("Biên lợi nhuận", fmt_pct(fm.get("profit_margin"), 2), "LN ròng / Doanh thu", change_tone(fm.get("profit_margin"), "purple")),
                ("Tăng trưởng doanh thu", fmt_pct(fm.get("revenue_growth"), 2), "So với kỳ trước", change_tone(fm.get("revenue_growth"), "blue")),
            ]
            for col, (lab, val, sub, tone) in zip([c1, c2, c3, c4], fund_cards_1):
                col.markdown(metric_card(lab, val, sub, tone), unsafe_allow_html=True)

            c1, c2, c3, c4 = st.columns(4)
            fund_cards_2 = [
                ("Debt/Equity", "N/A" if fm.get("debt_to_equity") is None else f"{fm['debt_to_equity']:.2f}x", "Đòn bẩy tài chính", "amber"),
                ("Current Ratio", "N/A" if fm.get("current_ratio") is None else f"{fm['current_ratio']:.2f}x", "Khả năng thanh toán ngắn hạn", "blue"),
                ("Doanh thu", fmt_money(fm.get("total_revenue"), currency), "Quy mô hoạt động", "purple"),
                ("LN ròng", fmt_money(fm.get("net_income"), currency), "Lợi nhuận sau thuế", change_tone(fm.get("net_income"), "teal")),
            ]
            for col, (lab, val, sub, tone) in zip([c1, c2, c3, c4], fund_cards_2):
                col.markdown(metric_card(lab, val, sub, tone), unsafe_allow_html=True)

        st.info(f.get("commentary", "Không đủ dữ liệu tài chính."))

        component_label_map = {
            "roe": "ROE",
            "roa": "ROA",
            "profit_margin": "Biên lợi nhuận ròng",
            "revenue_growth": "Tăng trưởng doanh thu",
            "debt_to_equity": "Debt/Equity",
            "current_ratio": "Current Ratio",
            "net_income_growth": "Tăng trưởng LNST",
            "asset_growth": "Tăng trưởng tổng tài sản",
            "equity_to_assets": "VCSH/Tổng tài sản",
            "operating_income_growth": "Tăng trưởng thu nhập HĐ",
        }
        comp = pd.DataFrame([
            {
                "Chỉ tiêu": component_label_map.get(k, k),
                "Điểm": val,
                "Trọng số": f"{100 * f.get('component_weights', {}).get(k, 0):.0f}%",
            }
            for k, val in (f.get("component_scores", {}) or {}).items()
        ])
        if not comp.empty:
            st.dataframe(comp, use_container_width=True, hide_index=True)

        st.markdown('<div class="sl-section-title">Lịch sử tài chính theo năm</div>', unsafe_allow_html=True)
        hist_table = financial_history_table(financial_data)
        if hist_table.empty:
            st.warning("vnstock/KBS chưa trả lịch sử tài chính đủ để hiển thị.")
        else:
            hist_display = hist_table.copy()
            for col_name in ["ROE", "ROA"]:
                if col_name in hist_display.columns:
                    hist_display[col_name] = hist_display[col_name].apply(lambda x: "N/A" if pd.isna(x) else f"{x:.2%}")
            st.dataframe(hist_display, use_container_width=True, hide_index=True)

            trend_fig = financial_trend_chart(financial_data)
            if trend_fig is not None:
                st.plotly_chart(trend_fig, use_container_width=True, config={"displayModeBar": False})
                chart_text = "Thu nhập hoạt động và LNST theo năm" if is_bank else "Doanh thu và lợi nhuận sau thuế theo năm"
                st.markdown(f'<div class="sl-chart-caption"><b>Biểu đồ 5.</b> {chart_text}</div>', unsafe_allow_html=True)

            periods = financial_periods(financial_data)
            if periods:
                selected_period = st.selectbox(
                    "Chọn năm để xem BCTC chi tiết",
                    periods,
                    index=0,
                    key="financial_period_selector",
                )
                selected_row = next(
                    (row for row in financial_data.get("financialHistory", []) if str(row.get("period")) == str(selected_period)),
                    None,
                )
                if selected_row:
                    if is_bank:
                        selected_metrics = [
                            ("LNST", fmt_money(selected_row.get("net_profit"), currency), f"Năm {selected_period}", change_tone(selected_row.get("net_profit"), "green")),
                            ("Tổng tài sản", fmt_money(selected_row.get("total_assets"), currency), f"Năm {selected_period}", "purple"),
                            ("VCSH", fmt_money(selected_row.get("equity"), currency), f"Năm {selected_period}", "pink"),
                            ("ROE", fmt_pct(selected_row.get("roe"), 2), f"Năm {selected_period}", "green"),
                            ("ROA", fmt_pct(selected_row.get("roa"), 2), f"Năm {selected_period}", "teal"),
                        ]
                        if finite(selected_row.get("revenue")) is not None:
                            selected_metrics.insert(0, ("Thu nhập hoạt động", fmt_money(selected_row.get("revenue"), currency), f"Năm {selected_period}", "blue"))
                        selected_metrics = [x for x in selected_metrics if x[1] != "N/A"]
                    else:
                        selected_metrics = [
                            ("Doanh thu", fmt_money(selected_row.get("revenue"), currency), f"Năm {selected_period}", "blue"),
                            ("Lợi nhuận gộp", fmt_money(selected_row.get("gross_profit"), currency), f"Năm {selected_period}", "teal"),
                            ("LNST", fmt_money(selected_row.get("net_profit"), currency), f"Năm {selected_period}", change_tone(selected_row.get("net_profit"), "green")),
                            ("Tổng tài sản", fmt_money(selected_row.get("total_assets"), currency), f"Năm {selected_period}", "purple"),
                            ("VCSH", fmt_money(selected_row.get("equity"), currency), f"Năm {selected_period}", "pink"),
                        ]

                    for i in range(0, len(selected_metrics), 5):
                        row_metrics = selected_metrics[i:i+5]
                        cols = st.columns(len(row_metrics))
                        for col, (lab, val, sub, tone) in zip(cols, row_metrics):
                            col.markdown(metric_card(lab, val, sub, tone), unsafe_allow_html=True)

                bstabs = st.tabs(["Kết quả kinh doanh", "Bảng cân đối kế toán", "Lưu chuyển tiền tệ", "Chỉ số tài chính"])
                statement_specs = [
                    ("income_statement", True),
                    ("balance_sheet", True),
                    ("cash_flow", True),
                    ("ratios", False),
                ]
                for tab, (statement_key, scale_to_billion) in zip(bstabs, statement_specs):
                    with tab:
                        table_ = statement_table(financial_data, statement_key, selected_period, scale_to_billion)
                        if table_.empty:
                            st.warning(f"Không có dữ liệu {selected_period} cho bảng này.")
                        else:
                            st.dataframe(table_, use_container_width=True, hide_index=True, height=430)

        st.caption("Nguồn tài chính: vnstock / KBS. Giá thị trường: DNSE OpenAPI.")
        if company.get("description"):
            with st.expander("Mô tả doanh nghiệp từ vnstock"):
                st.write(company["description"])

    with tabs[3]:
        # ==============================================================
        # A. HISTORICAL VALUATION - GIỮ NGUYÊN VALUATION SCORE GỐC
        # ==============================================================
        st.markdown('<div class="sl-section-title">Định giá theo lịch sử doanh nghiệp</div>', unsafe_allow_html=True)

        vm = v.get("metrics", {}) or {}
        pe_now = finite(v.get("pe", vm.get("pe")))
        pb_now = finite(v.get("pb", vm.get("pb")))
        pe_median = finite(v.get("historical_pe_median", vm.get("historical_pe_median")))
        pb_median = finite(v.get("historical_pb_median", vm.get("historical_pb_median")))
        valuation_score = finite(v.get("score"))

        cc = st.columns(5)
        vals = [
            ("Valuation Score", "N/A" if valuation_score is None else f"{valuation_score:.1f}/100", v.get("classification") or "Điểm định giá lịch sử", score_tone(valuation_score)),
            ("P/E hiện tại", "N/A" if pe_now is None else f"{pe_now:.2f}x", "Multiple lợi nhuận", "blue"),
            ("P/B hiện tại", "N/A" if pb_now is None else f"{pb_now:.2f}x", "Multiple giá trị sổ sách", "purple"),
            ("Median P/E lịch sử", "N/A" if pe_median is None else f"{pe_median:.2f}x", "Trung vị lịch sử", "teal"),
            ("Median P/B lịch sử", "N/A" if pb_median is None else f"{pb_median:.2f}x", "Trung vị lịch sử", "pink"),
        ]
        for col, (lab, val, sub, tone) in zip(cc, vals):
            col.markdown(metric_card(lab, val, sub, tone), unsafe_allow_html=True)

        if pe_now is not None and pe_median not in (None, 0):
            pe_gap = pe_now / pe_median - 1
            pe_text = f"P/E hiện tại {'thấp hơn' if pe_gap < 0 else 'cao hơn'} median lịch sử {abs(pe_gap):.1%}."
        else:
            pe_text = "Chưa đủ dữ liệu để so sánh P/E với lịch sử."

        if pb_now is not None and pb_median not in (None, 0):
            pb_gap = pb_now / pb_median - 1
            pb_text = f"P/B hiện tại {'thấp hơn' if pb_gap < 0 else 'cao hơn'} median lịch sử {abs(pb_gap):.1%}."
        else:
            pb_text = "Chưa đủ dữ liệu để so sánh P/B với lịch sử."

        st.caption(pe_text + " " + pb_text)
        st.info(v.get("commentary", "Không đủ dữ liệu định giá."))

        comp = pd.DataFrame([
            {"Thành phần": k, "Điểm": val, "Trọng số": f"{100 * v.get('component_weights', {}).get(k, 0):.0f}%"}
            for k, val in (v.get("component_scores", {}) or {}).items()
        ])
        if not comp.empty:
            st.dataframe(comp, use_container_width=True, hide_index=True)

        # ==============================================================
        # B. PEER VALUATION - LỚP ĐỊNH GIÁ BỔ SUNG
        # ==============================================================
        st.markdown('<div class="sl-section-title" style="margin-top:18px">Peer Valuation – so sánh doanh nghiệp cùng ngành</div>', unsafe_allow_html=True)

        peer = v.get("peer_valuation", {}) or {}

        if not peer.get("data_available"):
            st.warning(
                peer.get("commentary")
                or "Chưa đủ dữ liệu doanh nghiệp cùng ngành để thực hiện Peer Valuation."
            )
        else:
            peer_score = finite(v.get("peer_score", peer.get("score")))
            peer_fair_value = finite(v.get("peer_fair_value", peer.get("peer_fair_value")))
            peer_upside = finite(v.get("peer_upside_downside", peer.get("upside_downside")))
            peer_median_pe = finite(v.get("peer_median_pe", peer.get("peer_median_pe")))
            peer_median_pb = finite(v.get("peer_median_pb", peer.get("peer_median_pb")))
            peer_quality = v.get("peer_quality_status") or peer.get("peer_quality_status") or "Chưa đánh giá"

            pc = st.columns(5)
            peer_cards = [
                ("Peer Score", "N/A" if peer_score is None else f"{peer_score:.1f}/100", peer.get("classification") or "So với peers", score_tone(peer_score)),
                ("Peer Fair Value", fmt_price(peer_fair_value, currency), "Giá trị hàm ý tương đối", "purple"),
                ("Upside / Downside", "N/A" if peer_upside is None else f"{peer_upside:+.1%}", "So với giá hiện tại", change_tone(peer_upside, "blue")),
                ("Median P/E peers", "N/A" if peer_median_pe is None else f"{peer_median_pe:.2f}x", "Trung vị doanh nghiệp cùng ngành", "blue"),
                ("Median P/B peers", "N/A" if peer_median_pb is None else f"{peer_median_pb:.2f}x", "Trung vị doanh nghiệp cùng ngành", "teal"),
            ]
            for col, (lab, val, sub, tone) in zip(pc, peer_cards):
                col.markdown(metric_card(lab, val, sub, tone), unsafe_allow_html=True)

            weights = peer.get("valuation_weights", {}) or {}
            weight_label = weights.get("label") or "Trọng số peer theo quy tắc StockLens"
            icb_level = peer.get("industry_icb_level")
            icb_code = peer.get("industry_icb_code")
            industry_name = peer.get("industry") or company.get("sector") or "N/A"
            requested_peers = peer.get("requested_peers", []) or []
            peer_count = peer.get("peer_count") or 0

            meta_parts = [f"Ngành: {industry_name}"]
            if icb_level is not None:
                meta_parts.append(f"ICB cấp {icb_level}")
            if icb_code:
                meta_parts.append(f"Mã ICB {icb_code}")
            if requested_peers:
                meta_parts.append(f"{peer_count}/{len(requested_peers)} peer hợp lệ")
            else:
                meta_parts.append(f"{peer_count} peer hợp lệ")
            meta_parts.append(weight_label)
            st.caption(" • ".join(meta_parts))

            # Các đầu vào quy đổi multiple thành giá hàm ý
            p2 = st.columns(4)
            peer_detail_cards = [
                ("EPS", fmt_price(peer.get("eps"), currency), "Thu nhập trên mỗi cổ phiếu", "green"),
                ("BVPS", fmt_price(peer.get("bvps"), currency), "Giá trị sổ sách/cổ phiếu", "teal"),
                ("Giá hàm ý theo P/E", fmt_price(v.get("peer_implied_price_pe", peer.get("implied_price_pe")), currency), "EPS × Median P/E peers", "blue"),
                ("Giá hàm ý theo P/B", fmt_price(v.get("peer_implied_price_pb", peer.get("implied_price_pb")), currency), "BVPS × Median P/B peers", "purple"),
            ]
            for col, (lab, val, sub, tone) in zip(p2, peer_detail_cards):
                col.markdown(metric_card(lab, val, sub, tone), unsafe_allow_html=True)

            st.markdown('<div class="sl-panel-title" style="margin-top:12px">Bảng doanh nghiệp so sánh</div>', unsafe_allow_html=True)

            quality_map = {}
            for q in peer.get("peer_quality", []) or []:
                if not isinstance(q, dict):
                    continue
                sym = str(q.get("symbol") or "").upper()
                flags = q.get("flags") or []
                quality_map[sym] = {
                    "status": q.get("status") or "N/A",
                    "flags": "; ".join(str(x) for x in flags) if flags else "-",
                }

            peer_rows = []
            for row in peer.get("peers", []) or []:
                if not isinstance(row, dict):
                    continue
                sym = str(row.get("symbol") or "").upper()
                q = quality_map.get(sym, {})
                roe = finite(row.get("roe"))
                pe_peer = finite(row.get("pe"))
                pb_peer = finite(row.get("pb"))
                peer_rows.append({
                    "Mã": sym,
                    "Doanh nghiệp": row.get("name") or sym,
                    "P/E": "N/A" if pe_peer is None else f"{pe_peer:.2f}x",
                    "P/B": "N/A" if pb_peer is None else f"{pb_peer:.2f}x",
                    "ROE": "N/A" if roe is None else f"{roe:.2f}%",
                    "Quality": q.get("status", "OK"),
                    "Cảnh báo": q.get("flags", "-"),
                })

            if peer_rows:
                peer_df = pd.DataFrame(peer_rows)
                st.dataframe(peer_df, use_container_width=True, hide_index=True)
            else:
                st.warning("Không có peer hợp lệ để hiển thị trong bảng.")

            quality_warnings = v.get("peer_quality_warnings") or peer.get("peer_quality_warnings") or []
            if quality_warnings:
                warning_text = "\n".join(f"• {x}" for x in quality_warnings)
                if str(peer_quality).lower().startswith("cần"):
                    st.warning(f"**Chất lượng bộ peer: {peer_quality}**\n\n{warning_text}")
                else:
                    st.info(f"**Chất lượng bộ peer: {peer_quality}**\n\n{warning_text}")
            else:
                st.success(f"Chất lượng bộ peer: {peer_quality}")

            peer_pos = v.get("peer_positives") or peer.get("positives") or []
            peer_risks = v.get("peer_risks") or peer.get("risks") or []
            pos_col, risk_col = st.columns(2)
            with pos_col:
                st.success(
                    "\n".join(f"• {x}" for x in peer_pos)
                    if peer_pos
                    else "Chưa có tín hiệu định giá peer tích cực nổi bật."
                )
            with risk_col:
                st.error(
                    "\n".join(f"• {x}" for x in peer_risks)
                    if peer_risks
                    else "Chưa ghi nhận cảnh báo định giá peer nổi bật."
                )

            peer_commentary = v.get("peer_commentary") or peer.get("commentary")
            if peer_commentary:
                st.info(peer_commentary)

        st.caption(
            "Peer Fair Value là giá trị hàm ý tương đối theo multiples của doanh nghiệp cùng ngành, "
            "không phải giá trị nội tại DCF và không phải target price/khuyến nghị mua bán. "
            "Valuation Score dùng trong Investment Score vẫn là điểm định giá gốc theo P/E, P/B và lịch sử doanh nghiệp."
        )

    with tabs[4]:
        st.markdown('<div class="sl-section-title">Tin tức & triển vọng</div>', unsafe_allow_html=True)
        news_score = n.get("score")
        news_col, _ = st.columns([1, 3])
        news_col.markdown(
            metric_card(
                "News Score",
                "N/A" if news_score is None else f"{news_score:.1f}/100",
                n.get("classification") or "Sentiment tin tức",
                score_tone(news_score),
            ),
            unsafe_allow_html=True,
        )
        st.write(n.get("commentary", ""))
        items = n.get("items", [])
        if not items:
            st.warning("Không có đủ tin liên quan trực tiếp để chấm điểm.")
        else:
            for item in items:
                sentiment = item.get("sentiment", "Neutral")
                st.markdown(
                    f"**{sentiment}** · {esc(item.get('published', ''))}  \n"
                    f"[{esc(item.get('title', ''))}]({item.get('link', '')})"
                )
        st.caption(n.get("source", ""))


def render_report_page(a, ticker, start, end, profile, results, summary, company, financial_data):
    render_company_strip(ticker, company, df=a.get("df"), results=results)

    pdf_bytes = st.session_state.get("custom_pdf") or a.get("pdf")

    head_left, head_right = st.columns([3.2, 1], gap="medium")
    with head_left:
        st.markdown(
            '<div class="sl-report-heading">▣ Báo cáo phân tích doanh nghiệp</div>'
            f'<div class="sl-report-sub">Báo cáo nghiên cứu chi tiết 8 trang về {esc(ticker)} – {esc(company["name"])}</div>',
            unsafe_allow_html=True,
        )
    with head_right:
        if pdf_bytes:
            st.download_button(
                "↓  Tải báo cáo phân tích PDF",
                data=pdf_bytes,
                file_name=f"StockLens_{ticker}_{end}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True,
                key="report_pdf_download_top",
            )
            st.markdown('<div class="sl-report-download-note">Tạo báo cáo với dữ liệu mới nhất</div>', unsafe_allow_html=True)

    st.markdown('<div style="height:7px"></div>', unsafe_allow_html=True)
    nav_col, preview_col = st.columns([1.02, 3.58], gap="medium")

    with nav_col:
        st.markdown(
            """
<div class="sl-report-menu">
  <div class="sl-report-menu-item"><span>▧</span><div><b>Tổng quan đầu tư</b><br><small>Thông tin chung và chỉ số nổi bật</small></div></div>
  <div class="sl-report-menu-item"><span>⌁</span><div><b>Phân tích kỹ thuật</b><br><small>Xu hướng giá, động lượng, rủi ro</small></div></div>
  <div class="sl-report-menu-item"><span>▥</span><div><b>Phân tích tài chính</b><br><small>KQKD, cân đối kế toán, dòng tiền</small></div></div>
  <div class="sl-report-menu-item"><span>◔</span><div><b>Phân tích định giá</b><br><small>P/E, P/B và lịch sử định giá</small></div></div>
  <div class="sl-report-menu-item"><span>▤</span><div><b>Tin tức & triển vọng</b><br><small>Cập nhật tin mới và triển vọng</small></div></div>
  <div class="sl-report-menu-item active"><span>▣</span><div><b>Báo cáo phân tích</b><br><small>Tải báo cáo PDF chi tiết</small></div></div>
</div>
""",
            unsafe_allow_html=True,
        )

        st.markdown('<div class="sl-section-title" style="margin-top:12px">Tùy chọn báo cáo</div>', unsafe_allow_html=True)
        labels = {
            "technical": "Kỹ thuật", "fundamental": "Tài chính", "valuation": "Định giá",
            "news": "Tin tức", "score": "Điểm tổng hợp", "method": "Phương pháp & nguồn",
        }
        pdf_sections = st.multiselect(
            "Nội dung đưa vào PDF",
            list(labels), default=list(labels), format_func=lambda k: labels[k], key="report_pdf_sections",
        )
        if st.button("Tạo lại PDF", use_container_width=True, key="report_regenerate_pdf"):
            try:
                custom_pdf = generate_pdf(
                    ticker, f"{start} → {end}", results, summary, pdf_sections, profile,
                    company_info=company, financial_data=financial_data,
                )
                st.session_state["custom_pdf"] = custom_pdf
                pdf_bytes = custom_pdf
                st.success("Đã tạo lại PDF.")
                st.rerun()
            except Exception as exc:
                st.error(f"Không tạo được PDF: {exc}")

        quick = "".join([
            quick_row("Investment Score", "N/A" if summary.get("score") is None else f"{summary['score']:.1f}/100"),
            quick_row("Hồ sơ", profile),
            quick_row("Kỳ BCTC", company.get("report_period") or "N/A"),
            quick_row("P/E", "N/A" if company.get("pe") is None else f"{company['pe']:.2f}x"),
            quick_row("P/B", "N/A" if company.get("pb") is None else f"{company['pb']:.2f}x"),
        ])
        st.markdown('<div class="sl-panel" style="margin-top:10px">' + quick + '</div>', unsafe_allow_html=True)

    with preview_col:
        st.markdown('<div class="sl-report-shell">', unsafe_allow_html=True)
        if pdf_bytes:
            b64 = base64.b64encode(pdf_bytes).decode("ascii")
            st.markdown(
                f"""<div class=\"sl-pdf-frame\">
<iframe src=\"data:application/pdf;base64,{b64}#toolbar=1&navpanes=1&scrollbar=1\" width=\"100%\" height=\"820\" style=\"border:0;border-radius:8px;background:#fff\"></iframe>
</div>""",
                unsafe_allow_html=True,
            )
        elif a.get("pdf_error"):
            st.error(a["pdf_error"])
        else:
            st.warning("PDF chưa được tạo trong lần phân tích hiện tại.")
        st.markdown('</div>', unsafe_allow_html=True)


def render_about_page():
    st.markdown(
        """
<div class="sl-panel" style="padding:22px 24px">
  <div class="sl-section-title" style="margin-top:0">Giới thiệu StockLens</div>
  <div style="font-size:.88rem;color:#4F6076;line-height:1.75">
    <b>StockLens – Hệ thống phân tích và đánh giá cơ hội đầu tư cổ phiếu</b> là nền tảng phục vụ mục đích học tập,
    tổng hợp dữ liệu thị trường, báo cáo tài chính, định giá, chỉ báo kỹ thuật, tin tức và rủi ro thành một góc nhìn thống nhất.
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sl-section-title" style="margin-top:16px">Nguồn dữ liệu</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.markdown(kpi("DNSE OpenAPI", "OHLCV", "Giá • Khối lượng • Dữ liệu thị trường", "sl-kpi-good"), unsafe_allow_html=True)
    c2.markdown(kpi("vnstock / KBS", "BCTC", "Báo cáo tài chính • Chỉ số • Định giá", "sl-kpi-good"), unsafe_allow_html=True)
    c3.markdown(kpi("Google News RSS", "NEWS", "Tin tức và sentiment tiêu đề", "sl-kpi-warn"), unsafe_allow_html=True)

    st.markdown('<div class="sl-section-title" style="margin-top:16px">Mô hình Investment Score</div>', unsafe_allow_html=True)
    score_df = pd.DataFrame([
        {"Thành phần": "Fundamental", "Trọng số": "25%", "Nội dung": "Doanh nghiệp thường: ROE, ROA, margin, growth, D/E, Current Ratio; ngân hàng dùng bộ KPI riêng"},
        {"Thành phần": "Valuation", "Trọng số": "25%", "Nội dung": "P/E, P/B và lịch sử doanh nghiệp; Peer Valuation theo ICB là lớp phân tích bổ sung"},
        {"Thành phần": "Technical", "Trọng số": "25%", "Nội dung": "MA20, MA50, RSI, MACD, Volume, Volatility"},
        {"Thành phần": "News/Sentiment", "Trọng số": "15%", "Nội dung": "Sentiment tiêu đề và trọng số theo độ mới"},
        {"Thành phần": "Risk/Safety", "Trọng số": "10%", "Nội dung": "Volatility và Maximum Drawdown"},
    ])
    st.dataframe(score_df, use_container_width=True, hide_index=True)

    st.info(
        "StockLens là công cụ hỗ trợ nghiên cứu. Các ngưỡng chấm điểm là heuristic của nhóm, không phải chuẩn đầu tư phổ quát, "
        "không phải dự báo chắc chắn và không phải khuyến nghị mua/bán hoặc tư vấn đầu tư cá nhân."
    )


# -----------------------------------------------------------------------------
# Page routing
# -----------------------------------------------------------------------------
if current_page in {"overview", "analysis"}:
    render_analysis_form()

if current_page == "about":
    render_about_page()
    st.caption("StockLens • Giá: DNSE OpenAPI • BCTC/chỉ số: vnstock/KBS • Tin tức: Google News RSS • Dự án học tập • Không phải khuyến nghị mua/bán hoặc tư vấn đầu tư cá nhân.")
    st.stop()

if "analysis" not in st.session_state:
    render_empty_state(current_page)
    st.caption("StockLens • Giá: DNSE OpenAPI • BCTC/chỉ số: vnstock/KBS • Tin tức: Google News RSS • Dự án học tập • Không phải khuyến nghị mua/bán hoặc tư vấn đầu tư cá nhân.")
    st.stop()

# Shared analyzed data
a = st.session_state["analysis"]
ticker = a["ticker"]
start = a["start"]
end = a["end"]
profile = a["profile"]
df = a["df"]
results = a["results"]
summary = a["summary"]
company = a["company"]
financial_data = a["financial_data"]

if current_page == "overview":
    render_overview_page(a, ticker, start, end, profile, df, results, summary, company, financial_data)
elif current_page == "analysis":
    render_analysis_page(ticker, profile, results, summary, company, financial_data)
elif current_page == "report":
    render_report_page(a, ticker, start, end, profile, results, summary, company, financial_data)

st.caption("StockLens • Giá: DNSE OpenAPI • BCTC/chỉ số: vnstock/KBS • Tin tức: Google News RSS • Dự án học tập • Không phải khuyến nghị mua/bán hoặc tư vấn đầu tư cá nhân.")
