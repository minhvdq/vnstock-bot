import json
import logging
from fastapi import APIRouter, status, HTTPException
from vnstock import Trading, Listing
from app.services.company_service import get_all_companies

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/company", tags=["company"])

@router.get("/all-companies")
def get_all_symbols():
    """
    Get all the companies available on market
    """
    try: 
        companies = get_all_companies()
        print(companies)
        return companies
    except Exception as e:
        logger.error(f"Error fetching all stock symbols: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Failed to fetch all the stock symbols: {e}"
        )