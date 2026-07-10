from fastapi import FastAPI

from app.routers.patients import router as patients_router


app = FastAPI(
    title="MediSchedule API",
    version="1.0.0",
)


@app.get("/", tags=["General"])
def home():
    return {
        "application": "MediSchedule API",
        "status": "running",
    }


app.include_router(patients_router)