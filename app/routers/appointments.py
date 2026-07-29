from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.models import (
    Appointment as AppointmentModel,
    Doctor as DoctorModel,
    DoctorSchedule as DoctorScheduleModel,
    Patient as PatientModel,
)
from app.schemas import (
    Appointment,
    AppointmentCreate,
    AppointmentListResponse,
    AppointmentReschedule,
    AppointmentStatus,
    AppointmentUpdate,
)

router = APIRouter(
    prefix="/appointments",
    tags=["Appointments"],
)

def validate_appointment_interval(
    starts_at: datetime,
    ends_at: datetime,
) -> None:
    if ends_at <= starts_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="ends_at must be after starts_at",
        )

    if starts_at <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="starts_at must be in the future",
        )

    if starts_at.date() != ends_at.date():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Appointment must start and end on the same day",
        )

def validate_doctor_schedule(
    database: Session,
    doctor_id: int,
    starts_at: datetime,
    ends_at: datetime,
) -> None:
    weekday = starts_at.weekday()
    starts_at_time = starts_at.timetz().replace(tzinfo=None)
    ends_at_time = ends_at.timetz().replace(tzinfo=None)

    schedule_query = select(DoctorScheduleModel.id).where(
        DoctorScheduleModel.doctor_id == doctor_id,
        DoctorScheduleModel.weekday == weekday,
        DoctorScheduleModel.work_start <= starts_at_time,
        DoctorScheduleModel.work_end >= ends_at_time,
    )

    if database.scalar(schedule_query) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Appointment is outside the doctor's schedule",
        )

def validate_appointment_relations(
    payload: AppointmentCreate | AppointmentUpdate,
    database: Session,
) -> None:
    patient = database.get(PatientModel, payload.patient_id)

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    doctor = database.get(DoctorModel, payload.doctor_id)

    if doctor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor not found",
        )

    validate_appointment_interval(
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )

    validate_doctor_schedule(
        database=database,
        doctor_id=payload.doctor_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )

def appointment_overlaps(
    database: Session,
    doctor_id: int,
    starts_at: datetime,
    ends_at: datetime,
    exclude_appointment_id: int | None = None,
) -> bool:
    query = select(AppointmentModel.id).where(
    AppointmentModel.doctor_id == doctor_id,
    AppointmentModel.status != "cancelled",
    AppointmentModel.starts_at < ends_at,
    AppointmentModel.ends_at > starts_at,
    )

    if exclude_appointment_id is not None:
        query = query.where(
            AppointmentModel.id != exclude_appointment_id
        )

    return database.scalar(query) is not None


@router.get("", response_model=AppointmentListResponse)
def get_appointments(
    doctor_id: int | None = Query(default=None, ge=1),
    patient_id: int | None = Query(default=None, ge=1),
    appointment_status: AppointmentStatus | None = Query(
        default=None,
        description="Filter by appointment status",
    ),
    date_from: datetime | None = Query(
        default=None,
        description="Filter appointments starting from this date",
    ),
    date_to: datetime | None = Query(
        default=None,
        description="Filter appointments starting before this date",
    ),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    database: Session = Depends(get_database_session),
):
    filters = []

    if doctor_id is not None:
        filters.append(
            AppointmentModel.doctor_id == doctor_id
        )

    if patient_id is not None:
        filters.append(
            AppointmentModel.patient_id == patient_id
        )

    if appointment_status is not None:
        filters.append(
            AppointmentModel.status == appointment_status.value
        )

    if date_from is not None:
        filters.append(
            AppointmentModel.starts_at >= date_from
        )

    if date_to is not None:
        filters.append(
            AppointmentModel.starts_at <= date_to
        )

    query = select(AppointmentModel)
    count_query = select(func.count()).select_from(AppointmentModel)

    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    query = (
        query
        .order_by(AppointmentModel.starts_at.asc())
        .offset(offset)
        .limit(limit)
    )

    appointments = list(database.scalars(query).all())
    total = database.scalar(count_query) or 0

    return {
        "items": appointments,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/{appointment_id}",
    response_model=Appointment,
    responses={
        404: {
            "description": "Appointment not found",
        }
    },
)
def get_appointment(
    appointment_id: int,
    database: Session = Depends(get_database_session),
):
    appointment = database.get(AppointmentModel, appointment_id)

    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    return appointment


@router.post(
    "",
    response_model=Appointment,
    status_code=status.HTTP_201_CREATED,
    responses={
        404: {
            "description": "Patient or doctor not found",
        },
        409: {
            "description": "Appointment overlaps another appointment",
        },
    },
)
def create_appointment(
    payload: AppointmentCreate,
    database: Session = Depends(get_database_session),
):
    validate_appointment_relations(payload, database)

    if appointment_overlaps(
        database=database,
        doctor_id=payload.doctor_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Doctor already has an overlapping appointment",
        )

    appointment = AppointmentModel(
        patient_id=payload.patient_id,
        doctor_id=payload.doctor_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        status=payload.status.value,
        notes=payload.notes,
    )

    database.add(appointment)
    database.commit()
    database.refresh(appointment)

    return appointment


@router.put(
    "/{appointment_id}",
    response_model=Appointment,
    responses={
        404: {
            "description": "Appointment, patient or doctor not found",
        },
        409: {
            "description": "Appointment cannot be updated",
        },
    },
)
def update_appointment(
    appointment_id: int,
    payload: AppointmentUpdate,
    database: Session = Depends(get_database_session),
):
    appointment = database.get(AppointmentModel, appointment_id)

    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    if appointment.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancelled appointment cannot be updated",
        )

    if appointment.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Completed appointment cannot be updated",
        )

    validate_appointment_relations(payload, database)

    if appointment_overlaps(
        database=database,
        doctor_id=payload.doctor_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        exclude_appointment_id=appointment_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Doctor already has an overlapping appointment",
        )

    appointment.patient_id = payload.patient_id
    appointment.doctor_id = payload.doctor_id
    appointment.starts_at = payload.starts_at
    appointment.ends_at = payload.ends_at
    appointment.status = payload.status.value
    appointment.notes = payload.notes

    database.commit()
    database.refresh(appointment)

    return appointment



@router.patch(
    "/{appointment_id}/reschedule",
    response_model=Appointment,
    responses={
        404: {
            "description": "Appointment not found",
        },
        409: {
            "description": "Appointment cannot be rescheduled",
        },
        422: {
            "description": "Invalid appointment interval",
        },
    },
)

def reschedule_appointment(
    appointment_id: int,
    payload: AppointmentReschedule,
    database: Session = Depends(get_database_session),
):
    appointment = database.get(AppointmentModel, appointment_id)

    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    if appointment.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancelled appointment cannot be rescheduled",
        )

    if appointment.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Completed appointment cannot be rescheduled",
        )

    validate_appointment_interval(
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )

    validate_doctor_schedule(
        database=database,
        doctor_id=appointment.doctor_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
    )

    if appointment_overlaps(
        database=database,
        doctor_id=appointment.doctor_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        exclude_appointment_id=appointment_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Doctor already has an overlapping appointment",
        )

    appointment.starts_at = payload.starts_at
    appointment.ends_at = payload.ends_at

    database.commit()
    database.refresh(appointment)

    return appointment

@router.patch(
    "/{appointment_id}/cancel",
    response_model=Appointment,
    responses={
        404: {
            "description": "Appointment not found",
        },
        409: {
            "description": "Appointment is already cancelled",
        },
    },
)

def cancel_appointment(
    appointment_id: int,
    database: Session = Depends(get_database_session),
):
    appointment = database.get(AppointmentModel, appointment_id)

    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    if appointment.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Appointment is already cancelled",
        )

    if appointment.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Completed appointment cannot be cancelled",
        )

    appointment.status = "cancelled"

    database.commit()
    database.refresh(appointment)

    return appointment

@router.patch(
    "/{appointment_id}/confirm",
    response_model=Appointment,
    responses={
        404: {
            "description": "Appointment not found",
        },
        409: {
            "description": "Appointment cannot be confirmed",
        },
    },
)
def confirm_appointment(
    appointment_id: int,
    database: Session = Depends(get_database_session),
):
    appointment = database.get(AppointmentModel, appointment_id)

    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    if appointment.status == "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Appointment is already confirmed",
        )

    if appointment.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancelled appointment cannot be confirmed",
        )

    if appointment.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Completed appointment cannot be confirmed",
        )

    appointment.status = "confirmed"

    database.commit()
    database.refresh(appointment)

    return appointment

@router.patch(
    "/{appointment_id}/complete",
    response_model=Appointment,
    responses={
        404: {
            "description": "Appointment not found",
        },
        409: {
            "description": "Appointment cannot be completed",
        },
    },
)
def complete_appointment(
    appointment_id: int,
    database: Session = Depends(get_database_session),
):
    appointment = database.get(AppointmentModel, appointment_id)

    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    if appointment.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Appointment is already completed",
        )

    if appointment.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancelled appointment cannot be completed",
        )

    if appointment.status != "confirmed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only confirmed appointments can be completed",
        )

    appointment.status = "completed"

    database.commit()
    database.refresh(appointment)

    return appointment

@router.delete(
    "/{appointment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {
            "description": "Appointment not found",
        },
        409: {
            "description": "Completed appointment cannot be deleted",
        },
    },
)
def delete_appointment(
    appointment_id: int,
    database: Session = Depends(get_database_session),
):
    appointment = database.get(AppointmentModel, appointment_id)

    if appointment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found",
        )

    if appointment.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Completed appointment cannot be deleted",
        )

    database.delete(appointment)
    database.commit()