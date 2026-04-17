import pandas as pd
import pytest
from app.algorithms.volume_breakout import VolumeBreakoutStrategy


def _make_df(closes: list, volumes: list) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        'time': [f'2024-01-01 {i:02d}:00' for i in range(n)],
        'open': closes,
        'high': [c + 0.5 for c in closes],
        'low': [c - 0.5 for c in closes],
        'close': closes,
        'volume': volumes,
        'RSI': [50.0] * n,
    })


def test_volume_breakout_has_intraday_timeframe():
    assert VolumeBreakoutStrategy.timeframe == "intraday"

def test_volume_breakout_has_exit_rules():
    rules = VolumeBreakoutStrategy.exit_rules
    assert rules["stop_loss_pct"] == -0.02
    assert rules["take_profit_pct"] == 0.04
    assert rules["max_days"] == 1
    assert rules["eod_close"] is True

def test_volume_breakout_has_display_name():
    assert VolumeBreakoutStrategy.display_name == "Volume Breakout"

def test_volume_breakout_buy_signal_on_price_and_volume_spike():
    closes = [100.0] * 25
    volumes = [1000] * 25
    df = _make_df(closes, volumes)
    breakout = _make_df([106.0], [2000])
    df = pd.concat([df, breakout], ignore_index=True)
    result = VolumeBreakoutStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == 1

def test_volume_breakout_no_signal_without_volume():
    closes = [100.0] * 25
    volumes = [1000] * 25
    df = _make_df(closes, volumes)
    no_vol = _make_df([106.0], [1000])
    df = pd.concat([df, no_vol], ignore_index=True)
    result = VolumeBreakoutStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == 0

def test_volume_breakout_no_signal_without_price_breakout():
    closes = [100.0] * 25
    volumes = [1000] * 25
    df = _make_df(closes, volumes)
    no_price = _make_df([99.0], [3000])
    df = pd.concat([df, no_price], ignore_index=True)
    result = VolumeBreakoutStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == 0

def test_volume_breakout_no_sell_signal():
    """VolumeBreakoutStrategy never generates sell signals."""
    closes = [100.0] * 25 + [106.0, 80.0]
    volumes = [1000] * 25 + [2000, 500]
    df = _make_df(closes, volumes)
    result = VolumeBreakoutStrategy().generate_signals(df)
    assert not (result['signal'] == -1).any()

def test_volume_breakout_does_not_mutate_input():
    df = _make_df([100.0] * 30, [1000] * 30)
    original = df.copy()
    VolumeBreakoutStrategy().generate_signals(df)
    pd.testing.assert_frame_equal(df, original)
