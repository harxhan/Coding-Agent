from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID

from database.models.activity_log import ActivityLog
from database.utils.deps import get_db
from database.models.habit import Habit
from database.models.activity import Activity

from pydantic_schemas.requests import ActivityLogCreate, ActivityUpdate
from pydantic_schemas.responses import ActivityLogView

router = APIRouter(prefix="/activities", tags=["Activities"])

@router.get(
    "/view/{habit_id}",
    response_model=list[ActivityLogView]
)
def get_activity_logs_by_habit(
    habit_id: UUID,
    db: Session = Depends(get_db)
):
    logs = (
        db.query(
            ActivityLog.activity_id,
            Activity.name.label("activity_name"),
            Habit.habit_id,
            Habit.month.label("habit_month"),
            ActivityLog.date
        )
        .join(Activity, Activity.activity_id == ActivityLog.activity_id)
        .join(Habit, Habit.habit_id == Activity.habit_id)
        .filter(Habit.habit_id == habit_id)
        .order_by(ActivityLog.date.desc())
        .all()
    )

    return logs

@router.post("/insert/{activity_id}", status_code=status.HTTP_201_CREATED)
def create_activity_log(
    activity_id: UUID,
    payload: ActivityLogCreate,
    db: Session = Depends(get_db)
):
    activity = db.query(Activity).filter(Activity.activity_id == activity_id).first()

    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    log = ActivityLog(
        activity_id=activity_id,
        date=payload.date
    )

    db.add(log)
    db.commit()

    return log

@router.put("/update/{activity_id}")
def update_activity(
    activity_id: UUID,
    payload: ActivityUpdate,
    db: Session = Depends(get_db)
):
    activity = db.query(Activity).filter(Activity.activity_id == activity_id).first()

    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(activity, field, value)

    db.commit()
    db.refresh(activity)

    return activity