from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.user import User
from app.models.stock import Stock
from app.schemas.user import UserResponse, UserCreate
from app.db.database import SessionLocal
from app.core.security import hash_password
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
            name=user.name,
            email=user.email,
            phone=user.phone,
            stocks=user.stocks if user.stocks else []
        ) for user in users]
    finally:
        db.close()

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