# Stock Price Tracker & Analyzer

Analyzes all S&P 500 stocks every weekday after market close and emails a ranked
HTML report of the best buy and sell opportunities.

## How it works

1. Pulls the current S&P 500 constituent list from Wikipedia.
2. Downloads 1 year of daily adjusted close prices via [yfinance](https://github.com/ranaroussi/yfinance) (no API key needed).
3. Scores each stock on **4 signals** (0–4 points each for buy and sell):

| Signal | Buy | Sell |
|--------|-----|------|
| **52-week range** | Price within 5% of 52wk low | Price within 5% of 52wk high |
| **Moving average** | 50-day MA crosses above 200-day MA (Golden Cross) | 50-day MA crosses below 200-day MA (Death Cross) |
| **RSI (14-day)** | RSI < 30 (oversold) | RSI > 70 (overbought) |
| **Alpha / Beta** | Alpha > 0 and Beta < 1 | Alpha < 0 and Beta > 1 |

4. Emails an HTML report listing any stock that scores **3 or 4 out of 4** signals.

> **Disclaimer:** This tool is for informational purposes only.
> It does not constitute financial advice. Always do your own research.

---

## Setup

### Prerequisites

- Python 3.11+
- A Gmail account with an [App Password](https://myaccount.google.com/apppasswords) configured

### Local installation

```bash
cd stock-tracker
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Gmail credentials
python main.py
```

### GitHub Actions (automated daily runs)

The tool runs automatically at **4:15 pm ET every weekday** via GitHub Actions.

**Required repository secrets** (Settings → Secrets → Actions):

| Secret | Value |
|--------|-------|
| `EMAIL_FROM` | Gmail address that sends alerts |
| `EMAIL_TO` | Gmail address that receives alerts |
| `EMAIL_APP_PASSWORD` | 16-character Gmail App Password |

#### Running in ncdmv-checker (current repo)

The workflow at `.github/workflows/stock-tracker.yml` is already configured
with `working-directory: stock-tracker`, so it runs from within this subfolder.

#### Moving to a standalone repo

1. Create a new GitHub repository.
2. Copy the **contents** of this `stock-tracker/` folder to the new repo root.
3. The `.github/workflows/stock-tracker.yml` inside this folder is already
   written for a standalone repo (no `working-directory` needed).
4. Add the three secrets above to the new repo.
5. Push — the Action will activate on the next weekday at 4:15 pm ET.

---

## File structure

```
stock-tracker/
  main.py          # orchestrator: fetch → analyze → email
  sp500.py         # fetches current S&P 500 tickers from Wikipedia
  analyzer.py      # computes RSI, moving averages, beta, alpha, signal scores
  emailer.py       # builds and sends the HTML email report
  requirements.txt
  .env.example
  .github/
    workflows/
      stock-tracker.yml   # standalone-repo workflow
```

---

## Signal details

### RSI (Relative Strength Index)
14-period Wilder's RSI. Below 30 suggests oversold conditions; above 70 suggests overbought.

### Moving Average Crossover
50-day and 200-day simple moving averages. A **Golden Cross** (50 crosses above 200) is
a classic bullish signal; a **Death Cross** (50 crosses below 200) is bearish.

### Beta
Sensitivity to S&P 500 market movements, calculated from 1 year of daily returns.
Beta < 1 = lower volatility than the market; Beta > 1 = higher volatility.

### Alpha (Jensen's Alpha, annualised)
Excess return above what CAPM predicts given the stock's beta.
Positive alpha = outperforming; negative alpha = underperforming.
Uses a 4.3% annual risk-free rate (approximate 10-year Treasury yield).
