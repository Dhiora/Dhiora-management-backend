"""Schemas for class schedule (timetable-derived) and exam APIs."""

from typing import Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ----- Class Schedule (from timetable) -----
class ClassScheduleSlot(BaseModel):
    """One period in the weekly class schedule."""
    subject_id: str
    teacher_id: str
    start_time: str  # "09:00"
    end_time: str   # "09:45"
    subject_name: Optional[str] = None
    teacher_name: Optional[str] = None


class ClassScheduleResponse(BaseModel):
    """Weekly schedule by day. Keys: monday .. sunday; values: list of slots ordered by start_time."""
    monday: List[ClassScheduleSlot] = Field(default_factory=list)
    tuesday: List[ClassScheduleSlot] = Field(default_factory=list)
    wednesday: List[ClassScheduleSlot] = Field(default_factory=list)
    thursday: List[ClassScheduleSlot] = Field(default_factory=list)
    friday: List[ClassScheduleSlot] = Field(default_factory=list)
    saturday: List[ClassScheduleSlot] = Field(default_factory=list)
    sunday: List[ClassScheduleSlot] = Field(default_factory=list)

    @classmethod
    def from_day_lists(cls, day_slots: Dict[str, List[ClassScheduleSlot]]) -> "ClassScheduleResponse":
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        return cls(**{d: day_slots.get(d, []) for d in days})


class ClassScheduleItemResponse(BaseModel):
    """Schedule for one class/section: identifiers plus weekly slots."""
    class_id: UUID
    section_id: UUID
    class_name: Optional[str] = None
    section_name: Optional[str] = None
    monday: List[ClassScheduleSlot] = Field(default_factory=list)
    tuesday: List[ClassScheduleSlot] = Field(default_factory=list)
    wednesday: List[ClassScheduleSlot] = Field(default_factory=list)
    thursday: List[ClassScheduleSlot] = Field(default_factory=list)
    friday: List[ClassScheduleSlot] = Field(default_factory=list)
    saturday: List[ClassScheduleSlot] = Field(default_factory=list)
    sunday: List[ClassScheduleSlot] = Field(default_factory=list)
