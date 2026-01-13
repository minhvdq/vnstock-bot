import asyncio
from datetime import date
from app.services.user_service import get_all_users
from app.services.stock_api_service import is_divergence, get_price_today, get_mock_price
from app.utils.telegram import send_message
from sqlalchemy.exc import OperationalError, DisconnectionError

async def stock_worker():
    while(True):
        try:
            users = get_all_users()
            for user in users:
                if not user.chat_id or user.chat_id == "":
                    continue
                for stock in user.stocks:
                    df = get_mock_price(stock)
                    print(df)
                    l = len(df)
                    print("length is " + str(l))
                    divergence = is_divergence(df, l - 1)
                    # if divergence:
                    #     print("Got the divergence " + str(divergence))
                        # send_message(user.chat_id, f"Stock {stock} is a divergence: {divergence.suffixIndex} and {divergence.prefixIndex} at type {divergence.type}")
            print("Hello World!")
            await asyncio.sleep(5)
        except (OperationalError, DisconnectionError) as e:
            print(f"Database connection error in stock_worker: {e}")
            print("Retrying in 10 seconds...")
            await asyncio.sleep(10)  # Wait longer before retrying on DB errors
            continue
        except Exception as e:
            print(f"Error in stock_worker: {str(e)}")
            await asyncio.sleep(5)
            continue