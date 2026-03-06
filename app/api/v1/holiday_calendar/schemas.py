"""Pydantic schemas for Holiday Calendar API."""

from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class HolidayCreate(BaseModel):
    academic_year_id: UUID
    holiday_name: str = Field(..., max_length=255)
    holiday_date: date
    description: Optional[str] = None


class HolidayUpdate(BaseModel):
    holiday_name: Optional[str] = Field(None, max_length=255)
    holiday_date: Optional[date] = None
    description: Optional[str] = None


class HolidayResponse(BaseModel):
    id: UUID
    academic_year_id: UUID
    holiday_name: str
    holiday_date: date
    month: int
    year: int
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

