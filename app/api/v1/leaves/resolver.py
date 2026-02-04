"""
Resolve assigned_to_user_id for leave requests by tenant_type and applicant_type.
SCHOOL: student -> class teacher; employee -> admin
COLLEGE: student -> mentor; employee -> HOD
SOFTWARE: employee -> reporting manager (or admin fallback)
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.models import AcademicYear, StudentAcademicRecord, TeacherClassAssignment


def _normalize_tenant_type(organization_type: str) -> str:
    """Map tenant organization_type to SCHOOL / COLLEGE / SOFTWARE."""
    if not organization_type:
        return "SCHOOL"
    t = organization_type.strip().upper()
    if t in ("SCHOOL", "School"):
        return "SCHOOL"
    if t in ("COLLEGE", "College"):
        return "COLLEGE"
    if t in ("SOFTWARE", "Software", "IT", "TECH"):
        return "SOFTWARE"
    return t


async def resolve_leave_approver(
    db: AsyncSession,
    tenant_id: UUID,
    tenant_type: str,
    applicant_type: str,
    employee_id: Optional[UUID] = None,
    student_id: Optional[UUID] = None,
) -> Optional[UUID]:
    """
    Return user_id of the approver for this leave request.
    SCHOOL: student -> class teacher; employee -> first ADMIN
    COLLEGE: student -> first Mentor/Advisor; employee -> first HOD
    SOFTWARE: employee -> reporting_manager_id or first ADMIN
    Returns None if no approver found (caller may fall back to first user with leave_approve).
    """
    if applicant_type == "STUDENT":
        if not student_id:
            return None
        if tenant_type == "SCHOOL":
            # Class teacher for student's current class/section
            ay = await db.execute(
                select(AcademicYear.id).where(
                    AcademicYear.tenant_id == tenant_id,
                    AcademicYear.is_current.is_(True),
                )
            )
            ay_row = ay.scalar_one_or_none()
            if not ay_row:
                return None
            ay_id = ay_row
            rec = await db.execute(
                select(StudentAcademicRecord.class_id, StudentAcademicRecord.section_id).where(
                    StudentAcademicRecord.student_id == student_id,
                    StudentAcademicRecord.academic_year_id == ay_id,
                    StudentAcademicRecord.status == "ACTIVE",
                )
            )
            rec_row = rec.scalar_one_or_none()
            if not rec_row:
                return None
            class_id, section_id = rec_row.class_id, rec_row.section_id
            tca = await db.execute(
                select(TeacherClassAssignment.teacher_id).where(
                    TeacherClassAssignment.class_id == class_id,
                    TeacherClassAssignment.section_id == section_id,
                    TeacherClassAssignment.academic_year_id == ay_id,
                ).limit(1)
            )
            teacher_row = tca.scalar_one_or_none()
            return teacher_row if teacher_row else None
        if tenant_type == "COLLEGE":
            # First user with role Mentor or Advisor
            r = await db.execute(
                select(User.id).where(
                    User.tenant_id == tenant_id,
                    User.role.in_(["Mentor", "Advisor", "MENTOR", "ADVISOR"]),
                    User.status == "ACTIVE",
                ).limit(1)
            )
            row = r.scalar_one_or_none()
            return row if row else None
        # Other tenant types: no student path or fallback to first admin
        return None

    if applicant_type == "EMPLOYEE":
        if not employee_id:
            return None
        if tenant_type == "SOFTWARE":
            # Reporting manager from staff_profile
            from app.auth.models import StaffProfile
            sp = await db.execute(
                select(StaffProfile.reporting_manager_id).where(StaffProfile.user_id == employee_id)
            )
            rm = sp.scalar_one_or_none()
            if rm:
                return rm
            # Fallback: first ADMIN
        if tenant_type in ("SCHOOL", "COLLEGE", "SOFTWARE"):
            # First user with role ADMIN or SUPER_ADMIN (or HOD for COLLEGE employee)
            roles = ["ADMIN", "SUPER_ADMIN"]
            if tenant_type == "COLLEGE":
                roles = ["HOD", "ADMIN", "SUPER_ADMIN"]
            r = await db.execute(
                select(User.id).where(
                    User.tenant_id == tenant_id,
                    User.role.in_(roles),
                    User.status == "ACTIVE",
                ).limit(1)
            )
            row = r.scalar_one_or_none()
            return row if row else None
    return None
