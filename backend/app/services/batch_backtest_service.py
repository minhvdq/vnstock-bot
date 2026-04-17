from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert
from app.db.database import SessionLocal
from app.models.batch_backtest import BatchBacktestResult
from app.services.backtest_service import run_backtest

# Top 20 VN30 liquid stocks with reliable vnstock history
DEFAULT_SYMBOLS = [
    'VCB', 'VHM', 'VIC', 'HPG', 'MWG',
    'VNM', 'TCB', 'BID', 'CTG', 'FPT',
    'MSN', 'VPB', 'MBB', 'GAS', 'PLX',
    'SSI', 'ACB', 'STB', 'HDB', 'PDR',
]

DEFAULT_STRATEGIES = ['rsi_divergence', 'ema_macd', 'donchian_breakout']


def _run_one(symbol: str, strategy: str, start: str, end: str) -> dict:
    try:
        result = run_backtest(symbol=symbol, strategy_name=strategy,
                              start_date=start, end_date=end)
        return {
            'symbol': symbol,
            'strategy_name': strategy,
            'start_date': start,
            'end_date': end,
            'initial_capital': result.initial_capital,
            'final_value': result.final_value,
            'pnl': result.pnl,
            'pnl_pct': result.pnl_pct,
            'win_rate': result.win_rate,
            'max_drawdown': result.max_drawdown,
            'total_trades': result.total_trades,
            'error': None,
        }
    except Exception as e:
        return {
            'symbol': symbol,
            'strategy_name': strategy,
            'start_date': start,
            'end_date': end,
            'initial_capital': 100_000_000.0,
            'final_value': 100_000_000.0,
            'pnl': 0.0,
            'pnl_pct': 0.0,
            'win_rate': 0.0,
            'max_drawdown': 0.0,
            'total_trades': 0,
            'error': str(e)[:200],
        }


def run_batch(
    symbols: list[str] = DEFAULT_SYMBOLS,
    strategies: list[str] = DEFAULT_STRATEGIES,
    start: str = '2024-01-01',
    end: str = '2025-12-31',
    max_workers: int = 8,
) -> list[dict]:
    """
    Run backtest for every (symbol, strategy) pair in parallel.
    Upserts results to DB and returns the full list.
    """
    tasks = [(s, st) for s in symbols for st in strategies]
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_one, sym, strat, start, end): (sym, strat)
                   for sym, strat in tasks}
        for future in as_completed(futures):
            results.append(future.result())

    _upsert_results(results)
    return results


def _upsert_results(results: list[dict]) -> None:
    now = datetime.now(timezone.utc)
    rows = [{**r, 'run_at': now} for r in results]
    db = SessionLocal()
    try:
        stmt = insert(BatchBacktestResult).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=['symbol', 'strategy_name', 'start_date', 'end_date'],
            set_={
                'final_value': stmt.excluded.final_value,
                'pnl': stmt.excluded.pnl,
                'pnl_pct': stmt.excluded.pnl_pct,
                'win_rate': stmt.excluded.win_rate,
                'max_drawdown': stmt.excluded.max_drawdown,
                'total_trades': stmt.excluded.total_trades,
                'error': stmt.excluded.error,
                'run_at': stmt.excluded.run_at,
            }
        )
        db.execute(stmt)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f'[batch_backtest] DB upsert error: {e}')
    finally:
        db.close()


def get_results(
    start: str = '2024-01-01',
    end: str = '2025-12-31',
) -> list[dict]:
    """Fetch stored batch results from DB for the given period."""
    db = SessionLocal()
    try:
        rows = (db.query(BatchBacktestResult)
                .filter(BatchBacktestResult.start_date == start,
                        BatchBacktestResult.end_date == end)
                .order_by(BatchBacktestResult.pnl_pct.desc())
                .all())
        return [
            {
                'symbol': r.symbol,
                'strategy_name': r.strategy_name,
                'pnl_pct': round(r.pnl_pct, 2),
                'win_rate': round(r.win_rate, 1),
                'max_drawdown': round(r.max_drawdown, 2),
                'total_trades': r.total_trades,
                'pnl': round(r.pnl),
                'run_at': r.run_at.isoformat() if r.run_at else None,
                'error': r.error,
            }
            for r in rows
        ]
    finally:
        db.close()
