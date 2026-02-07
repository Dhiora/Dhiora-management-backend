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
from app.api.v1.modules.users.employee_router import router as employees_router
from app.api.v1.modules.users.student_router import router as students_router
from app.api.v1.query.query_router import router as query_router
from app.api.v1.dropdown.dropdown_router import router as dropdown_router
from app.api.v1.leaves.router import router as leaves_router
from app.api.v1.subjects.router import router as subjects_router
from app.api.v1.class_subjects.router import router as class_subjects_router
from app.api.v1.timetables.router import router as timetables_router
from app.api.v1.teacher_subject_assignments.router import router as teacher_subject_assignments_router


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
    app.include_router(classes_router)
    app.include_router(sections_router)
    app.include_router(modules_router)
    app.include_router(subscription_plans_router)
    app.include_router(employees_router)
    app.include_router(students_router)
    app.include_router(query_router)
    app.include_router(dropdown_router)
    app.include_router(leaves_router)
    app.include_router(subjects_router)
    app.include_router(class_subjects_router)
    app.include_router(timetables_router)
    app.include_router(teacher_subject_assignments_router)

    return app


app = create_app()

