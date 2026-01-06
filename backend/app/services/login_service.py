import jwt
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.user import User
from app.schemas.user import UserResponse
from app.core.security import check_password
from app.db.database import SessionLocal
from app.core.config import SECRET_KEY, ALGORITHM

def login(email: str, password: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        print(f"user is {user}" )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with email {email} does not exist"
            )
        
        if not check_password(password=password, hashed_password=user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is invalid"
            )
        
        token = jwt.encode(
            {
                "id": user.id,
                "email": user.email,
                "exp": datetime.now() + timedelta(minutes=60)
            },
            SECRET_KEY,
            ALGORITHM
        )

        return {
            "token": token,
            "id": user.id
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error logging in {str(e)}"
        )