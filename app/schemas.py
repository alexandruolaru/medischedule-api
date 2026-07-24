from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from enum import Enum

class PatientBase(BaseModel):
    first_name: str = Field(min_length=2, max_length=100)
    last_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    phone: str | None = Field(
        default=None,
        min_length=10,
        max_length=20,
    )


class PatientCreate(PatientBase):
    pass


class PatientUpdate(PatientBase):
    pass


class Patient(PatientBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PatientListResponse(BaseModel):
    items: list[Patient]
    total: int
    limit: int
    offset: int

class DoctorBase(BaseModel):
    first_name: str = Field(min_length=2, max_length=100)
    last_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    specialty: str = Field(min_length=2, max_length=150)
    phone: str | None = Field(
        default=None,
        min_length=10,
        max_length=20,
    )


class DoctorCreate(DoctorBase):
    pass


class DoctorUpdate(DoctorBase):
    pass


class Doctor(DoctorBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DoctorListResponse(BaseModel):
    items: list[Doctor]
    total: int
    limit: int
    offset: int

class AppointmentStatus(str, Enum):
    scheduled = "scheduled"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"

class AppointmentBase(BaseModel):
    patient_id: int
    doctor_id: int
    starts_at: datetime
    ends_at: datetime
    status: AppointmentStatus = AppointmentStatus.scheduled
    notes: str | None = Field(
        default=None,
        max_length=500,
    )


class AppointmentCreate(AppointmentBase):
    pass


class AppointmentUpdate(AppointmentBase):
    pass


class Appointment(AppointmentBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentListResponse(BaseModel):
    items: list[Appointment]
    total: int
    limit: int
    offset: int
class AvailabilitySlot(BaseModel):
    starts_at: datetime
    ends_at: datetime


class DoctorAvailabilityResponse(BaseModel):
    doctor_id: int
    date: str
    slot_minutes: int
    available_slots: list[AvailabilitySlot]
class DoctorScheduleBase(BaseModel):
    weekday: int = Field(
        ge=0,
        le=6,
        description="0 = Monday, 6 = Sunday",
    )
    work_start: time
    work_end: time


class DoctorScheduleCreate(DoctorScheduleBase):
    pass


class DoctorSchedule(DoctorScheduleBase):
    id: int
    doctor_id: int

    model_config = ConfigDict(from_attributes=True)


class DoctorScheduleListResponse(BaseModel):
    doctor_id: int
    schedules: list[DoctorSchedule]