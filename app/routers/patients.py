from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_database_session
from app.models import Patient as PatientModel
from app.schemas import (
    Patient,
    PatientCreate,
    PatientListResponse,
    PatientUpdate,
)


router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
)

@router.get("", response_model=PatientListResponse)
def get_patients(
    search: str | None = Query(
        default=None,
        min_length=2,
        description="Search by first name, last name or email",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of patients returned",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Number of patients to skip",
    ),
    sort_by: str = Query(
        default="id",
        pattern="^(id|first_name|last_name|email)$",
        description="Field used for sorting",
    ),
    sort_order: str = Query(
        default="asc",
        pattern="^(asc|desc)$",
        description="Sort direction",
    ),
    database: Session = Depends(get_database_session),
):
    filters = []

    if search:
        search_value = f"%{search}%"

        filters.append(
            PatientModel.first_name.ilike(search_value)
            | PatientModel.last_name.ilike(search_value)
            | PatientModel.email.ilike(search_value)
        )

    query = select(PatientModel)
    count_query = select(func.count()).select_from(PatientModel)

    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    sort_columns = {
        "id": PatientModel.id,
        "first_name": PatientModel.first_name,
        "last_name": PatientModel.last_name,
        "email": PatientModel.email,
    }

    sort_column = sort_columns[sort_by]

    if sort_order == "desc":
        sort_column = sort_column.desc()
    else:
        sort_column = sort_column.asc()

    query = (
        query
        .order_by(sort_column)
        .offset(offset)
        .limit(limit)
    )

    patients = list(database.scalars(query).all())
    total = database.scalar(count_query) or 0

    return {
        "items": patients,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/{patient_id}",
    response_model=Patient,
    responses={
        404: {
            "description": "Patient not found",
        }
    },
)
def get_patient(
    patient_id: int,
    database: Session = Depends(get_database_session),
):
    patient = database.get(PatientModel, patient_id)

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    return patient


@router.post(
    "",
    response_model=Patient,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {
            "description": "Email already exists",
        }
    },
)
def create_patient(
    patient: PatientCreate,
    database: Session = Depends(get_database_session),
):
    new_patient = PatientModel(
        first_name=patient.first_name,
        last_name=patient.last_name,
        email=patient.email,
        phone=patient.phone,
    )

    database.add(new_patient)

    try:
        database.commit()
    except IntegrityError:
        database.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A patient with this email already exists",
        )

    database.refresh(new_patient)

    return new_patient


@router.put(
    "/{patient_id}",
    response_model=Patient,
    responses={
        404: {
            "description": "Patient not found",
        },
        409: {
            "description": "Email already exists",
        },
    },
)
def update_patient(
    patient_id: int,
    payload: PatientUpdate,
    database: Session = Depends(get_database_session),
):
    patient = database.get(PatientModel, patient_id)

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    patient.first_name = payload.first_name
    patient.last_name = payload.last_name
    patient.email = payload.email
    patient.phone = payload.phone

    try:
        database.commit()
    except IntegrityError:
        database.rollback()

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A patient with this email already exists",
        )

    database.refresh(patient)

    return patient


@router.delete(
    "/{patient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {
            "description": "Patient not found",
        }
    },
)
def delete_patient(
    patient_id: int,
    database: Session = Depends(get_database_session),
):
    patient = database.get(PatientModel, patient_id)

    if patient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found",
        )

    database.delete(patient)
    database.commit()