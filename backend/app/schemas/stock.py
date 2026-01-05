from typing import TYPE_CHECKING
from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas.user import UserResponse

class StockCreate(BaseModel):
    symbol: str
    name: str
    summary: str

class StockUpdate(BaseModel):
    summary: str
    # users: 

class StockResponse(BaseModel):
    id: int
    symbol: str
    name: str
    summary: str
    