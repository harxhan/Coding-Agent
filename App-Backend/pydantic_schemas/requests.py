from datetime import date
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

class ActivityCreate(BaseModel):
    name: str
    priority: Optional[int] = None
    days: Optional[int] = None

class ActivityUpdate(BaseModel):
    name: Optional[str] = None
    priority: Optional[int] = None
    days: Optional[int] = None
    
class HabitCreate(BaseModel):
    month: str
    start_date: date
    end_date: date
    activities: List[ActivityCreate]

class HabitUpdate(BaseModel):
    month: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class ActivityLogCreate(BaseModel):
    date: date
    