from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from app.utils.middlewares import authen_restricted
from app.services import paper_trading_service
from app.services.stock_api_service import get_current_price
from app.db.database import SessionLocal
from app.models.paper_trading import PaperTrade, TradeStatus
from app.services.weekly_report_service import build_weekly_report, format_weekly_report

router = APIRouter(
    prefix="/paper-trading",
    tags=["paper-trading"],
    dependencies=[Depends(authen_restricted)],
)


@router.get("/portfolio")
def get_portfolio(request: Request):
    user = request.state.user
    return paper_trading_service.get_portfolio_summary(user.id)


@router.get("/positions")
def get_positions(request: Request):
    """Open positions with live unrealized P&L."""
    user = request.state.user
    db = SessionLocal()
    try:
        trades = db.query(PaperTrade).filter(
            PaperTrade.user_id == user.id,
            PaperTrade.status == TradeStatus.open,
        ).all()

        result = []
        for t in trades:
            try:
                current_price = get_current_price(t.symbol)
            except Exception:
                current_price = t.entry_price  # fallback to entry if price fetch fails

            unrealized_pnl_pct = (current_price - t.entry_price) / t.entry_price * 100
            unrealized_pnl_amount = int((current_price - t.entry_price) * t.quantity)
            days_held = (
                datetime.now(timezone.utc)
                - t.entry_time.replace(tzinfo=timezone.utc)
            ).days

            result.append({
                "id": t.id,
                "symbol": t.symbol,
                "entry_price": t.entry_price,
                "current_price": current_price,
                "quantity": t.quantity,
                "position_value": t.position_value,
                "stop_loss_price": t.stop_loss_price,
                "take_profit_price": t.take_profit_price,
                "entry_time": t.entry_time.isoformat(),
                "days_held": days_held,
                "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
                "unrealized_pnl_amount": unrealized_pnl_amount,
            })
        return result
    finally:
        db.close()


@router.get("/trades")
def get_trades(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Closed trade history, paginated, newest first."""
    user = request.state.user
    db = SessionLocal()
    try:
        offset = (page - 1) * limit
        trades = (
            db.query(PaperTrade)
            .filter(PaperTrade.user_id == user.id, PaperTrade.status == TradeStatus.closed)
            .order_by(PaperTrade.exit_time.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        total = db.query(PaperTrade).filter(
            PaperTrade.user_id == user.id,
            PaperTrade.status == TradeStatus.closed,
        ).count()

        return {
            "total": total,
            "page": page,
            "limit": limit,
            "trades": [
                {
                    "id": t.id,
                    "symbol": t.symbol,
                    "entry_price": t.entry_price,
                    "exit_price": t.exit_price,
                    "quantity": t.quantity,
                    "position_value": t.position_value,
                    "pnl_amount": t.pnl_amount,
                    "pnl_pct": t.pnl_pct,
                    "exit_reason": t.exit_reason.value if t.exit_reason else None,
                    "entry_time": t.entry_time.isoformat(),
                    "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                }
                for t in trades
            ],
        }
    finally:
        db.close()


@router.get("/report")
async def get_weekly_report(request: Request, days: int = Query(default=7, ge=1, le=30)):
    """Return (and optionally send) the weekly P&L report for the authenticated user."""
    user = request.state.user
    report = build_weekly_report(user.id, days=days)
    return {'report': report, 'formatted': format_weekly_report(report)}


@router.delete("/positions/{trade_id}")
async def close_position(trade_id: int, request: Request):
    """Manually close an open position at current market price."""
    user = request.state.user
    try:
        trade = paper_trading_service.close_position(trade_id=trade_id, user_id=user.id)
        return {
            "id": trade.id,
            "symbol": trade.symbol,
            "exit_price": trade.exit_price,
            "pnl_amount": trade.pnl_amount,
            "pnl_pct": trade.pnl_pct,
            "exit_reason": trade.exit_reason.value if trade.exit_reason else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
