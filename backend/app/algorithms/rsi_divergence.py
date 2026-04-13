from __future__ import annotations
import pandas as pd
from app.algorithms.base import BaseStrategy


# ── Private helpers ──────────────────────────────────────────────────────────

def _is_in_range(rsi: float, kind: str = 'any') -> bool:
    """Return True if RSI is in the overbought/oversold zone."""
    if kind == 'bearish':
        return rsi > 65
    if kind == 'bullish':
        return rsi < 35
    return rsi < 35 or rsi > 65


def _is_peak(df: list, i: int, order: int = 5) -> bool:
    """Return True if candle i is a local high with `order` strictly lower neighbors on each side."""
    if i < order or i >= len(df) - order:
        return False
    current_high = df[i]['high']
    for j in range(i - order, i):
        if df[j]['high'] >= current_high:
            return False
    for j in range(i + 1, i + order + 1):
        if df[j]['high'] >= current_high:
            return False
    return True


def _is_trough(df: list, i: int, order: int = 5) -> bool:
    """Return True if candle i is a local low with `order` strictly higher neighbors on each side."""
    if i < order or i >= len(df) - order:
        return False
    current_low = df[i]['low']
    for j in range(i - order, i):
        if df[j]['low'] <= current_low:
            return False
    for j in range(i + 1, i + order + 1):
        if df[j]['low'] <= current_low:
            return False
    return True


def _find_divergences(df: list) -> list:
    """
    Full-scan divergence detector (renamed from tim_phan_ky).

    Scans the entire candle list and returns every RSI divergence found.
    Each divergence: {'prefixIndex': int, 'suffixIndex': int, 'type': 'bearish'|'bullish'}

    Used by RSIStrategy.generate_signals() for backtesting.
    """
    n = len(df)
    peaks: list[int] = []
    troughs: list[int] = []
    divergences: list[dict] = []

    for i in range(n):
        if _is_peak(df, i):
            for j in range(len(peaks) - 1, -1, -1):
                old_idx = peaks[j]
                distance = i - old_idx
                if distance > 60:
                    break
                if distance < 10:
                    continue
                if _is_in_range(df[i]['RSI'], 'bearish') or _is_in_range(df[old_idx]['RSI'], 'bearish'):
                    if df[i]['high'] > df[old_idx]['high'] and df[i]['RSI'] < df[old_idx]['RSI']:
                        divergences.append({'prefixIndex': old_idx, 'suffixIndex': i, 'type': 'bearish'})
            peaks.append(i)

        if _is_trough(df, i):
            for j in range(len(troughs) - 1, -1, -1):
                old_idx = troughs[j]
                distance = i - old_idx
                if distance > 60:
                    break
                if distance < 10:
                    continue
                if _is_in_range(df[i]['RSI'], 'bullish') or _is_in_range(df[old_idx]['RSI'], 'bullish'):
                    if df[i]['low'] < df[old_idx]['low'] and df[i]['RSI'] > df[old_idx]['RSI']:
                        divergences.append({'prefixIndex': old_idx, 'suffixIndex': i, 'type': 'bullish'})
            troughs.append(i)

    return divergences


def _has_divergence_at(df: list, index: int) -> dict | None:
    """
    Single-candle divergence checker (renamed from is_divergence).

    Requires 2 confirming peak/trough pairs to reduce false positives.
    Used by the live stock worker (Phase 2) for per-tick signal checking.
    Returns a divergence dict or None.
    """
    peaks: list[int] = []
    troughs: list[int] = []
    for i in range(len(df)):
        if _is_peak(df, i):
            peaks.append(i)
        if _is_trough(df, i):
            troughs.append(i)

    bearish_cnt = 0
    first_match_bearish = None
    if _is_peak(df, index):
        earlier_peaks = [p for p in peaks if p < index]
        for j in range(len(earlier_peaks) - 1, -1, -1):
            old_idx = earlier_peaks[j]
            distance = index - old_idx
            if distance > 60:
                break
            if distance < 10:
                continue
            if _is_in_range(df[index]['RSI'], 'bearish') or _is_in_range(df[old_idx]['RSI'], 'bearish'):
                if df[index]['high'] > df[old_idx]['high'] and df[index]['RSI'] < df[old_idx]['RSI']:
                    bearish_cnt += 1
                    if bearish_cnt == 1:
                        first_match_bearish = old_idx
                    if bearish_cnt >= 2:
                        return {'prefixIndex': first_match_bearish, 'suffixIndex': index, 'type': 'bearish'}

    bullish_cnt = 0
    first_match_bullish = None
    if _is_trough(df, index):
        earlier_troughs = [t for t in troughs if t < index]
        for j in range(len(earlier_troughs) - 1, -1, -1):
            old_idx = earlier_troughs[j]
            distance = index - old_idx
            if distance > 60:
                break
            if distance < 10:
                continue
            if _is_in_range(df[index]['RSI'], 'bullish') or _is_in_range(df[old_idx]['RSI'], 'bullish'):
                if df[index]['low'] < df[old_idx]['low'] and df[index]['RSI'] > df[old_idx]['RSI']:
                    bullish_cnt += 1
                    if bullish_cnt == 1:
                        first_match_bullish = old_idx
                    if bullish_cnt >= 2:
                        return {'prefixIndex': first_match_bullish, 'suffixIndex': index, 'type': 'bullish'}

    return None


# ── Strategy ─────────────────────────────────────────────────────────────────

class RSIStrategy(BaseStrategy):
    """
    RSI Divergence strategy.

    Generates buy signals (1) at bullish divergence suffix candles and
    sell signals (-1) at bearish divergence suffix candles.
    Conflict rule: if both types land on the same candle, bearish (-1) wins.
    """

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['signal'] = 0

        records = df.to_dict(orient='records')
        divergences = _find_divergences(records)

        for div in divergences:
            idx = div['suffixIndex']
            if div['type'] == 'bullish':
                # Only set buy if bearish has not already claimed this candle
                if df.iloc[idx]['signal'] != -1:
                    df.iloc[idx, df.columns.get_loc('signal')] = 1
            elif div['type'] == 'bearish':
                # Always overrides — bearish wins conflicts
                df.iloc[idx, df.columns.get_loc('signal')] = -1

        return df
