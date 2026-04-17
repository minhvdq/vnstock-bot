from sqlalchemy import Column, Integer, BigInteger, Float, String, DateTime, Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.database import Base
import enum


class TradeStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class ExitReason(str, enum.Enum):
    stop_loss = "stop_loss"
    take_profit = "take_profit"
    time_stop = "time_stop"
    manual = "manual"


class PaperPortfolio(Base):
    __tablename__ = "paper_portfolios"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    starting_balance = Column(BigInteger, nullable=False, default=100_000_000)
    available_cash = Column(BigInteger, nullable=False, default=100_000_000)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    trades = relationship("PaperTrade", back_populates="portfolio", foreign_keys="PaperTrade.user_id",
                          primaryjoin="PaperPortfolio.user_id == PaperTrade.user_id")

    __table_args__ = (UniqueConstraint("user_id", name="uq_paper_portfolio_user"),)


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    entry_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    position_value = Column(BigInteger, nullable=False)
    stop_loss_price = Column(Float, nullable=False)
    take_profit_price = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    exit_price = Column(Float, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    exit_reason = Column(Enum(ExitReason), nullable=True)
    pnl_amount = Column(BigInteger, nullable=True)
    pnl_pct = Column(Float, nullable=True)
    status = Column(Enum(TradeStatus), nullable=False, default=TradeStatus.open)

    portfolio = relationship("PaperPortfolio", back_populates="trades",
                             foreign_keys=[user_id],
                             primaryjoin="PaperTrade.user_id == PaperPortfolio.user_id")
