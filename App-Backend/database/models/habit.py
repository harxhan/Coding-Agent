import os
import uuid

from sqlalchemy import Column, Date, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import Base

from dotenv import load_dotenv

load_dotenv()

SCHEMA = os.getenv("DATABASE_SCHEMA", "public")

class Habit(Base):
    __tablename__ = "habits"
    __table_args__ = {"schema": SCHEMA}

    habit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    month = Column(String(20), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)

    activities = relationship(
        "Activity",
        back_populates="habit",
        cascade="all, delete-orphan"
    )