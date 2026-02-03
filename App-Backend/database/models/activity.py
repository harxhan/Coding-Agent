import os
import uuid

from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base

from dotenv import load_dotenv

load_dotenv()

SCHEMA = os.getenv("DATABASE_SCHEMA", "public")
    
class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = {"schema": SCHEMA}

    activity_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    habit_id = Column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.habits.habit_id", ondelete="CASCADE"))
    name = Column(String(100), nullable=False)
    priority = Column(Integer)
    days = Column(Integer)
    
    habit = relationship("Habit", back_populates="activities")
