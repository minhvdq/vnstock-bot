from __future__ import annotations
import pandas as pd
from app.algorithms.base import BaseStrategy


class VolumeBreakoutStrategy(BaseStrategy):
    """
    Volume Breakout strategy (5-min intraday bars).

    Buy when:
      1. close > highest close of previous `lookback` bars
      2. volume > vol_multiplier x avg volume of last vol_window bars

    No sell signal — exits managed entirely by check_positions() via exit_rules.
    Once-per-day deduplication is enforced in the worker, not here.
    """
    timeframe = "intraday"
    display_name = "Volume Breakout (Futures)"
    exit_rules = {
        "stop_loss_pct": -0.02,
        "take_profit_pct": 0.04,
        "max_days": 1,
        "eod_close": True,
    }

    def __init__(
        self,
        lookback: int = 20,
        vol_multiplier: float = 1.5,
        vol_window: int = 20,
    ):
        self.lookback = lookback
        self.vol_multiplier = vol_multiplier
        self.vol_window = vol_window

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0

        # shift(1) excludes current bar from window
        df['_rolling_high'] = df['close'].shift(1).rolling(self.lookback).max()
        df['_avg_vol'] = df['volume'].rolling(self.vol_window).mean()

        for i in range(self.lookback + 1, len(df)):
            close = df.iloc[i]['close']
            rolling_high = df.iloc[i]['_rolling_high']
            avg_vol = df.iloc[i]['_avg_vol']
            volume = df.iloc[i]['volume']

            if pd.isna(rolling_high) or pd.isna(avg_vol):
                continue

            if close > rolling_high and volume > self.vol_multiplier * avg_vol:
                df.iloc[i, df.columns.get_loc('signal')] = 1

        df.drop(columns=['_rolling_high', '_avg_vol'], inplace=True)
        return df
