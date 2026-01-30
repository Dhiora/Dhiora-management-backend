from fastapi import FastAPI

from app.api.v1.auth.router import router as auth_router
from app.api.v1.auth.roles_router import router as roles_router
from app.api.v1.classes.classes_router import router as classes_router
from app.api.v1.departments.department_router import router as departments_router
from app.api.v1.modules.router import router as modules_router
from app.api.v1.sections.sections_router import router as sections_router
from app.api.v1.modules.users.employee_router import router as employees_router
from app.api.v1.modules.users.student_router import router as students_router
from app.api.v1.query.query_router import router as query_router
from app.api.v1.dropdown.dropdown_router import router as dropdown_router


def create_app() -> FastAPI:
    app = FastAPI(title="Management Backend")

    # Routers
    app.include_router(auth_router)
    app.include_router(roles_router)
    app.include_router(departments_router)
    app.include_router(classes_router)
    app.include_router(sections_router)
    app.include_router(modules_router)
    app.include_router(employees_router)
    app.include_router(students_router)
    app.include_router(query_router)
    app.include_router(dropdown_router)

    return app


app = create_app()

