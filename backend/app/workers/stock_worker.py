import asyncio
from datetime import date
from app.services.user_service import get_all_users
from app.services.stock_api_service import is_divergence
from app.utils.telegram import send_message
from sqlalchemy.exc import OperationalError, DisconnectionError

async def stock_worker():
    while(True):
        try:
            tday = date.today()  # Fixed: added parentheses to call the method
            users = get_all_users()
            await send_message("123", "Hello World!")
            await asyncio.sleep(5)
        except (OperationalError, DisconnectionError) as e:
            print(f"Database connection error in stock_worker: {e}")
            print("Retrying in 10 seconds...")
            await asyncio.sleep(10)  # Wait longer before retrying on DB errors
            continue
        except Exception as e:
            print(f"Error in stock_worker: {e}")
            await asyncio.sleep(5)  # Wait before retrying
            continue