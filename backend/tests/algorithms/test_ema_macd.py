import pandas as pd
import pytest
from app.algorithms.ema_macd import EMAMACDStrategy


def _make_df(closes: list, volumes: list = None) -> pd.DataFrame:
    n = len(closes)
    if volumes is None:
        volumes = [1000] * n
    return pd.DataFrame({
        'time': [f'2024-01-{i+1:03d}' for i in range(n)],
        'open': closes,
        'high': [c + 1 for c in closes],
        'low': [c - 1 for c in closes],
        'close': closes,
        'volume': volumes,
        'RSI': [50.0] * n,
    })


def _flat_then_surge(flat_val=100.0, n_flat=80, surge_vals=None) -> pd.DataFrame:
    """80 flat bars then a sharp uptrend to force MACD crossover above signal."""
    if surge_vals is None:
        surge_vals = [102, 105, 109, 114, 120, 128, 137, 147, 158, 170]
    closes = [flat_val] * n_flat + [float(v) for v in surge_vals]
    return _make_df(closes)


# ── class attributes ──────────────────────────────────────────────────────────

def test_ema_macd_has_daily_timeframe():
    assert EMAMACDStrategy.timeframe == "daily"


def test_ema_macd_has_exit_rules():
    rules = EMAMACDStrategy.exit_rules
    assert rules["stop_loss_pct"] == -0.07
    assert rules["take_profit_pct"] == 0.15
    assert rules["max_days"] == 15
    assert rules["eod_close"] is False


def test_ema_macd_has_display_name():
    assert EMAMACDStrategy.display_name == "EMA+MACD"


# ── generate_signals ──────────────────────────────────────────────────────────

def test_generate_signals_returns_signal_column():
    df = _make_df([100.0] * 60)
    result = EMAMACDStrategy().generate_signals(df)
    assert 'signal' in result.columns


def test_generate_signals_no_signal_for_flat_data():
    """Flat price → MACD stays near zero, no crossovers."""
    df = _make_df([100.0] * 80)
    result = EMAMACDStrategy().generate_signals(df)
    assert (result['signal'] == 0).all()


def test_generate_signals_buy_signal_on_uptrend():
    """Sharp uptrend after flat base triggers MACD crossover above EMA50."""
    df = _flat_then_surge()
    result = EMAMACDStrategy().generate_signals(df)
    assert (result['signal'] == 1).any(), "Expected at least one buy signal"


def test_generate_signals_no_buy_when_price_below_ema50():
    """Downtrend → price stays below EMA50 trend filter → no buy."""
    closes = [float(100 - i * 0.5) for i in range(90)]  # gradual decline
    df = _make_df(closes)
    result = EMAMACDStrategy().generate_signals(df)
    assert not (result['signal'] == 1).any(), "No buy signal when below EMA50"


def test_generate_signals_does_not_mutate_input():
    df = _flat_then_surge()
    original = df.copy()
    EMAMACDStrategy().generate_signals(df)
    pd.testing.assert_frame_equal(df, original)
