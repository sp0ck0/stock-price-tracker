import os
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pandas as pd


# ── HTML helpers ──────────────────────────────────────────────────────────────

_TH_STYLE = "padding:8px 12px;text-align:left;white-space:nowrap"
_TD_STYLE = "padding:7px 12px;border-bottom:1px solid #eee;white-space:nowrap"


def _score_color(score: int) -> str:
    return {4: "#0a6e2e", 3: "#1f7a45"}.get(score, "#555")


def _fmt_alpha(val) -> str:
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.1f}%"


def _fmt_beta(val) -> str:
    return "N/A" if val is None else f"{val:.2f}"


def _build_table(df: pd.DataFrame, score_col: str, title: str, accent: str) -> str:
    if df.empty:
        return (
            f"<h2 style='color:{accent};margin-top:32px'>{title}</h2>"
            "<p style='color:#666'>No stocks met the minimum signal threshold today.</p>"
        )

    header = f"""
<h2 style="color:{accent};margin-top:32px;border-left:4px solid {accent};padding-left:10px">{title}</h2>
<table style="border-collapse:collapse;width:100%;font-size:13px;background:#fff">
  <thead>
    <tr style="background:{accent};color:#fff">
      <th style="{_TH_STYLE}">Ticker</th>
      <th style="{_TH_STYLE}">Company</th>
      <th style="{_TH_STYLE}">Price</th>
      <th style="{_TH_STYLE}">% from 52wk Low</th>
      <th style="{_TH_STYLE}">% from 52wk High</th>
      <th style="{_TH_STYLE}">RSI</th>
      <th style="{_TH_STYLE}">Beta</th>
      <th style="{_TH_STYLE}">Alpha (ann.)</th>
      <th style="{_TH_STYLE}">MA Signal</th>
      <th style="{_TH_STYLE}">Score</th>
    </tr>
  </thead>
  <tbody>"""

    body_rows = []
    for _, row in df.iterrows():
        score = row[score_col]
        body_rows.append(f"""
    <tr>
      <td style="{_TD_STYLE}"><strong>{row['ticker']}</strong></td>
      <td style="{_TD_STYLE}">{row['company']}</td>
      <td style="{_TD_STYLE}">${row['price']:.2f}</td>
      <td style="{_TD_STYLE}">{row['pct_from_low']:.1f}%</td>
      <td style="{_TD_STYLE}">{row['pct_from_high']:.1f}%</td>
      <td style="{_TD_STYLE}">{row['rsi']:.1f}</td>
      <td style="{_TD_STYLE}">{_fmt_beta(row['beta'])}</td>
      <td style="{_TD_STYLE}">{_fmt_alpha(row['alpha_pct'])}</td>
      <td style="{_TD_STYLE}">{row['ma_signal']}</td>
      <td style="{_TD_STYLE};color:{_score_color(score)};font-weight:bold">{score}/4</td>
    </tr>""")

    return header + "".join(body_rows) + "\n  </tbody>\n</table>"


def build_html(buys: pd.DataFrame, sells: pd.DataFrame) -> str:
    today = date.today().strftime("%B %d, %Y")
    buy_table  = _build_table(
        buys.sort_values("buy_score", ascending=False),
        "buy_score", "Top Buy Opportunities", "#0a6e2e",
    )
    sell_table = _build_table(
        sells.sort_values("sell_score", ascending=False),
        "sell_score", "Top Sell Candidates", "#b5131a",
    )
    return f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,Helvetica,sans-serif;max-width:1100px;margin:auto;padding:24px;color:#222">
  <h1 style="border-bottom:2px solid #333;padding-bottom:10px">
    S&amp;P 500 Stock Signal Report &mdash; {today}
  </h1>
  <p style="color:#555;margin-top:0">
    Stocks scoring <strong>3 or 4 out of 4 signals</strong>.
    Signals: 52-week range proximity &bull; Moving average crossover &bull; RSI &bull; Alpha &amp; Beta.
  </p>

  {buy_table}
  {sell_table}

  <hr style="margin-top:48px;border:none;border-top:1px solid #ddd">
  <p style="color:#999;font-size:11px">
    This report is for informational purposes only and does not constitute financial advice.
    Always conduct your own research before making investment decisions.
    Data sourced from Yahoo Finance via yfinance.
  </p>
</body>
</html>"""


# ── Send ──────────────────────────────────────────────────────────────────────

def send_email(buys: pd.DataFrame, sells: pd.DataFrame) -> None:
    from_addr = os.environ["EMAIL_FROM"]
    to_addr   = os.environ["EMAIL_TO"]
    password  = os.environ["EMAIL_APP_PASSWORD"]

    today = date.today().strftime("%Y-%m-%d")
    n_buy  = len(buys)
    n_sell = len(sells)
    subject = f"[Stock Tracker] {n_buy} buy / {n_sell} sell signal(s) — {today}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_addr
    msg.attach(MIMEText(build_html(buys, sells), "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_addr, password)
        server.sendmail(from_addr, to_addr, msg.as_string())

    print(f"Email sent — {n_buy} buy, {n_sell} sell signal(s) to {to_addr}")
