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
