from typing import TYPE_CHECKING
from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.stock import StockResponse

class UserCreate(BaseModel):
    name: str
    email: str
    phone: str
    password: str

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    stocks: list[str]
