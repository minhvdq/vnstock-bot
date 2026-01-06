import httpx
from app.core.config import TELEGRAM_TOKEN

async def send_message(chat_id: str, text: str):
    print(f"sending {text} to {chat_id}")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    async with httpx.AsyncClient() as client:
        await client.post(url, json={"chat_id": chat_id, "text": text})