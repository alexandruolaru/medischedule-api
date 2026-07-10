from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.models import Doctor as DoctorModel
from app.schemas import (
    Doctor,
    DoctorCreate,
    DoctorListResponse,
    DoctorUpdate,
)


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