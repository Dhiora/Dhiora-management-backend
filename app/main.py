from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.academic_years.router import router as academic_years_router
from app.api.v1.admissions.router import router as admissions_router
from app.api.v1.attendance.router import router as attendance_router
from app.api.v1.homework.router import router as homework_router
from app.api.v1.auth.router import router as auth_router
from app.api.v1.auth.roles_router import router as roles_router
from app.api.v1.classes.classes_router import router as classes_router
from app.api.v1.departments.department_router import router as departments_router
from app.api.v1.modules.router import router as modules_router
from app.api.v1.sections.sections_router import router as sections_router
from app.api.v1.subscription_plans.router import router as subscription_plans_router
from app.api.v1.subscriptions.router import router as subscriptions_router
from app.api.v1.modules.users.employee_router import router as employees_router
from app.api.v1.modules.users.student_router import router as students_router
from app.api.v1.query.query_router import router as query_router
from app.api.v1.dropdown.dropdown_router import router as dropdown_router
from app.api.v1.leaves.router import router as leaves_router
from app.api.v1.assets.router import router as assets_router
from app.api.v1.subjects.router import router as subjects_router
from app.api.v1.class_subjects.router import router as class_subjects_router
from app.api.v1.timetables.router import router as timetables_router
from app.api.v1.time_slots.router import router as time_slots_router
from app.api.v1.teacher_subject_assignments.router import router as teacher_subject_assignments_router
from app.api.v1.class_teachers.router import router as class_teachers_router
from app.api.v1.schedule.class_schedule_router import router as schedule_router
from app.api.v1.exam.router import router as exam_router
from app.api.v1.fee_components.router import router as fee_components_router
from app.api.v1.fees.router import router as fees_router
from app.api.v1.transport.router import router as transport_router
from app.api.v1.ai_classroom.router import router as ai_classroom_router
from app.api.v1.ws.router import router as ws_router
from app.api.v1.holiday_calendar.router import router as holiday_calendar_router
from app.api.v1.dashboard.router import router as dashboard_router
from app.api.v1.online_assessments.router import router as online_assessments_router
from app.api.v1.test.router import router as test_router
from app.api.v1.school_profile.router import router as school_profile_router
from app.api.v1.stationary.router import router as stationary_router
from app.api.v1.super_admin.router import router as super_admin_router
from app.api.v1.public.router import router as public_router
from app.api.v1.platform_leads.router import router as platform_leads_router
from app.api.v1.grades.router import router as grades_router
from app.api.v1.parent_portal import models as parent_portal_models  # noqa: F401
from app.api.v1.parent_portal.admin_router import router as parent_admin_router
from app.api.v1.parent_portal.auth_router import router as parent_auth_router
from app.api.v1.parent_portal.parent_router import router as parent_router
from app.core.config import settings
from modules.payroll import models as payroll_models  # noqa: F401 - register payroll tables with SQLAlchemy
from modules.payroll.router import router as payroll_router


def create_app() -> FastAPI:
    app = FastAPI(title="Management Backend")

    # CORS: allow frontend to call this API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # or set specific origins, e.g. ["https://yourfrontend.com", "http://localhost:3000"]
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(auth_router)
    app.include_router(roles_router)
    app.include_router(academic_years_router)
    app.include_router(admissions_router)
    app.include_router(attendance_router)
    app.include_router(homework_router)
    app.include_router(departments_router)
    app.include_router(schedule_router)  # before classes so /{class_id}/sections/{section_id}/schedule matches
    app.include_router(classes_router)
    app.include_router(sections_router)
    app.include_router(modules_router)
    app.include_router(subscription_plans_router)
    app.include_router(subscriptions_router)
    app.include_router(employees_router)
    app.include_router(students_router)
    app.include_router(query_router)
    app.include_router(dropdown_router)
    app.include_router(leaves_router)
    app.include_router(assets_router)
    app.include_router(subjects_router)
    app.include_router(class_subjects_router)
    app.include_router(timetables_router)
    app.include_router(time_slots_router)
    app.include_router(teacher_subject_assignments_router)
    app.include_router(class_teachers_router)
    app.include_router(exam_router)
    app.include_router(grades_router)
    app.include_router(fee_components_router)
    app.include_router(fees_router)
    app.include_router(transport_router)
    app.include_router(ai_classroom_router)
    app.include_router(ws_router)
    app.include_router(holiday_calendar_router)
    app.include_router(dashboard_router)
    app.include_router(payroll_router)
    app.include_router(online_assessments_router)
    app.include_router(school_profile_router)
    app.include_router(stationary_router)
    app.include_router(super_admin_router)
    app.include_router(public_router)
    app.include_router(platform_leads_router)
    app.include_router(test_router)
    if settings.parent_portal_enabled:
        app.include_router(parent_auth_router)
        app.include_router(parent_router)
        app.include_router(parent_admin_router)

    return app


app = create_app()

