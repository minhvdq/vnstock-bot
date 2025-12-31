from datetime import date
import pandas as pd
import numpy as np
import talib
from vnstock import Listing

def get_all_companies():
    """
    Get all the companies available on market
    """
    try: 
        listing = Listing()
        df = listing.all_symbols()
        return df.to_dict(orient="records")
    except Exception as e:
        print(f"Error fetching all stock symbols: {e}")
        return []