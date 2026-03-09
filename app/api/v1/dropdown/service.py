"""Global dropdown service: academic years, teachers, classes, and classes-with-sections."""

from typing import List, Optional, Union
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.academic_years import service as academic_years_service
from app.api.v1.classes import service as class_service
from app.api.v1.class_subjects import service as class_subjects_service
from app.api.v1.time_slots import service as time_slots_service
from app.api.v1.modules.users import service as users_service
from app.api.v1.sections import service as section_service

from .schemas import (
    AcademicYearDropdownItem,
    ClassOnlyDropdownItem,
    ClassWithSectionsDropdownItem,
    ClassWithSectionsAndSubjectsDropdownItem,
    SectionDropdownItem,
    SubjectDropdownItem,
    TeacherDropdownItem,
    EmployeeDropdownItem,
    TimeSlotDropdownItem,
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
    List[TeacherDropdownItem],
    List[EmployeeDropdownItem],
    List[ClassOnlyDropdownItem],
    List[ClassWithSectionsDropdownItem],
    List[ClassWithSectionsAndSubjectsDropdownItem],
    List[TimeSlotDropdownItem],
]:
    """
    Get dropdown data by indicator.
    - indicator=AY: list of { academicYearId, academicYearName }.
    - indicator=T: list of { teacherId, teacherName } (employees).
    - indicator=EMP: list of { label: employee name, value: employee id } (all employees).
    - indicator=C: list of { className, classId } (no sections key).
    - indicator=CS: list of { className, classId, sections: [...] } (sections for given academic year).
    - indicator=CSS: list of { className, classId, sections: [...], subjects: [...] } for given academic year.
    - indicator=TS: list of { label: 'HH:MM - HH:MM', value: slotId } for active time slots.
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

    if indicator == "T":
        employees = await users_service.list_employees(db, tenant_id)
        return [
            TeacherDropdownItem(
                teacherId=_to_uuid(emp.id),
                teacherName=emp.full_name or "",
            )
            for emp in employees
        ]

    if indicator == "EMP":
        employees = await users_service.list_employees(db, tenant_id)
        return [
            EmployeeDropdownItem(
                label=emp.full_name or "",
                value=_to_uuid(emp.id),
            )
            for emp in employees
        ]

    if indicator == "TS":
        slots = await time_slots_service.list_time_slots(db, tenant_id)
        return [
            TimeSlotDropdownItem(
                label=f"{s.start_time.strftime('%H:%M')} - {s.end_time.strftime('%H:%M')}",
                value=_to_uuid(s.id),
            )
            for s in slots
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

    if indicator == "CSS":
        result_css: List[ClassWithSectionsAndSubjectsDropdownItem] = []
        for c in classes:
            class_id = _to_uuid(c.id)
            sections_list = await section_service.list_sections(
                db, tenant_id, academic_year_id=academic_year_id, active_only=True, class_id=class_id
            )
            sections = [
                SectionDropdownItem(sectionName=s.name, sectionId=_to_uuid(s.id))
                for s in sections_list
            ]
            # Subjects for this class in this academic year
            subjects_list = await class_subjects_service.list_class_subjects(
                db, tenant_id, academic_year_id=academic_year_id, class_id=class_id
            )
            subjects = [
                SubjectDropdownItem(subjectName=cs.subject_name or "", subjectId=_to_uuid(cs.subject_id))
                for cs in subjects_list
            ]
            result_css.append(
                ClassWithSectionsAndSubjectsDropdownItem(
                    className=c.name,
                    classId=class_id,
                    sections=sections,
                    subjects=subjects,
                )
            )
        return result_css

    # C or any other: classes only (no sections key in response)
    return [
        ClassOnlyDropdownItem(className=c.name, classId=_to_uuid(c.id))
        for c in classes
    ]
