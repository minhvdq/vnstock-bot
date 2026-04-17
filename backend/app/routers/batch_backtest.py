from __future__ import annotations
import threading
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from app.services.batch_backtest_service import (
    run_batch, get_results,
    DEFAULT_SYMBOLS, DEFAULT_STRATEGIES,
)

router = APIRouter(prefix='/batch-backtest', tags=['batch-backtest'])

# In-memory job state (single-process — fine for one Fly machine at a time)
_job: dict = {'status': 'idle', 'start': None, 'end': None, 'ok': 0, 'failed': 0, 'total': 0}
_lock = threading.Lock()


def _run_background(start: str, end: str) -> None:
    global _job
    try:
        results = run_batch(start=start, end=end)
        ok = sum(1 for r in results if not r['error'])
        failed = sum(1 for r in results if r['error'])
        with _lock:
            _job.update({'status': 'done', 'ok': ok, 'failed': failed, 'total': len(results)})
    except Exception as e:
        with _lock:
            _job.update({'status': 'error', 'error': str(e)})


@router.post('/run')
def trigger_batch(
    background_tasks: BackgroundTasks,
    start: str = Query(default='2024-01-01'),
    end: str = Query(default='2025-12-31'),
) -> dict:
    """
    Start batch backtest in background. Returns 202 immediately.
    Poll GET /batch-backtest/status until status == 'done', then fetch /results.
    """
    with _lock:
        if _job['status'] == 'running':
            raise HTTPException(status_code=409, detail='Batch run already in progress')
        _job.update({'status': 'running', 'start': start, 'end': end, 'ok': 0, 'failed': 0, 'total': 0})

    background_tasks.add_task(_run_background, start, end)
    return {'status': 'running', 'message': 'Batch started. Poll /batch-backtest/status for progress.'}


@router.get('/status')
def get_status() -> dict:
    with _lock:
        return dict(_job)


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
