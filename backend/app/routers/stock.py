import json
import logging
from fastapi import APIRouter, status, HTTPException
from vnstock import Trading
from app.services.stock_service import get_price_today, get_mock_price # Assuming this exists

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stock", tags=["stock"])

@router.get("/price-board")
def get_price_board(symbol: str = "ACB"):
    """
    Get real-time price board data for a specific symbol.
    """
    try:
        # Initialize Trading without a dummy symbol if possible, 
        # or use a default one if the library forces it.
        # Note: price_board usually expects a list of symbols.
        trading = Trading(symbol=symbol) 
        
        # Fetch data (Returns a Pandas DataFrame)
        board_df = trading.price_board(symbols_list=[symbol])
        
        if board_df is None or board_df.empty:
             raise HTTPException(status_code=404, detail=f"No data found for symbol {symbol}")

        # Convert DataFrame to Dict (FastAPI handles the JSON serialization)
        # orient='records' creates a list of objects: [{"ticker": "ACB", "price": ...}]
        return board_df.to_dict(orient="records")
        
    except Exception as e:
        logger.error(f"Error fetching price board for {symbol}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Failed to fetch stock data: {str(e)}"
        )

@router.get("/price-today")
def get_day_price(): # Fixed Typo 'pice' -> 'price'
    try:
        records_json = get_price_today()
        
        return {"data": records_json}
        
    except ValueError as e:
        logger.warning(f"Validation error in price-today: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
        
    except Exception as e:
        logger.error(f"System error in price-today: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal Server Error"
        )

@router.get("/mock-price")
def get_mock_price_endpoint():
    try:
        records_json = get_mock_price()
        return {"data": records_json}
    except Exception as e:
        logger.error(f"System error in mock-price: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal Server Error"
        )