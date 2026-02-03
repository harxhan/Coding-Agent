from fastapi import APIRouter, Depends, HTTPException, status

from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from database.utils.deps import get_db
from database.models.habit import Habit
from database.models.activity import Activity

from pydantic_schemas.requests import HabitCreate, HabitUpdate
from pydantic_schemas.responses import HabitInsertionResponse, HabitResponse


router = APIRouter(prefix="/habits", tags=["Habits"])

# View all habits with their activities ================
@router.get("/view", response_model=list[HabitResponse])
def get_all_habits(db: Session = Depends(get_db)):
    habits = (
        db.query(Habit)
        .options(joinedload(Habit.activities))
        .all()
    )

    return habits

# Create New Habit ================================================================================
@router.post("/insert", response_model=HabitInsertionResponse, status_code=status.HTTP_201_CREATED)
def create_habit(payload: HabitCreate, db: Session = Depends(get_db)):
    try:
        habit = Habit(
            month=payload.month,
            start_date=payload.start_date,
            end_date=payload.end_date,
        )

        db.add(habit)
        db.flush()  # 🔥 ensures habit_id is generated

        for act in payload.activities:
            activity = Activity(
                habit_id=habit.habit_id,
                name=act.name,
                priority=act.priority,
                days=act.days,
            )
            db.add(activity)

        db.commit()
        db.refresh(habit)

        return habit

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# Update Habit ==================
@router.put("/update/{habit_id}", status_code=204)
def update_habit(
    habit_id: UUID,
    payload: HabitUpdate,
    db: Session = Depends(get_db)
):
    habit = db.query(Habit).filter(Habit.habit_id == habit_id).first()

    if not habit:
        raise HTTPException(status_code=404, detail="Habit not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(habit, field, value)

    db.commit()
    db.refresh(habit)

    return habit

# Delete Habit =============================================================
@router.delete("/delete/{habit_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_habit(habit_id: UUID, db: Session = Depends(get_db)):
    habit = db.query(Habit).filter(Habit.habit_id == habit_id).first()

    if not habit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Habit not found"
        )

    db.delete(habit)
    db.commit()

    return None

