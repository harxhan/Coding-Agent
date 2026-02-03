import os

from sqlalchemy import Column, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from .base import Base

from dotenv import load_dotenv

load_dotenv()

SCHEMA = os.getenv("DATABASE_SCHEMA", "public")

class ActivityLog(Base):
    __tablename__ = "activity_logs"
    __table_args__ = {"schema": SCHEMA}
    
    activity_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.activities.activity_id", ondelete="CASCADE"), primary_key=True)
    date = Column(Date, primary_key=True)
