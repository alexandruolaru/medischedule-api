from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.models import (
    Appointment as AppointmentModel,
    Doctor as DoctorModel,
)
from app.schemas import (
    Doctor,
    DoctorAvailabilityResponse,
    DoctorCreate,
    DoctorListResponse,
    DoctorUpdate,
)
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

router = APIRouter(
    prefix="/doctors",
    tags=["Doctors"],
)


@router.get("", response_model=DoctorListResponse)
def get_doctors(
    search: str | None = Query(
        default=None,
        min_length=2,
        description="Search by first name, last name, email or specialty",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    database: Session = Depends(get_database_session),
):
    filters = []

    if search:
        search_value = f"%{search}%"

        filters.append(
            DoctorModel.first_name.ilike(search_value)
            | DoctorModel.last_name.ilike(search_value)
            | DoctorModel.email.ilike(search_value)
            | DoctorModel.specialty.ilike(search_value)
        )

    query = select(DoctorModel)
    count_query = select(func.count()).select_from(DoctorModel)

    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    query = (
        query
        .order_by(DoctorModel.id.asc())
        .offset(offset)
        .limit(limit)
    )

    doctors = list(database.scalars(query).all())
    total = database.scalar(count_query) or 0

    return {
        "items": doctors,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
@router.get(
    "/{doctor_id}/availability",
    response_model=DoctorAvailabilityResponse,
    responses={
        404: {
            "description": "Doctor not found",
        }
    },
)
def get_doctor_availability(
    doctor_id: int,
    availability_date: date = Query(
        alias="date",
        description="Date for which availability is calculated",
    ),
    work_start: time = Query(
        default=time(9, 0),
        description="Doctor workday start time",
    ),
    work_end: time = Query(
        default=time(17, 0),
        description="Doctor workday end time",
    ),
    slot_minutes: int = Query(
        default=30,
        ge=5,
        le=240,
        description="Duration of one appointment slot",
    ),
    database: Session = Depends(get_database_session),
):
    doctor = database.get(DoctorModel, doctor_id)

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    if work_end <= work_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="work_end must be after work_start",
        )

    timezone = ZoneInfo("Europe/Bucharest")

    workday_start = datetime.combine(
        availability_date,
        work_start,
        tzinfo=timezone,
    )

    workday_end = datetime.combine(
        availability_date,
        work_end,
        tzinfo=timezone,
    )

    appointments_query = (
        select(AppointmentModel)
        .where(
            AppointmentModel.doctor_id == doctor_id,
            AppointmentModel.status != "cancelled",
            AppointmentModel.starts_at < workday_end,
            AppointmentModel.ends_at > workday_start,
        )
        .order_by(AppointmentModel.starts_at.asc())
    )

    appointments = list(
        database.scalars(appointments_query).all()
    )

    available_slots = []
    current_start = workday_start
    slot_duration = timedelta(minutes=slot_minutes)

    while current_start + slot_duration <= workday_end:
        current_end = current_start + slot_duration

        overlaps = any(
            appointment.starts_at < current_end
            and appointment.ends_at > current_start
            for appointment in appointments
        )

        if not overlaps:
            available_slots.append(
                {
                    "starts_at": current_start,
                    "ends_at": current_end,
                }
            )

        current_start = current_end

    return {
        "doctor_id": doctor_id,
        "date": availability_date.isoformat(),
        "slot_minutes": slot_minutes,
        "available_slots": available_slots,
    }

@router.get(
    "/{doctor_id}",
    response_model=Doctor,
    responses={
        404: {
            "description": "Doctor not found",
        }
    },
)
def get_doctor(
    doctor_id: int,
    database: Session = Depends(get_database_session),
):
    doctor = database.get(DoctorModel, doctor_id)

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    return doctor


@router.post(
    "",
    response_model=Doctor,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {
            "description": "Email already exists",
        }
    },
)
def create_doctor(
    payload: DoctorCreate,
    database: Session = Depends(get_database_session),
):
    doctor = DoctorModel(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        specialty=payload.specialty,
        phone=payload.phone,
    )

    database.add(doctor)

    try:
        database.commit()
    except IntegrityError:
        database.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A doctor with this email already exists",
        )

    database.refresh(doctor)

    return doctor


@router.put(
    "/{doctor_id}",
    response_model=Doctor,
    responses={
        404: {
            "description": "Doctor not found",
        },
        409: {
            "description": "Email already exists",
        },
    },
)
def update_doctor(
    doctor_id: int,
    payload: DoctorUpdate,
    database: Session = Depends(get_database_session),
):
    doctor = database.get(DoctorModel, doctor_id)

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    doctor.first_name = payload.first_name
    doctor.last_name = payload.last_name
    doctor.email = payload.email
    doctor.specialty = payload.specialty
    doctor.phone = payload.phone

    try:
        database.commit()
    except IntegrityError:
        database.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A doctor with this email already exists",
        )

    database.refresh(doctor)

    return doctor


@router.delete(
    "/{doctor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {
            "description": "Doctor not found",
        }
    },
)
def delete_doctor(
    doctor_id: int,
    database: Session = Depends(get_database_session),
):
    doctor = database.get(DoctorModel, doctor_id)

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    database.delete(doctor)
    database.commit()