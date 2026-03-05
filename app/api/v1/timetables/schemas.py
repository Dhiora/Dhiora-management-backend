from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TimetableSlotCreate(BaseModel):
    academic_year_id: UUID
    class_id: UUID
    section_id: UUID
    subject_id: UUID
    teacher_id: UUID
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday .. 6=Sunday")
    slot_id: UUID = Field(..., description="TimeSlot ID")


class TimetableSlotUpdate(BaseModel):
    teacher_id: Optional[UUID] = None
    slot_id: Optional[UUID] = Field(None, description="New TimeSlot ID")


class TimeSlotInfo(BaseModel):
    id: UUID
    name: str
    start_time: str
    end_time: str
    slot_type: str


class TimetableSlotResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    class_id: UUID
    section_id: UUID
    subject_id: UUID
    teacher_id: UUID
    day_of_week: int
    slot: TimeSlotInfo
    created_at: datetime
    class_name: Optional[str] = None
    section_name: Optional[str] = None
    subject_name: Optional[str] = None
    teacher_name: Optional[str] = None

    class Config:
        from_attributes = True
