from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.user import User
from app.models.stock import Stock
from app.models.user_stock import user_stock_association
from app.schemas.user import UserResponse, UserCreate
from app.db.database import SessionLocal
from app.core.security import hash_password
from app.services.stock_service import create_stocks_with_symbols
from typing import List
from fastapi import HTTPException, status

def get_all_users() -> List[UserResponse]:
    """
    Get all users from the database.
    
    Returns:
        List of UserResponse objects
    """
    db = SessionLocal()
    try:
        users = db.query(User).all()
        return [UserResponse(
            id = user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            chat_id=user.chat_id,
            stocks=[str(stock.symbol) for stock in user.stocks]
        ) for user in users]
    finally:
        db.close()
    
def get_by_id(id: str) -> UserResponse | None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == id).first()
        if not user:
            return None
        return UserResponse(
            id= user.id,
            name=user.name,
            email=user.email,
            chat_id=user.chat_id,
            phone=user.phone,
            hash_password=user.password_hash,
            stocks=[str(stock.symbol) for stock in user.stocks]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error fetching user id {id}: {str(e)}"
        )

def create_user(user: UserCreate) -> UserResponse:
    """
    Create a new user in the database.
    
    Args:
        user: UserCreate schema with user data
        
    Returns:
        UserResponse object with created user data
        
    Raises:
        HTTPException: If email already exists (409 Conflict)
    """
    db = SessionLocal()
    print(user)
    try:
        # Check if user with this email already exists
        existing_user = db.query(User).filter(User.email == user.email or User.phone == user.phone).first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User with email {user.email} or phone number {user.phone} already exists"
            )
        
        # Create new user instance
        db_user = User(
            name=user.name,
            email=user.email,
            phone=user.phone,
            password_hash=hash_password(user.password)
        )
        
        # Add to database
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        # Convert to response schema
        return UserResponse(
            name=db_user.name,
            email=db_user.email,
            phone=db_user.phone,
            chat_id=db_user.chat_id,
            stocks=[]  # New user has no stocks initially
        )
    except HTTPException:
        # Re-raise HTTPException without modification (finally will close db)
        raise
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email {user.email} already exists"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating user: {str(e)}"
        )
    finally:
        db.close()

def add_stock_to_user(user_id: int, stock_symbol: str) -> UserResponse:
    """
    Add a stock to a user's portfolio.
    
    Args:
        user_id: The ID of the user to add the stock to
        stock_symbol: The symbol of the stock to add
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        stock = db.query(Stock).filter(Stock.symbol == stock_symbol).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"User with id {user_id} not found"
            )
        
        if [s for s in user.stocks if s.symbol == stock_symbol]:
            stocks_str = [s.symbol for s in user.stocks]
            return UserResponse(
                id=user.id,
                name=user.name,
                email=user.email,
                phone=user.phone,
                chat_id=user.chat_id,
                stocks=stocks_str
            )

        if not stock:
            stock = create_stocks_with_symbols([stock_symbol])

        stmt = user_stock_association.insert().values(user_id=user.id, stock_id=stock.id)
        db.execute(stmt)
        db.commit() 
        db.refresh(user)
        stocks_str = [s.symbol for s in user.stocks]
        return UserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            chat_id=user.chat_id,
            stocks=stocks_str
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding stock to user: {str(e)}"
        )
    finally:
        db.close()
    
def define_user_chatid(user_id: int, chat_id: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"User with id {user_id} not found"
            )
        user.chat_id = chat_id
        db.commit()
        db.refresh(user)
        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error assigning chat id to user {user_id}: {str(e)}"
        )