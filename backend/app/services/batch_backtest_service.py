from __future__ import annotations
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import insert
from app.db.database import SessionLocal
from app.models.batch_backtest import BatchBacktestResult
from app.services.backtest_service import run_backtest

# Configure vnstock API key if provided (community: 60 req/min vs guest: 20 req/min)
_api_key = os.getenv('VNSTOCK_API_KEY')
if _api_key:
    try:
        import vnai
        vnai.setup_api_key(_api_key)
    except Exception:
        pass

# Top 20 VN30 liquid stocks with reliable vnstock history
DEFAULT_SYMBOLS = [
    'VCB', 'VHM', 'VIC', 'HPG', 'MWG',
    'VNM', 'TCB', 'BID', 'CTG', 'FPT',
    'MSN', 'VPB', 'MBB', 'GAS', 'PLX',
    'SSI', 'ACB', 'STB', 'HDB', 'PDR',
]

DEFAULT_STRATEGIES = ['rsi_divergence', 'ema_macd', 'donchian_breakout']


# Community key: 60 req/min → 1.1s delay. Guest (no key): 20 req/min → 3.5s delay.
DELAY_SECONDS = 1.1 if _api_key else 3.5
_rate_lock = threading.Lock()
_last_request_time: float = 0.0


def _throttled_run_one(
    symbol: str, strategy: str, start: str, end: str,
    index: int = 0, total: int = 0,
) -> dict:
    """Rate-limited wrapper: enforces minimum gap between requests."""
    global _last_request_time
    with _rate_lock:
        now = time.monotonic()
        wait = DELAY_SECONDS - (now - _last_request_time)
        if wait > 0:
            time.sleep(wait)
        _last_request_time = time.monotonic()

    tag = f'[{index}/{total}]' if total else ''
    t0 = time.monotonic()
    print(f'[batch] {tag} START {symbol}/{strategy}')

    try:
        result = run_backtest(symbol=symbol, strategy_name=strategy,
                              start_date=start, end_date=end)
        elapsed = time.monotonic() - t0
        print(f'[batch] {tag} OK    {symbol}/{strategy} '
              f'pnl={result.pnl_pct:+.1f}% trades={result.total_trades} '
              f'win={result.win_rate:.0f}% ({elapsed:.1f}s)')
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
    except BaseException as e:
        elapsed = time.monotonic() - t0
        error_msg = str(e)[:200] if str(e) else type(e).__name__
        print(f'[batch] {tag} FAIL  {symbol}/{strategy} ({elapsed:.1f}s): {error_msg}')
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
            'error': error_msg,
        }


def run_batch(
    symbols: list[str] = DEFAULT_SYMBOLS,
    strategies: list[str] = DEFAULT_STRATEGIES,
    start: str = '2024-01-01',
    end: str = '2025-12-31',
    progress_cb=None,
) -> list[dict]:
    """
    Run backtest for every (symbol, strategy) pair sequentially with rate limiting.
    Community key (60 req/min): 1.1s delay → ~70s for 60 requests.
    Guest (no key, 20 req/min): 3.5s delay → ~3.5 min for 60 requests.
    """
    tasks = [(s, st) for s in symbols for st in strategies]
    total = len(tasks)
    results = []

    tier = 'community' if _api_key else 'guest'
    print(f'[batch] START {total} tasks ({len(symbols)} symbols × {len(strategies)} strategies) '
          f'period={start}→{end} tier={tier} delay={DELAY_SECONDS}s')

    batch_t0 = time.monotonic()

    # Single worker: rate limiter serialises requests anyway.
    with ThreadPoolExecutor(max_workers=1) as pool:
        futures = {
            pool.submit(_throttled_run_one, sym, strat, start, end, i + 1, total): (sym, strat)
            for i, (sym, strat) in enumerate(tasks)
        }
        for future in as_completed(futures):
            results.append(future.result())
            ok_so_far = sum(1 for r in results if not r['error'])
            if progress_cb:
                progress_cb(len(results), total, ok_so_far, len(results) - ok_so_far)

    ok = sum(1 for r in results if not r['error'])
    failed = total - ok
    elapsed = time.monotonic() - batch_t0
    print(f'[batch] DONE  {ok}/{total} OK, {failed} failed in {elapsed:.0f}s — persisting to DB')

    _upsert_results(results)
    print(f'[batch] DB upsert complete')
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
