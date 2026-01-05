import json
import logging
from fastapi import APIRouter, status, HTTPException
from vnstock import Trading, Listing
from app.services.stock_api_service import get_price_today, get_mock_price # Assuming this exists
from app.services.stock_service import get_all_stocks
# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stock", tags=["stock"])

@router.get("/")
def get_all_stocks_in_db():
    try:
        stocks = get_all_stocks()
        print(stocks)
        return stocks
    except Exception as e:
        logger.error(f"Error getting stocks in db: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Failed to fetch all the stocks in the db: {e}"
        )

# @router.get("/all-stocks")
# def get_all_stocks():
#     """
#     Get all the stocks available on market
#     """
#     try: 
#         listing = Listing()
#         df = listing.all_symbols()
#         print(df["symbol"], df["organ_name"])
#     except Exception as e:
#         logger.error(f"Error fetching all stock symbols: {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
#             detail=f"Failed to fetch all the stock symbols: {e}"
#         )

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
        records_json, divergences = get_mock_price()
        return {"data": records_json, "divergences": divergences}
    except Exception as e:
        logger.error(f"System error in mock-price: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Internal Server Error"
        )