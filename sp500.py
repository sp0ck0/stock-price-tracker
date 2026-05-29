import io

import pandas as pd
import requests

# Wikipedia blocks the default urllib user-agent; send a browser-like one.
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; stock-tracker-bot/1.0)"}
_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def get_sp500_tickers() -> tuple[list[str], dict[str, str]]:
    """Return (tickers, {ticker: company_name}) for current S&P 500 constituents."""
    try:
        resp = requests.get(_WIKI_URL, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text), header=0)
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch S&P 500 list from Wikipedia: {exc}") from exc

    df = tables[0]
    # Wikipedia uses '.' in some tickers (e.g. BRK.B); yfinance needs '-' (BRK-B)
    symbols = df["Symbol"].str.replace(".", "-", regex=False)
    companies = dict(zip(symbols, df["Security"]))
    return symbols.tolist(), companies
