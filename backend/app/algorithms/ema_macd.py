from __future__ import annotations
import pandas as pd
from app.algorithms.base import BaseStrategy


class EMAMACDStrategy(BaseStrategy):
    """
    EMA + MACD swing strategy (daily bars).

    Buy when:
      1. close > EMA(50) — uptrend filter
      2. MACD line crosses above signal line (12/26/9)
      3. MACD histogram flips from negative to positive

    Sell when MACD line crosses below signal line.
    """
    timeframe = "daily"
    display_name = "EMA+MACD"
    exit_rules = {
        "stop_loss_pct": -0.07,
        "take_profit_pct": 0.15,
        "max_days": 15,
        "eod_close": False,
    }

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9, trend_ema: int = 50):
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self.trend_ema = trend_ema

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0

        close = df['close']
        df['_ema_trend'] = close.ewm(span=self.trend_ema, adjust=False).mean()
        ema_fast = close.ewm(span=self.fast, adjust=False).mean()
        ema_slow = close.ewm(span=self.slow, adjust=False).mean()
        df['_macd'] = ema_fast - ema_slow
        df['_macd_sig'] = df['_macd'].ewm(span=self.signal_period, adjust=False).mean()
        df['_hist'] = df['_macd'] - df['_macd_sig']

        for i in range(1, len(df)):
            price = df.iloc[i]['close']
            ema_trend = df.iloc[i]['_ema_trend']
            macd_now = df.iloc[i]['_macd']
            sig_now = df.iloc[i]['_macd_sig']
            hist_now = df.iloc[i]['_hist']
            macd_prev = df.iloc[i - 1]['_macd']
            sig_prev = df.iloc[i - 1]['_macd_sig']
            hist_prev = df.iloc[i - 1]['_hist']

            # Buy: price above trend EMA, MACD crosses above signal, histogram flips positive
            if (price > ema_trend
                    and macd_now > sig_now and macd_prev <= sig_prev
                    and hist_now > 0 and hist_prev <= 0):
                df.iloc[i, df.columns.get_loc('signal')] = 1

            # Sell: MACD crosses below signal
            elif macd_now < sig_now and macd_prev >= sig_prev:
                df.iloc[i, df.columns.get_loc('signal')] = -1

        # Drop internal indicator columns to keep output clean
        df.drop(columns=['_ema_trend', '_macd', '_macd_sig', '_hist'], inplace=True)
        return df
