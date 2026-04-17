from sqlalchemy import Column, Integer, Float, String, DateTime, UniqueConstraint
from datetime import datetime, timezone
from app.db.database import Base


class BatchBacktestResult(Base):
    __tablename__ = "batch_backtest_results"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    strategy_name = Column(String(50), nullable=False, index=True)
    start_date = Column(String(20), nullable=False)
    end_date = Column(String(20), nullable=False)
    initial_capital = Column(Float, nullable=False)
    final_value = Column(Float, nullable=False)
    pnl = Column(Float, nullable=False)
    pnl_pct = Column(Float, nullable=False)
    win_rate = Column(Float, nullable=False)
    max_drawdown = Column(Float, nullable=False)
    total_trades = Column(Integer, nullable=False)
    run_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    error = Column(String(200), nullable=True)

    __table_args__ = (
        UniqueConstraint("symbol", "strategy_name", "start_date", "end_date",
                         name="uq_batch_result_symbol_strategy_period"),
    )
