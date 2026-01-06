from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.db.database import Base
from app.models.user_stock import user_stock_association

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String, index=True)
    password_hash = Column(String)
    chat_id = Column(String)

    # Relationship to Stock (using string reference to avoid circular import)
    stocks = relationship("Stock", secondary=user_stock_association, back_populates="users")