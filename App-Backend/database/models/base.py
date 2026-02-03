import os

from sqlalchemy.orm import declarative_base

from dotenv import load_dotenv

load_dotenv()

SCHEMA = os.getenv("DATABASE_SCHEMA", "public")

Base = declarative_base()
