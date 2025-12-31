from sqlalchemy import Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship
from app.db.database import Base

# 1. Association Table: Links Users and Stocks
user_stock_association = Table(
    "user_stock_association",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("stock_id", Integer, ForeignKey("stocks.id"), primary_key=True),
)