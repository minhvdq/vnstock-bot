import json
import logging
from fastapi import APIRouter, status, HTTPException
from app.services.user_service import get_all_users, create_user
from app.schemas.user import UserCreate

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["user"])

@router.get("/")
def get_all():
    try:
        users = get_all_users()   
        return users
    except Exception as e:
        logger.error(f"Error getting all users: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/")
def create(user: UserCreate):
    try:
        user = create_user(user)
        return user
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))