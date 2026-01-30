"""Global dropdown service: classes and classes-with-sections."""

from typing import List, Union
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.classes import service as class_service
from app.api.v1.sections import service as section_service

from .schemas import ClassOnlyDropdownItem, ClassWithSectionsDropdownItem, SectionDropdownItem


def _to_uuid(val):
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


async def get_classes_sections_dropdown(
    db: AsyncSession,
    tenant_id: UUID,
    indicator: str,
) -> Union[List[ClassOnlyDropdownItem], List[ClassWithSectionsDropdownItem]]:
    """
    Get dropdown data for classes and optionally sections.
    - indicator=C: list of { className, classId } (no sections key).
    - indicator=CS: list of { className, classId, sections: [...] }.
    """
    indicator = (indicator or "").strip().upper()
    classes = await class_service.list_classes(db, tenant_id, active_only=True)
    if indicator == "CS":
        result: List[ClassWithSectionsDropdownItem] = []
        for c in classes:
            class_id = _to_uuid(c.id)
            sections_list = await section_service.list_sections(
                db, tenant_id, active_only=True, class_id=class_id
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
