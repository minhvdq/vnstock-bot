from sqlalchemy import Column, Integer, Float, String, DateTime, UniqueConstraint
from datetime import datetime, timezone
from app.db.database import Base


class IntradayBar(Base):
    __tablename__ = "intraday_bars"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    bar_time = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False, default=0)
    rsi = Column(Float, nullable=True)
    fetched_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("symbol", "bar_time", name="uq_intraday_bar_symbol_time"),
    )
