import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv("DATABASE_USER", "")
DB_PASSWORD = os.getenv("DATABASE_PASSWORD", "")
DB_HOST = os.getenv("DATABASE_HOST", "")
DB_PORT = os.getenv("DATABASE_PORT", "")
DB_NAME = os.getenv("DATABASE_NAME", "")
DB_DRIVER = os.getenv("DATABASE_DRIVER", "")

DATABASE_URL = (
    f"{DB_DRIVER}://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)
