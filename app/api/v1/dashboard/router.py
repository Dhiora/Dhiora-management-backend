"""Dashboard API: single summary endpoint by role (admin, teacher, student, super_admin)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.db.session import get_db

from . import service

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get(
    "/summary",
    summary="Get dashboard summary",
    description=(
        "Returns role-based dashboard data. "
        "Admin: counts (students, teachers, classes, sections), daily presence, attendance trend, "
        "homework status, upcoming exams, today's timetable, fee & payroll status, alerts. "
        "Teacher: my classes, homework assigned, timetable today, upcoming exams. "
        "Student: attendance today, homework pending/submitted, fee status, timetable, exams. "
        "Super admin: platform totals (tenants, students, employees)."
    ),
)
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    data = await service.get_dashboard_summary(
        db,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        role=current_user.role,
        user_type=current_user.user_type,
        academic_year_id=current_user.academic_year_id,
    )
    return {"success": True, "data": data}
