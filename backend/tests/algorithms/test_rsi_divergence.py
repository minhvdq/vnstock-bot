import pandas as pd
import pytest
from app.algorithms.rsi_divergence import (
    RSIStrategy,
    _is_peak,
    _is_trough,
    _is_in_range,
    _find_divergences,
    _has_divergence_at,
)


def _make_candle(high: float, low: float, close: float, rsi: float, time: str) -> dict:
    return {'time': time, 'open': close, 'high': high, 'low': low, 'close': close, 'RSI': rsi}


def _flat_data(n: int = 35) -> list:
    return [_make_candle(50.0, 40.0, 45.0, 50.0, f'2024-01-{i+1:02d}') for i in range(n)]


def _bearish_divergence_data() -> list:
    """
    35-candle series with one guaranteed bearish divergence.

    Peak 1 at index 7 (order=5): high=100, RSI=72 (bearish zone >65).
    Peak 2 at index 22 (order=5): high=110, RSI=68.
      - higher high (110 > 100) + lower RSI (68 < 72) = bearish divergence
      - distance = 22 - 7 = 15  (valid: 10 <= 15 <= 60)
    """
    rows = _flat_data(35)
    # Peak 1 shape: rise through indices 2-7, fall through 8-12
    for idx, val in zip(range(2, 13), [60, 70, 80, 90, 95, 100, 95, 90, 85, 80, 75]):
        rows[idx]['high'] = float(val)
    rows[7]['RSI'] = 72.0

    # Peak 2 shape: rise through indices 17-22, fall through 23-27
    for idx, val in zip(range(17, 28), [70, 80, 90, 100, 105, 110, 105, 100, 90, 80, 70]):
        rows[idx]['high'] = float(val)
    rows[22]['RSI'] = 68.0  # higher high but lower RSI → bearish divergence
    return rows


# ── _is_peak ────────────────────────────────────────────────────────────────

def test_is_peak_detects_local_maximum():
    rows = _flat_data(11)
    for idx, val in zip(range(0, 11), [60, 70, 80, 90, 95, 100, 95, 90, 85, 80, 75]):
        rows[idx]['high'] = float(val)
    assert _is_peak(rows, 5, order=5) is True


def test_is_peak_false_at_left_boundary():
    rows = _flat_data(11)
    assert _is_peak(rows, 0, order=5) is False


def test_is_peak_false_at_right_boundary():
    rows = _flat_data(11)
    assert _is_peak(rows, 10, order=5) is False


def test_is_peak_false_when_not_maximum():
    rows = _flat_data(11)
    for idx, val in zip(range(0, 11), [60, 70, 80, 90, 95, 100, 95, 90, 85, 80, 75]):
        rows[idx]['high'] = float(val)
    assert _is_peak(rows, 3, order=5) is False


# ── _is_trough ───────────────────────────────────────────────────────────────

def test_is_trough_detects_local_minimum():
    rows = _flat_data(11)
    for idx, val in zip(range(0, 11), [90, 80, 70, 60, 55, 50, 55, 60, 65, 70, 75]):
        rows[idx]['low'] = float(val)
    assert _is_trough(rows, 5, order=5) is True


def test_is_trough_false_at_boundary():
    rows = _flat_data(11)
    assert _is_trough(rows, 0, order=5) is False
    assert _is_trough(rows, 10, order=5) is False


# ── _is_in_range ─────────────────────────────────────────────────────────────

def test_is_in_range_bearish_above_threshold():
    assert _is_in_range(70.0, 'bearish') is True
    assert _is_in_range(65.1, 'bearish') is True


def test_is_in_range_bearish_below_threshold():
    assert _is_in_range(50.0, 'bearish') is False


def test_is_in_range_bullish_below_threshold():
    assert _is_in_range(30.0, 'bullish') is True


def test_is_in_range_bullish_above_threshold():
    assert _is_in_range(50.0, 'bullish') is False


# ── _find_divergences ────────────────────────────────────────────────────────

def test_find_divergences_detects_bearish():
    rows = _bearish_divergence_data()
    result = _find_divergences(rows)
    bearish = [d for d in result if d['type'] == 'bearish']
    assert len(bearish) >= 1
    assert bearish[0]['prefixIndex'] == 7
    assert bearish[0]['suffixIndex'] == 22


def test_find_divergences_empty_for_flat_data():
    assert _find_divergences(_flat_data(35)) == []


# ── RSIStrategy.generate_signals ─────────────────────────────────────────────

def test_generate_signals_sets_bearish_signal_at_suffix():
    df = pd.DataFrame(_bearish_divergence_data())
    result = RSIStrategy().generate_signals(df)
    assert result.iloc[22]['signal'] == -1


def test_generate_signals_zero_for_flat_data():
    df = pd.DataFrame(_flat_data(35))
    result = RSIStrategy().generate_signals(df)
    assert (result['signal'] == 0).all()


def test_generate_signals_bearish_overrides_bullish_on_same_candle():
    """Bearish (-1) takes priority when both signal types land on the same index."""
    rows = _bearish_divergence_data()
    df = pd.DataFrame(rows)
    strategy = RSIStrategy()
    result = strategy.generate_signals(df)
    # Index 22 has bearish divergence — it must not be overwritten to 1
    assert result.iloc[22]['signal'] == -1


def _bullish_divergence_data() -> list:
    """
    35-candle series with one guaranteed bullish divergence.

    Trough 1 at index 7 (order=5): low=20, RSI=30 (bullish zone <35).
    Trough 2 at index 22 (order=5): low=15, RSI=33.
      - lower low (15 < 20) + higher RSI (33 > 30) = bullish divergence
      - distance = 22 - 7 = 15  (valid: 10 <= 15 <= 60)
    """
    rows = _flat_data(35)
    # Trough 1 shape: fall through indices 2-7, rise through 8-12
    for idx, val in zip(range(2, 13), [40, 30, 25, 22, 21, 20, 21, 22, 25, 30, 35]):
        rows[idx]['low'] = float(val)
    rows[7]['RSI'] = 30.0

    # Trough 2 shape: fall through indices 17-22, rise through 23-27
    for idx, val in zip(range(17, 28), [35, 28, 22, 18, 16, 15, 16, 18, 22, 28, 35]):
        rows[idx]['low'] = float(val)
    rows[22]['RSI'] = 33.0  # lower low but higher RSI → bullish divergence
    return rows


def test_find_divergences_detects_bullish():
    rows = _bullish_divergence_data()
    result = _find_divergences(rows)
    bullish = [d for d in result if d['type'] == 'bullish']
    assert len(bullish) >= 1
    assert bullish[0]['prefixIndex'] == 7
    assert bullish[0]['suffixIndex'] == 22


def test_generate_signals_sets_bullish_signal_at_suffix():
    df = pd.DataFrame(_bullish_divergence_data())
    result = RSIStrategy().generate_signals(df)
    assert result.iloc[22]['signal'] == 1


def test_has_divergence_at_returns_none_for_non_divergence():
    rows = _flat_data(35)
    # No peaks/troughs in flat data, so no divergence at any index
    assert _has_divergence_at(rows, 17) is None
