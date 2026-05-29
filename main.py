#!/usr/bin/env python3
"""
Stock Price Tracker & Analyzer
Fetches all S&P 500 daily prices, scores buy/sell signals, emails a report.
"""

import sys
import traceback

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

import yfinance as yf

from analyzer import analyze
from emailer import send_email
from sp500 import get_sp500_tickers

MIN_SCORE = 3   # minimum signal count (out of 4) to include in the email


def main() -> None:
    print("Fetching S&P 500 ticker list from Wikipedia...")
    tickers, companies = get_sp500_tickers()
    print(f"  {len(tickers)} tickers found")

    all_symbols = tickers + ["^GSPC"]
    print(f"Downloading 1 year of daily price data for {len(all_symbols)} symbols (this may take ~60s)...")
    data = yf.download(
        all_symbols,
        period="1y",
        interval="1d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )

    if data.empty:
        print("ERROR: yfinance returned no data.", file=sys.stderr)
        sys.exit(1)

    print(f"  Download complete. DataFrame shape: {data.shape}, columns type: {type(data.columns).__name__}")

    # With multiple tickers yfinance returns MultiIndex columns: (field, ticker)
    if isinstance(data.columns, pd.MultiIndex):
        closes = data["Close"]
    else:
        closes = data[["Close"]].rename(columns={"Close": all_symbols[0]})

    print(f"  Close prices shape: {closes.shape}")

    if "^GSPC" not in closes.columns:
        print(f"ERROR: S&P 500 benchmark (^GSPC) not found. Available columns (first 10): {list(closes.columns[:10])}", file=sys.stderr)
        sys.exit(1)

    market_closes = closes["^GSPC"]
    stock_closes  = closes.drop(columns=["^GSPC"])

    print("Running signal analysis...")
    results = analyze(stock_closes, market_closes, companies)
    print(f"  Analyzed {len(results)} stocks")

    buys  = results[results["buy_score"]  >= MIN_SCORE].copy()
    sells = results[results["sell_score"] >= MIN_SCORE].copy()
    print(f"  Buy signals (score >= {MIN_SCORE}): {len(buys)}")
    print(f"  Sell signals (score >= {MIN_SCORE}): {len(sells)}")

    if buys.empty and sells.empty:
        print("No stocks met the minimum score threshold today. No email sent.")
        return

    print("Sending email report...")
    send_email(buys, sells)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\n--- UNHANDLED EXCEPTION ---", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
