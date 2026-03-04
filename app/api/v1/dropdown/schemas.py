"""Global dropdown API schemas (camelCase for frontend)."""

from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


class AcademicYearDropdownItem(BaseModel):
    """Academic year (indicator=AY)."""
    academicYearId: UUID = Field(..., description="Academic year UUID")
    academicYearName: str = Field(..., description="Academic year name (e.g. 2025-2026)")

    class Config:
        populate_by_name = True


class TeacherDropdownItem(BaseModel):
    """Teacher/employee (indicator=T)."""
    teacherId: UUID = Field(..., description="User UUID (employee)")
    teacherName: str = Field(..., description="Full name")

    class Config:
        populate_by_name = True


class SectionDropdownItem(BaseModel):
    sectionName: str = Field(..., description="Section name (e.g. A, B, C)")
    sectionId: UUID = Field(..., description="Section UUID")

    class Config:
        populate_by_name = True


class ClassOnlyDropdownItem(BaseModel):
    """Class only (indicator=C). No sections key in response."""
    className: str = Field(..., description="Class name (e.g. 1st, 2nd)")
    classId: UUID = Field(..., description="Class UUID")

    class Config:
        populate_by_name = True


class ClassWithSectionsDropdownItem(BaseModel):
    """Class with sections (indicator=CS)."""
    className: str = Field(..., description="Class name (e.g. 1st, 2nd)")
    classId: UUID = Field(..., description="Class UUID")
    sections: List[SectionDropdownItem] = Field(..., description="Sections under this class")

    class Config:
        populate_by_name = True


class SubjectDropdownItem(BaseModel):
    """Subject (for CSS indicator)."""
    subjectName: str = Field(..., description="Subject name")
    subjectId: UUID = Field(..., description="Subject UUID")

    class Config:
        populate_by_name = True


class ClassWithSectionsAndSubjectsDropdownItem(BaseModel):
    """Class with sections and subjects (indicator=CSS)."""
    className: str = Field(..., description="Class name (e.g. 1st, 2nd)")
    classId: UUID = Field(..., description="Class UUID")
    sections: List[SectionDropdownItem] = Field(..., description="Sections under this class")
    subjects: List[SubjectDropdownItem] = Field(..., description="Subjects assigned to this class for the academic year")

    class Config:
        populate_by_name = True


class TimeSlotDropdownItem(BaseModel):
    """Time slot (indicator=TS)."""
    label: str = Field(..., description="Display label, e.g. '09:00 - 09:45'")
    value: UUID = Field(..., description="Time slot UUID")

    class Config:
        populate_by_name = True
