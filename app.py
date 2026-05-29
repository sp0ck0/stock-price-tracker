import time

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

from analyzer import (
    MIN_HISTORY, _beta_alpha, _rsi,
    MA_SHORT, MA_LONG, NEAR_52WK_PCT,
)

_QUOTE_TYPE_LABEL = {
    "EQUITY":     "Stock",
    "ETF":        "ETF",
    "MUTUALFUND": "Mutual Fund",
    "INDEX":      "Index",
}

_REC_LABELS = {
    (1.0, 1.5): ("Strong Buy",  "green"),
    (1.5, 2.5): ("Buy",         "green"),
    (2.5, 3.5): ("Hold",        "gray"),
    (3.5, 4.5): ("Sell",        "red"),
    (4.5, 5.1): ("Strong Sell", "red"),
}

def _rec_label(mean: float) -> tuple[str, str]:
    for (lo, hi), (label, color) in _REC_LABELS.items():
        if lo <= mean < hi:
            return label, color
    return "N/A", "gray"


def _yf_call(fn, retries: int = 3, delay: float = 2.0):
    """Call a yfinance function, retrying on rate-limit errors."""
    for attempt in range(retries):
        try:
            return fn()
        except YFRateLimitError:
            if attempt < retries - 1:
                time.sleep(delay * (attempt + 1))
            else:
                raise
    return None


@st.cache_data(ttl=300, show_spinner=False)
def search_securities(query: str) -> list[dict]:
    try:
        results = _yf_call(lambda: yf.Search(query, max_results=10).quotes)
        us_exchanges = {
            "NMS", "NYQ", "NGM", "NCM", "PCX", "ASE",
            "BTS", "YHD", "NAS", "NYS",
        }
        return [
            r for r in (results or [])
            if r.get("quoteType") in ("EQUITY", "ETF", "MUTUALFUND", "INDEX")
            and r.get("exchange") in us_exchanges
        ]
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def fetch_prices(ticker: str) -> pd.DataFrame:
    return _yf_call(lambda: yf.download(
        [ticker, "^GSPC"],
        period="1y",
        interval="1d",
        auto_adjust=True,
        progress=False,
    ))


@st.cache_data(ttl=300, show_spinner=False)
def fetch_info(ticker: str) -> dict:
    try:
        return _yf_call(lambda: yf.Ticker(ticker).info) or {}
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner=False)
def fetch_recommendations(ticker: str) -> pd.DataFrame | None:
    try:
        return _yf_call(lambda: yf.Ticker(ticker).recommendations)
    except Exception:
        return None


# ── Page ──────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Stock Analyzer", page_icon="📈", layout="wide")
st.title("📈 Stock Direction Analyzer")

query = st.text_input(
    "Search by ticker, company name, ETF, or mutual fund",
    placeholder="e.g. Apple, AAPL, QQQ, Vanguard 500",
).strip()

if not query:
    st.stop()

with st.spinner("Searching..."):
    results = search_securities(query)

if not results:
    st.warning("No results found. Try a different name or ticker symbol.")
    st.stop()

def _fmt(r: dict) -> str:
    name  = r.get("longname") or r.get("shortname") or r["symbol"]
    qtype = _QUOTE_TYPE_LABEL.get(r.get("quoteType", ""), r.get("quoteType", ""))
    return f"{r['symbol']} — {name} ({qtype})"

options      = [_fmt(r) for r in results]
selected     = st.selectbox("Select a security", options)
sel_quote    = results[options.index(selected)]
ticker_sym   = sel_quote["symbol"]
quote_type   = sel_quote.get("quoteType", "EQUITY")

# ── Fetch data (all cached) ───────────────────────────────────────────────────
with st.spinner(f"Fetching data for {ticker_sym}..."):
    data = fetch_prices(ticker_sym)
    info = fetch_info(ticker_sym)

if data is None or data.empty:
    st.error(f"No price data found for **{ticker_sym}**.")
    st.stop()

closes = data["Close"]
if ticker_sym not in closes.columns:
    st.error(f"Could not load prices for **{ticker_sym}**.")
    st.stop()

prices = closes[ticker_sym].dropna()
market = closes["^GSPC"].dropna()

if len(prices) < MIN_HISTORY:
    st.warning(f"Not enough price history ({len(prices)} days, need {MIN_HISTORY}).")
    st.stop()

# ── Technical signals ─────────────────────────────────────────────────────────
company       = info.get("longName") or info.get("shortName") or sel_quote.get("longname") or ticker_sym
current       = float(prices.iloc[-1])
window        = prices.tail(252)
high_52       = float(window.max())
low_52        = float(window.min())
pct_from_low  = (current - low_52)  / low_52  * 100
pct_from_high = (high_52 - current) / high_52 * 100

rsi_val      = _rsi(prices)
ma50         = prices.rolling(MA_SHORT).mean()
ma200        = prices.rolling(MA_LONG).mean()
golden_cross = bool(ma50.iloc[-2] <= ma200.iloc[-2] and ma50.iloc[-1] > ma200.iloc[-1])
death_cross  = bool(ma50.iloc[-2] >= ma200.iloc[-2] and ma50.iloc[-1] < ma200.iloc[-1])
beta, alpha  = _beta_alpha(prices.pct_change().dropna(), market.pct_change().dropna())
alpha_ok     = not np.isnan(alpha)
beta_ok      = not np.isnan(beta)

# ── Analyst sentiment (stocks only) ──────────────────────────────────────────
is_stock     = quote_type == "EQUITY"
rec_mean     = info.get("recommendationMean")              if is_stock else None
num_analysts = (info.get("numberOfAnalystOpinions") or 0)  if is_stock else 0
target_mean  = info.get("targetMeanPrice")                 if is_stock else None
target_low   = info.get("targetLowPrice")                  if is_stock else None
target_high  = info.get("targetHighPrice")                 if is_stock else None
upside_pct   = ((target_mean - current) / current * 100)   if target_mean else None

analyst_bullish = rec_mean    is not None and rec_mean    <= 2.5
analyst_bearish = rec_mean    is not None and rec_mean    >= 3.5
target_bullish  = upside_pct  is not None and upside_pct  >= 10
target_bearish  = upside_pct  is not None and upside_pct  <= -5

# ── Signal lists ──────────────────────────────────────────────────────────────
buy_signals = [
    ("Near 52-week low",        pct_from_low  <= NEAR_52WK_PCT * 100),
    ("Golden Cross (MA)",       golden_cross),
    ("RSI oversold (<30)",      rsi_val < 30),
    ("Strong alpha & low beta", alpha_ok and beta_ok and alpha > 0 and beta < 1),
]
sell_signals = [
    ("Near 52-week high",       pct_from_high <= NEAR_52WK_PCT * 100),
    ("Death Cross (MA)",        death_cross),
    ("RSI overbought (>70)",    rsi_val > 70),
    ("Weak alpha & high beta",  alpha_ok and beta_ok and alpha < 0 and beta > 1),
]
max_score = 4

if is_stock:
    buy_signals  += [
        ("Analyst consensus: Buy",   analyst_bullish),
        ("Price target upside ≥10%", target_bullish),
    ]
    sell_signals += [
        ("Analyst consensus: Sell",  analyst_bearish),
        ("Price target downside",    target_bearish),
    ]
    max_score = 6

buy_score  = sum(v for _, v in buy_signals)
sell_score = sum(v for _, v in sell_signals)

if buy_score > sell_score:
    direction, color, icon = "BULLISH", "green", "🟢"
elif sell_score > buy_score:
    direction, color, icon = "BEARISH", "red", "🔴"
else:
    direction, color, icon = "NEUTRAL", "gray", "⚪"

# ── Header ────────────────────────────────────────────────────────────────────
type_label = _QUOTE_TYPE_LABEL.get(quote_type, quote_type)
st.subheader(f"{company} ({ticker_sym})  ·  {type_label}")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Price",        f"${current:.2f}")
col2.metric("52-week High", f"${high_52:.2f}",  f"-{pct_from_high:.1f}%")
col3.metric("52-week Low",  f"${low_52:.2f}",   f"+{pct_from_low:.1f}%")
col4.metric("RSI (14)",     f"{rsi_val:.1f}")

st.markdown(
    f"### {icon} Direction: :{color}[**{direction}**]  "
    f"—  Buy score: {buy_score}/{max_score} · Sell score: {sell_score}/{max_score}"
)

# ── Signal breakdown ──────────────────────────────────────────────────────────
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Buy signals**")
    for label, triggered in buy_signals:
        st.markdown(f"{'✅' if triggered else '⬜'} {label}")
with c2:
    st.markdown("**Sell signals**")
    for label, triggered in sell_signals:
        st.markdown(f"{'🔴' if triggered else '⬜'} {label}")

if beta_ok and alpha_ok:
    st.caption(f"Beta: {beta:.2f}  |  Alpha (ann.): {'+' if alpha >= 0 else ''}{alpha*100:.1f}%")

# ── Analyst sentiment panel ───────────────────────────────────────────────────
if is_stock:
    st.markdown("---")
    st.markdown("### 🧑‍💼 Analyst Sentiment")
    a1, a2, a3 = st.columns(3)

    if rec_mean is not None:
        rec_str, _ = _rec_label(rec_mean)
        a1.metric("Consensus Rating", rec_str, f"{num_analysts} analyst{'s' if num_analysts != 1 else ''}")
        a1.caption(f"Score: {rec_mean:.2f} / 5.0  (1=Strong Buy, 5=Strong Sell)")
    else:
        a1.metric("Consensus Rating", "N/A")

    if target_mean is not None:
        sign = "+" if upside_pct >= 0 else ""
        a2.metric("Mean Price Target", f"${target_mean:.2f}", f"{sign}{upside_pct:.1f}% vs current")
    else:
        a2.metric("Mean Price Target", "N/A")

    if target_low is not None and target_high is not None:
        a3.metric("Target Range", f"${target_low:.2f} – ${target_high:.2f}")
    else:
        a3.metric("Target Range", "N/A")

    recs = fetch_recommendations(ticker_sym)
    if recs is not None and not recs.empty:
        st.markdown("**Recent analyst actions (last 10)**")
        st.dataframe(recs.tail(10).iloc[::-1], use_container_width=True)

# ── Price + MA chart ──────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("**Price with 50-day and 200-day moving averages**")
chart_df = pd.DataFrame({
    "Price":  prices,
    "MA 50":  ma50,
    "MA 200": ma200,
}).dropna(subset=["MA 200"])
st.line_chart(chart_df)

# ── RSI chart ─────────────────────────────────────────────────────────────────
st.markdown("**RSI (14-day)**")
delta    = prices.diff().dropna()
gains    = delta.clip(lower=0)
losses   = (-delta).clip(lower=0)
avg_gain = gains.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
avg_loss = losses.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
rs = avg_gain / avg_loss.replace(0, np.nan)
rsi_series = (100 - (100 / (1 + rs))).fillna(100)
rsi_series = rsi_series[rsi_series.index >= chart_df.index[0]]

st.line_chart(pd.DataFrame({"RSI": rsi_series}))
st.caption("Oversold < 30  |  Overbought > 70")
