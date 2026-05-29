import numpy as np
import pandas as pd

RISK_FREE_RATE = 0.043        # ~4.3% annual (10-year Treasury approximation)
NEAR_52WK_PCT   = 0.05        # 5% threshold for "near" 52-week high/low
RSI_PERIOD      = 14
MA_SHORT        = 50
MA_LONG         = 200
MIN_HISTORY     = MA_LONG + 5 # need at least 205 trading days of data


def _rsi(prices: pd.Series) -> float:
    delta  = prices.diff().dropna()
    gains  = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    # Wilder's smoothing: alpha = 1/period
    avg_gain = gains.ewm(alpha=1 / RSI_PERIOD, min_periods=RSI_PERIOD, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1 / RSI_PERIOD, min_periods=RSI_PERIOD, adjust=False).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


def _beta_alpha(stock_ret: pd.Series, market_ret: pd.Series) -> tuple[float, float]:
    aligned = pd.concat([stock_ret, market_ret], axis=1).dropna()
    if len(aligned) < 30:
        return np.nan, np.nan
    s = aligned.iloc[:, 0].values
    m = aligned.iloc[:, 1].values
    beta = float(np.cov(s, m)[0, 1] / np.var(m))
    # Jensen's alpha (annualised from daily)
    rf_daily    = (1 + RISK_FREE_RATE) ** (1 / 252) - 1
    alpha_daily = s.mean() - rf_daily - beta * (m.mean() - rf_daily)
    alpha_ann   = alpha_daily * 252
    return beta, alpha_ann


def analyze(closes: pd.DataFrame, market_closes: pd.Series, companies: dict) -> pd.DataFrame:
    """
    closes        — DataFrame of daily adjusted close prices, tickers as columns
    market_closes — Series of S&P 500 (^GSPC) adjusted close prices
    companies     — {ticker: company_name}

    Returns a DataFrame with one row per ticker including signal scores.
    """
    market_ret = market_closes.pct_change().dropna()
    rows = []

    for ticker in closes.columns:
        prices = closes[ticker].dropna()
        if len(prices) < MIN_HISTORY:
            continue
        try:
            current = float(prices.iloc[-1])
            window  = prices.tail(252)
            high_52 = float(window.max())
            low_52  = float(window.min())
            pct_from_low  = (current - low_52)  / low_52  * 100
            pct_from_high = (high_52 - current) / high_52 * 100

            rsi = _rsi(prices)

            ma50  = prices.rolling(MA_SHORT).mean()
            ma200 = prices.rolling(MA_LONG).mean()
            golden_cross = bool(ma50.iloc[-2] <= ma200.iloc[-2] and ma50.iloc[-1] > ma200.iloc[-1])
            death_cross  = bool(ma50.iloc[-2] >= ma200.iloc[-2] and ma50.iloc[-1] < ma200.iloc[-1])
            if golden_cross:
                ma_signal = "Golden Cross"
            elif death_cross:
                ma_signal = "Death Cross"
            else:
                ma_signal = "Neutral"

            beta, alpha = _beta_alpha(prices.pct_change().dropna(), market_ret)

            alpha_ok = not np.isnan(alpha)
            beta_ok  = not np.isnan(beta)

            buy_score = sum([
                pct_from_low  <= NEAR_52WK_PCT * 100,   # near 52wk low
                golden_cross,                             # MA crossover up
                rsi < 30,                                 # oversold
                alpha_ok and beta_ok and alpha > 0 and beta < 1,  # outperforming + low vol
            ])
            sell_score = sum([
                pct_from_high <= NEAR_52WK_PCT * 100,   # near 52wk high
                death_cross,                              # MA crossover down
                rsi > 70,                                 # overbought
                alpha_ok and beta_ok and alpha < 0 and beta > 1,  # underperforming + high vol
            ])

            rows.append({
                "ticker":        ticker,
                "company":       companies.get(ticker, ticker),
                "price":         round(current, 2),
                "52wk_high":     round(high_52, 2),
                "52wk_low":      round(low_52, 2),
                "pct_from_low":  round(pct_from_low, 1),
                "pct_from_high": round(pct_from_high, 1),
                "rsi":           round(rsi, 1),
                "beta":          round(beta, 2) if beta_ok else None,
                "alpha_pct":     round(alpha * 100, 1) if alpha_ok else None,  # stored as %, e.g. 5.2
                "ma_signal":     ma_signal,
                "buy_score":     buy_score,
                "sell_score":    sell_score,
            })
        except Exception:
            continue

    return pd.DataFrame(rows)
