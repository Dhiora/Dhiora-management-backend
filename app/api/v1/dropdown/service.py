"""Global dropdown service: classes, classes-with-sections, and academic years."""

from typing import List, Optional, Union
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.academic_years import service as academic_years_service
from app.api.v1.classes import service as class_service
from app.api.v1.sections import service as section_service

from .schemas import (
    AcademicYearDropdownItem,
    ClassOnlyDropdownItem,
    ClassWithSectionsDropdownItem,
    SectionDropdownItem,
)


def _to_uuid(val):
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


async def get_classes_sections_dropdown(
    db: AsyncSession,
    tenant_id: UUID,
    indicator: str,
    academic_year_id: Optional[UUID] = None,
) -> Union[
    List[AcademicYearDropdownItem],
    List[ClassOnlyDropdownItem],
    List[ClassWithSectionsDropdownItem],
]:
    """
    Get dropdown data by indicator.
    - indicator=AY: list of { academicYearId, academicYearName }.
    - indicator=C: list of { className, classId } (no sections key).
    - indicator=CS: list of { className, classId, sections: [...] } (sections for given academic year).
    """
    indicator = (indicator or "").strip().upper()

    if indicator == "AY":
        years = await academic_years_service.list_academic_years(db, tenant_id, status_filter=None)
        return [
            AcademicYearDropdownItem(
                academicYearId=_to_uuid(ay.id),
                academicYearName=ay.name,
            )
            for ay in years
        ]

    classes = await class_service.list_classes(db, tenant_id, active_only=True)
    if indicator == "CS":
        result: List[ClassWithSectionsDropdownItem] = []
        for c in classes:
            class_id = _to_uuid(c.id)
            sections_list = await section_service.list_sections(
                db, tenant_id, academic_year_id=academic_year_id, active_only=True, class_id=class_id
            )
            sections = [
                SectionDropdownItem(sectionName=s.name, sectionId=_to_uuid(s.id))
                for s in sections_list
            ]
            result.append(
                ClassWithSectionsDropdownItem(
                    className=c.name,
                    classId=class_id,
                    sections=sections,
                )
            )
        return result
    # C or any other: classes only (no sections key in response)
    return [
        ClassOnlyDropdownItem(className=c.name, classId=_to_uuid(c.id))
        for c in classes
    ]
