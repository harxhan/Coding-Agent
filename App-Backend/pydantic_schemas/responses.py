from datetime import date
from pydantic import BaseModel, ConfigDict, ConfigDict


from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

class HabitInsertionResponse(BaseModel):
    habit_id: UUID

    model_config = ConfigDict(from_attributes=True)
    
class ActivityResponse(BaseModel):
    activity_id: UUID
    name: str
    priority: Optional[int]
    days: Optional[int]

    model_config = ConfigDict(from_attributes=True)

class HabitResponse(BaseModel):
    habit_id: UUID
    month: str
    start_date: date
    end_date: date
    activities: List[ActivityResponse]

    model_config = ConfigDict(from_attributes=True)

class ActivityLogView(BaseModel):
    activity_id: UUID
    activity_name: str
    habit_id: UUID
    habit_month: str
    date: date    
    