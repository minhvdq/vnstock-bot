import asyncio
from app.workers.stock_worker import stock_worker
from fastapi import FastAPI
from app.routers import stock, company, user, auth
from app.services.user_service import define_user_chatid
from app.utils.telegram import send_message
from app.services.user_service import get_all_users
from fastapi.middleware.cors import CORSMiddleware


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

@app.on_event("startup")
async def startup_event():
    # Start the background worker automatically
    # Wrap in try-except to prevent startup from hanging if worker fails
    try:
        asyncio.create_task(stock_worker())
        print("Stock worker started successfully")
    except Exception as e:
        print(f"Error starting stock worker: {e}")
        # Don't raise - allow the app to start even if worker fails

@app.post("/webhook")
async def telegram_webhook(update: dict):
    if "message" not in update: return {"ok": True}        

    text = update["message"].get("text", "")
    chat_id = update["message"]["chat"]["id"]
    if text.startswith("/start "):
        user_id = text.split(" ")[1]   
        # try:
        define_user_chatid(user_id=user_id, chat_id=chat_id)
        await send_message(chat_id=chat_id, msg=f"Successfully define chat id for user {user_id}")
        # return {"ok": True}
        # except Exception as e:
        #     raise HT
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