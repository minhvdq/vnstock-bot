import json
import logging
from fastapi import APIRouter, Request, Depends, status, HTTPException
from app.services.user_service import get_all_users, create_user, add_stock_to_user, remove_stock_from_user
from app.schemas.user import UserCreate
from app.utils.middlewares import authen_restricted
from pydantic import BaseModel

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/user", 
    tags=["user"],
    dependencies=[Depends(authen_restricted)]
)

class AddStockRequest(BaseModel):
    symbol: str

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

@router.put("/add_stock")
def add_stock(data: AddStockRequest, request: Request):
    try:
        user = request.state.user
        result = add_stock_to_user(user_id=user.id, stock_symbol=data.symbol)
        return result
    except Exception as e:
        logger.error(f"Error adding stock to user {user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.get("/me")
def get_me(request: Request):
    return request.state.user


class RemoveStockRequest(BaseModel):
    symbol: str


@router.delete("/remove_stock")
def remove_stock_endpoint(data: RemoveStockRequest, request: Request):
    try:
        user = request.state.user
        return remove_stock_from_user(user_id=user.id, stock_symbol=data.symbol)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing stock from user {user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/telegram_connect")
def get_link_connect_telegram(request: Request):
    user = request.state.user
    link = f"https://t.me/damianinvestbot?start={user.id}"
    return{
        "link": link
    }