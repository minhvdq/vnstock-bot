import logging
from fastapi import APIRouter, status, HTTPException
from app.services.login_service import login
from app.services.user_service import create_user
from app.schemas.user import UserCreate
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def log_in(data: LoginRequest):
    try:
        response = login(data.email, data.password)
        return response
    except Exception as e:
        raise


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(user: UserCreate):
    try:
        return create_user(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering user: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))