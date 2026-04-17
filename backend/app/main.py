import asyncio
from app.workers.intraday_worker import intraday_worker
from app.workers.daily_worker import daily_worker
from fastapi import FastAPI
from app.routers import stock, company, user, auth, backtest, paper_trading
from app.services.user_service import define_user_chatid
from app.utils.telegram import send_message
from app.services.user_service import get_all_users
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import engine, Base
from sqlalchemy import text
import app.models.paper_trading  # noqa: F401 — ensure tables are registered with Base


app = FastAPI(title="Stock Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(stock.router)
app.include_router(company.router)
app.include_router(user.router)
app.include_router(auth.router)
app.include_router(backtest.router)
app.include_router(paper_trading.router)

@app.on_event("startup")
async def startup_event():
    try:
        Base.metadata.create_all(bind=engine, checkfirst=True)
        # Add strategy_name column to existing paper_trades table if missing
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE paper_trades "
                "ADD COLUMN IF NOT EXISTS strategy_name VARCHAR(50) NOT NULL DEFAULT 'rsi_divergence'"
            ))
            conn.commit()
        asyncio.create_task(intraday_worker())
        asyncio.create_task(daily_worker())
        print("Workers started successfully")
    except Exception as e:
        print(f"Error starting workers: {e}")

@app.post("/webhook")
async def telegram_webhook(update: dict):
    if "message" not in update:
        return {"ok": True}

    text = update["message"].get("text", "")
    chat_id = str(update["message"]["chat"]["id"])

    if text.startswith("/start "):
        try:
            user_id = int(text.split(" ")[1])
            define_user_chatid(user_id=user_id, chat_id=chat_id)
            await send_message(chat_id=chat_id, text="✅ Telegram connected! You will now receive stock signals.")
        except Exception as e:
            print(f"Webhook /start error: {e}")
            await send_message(chat_id=chat_id, text="❌ Failed to connect. Please try the link again.")

    return {"ok": True}

@app.get("/test_telegram")
async def test_telegram():
    users = get_all_users()
    for user in users:
        await send_message(user.chat_id, "hello")
    return {"ok": True}

@app.get("/health")
def root():
    return {"message": "ok"}