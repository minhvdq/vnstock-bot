import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
# Import your base URL, but we will wrap it for safety
from app.core.config import DATABASE_URL

# 1. Fix the Prefix (SQLAlchemy 1.4+ requirement)
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 2. Safety Check: If URL is still missing, provide a clear error
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set! Check your Fly.io secrets.")

# 3. Create Engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # detect stale connections on checkout
    pool_recycle=1800,    # recycle connections every 30 min before server kills them
    pool_size=5,
    max_overflow=10,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL.lower() else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()