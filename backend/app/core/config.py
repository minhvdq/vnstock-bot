import os
from dotenv import load_dotenv

load_dotenv(override=True)

DATABASE_URL = os.getenv("DATABASE_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALGORITHM = "HS256"
# if not DATABASE_URL:
#     raise ValueError("DATABASE_URL environment variable is not set. Please set it in your .env file.")
