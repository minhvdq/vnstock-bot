from __future__ import annotations
import pandas as pd
from app.algorithms.base import BaseStrategy


class DonchianStrategy(BaseStrategy):
    """
    Donchian Channel Breakout strategy (daily bars).

    Buy when:
      1. close > highest close of previous `lookback` bars (price breakout)
      2. volume > vol_multiplier x avg volume of last vol_window bars

    Sell when close < rolling min of last exit_lookback bars (trailing exit).
    """
    timeframe = "daily"
    display_name = "Donchian Breakout"
    exit_rules = {
        "stop_loss_pct": -0.07,
        "take_profit_pct": 0.20,
        "max_days": 20,
        "eod_close": False,
    }

    def __init__(
        self,
        lookback: int = 20,
        vol_multiplier: float = 1.5,
        vol_window: int = 20,
        exit_lookback: int = 10,
    ):
        self.lookback = lookback
        self.vol_multiplier = vol_multiplier
        self.vol_window = vol_window
        self.exit_lookback = exit_lookback

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0

        # shift(1) excludes current bar — breakout must exceed PRIOR bars' high/low
        df['_rolling_high'] = df['close'].shift(1).rolling(self.lookback).max()
        df['_rolling_low'] = df['close'].shift(1).rolling(self.exit_lookback).min()
        df['_avg_vol'] = df['volume'].rolling(self.vol_window).mean()

        for i in range(self.lookback + 1, len(df)):
            close = df.iloc[i]['close']
            rolling_high = df.iloc[i]['_rolling_high']
            rolling_low = df.iloc[i]['_rolling_low']
            avg_vol = df.iloc[i]['_avg_vol']
            volume = df.iloc[i]['volume']

            if pd.isna(rolling_high) or pd.isna(avg_vol):
                continue

            if close > rolling_high and volume > self.vol_multiplier * avg_vol:
                df.iloc[i, df.columns.get_loc('signal')] = 1
            elif (not pd.isna(rolling_low)
                  and close < rolling_low
                  and rolling_high > rolling_low):
                # Sell only when trailing floor has been lifted by a prior
                # upward breakout (rolling_high > rolling_low), preventing
                # false exits on flat / slightly declining data.
                df.iloc[i, df.columns.get_loc('signal')] = -1

        df.drop(columns=['_rolling_high', '_rolling_low', '_avg_vol'], inplace=True)
        return df
