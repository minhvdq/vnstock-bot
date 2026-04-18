from __future__ import annotations
from app.db.database import SessionLocal
from app.models.batch_backtest import BatchBacktestResult

BASE_DAILY_PCT = 0.10
BASE_INTRADAY_PCT = 0.05
MIN_PCT = 0.05
MAX_PCT = 0.15


def get_strategy_position_pct(strategy_name: str, timeframe: str = 'daily') -> float:
    """
    Kelly-inspired position size based on batch backtest average win rate.

    Scale = clamp(avg_win_rate / 55.0, 0.5, 1.5)
    Result = clamp(base * scale, MIN_PCT, MAX_PCT)

    Falls back to fixed-fraction when no backtest data exists.
    55% is used as the neutral pivot — strategies beating it size up, lagging size down.
    """
    base = BASE_INTRADAY_PCT if timeframe == 'intraday' else BASE_DAILY_PCT
    db = SessionLocal()
    try:
        rows = (
            db.query(BatchBacktestResult.win_rate)
            .filter(
                BatchBacktestResult.strategy_name == strategy_name,
                BatchBacktestResult.error.is_(None),
            )
            .all()
        )
        if not rows:
            return base
        avg_win_rate = sum(r.win_rate for r in rows) / len(rows)
        scale = min(1.5, max(0.5, avg_win_rate / 55.0))
        return min(MAX_PCT, max(MIN_PCT, base * scale))
    except Exception:
        return base
    finally:
        db.close()
