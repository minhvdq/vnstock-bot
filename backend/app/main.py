from fastapi import FastAPI
from app.routers import stock, company, user
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="Stock Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allows all headers
)

app.include_router(stock.router)
app.include_router(company.router)
app.include_router(user.router)

@app.get("/health")
def root():
    return {"message": "ok"}