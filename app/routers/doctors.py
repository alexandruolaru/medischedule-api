from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.models import (
    Appointment as AppointmentModel,
    Doctor as DoctorModel,
    DoctorSchedule as DoctorScheduleModel,
)
from app.schemas import (
    Doctor,
    DoctorAvailabilityResponse,
    DoctorCreate,
    DoctorListResponse,
    DoctorSchedule,
    DoctorScheduleCreate,
    DoctorScheduleListResponse,
    DoctorScheduleUpdate,
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
    "/{doctor_id}/schedules",
    response_model=DoctorScheduleListResponse,
    responses={
        404: {
            "description": "Doctor not found",
        }
    },
)
def get_doctor_schedules(
    doctor_id: int,
    database: Session = Depends(get_database_session),
):
    doctor = database.get(DoctorModel, doctor_id)

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    query = (
        select(DoctorScheduleModel)
        .where(DoctorScheduleModel.doctor_id == doctor_id)
        .order_by(
            DoctorScheduleModel.weekday.asc(),
            DoctorScheduleModel.work_start.asc(),
        )
    )

    schedules = list(database.scalars(query).all())

    return {
        "doctor_id": doctor_id,
        "schedules": schedules,
    }
@router.post(
    "/{doctor_id}/schedules",
    response_model=DoctorSchedule,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {
            "description": "Doctor not found",
        },
        409: {
            "description": "Schedule overlaps an existing interval",
        },
    },
)
def create_doctor_schedule(
    doctor_id: int,
    payload: DoctorScheduleCreate,
    database: Session = Depends(get_database_session),
):
    doctor = database.get(DoctorModel, doctor_id)

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    if payload.work_end <= payload.work_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="work_end must be after work_start",
        )

    overlap_query = select(DoctorScheduleModel.id).where(
        DoctorScheduleModel.doctor_id == doctor_id,
        DoctorScheduleModel.weekday == payload.weekday,
        DoctorScheduleModel.work_start < payload.work_end,
        DoctorScheduleModel.work_end > payload.work_start,
    )

    if database.scalar(overlap_query) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Schedule overlaps an existing interval",
        )

    schedule = DoctorScheduleModel(
        doctor_id=doctor_id,
        weekday=payload.weekday,
        work_start=payload.work_start,
        work_end=payload.work_end,
    )

    database.add(schedule)
    database.commit()
    database.refresh(schedule)

    return schedule

@router.put(
    "/{doctor_id}/schedules/{schedule_id}",
    response_model=DoctorSchedule,
    responses={
        404: {
            "description": "Doctor or schedule not found",
        },
        409: {
            "description": "Schedule overlaps an existing interval",
        },
    },
)
def update_doctor_schedule(
    doctor_id: int,
    schedule_id: int,
    payload: DoctorScheduleUpdate,
    database: Session = Depends(get_database_session),
):
    doctor = database.get(DoctorModel, doctor_id)

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    schedule = database.get(DoctorScheduleModel, schedule_id)

    if schedule is None or schedule.doctor_id != doctor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    if payload.work_end <= payload.work_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="work_end must be after work_start",
        )

    overlap_query = select(DoctorScheduleModel.id).where(
        DoctorScheduleModel.doctor_id == doctor_id,
        DoctorScheduleModel.weekday == payload.weekday,
        DoctorScheduleModel.work_start < payload.work_end,
        DoctorScheduleModel.work_end > payload.work_start,
        DoctorScheduleModel.id != schedule_id,
    )

    if database.scalar(overlap_query) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Schedule overlaps an existing interval",
        )

    schedule.weekday = payload.weekday
    schedule.work_start = payload.work_start
    schedule.work_end = payload.work_end

    database.commit()
    database.refresh(schedule)

    return schedule
@router.delete(
    "/{doctor_id}/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {
            "description": "Doctor or schedule not found",
        }
    },
)
def delete_doctor_schedule(
    doctor_id: int,
    schedule_id: int,
    database: Session = Depends(get_database_session),
):
    doctor = database.get(DoctorModel, doctor_id)

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    schedule = database.get(DoctorScheduleModel, schedule_id)

    if schedule is None or schedule.doctor_id != doctor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )

    database.delete(schedule)
    database.commit()
@router.get(
    "/{doctor_id}/availability",
    response_model=DoctorAvailabilityResponse,
    responses={
        404: {
            "description": "Doctor or schedule not found",
        }
    },
)
def get_doctor_availability(
    doctor_id: int,
    availability_date: date = Query(
        alias="date",
        description="Date for which availability is calculated",
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

    weekday = availability_date.weekday()

    schedule_query = (
        select(DoctorScheduleModel)
        .where(
            DoctorScheduleModel.doctor_id == doctor_id,
            DoctorScheduleModel.weekday == weekday,
        )
        .order_by(DoctorScheduleModel.work_start.asc())
    )

    schedules = list(database.scalars(schedule_query).all())

    if not schedules:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor has no schedule for this day",
        )

    timezone = ZoneInfo("Europe/Bucharest")
    slot_duration = timedelta(minutes=slot_minutes)
    available_slots = []

    day_start = datetime.combine(
        availability_date,
        time.min,
        tzinfo=timezone,
    )

    day_end = datetime.combine(
        availability_date,
        time.max,
        tzinfo=timezone,
    )

    appointments_query = (
        select(AppointmentModel)
        .where(
            AppointmentModel.doctor_id == doctor_id,
            AppointmentModel.status != "cancelled",
            AppointmentModel.starts_at < day_end,
            AppointmentModel.ends_at > day_start,
        )
        .order_by(AppointmentModel.starts_at.asc())
    )

    appointments = list(
        database.scalars(appointments_query).all()
    )

    for schedule in schedules:
        workday_start = datetime.combine(
            availability_date,
            schedule.work_start,
            tzinfo=timezone,
        )

        workday_end = datetime.combine(
            availability_date,
            schedule.work_end,
            tzinfo=timezone,
        )

        current_start = workday_start

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