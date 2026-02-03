from fastapi import FastAPI

from routes.habits import router as habits_router
from routes.activities import router as activities_router

app = FastAPI(title="Habit Tracker API")

app.include_router(habits_router)
app.include_router(activities_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)