import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from analyzer import (
    MIN_HISTORY, _beta_alpha, _rsi,
    MA_SHORT, MA_LONG, NEAR_52WK_PCT,
)

st.set_page_config(page_title="Stock Analyzer", page_icon="📈", layout="wide")
st.title("📈 Stock Direction Analyzer")

ticker_input = st.text_input("Enter a stock ticker", placeholder="e.g. AAPL, TSLA, NVDA").strip().upper()

if not ticker_input:
    st.stop()

with st.spinner(f"Fetching data for {ticker_input}..."):
    data = yf.download(
        [ticker_input, "^GSPC"],
        period="1y",
        interval="1d",
        auto_adjust=True,
        progress=False,
    )

if data.empty:
    st.error(f"No data found for **{ticker_input}**. Check the ticker and try again.")
    st.stop()

closes = data["Close"]

if ticker_input not in closes.columns:
    st.error(f"Ticker **{ticker_input}** not found. Check the symbol and try again.")
    st.stop()

prices = closes[ticker_input].dropna()
market = closes["^GSPC"].dropna()

if len(prices) < MIN_HISTORY:
    st.warning(f"Not enough history ({len(prices)} days, need {MIN_HISTORY}). Try a more established ticker.")
    st.stop()

# ── Compute signals ───────────────────────────────────────────────────────────
info        = yf.Ticker(ticker_input).info
company     = info.get("longName") or info.get("shortName") or ticker_input
current     = float(prices.iloc[-1])
window      = prices.tail(252)
high_52     = float(window.max())
low_52      = float(window.min())
pct_from_low  = (current - low_52)  / low_52  * 100
pct_from_high = (high_52 - current) / high_52 * 100

rsi_val = _rsi(prices)

ma50  = prices.rolling(MA_SHORT).mean()
ma200 = prices.rolling(MA_LONG).mean()
golden_cross = bool(ma50.iloc[-2] <= ma200.iloc[-2] and ma50.iloc[-1] > ma200.iloc[-1])
death_cross  = bool(ma50.iloc[-2] >= ma200.iloc[-2] and ma50.iloc[-1] < ma200.iloc[-1])

beta, alpha = _beta_alpha(prices.pct_change().dropna(), market.pct_change().dropna())
alpha_ok = not np.isnan(alpha)
beta_ok  = not np.isnan(beta)

buy_signals = [
    ("Near 52-week low",    pct_from_low  <= NEAR_52WK_PCT * 100),
    ("Golden Cross (MA)",   golden_cross),
    ("RSI oversold (<30)",  rsi_val < 30),
    ("Strong alpha & low beta", alpha_ok and beta_ok and alpha > 0 and beta < 1),
]
sell_signals = [
    ("Near 52-week high",   pct_from_high <= NEAR_52WK_PCT * 100),
    ("Death Cross (MA)",    death_cross),
    ("RSI overbought (>70)", rsi_val > 70),
    ("Weak alpha & high beta", alpha_ok and beta_ok and alpha < 0 and beta > 1),
]

buy_score  = sum(v for _, v in buy_signals)
sell_score = sum(v for _, v in sell_signals)

if buy_score > sell_score:
    direction, color, icon = "BULLISH", "green", "🟢"
elif sell_score > buy_score:
    direction, color, icon = "BEARISH", "red", "🔴"
else:
    direction, color, icon = "NEUTRAL", "gray", "⚪"

# ── Header ────────────────────────────────────────────────────────────────────
st.subheader(f"{company} ({ticker_input})")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Price", f"${current:.2f}")
col2.metric("52-week High", f"${high_52:.2f}", f"-{pct_from_high:.1f}%")
col3.metric("52-week Low",  f"${low_52:.2f}",  f"+{pct_from_low:.1f}%")
col4.metric("RSI (14)",     f"{rsi_val:.1f}")

st.markdown(f"### {icon} Direction: :{color}[**{direction}**]  —  Buy score: {buy_score}/4 · Sell score: {sell_score}/4")

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

# ── Price + MA chart ──────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("**Price with 50-day and 200-day moving averages**")
chart_df = pd.DataFrame({
    "Price": prices,
    "MA 50": ma50,
    "MA 200": ma200,
}).dropna(subset=["MA 200"])
st.line_chart(chart_df)

# ── RSI chart ─────────────────────────────────────────────────────────────────
st.markdown("**RSI (14-day)**")
delta  = prices.diff().dropna()
gains  = delta.clip(lower=0)
losses = (-delta).clip(lower=0)
avg_gain = gains.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
avg_loss = losses.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
rs = avg_gain / avg_loss.replace(0, np.nan)
rsi_series = (100 - (100 / (1 + rs))).fillna(100)
rsi_series = rsi_series[rsi_series.index >= chart_df.index[0]]

rsi_df = pd.DataFrame({"RSI": rsi_series})
st.line_chart(rsi_df)
st.caption("Oversold < 30  |  Overbought > 70")
