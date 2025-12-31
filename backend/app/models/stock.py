from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.db.database import Base
from app.models.user_stock import user_stock_association

class Stock(Base):
    __tablename__ = "stocks"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True, unique=True)
    name = Column(String, index=True)
    summary = Column(String)

    # Relationship back to User (using string reference to avoid circular import)
    users = relationship("User", secondary=user_stock_association, back_populates="stocks")