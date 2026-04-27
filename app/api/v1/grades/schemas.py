"""Pydantic schemas for the grades and report-cards module."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ─── Grade Scales ────────────────────────────────────────────────────────────

class GradeScaleItem(BaseModel):
    id: UUID
    label: str
    min_percentage: Decimal
    max_percentage: Decimal
    gpa_points: Optional[Decimal] = None
    remarks: Optional[str] = None
    display_order: int


class GradeScaleCreate(BaseModel):
    label: str = Field(..., max_length=10)
    min_percentage: Decimal = Field(..., ge=0, le=100)
    max_percentage: Decimal = Field(..., ge=0, le=100)
    gpa_points: Optional[Decimal] = None
    remarks: Optional[str] = None
    display_order: int = 0


class GradeScaleUpdate(BaseModel):
    label: Optional[str] = Field(None, max_length=10)
    min_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    max_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    gpa_points: Optional[Decimal] = None
    remarks: Optional[str] = None
    display_order: Optional[int] = None


# ─── Marks Entry ─────────────────────────────────────────────────────────────

class MarkEntry(BaseModel):
    student_id: UUID
    subject_id: UUID
    marks_obtained: Optional[Decimal] = Field(None, ge=0)
    max_marks: Decimal = Field(default=Decimal("100"), gt=0)
    is_absent: bool = False
    remarks: Optional[str] = None


class BulkMarksRequest(BaseModel):
    marks: List[MarkEntry] = Field(..., min_length=1)


class MarkUpdateRequest(BaseModel):
    marks_obtained: Optional[Decimal] = Field(None, ge=0)
    max_marks: Optional[Decimal] = Field(None, gt=0)
    is_absent: Optional[bool] = None
    remarks: Optional[str] = None


# ─── Marks Responses ─────────────────────────────────────────────────────────

class SubjectMarkItem(BaseModel):
    mark_id: UUID
    subject_id: UUID
    subject_name: str
    marks_obtained: Optional[Decimal] = None
    max_marks: Decimal
    percentage: Optional[float] = None
    grade_label: Optional[str] = None
    is_absent: bool
    remarks: Optional[str] = None
    entered_by_name: Optional[str] = None
    updated_at: datetime


class StudentMarksRow(BaseModel):
    student_id: UUID
    full_name: str
    roll_number: Optional[str] = None
    subjects: List[SubjectMarkItem]
    total_marks_obtained: Optional[Decimal] = None
    total_max_marks: Decimal
    overall_percentage: Optional[float] = None
    overall_grade: Optional[str] = None


class ExamMarksResponse(BaseModel):
    exam_id: UUID
    exam_name: str
    class_name: str
    section_name: str
    students: List[StudentMarksRow]


# ─── Report Card ─────────────────────────────────────────────────────────────

class ReportCardSubject(BaseModel):
    subject_id: UUID
    subject_name: str
    marks_obtained: Optional[Decimal] = None
    max_marks: Decimal
    percentage: Optional[float] = None
    grade_label: Optional[str] = None
    is_absent: bool = False


class ReportCard(BaseModel):
    student_id: UUID
    student_name: str
    roll_number: Optional[str] = None
    class_name: str
    section_name: str
    academic_year_name: str
    exam_id: UUID
    exam_name: str
    exam_type: str
    start_date: date
    end_date: date
    subjects: List[ReportCardSubject]
    total_marks_obtained: Optional[Decimal] = None
    total_max_marks: Decimal
    overall_percentage: Optional[float] = None
    overall_grade: Optional[str] = None


# ─── Exam Summary (for student/parent grade list) ────────────────────────────

class ExamGradeSummary(BaseModel):
    exam_id: UUID
    exam_name: str
    exam_type: str
    start_date: date
    end_date: date
    status: str
    class_name: str
    section_name: str
    overall_percentage: Optional[float] = None
    overall_grade: Optional[str] = None
    marks_entered: bool


# ─── Bulk result ─────────────────────────────────────────────────────────────

class BulkMarksResult(BaseModel):
    saved: int
    errors: List[Dict[str, Any]] = []
