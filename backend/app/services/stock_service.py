from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.user import User
from app.models.stock import Stock
# from app.schemas.user import UserResponse, UserCreate
from app.schemas.stock import StockCreate, StockResponse, StockUpdate
from app.db.database import SessionLocal
from app.services.company_service import get_all_companies
from app.core.security import hash_password
from typing import List
from fastapi import HTTPException, status


def get_all_stocks():
    db = SessionLocal()
    try:
        stocks = db.query(Stock).all()
        return [StockResponse(
            id = stock.id,
            symbol = stock.symbol,
            name = stock.name,
            summary = stock.summary

        ) for stock in stocks]
    finally:
        db.close() 

def create_stocks_with_symbols(symbols: list[str]):
    print(f"creating stocks {symbols}")
    for symbol in symbols:
        symbol.upper()
        symbol.replace(" ", "")
        df = get_all_companies()
        api_stock = [item for item in df if item.get("symbol") == symbol] 
        if not api_stock:
            raise HTTPException(
                status_code = status.HTTP_409_CONFLICT,
                detail = f"stock {symbol} does not exists"
            )
        print(f"stock found is {api_stock}")
        stock = api_stock[0]
        create_stock(StockCreate(
            name = stock["organ_name"],
            symbol = stock["symbol"],
            summary = ""
        ))



def create_stock(stock: StockCreate):
    db = SessionLocal()
    try:
        # Check if user with this email already exists
        existing_stock = db.query(Stock).filter(Stock.symbol == stock.symbol).first()
        if existing_stock:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Stock {stock.symbol} already exists"
            )
        db_stock = Stock(
            symbol = stock.symbol,
            name = stock.name,
            summary = stock.summary
        )

        db.add(db_stock)
        db.commit()
        db.refresh(db_stock)

        return StockResponse(
            name = db_stock.name,
            symbol = db_stock.symbol,
            summary = db_stock.summary
        )
    except HTTPException as e:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating stock: {str(e)}"
        )
    finally:
        db.close()