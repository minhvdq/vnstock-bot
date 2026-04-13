from __future__ import annotations
from dataclasses import asdict
from fastapi import APIRouter, HTTPException, Query
from app.services.backtest_service import run_backtest

router = APIRouter(prefix='/backtest', tags=['backtest'])


@router.get('/{symbol}')
def get_backtest(
    symbol: str,
    strategy: str = Query(default='rsi_divergence'),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    capital: float = Query(default=100_000_000.0),
) -> dict:
    try:
        result = run_backtest(
            symbol=symbol,
            strategy_name=strategy,
            start_date=start,
            end_date=end,
            initial_capital=capital,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return asdict(result)
