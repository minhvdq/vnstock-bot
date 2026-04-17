from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from app.services.batch_backtest_service import (
    run_batch, get_results,
    DEFAULT_SYMBOLS, DEFAULT_STRATEGIES,
)

router = APIRouter(prefix='/batch-backtest', tags=['batch-backtest'])

_running = False


@router.post('/run')
def trigger_batch(
    start: str = Query(default='2024-01-01'),
    end: str = Query(default='2025-12-31'),
) -> dict:
    """
    Run batch backtest synchronously (20 symbols × 3 strategies, ~2-3 min).
    Returns all results once complete.
    """
    global _running
    if _running:
        raise HTTPException(status_code=409, detail='Batch run already in progress')
    _running = True
    try:
        results = run_batch(start=start, end=end)
        ok = sum(1 for r in results if not r['error'])
        failed = sum(1 for r in results if r['error'])
        return {'status': 'done', 'total': len(results), 'ok': ok, 'failed': failed, 'results': results}
    finally:
        _running = False


@router.get('/results')
def fetch_results(
    start: str = Query(default='2024-01-01'),
    end: str = Query(default='2025-12-31'),
) -> dict:
    """Return stored batch results from DB, sorted by P&L % descending."""
    results = get_results(start=start, end=end)
    return {'count': len(results), 'results': results}


@router.get('/symbols')
def list_symbols() -> dict:
    return {'symbols': DEFAULT_SYMBOLS, 'strategies': DEFAULT_STRATEGIES}
