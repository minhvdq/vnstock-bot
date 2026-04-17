import pandas as pd
import pytest
from app.algorithms.donchian_breakout import DonchianStrategy


def _make_df(closes: list, volumes: list) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame({
        'time': [f'2024-01-{i+1:03d}' for i in range(n)],
        'open': closes,
        'high': [c + 1 for c in closes],
        'low': [c - 1 for c in closes],
        'close': closes,
        'volume': volumes,
        'RSI': [50.0] * n,
    })


def _flat_base(n=25, price=100.0, volume=1000):
    return _make_df([price] * n, [volume] * n)


def test_donchian_has_daily_timeframe():
    assert DonchianStrategy.timeframe == "daily"

def test_donchian_has_exit_rules():
    rules = DonchianStrategy.exit_rules
    assert rules["stop_loss_pct"] == -0.07
    assert rules["take_profit_pct"] == 0.20
    assert rules["max_days"] == 20
    assert rules["eod_close"] is False

def test_donchian_has_display_name():
    assert DonchianStrategy.display_name == "Donchian Breakout"

def test_donchian_buy_signal_on_price_and_volume_breakout():
    df = _flat_base(25, price=100.0, volume=1000)
    breakout = _make_df([106.0], [2000])
    df = pd.concat([df, breakout], ignore_index=True)
    result = DonchianStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == 1

def test_donchian_no_buy_without_volume_confirmation():
    df = _flat_base(25, price=100.0, volume=1000)
    breakout = _make_df([106.0], [1000])
    df = pd.concat([df, breakout], ignore_index=True)
    result = DonchianStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == 0

def test_donchian_no_buy_without_price_breakout():
    df = _flat_base(25, price=100.0, volume=1000)
    no_breakout = _make_df([99.0], [3000])
    df = pd.concat([df, no_breakout], ignore_index=True)
    result = DonchianStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == 0

def test_donchian_sell_signal_when_below_10day_low():
    closes = [100.0] * 25 + [120.0] * 5 + [85.0]
    volumes = [1000] * 31
    df = _make_df(closes, volumes)
    result = DonchianStrategy().generate_signals(df)
    assert result.iloc[-1]['signal'] == -1

def test_donchian_no_signal_for_flat_data():
    df = _flat_base(30)
    result = DonchianStrategy().generate_signals(df)
    assert (result['signal'] == 0).all()

def test_donchian_does_not_mutate_input():
    df = _flat_base(30)
    original = df.copy()
    DonchianStrategy().generate_signals(df)
    pd.testing.assert_frame_equal(df, original)
