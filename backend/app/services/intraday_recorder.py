from __future__ import annotations
from datetime import datetime, timezone
import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from app.db.database import SessionLocal
from app.models.intraday_bar import IntradayBar


def record_bars(symbol: str, records: list[dict]) -> int:
    """
    Upsert 1-min OHLCV bars for a symbol. Skips bars already in DB (by symbol+bar_time).
    Returns the number of rows inserted.
    """
    if not records:
        return 0

    rows = []
    now = datetime.now(timezone.utc)
    for r in records:
        bar_time = r.get('time')
        if bar_time is None:
            continue
        if isinstance(bar_time, str):
            bar_time = pd.to_datetime(bar_time).to_pydatetime()
        elif hasattr(bar_time, 'to_pydatetime'):
            bar_time = bar_time.to_pydatetime()
        # Strip tz to match DB column (stored as UTC naive)
        if bar_time.tzinfo is not None:
            bar_time = bar_time.replace(tzinfo=None)
        rows.append({
            'symbol': symbol,
            'bar_time': bar_time,
            'open': float(r['open']),
            'high': float(r['high']),
            'low': float(r['low']),
            'close': float(r['close']),
            'volume': int(r.get('volume', 0)),
            'rsi': float(r['RSI']) if r.get('RSI') is not None else None,
            'fetched_at': now,
        })

    if not rows:
        return 0

    db = SessionLocal()
    try:
        stmt = insert(IntradayBar).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=['symbol', 'bar_time']
        )
        result = db.execute(stmt)
        db.commit()
        return result.rowcount or 0
    except Exception as e:
        db.rollback()
        print(f'[recorder] {symbol}: DB error: {e}')
        return 0
    finally:
        db.close()
