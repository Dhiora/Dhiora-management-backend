"""Dashboard API router – 10 widget endpoints + legacy role-based summary.

All endpoints:
  - Require a valid JWT (get_current_user)
  - Are tenant-scoped via current_user.tenant_id
  - Use Redis caching where specified
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.db.session import get_db

from . import service
from .schemas import (
    # new widget schemas
    AdminSummaryResponse,
    AttendanceTodayResponse,
    AttendanceTrendsResponse,
    DashboardAlertItem,
    FeeTermResponse,
    HomeworkStatusResponse,
    LessonProgressResponse,
    PayrollStatusResponse,
    SetupProgressResponse,
    TimetableEntryResponse,
    UpcomingExamItem,
)

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


# ── Dependency: get current tenant's academic year id ───────────────────────

def _ay(current_user: CurrentUser = Depends(get_current_user)) -> Optional[str]:
    """Extract academic_year_id from the resolved JWT user (used as sub-dep)."""
    return current_user.academic_year_id


# ════════════════════════════════════════════════════════════════════════════
#  0. FRONTEND SETUP PROGRESS
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/setup-progress",
    response_model=SetupProgressResponse,
    summary="Tenant setup progress",
    description=(
        "Returns setup completion status for school onboarding. "
        "Includes required and optional steps, completion counts, and current paused step."
    ),
)
async def get_setup_progress(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SetupProgressResponse:
    return await service.get_setup_progress(
        db,
        tenant_id=current_user.tenant_id,
        academic_year_id=current_user.academic_year_id,
    )


# ════════════════════════════════════════════════════════════════════════════
#  1. ADMIN STRUCTURED SUMMARY  (Redis cached)
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/summary",
    response_model=AdminSummaryResponse,
    summary="Dashboard summary",
    description=(
        "Returns a structured admin dashboard summary: student counts, teacher/staff counts, "
        "class & section totals, and the active academic year info.  "
        "**Cached in Redis for 5 minutes per tenant.**"
    ),
)
async def get_dashboard_summary(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AdminSummaryResponse:
    return await service.get_admin_summary(
        db,
        tenant_id=current_user.tenant_id,
        academic_year_id=current_user.academic_year_id,
    )


# ════════════════════════════════════════════════════════════════════════════
#  2. ATTENDANCE TODAY  (Redis cached)
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/attendance/today",
    response_model=AttendanceTodayResponse,
    summary="Attendance overview for today",
    description=(
        "Returns student and staff present/absent counts for today plus the number "
        "of sections that haven't marked attendance yet.  "
        "**Cached in Redis for 5 minutes per tenant.**"
    ),
)
async def get_attendance_today(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AttendanceTodayResponse:
    return await service.get_attendance_today(
        db,
        tenant_id=current_user.tenant_id,
        academic_year_id=current_user.academic_year_id,
    )


# ════════════════════════════════════════════════════════════════════════════
#  3. ATTENDANCE TRENDS
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/attendance/trends",
    response_model=AttendanceTrendsResponse,
    summary="Attendance percentage trend",
    description=(
        "Returns daily student attendance percentages for the last *days* days "
        "(default 7, max 90), an overall average, and a day-over-day change label."
    ),
)
async def get_attendance_trends(
    days: int = Query(default=7, ge=1, le=90, description="Number of past days to include"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AttendanceTrendsResponse:
    return await service.get_attendance_trends(
        db,
        tenant_id=current_user.tenant_id,
        academic_year_id=current_user.academic_year_id,
        days=days,
    )


# ════════════════════════════════════════════════════════════════════════════
#  4. HOMEWORK STATUS
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/homework",
    response_model=HomeworkStatusResponse,
    summary="Homework assignment and submission stats",
    description=(
        "Aggregates total homework assignments, completed submissions, pending count, "
        "and an integer submission rate percentage for the entire tenant."
    ),
)
async def get_homework_status(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> HomeworkStatusResponse:
    return await service.get_homework_status(db, tenant_id=current_user.tenant_id)


# ════════════════════════════════════════════════════════════════════════════
#  5. UPCOMING EXAMS
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/exams/upcoming",
    response_model=List[UpcomingExamItem],
    summary="Upcoming exam schedule",
    description=(
        "Returns the next *limit* exam schedule entries (date, title, class, subject) "
        "ordered by exam date ascending.  Only exams on or after today are included."
    ),
)
async def get_upcoming_exams(
    limit: int = Query(default=10, ge=1, le=50, description="Maximum entries to return"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[UpcomingExamItem]:
    return await service.get_upcoming_exams(db, tenant_id=current_user.tenant_id, limit=limit)


# ════════════════════════════════════════════════════════════════════════════
#  6. LESSON PROGRESS
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/lesson-progress",
    response_model=LessonProgressResponse,
    summary="Curriculum / lesson plan progress",
    description=(
        "Returns overall curriculum completion percentage and a per-grade-group breakdown "
        "for the active academic year.  Managed via the LessonPlanProgress table."
    ),
)
async def get_lesson_progress(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> LessonProgressResponse:
    return await service.get_lesson_progress(
        db,
        tenant_id=current_user.tenant_id,
        academic_year_id=current_user.academic_year_id,
    )


# ════════════════════════════════════════════════════════════════════════════
#  7. TIMETABLE TODAY
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/timetable/today",
    response_model=List[TimetableEntryResponse],
    summary="Today's timetable (tenant-wide)",
    description=(
        "Returns all timetable slots for today across all classes and sections "
        "in the active academic year, ordered by time slot."
    ),
)
async def get_timetable_today(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[TimetableEntryResponse]:
    return await service.get_timetable_today(
        db,
        tenant_id=current_user.tenant_id,
        academic_year_id=current_user.academic_year_id,
    )


# ════════════════════════════════════════════════════════════════════════════
#  8. FEE STATUS
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/fees/term",
    response_model=FeeTermResponse,
    summary="Fee collection status for the current term",
    description=(
        "Returns total fees collected, pending balance, and an integer collection-rate "
        "percentage for the active academic year."
    ),
)
async def get_fee_term_status(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> FeeTermResponse:
    return await service.get_fee_term_status(
        db,
        tenant_id=current_user.tenant_id,
        academic_year_id=current_user.academic_year_id,
    )


# ════════════════════════════════════════════════════════════════════════════
#  9. PAYROLL STATUS
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/payroll/status",
    response_model=PayrollStatusResponse,
    summary="Latest payroll run status",
    description=(
        "Returns the status of the most recent payroll run (status string, human-readable "
        "message, and the date on which salaries were disbursed)."
    ),
)
async def get_payroll_status(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PayrollStatusResponse:
    return await service.get_payroll_status(db, tenant_id=current_user.tenant_id)


# ════════════════════════════════════════════════════════════════════════════
#  10. ALERTS
# ════════════════════════════════════════════════════════════════════════════

@router.get(
    "/alerts",
    response_model=List[DashboardAlertItem],
    summary="Active dashboard alerts",
    description=(
        "Returns all active dashboard alerts for the tenant.  "
        "Includes both manually created alerts (stored in dashboard_alerts table) "
        "and auto-generated system alerts (e.g. sections missing attendance)."
    ),
)
async def get_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[DashboardAlertItem]:
    return await service.get_alerts(
        db,
        tenant_id=current_user.tenant_id,
        academic_year_id=current_user.academic_year_id,
    )
