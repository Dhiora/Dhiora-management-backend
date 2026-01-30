"""
Seed script to populate core.modules and core.organization_type_modules tables.

This script:
1. Inserts all system-defined modules (HRMS and SCHOOL domains)
2. Maps all modules to organization_type = "School" with is_default=True, is_enabled=True
"""
import asyncio
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Import all models to ensure SQLAlchemy can resolve relationships
from app.auth.models import RefreshToken, User  # noqa: F401
from app.core.models import Module, OrganizationTypeModule, Tenant, TenantModule  # noqa: F401
from app.db.session import AsyncSessionLocal


# Module definitions: (module_key, module_name, module_domain, description)
HRMS_MODULES: List[Tuple[str, str, str, str]] = [
    ("USER_ROLE", "User & Role Management", "HRMS", "User and role management system"),
    ("ATTENDANCE", "Attendance Management", "HRMS", "Employee attendance tracking"),
    ("LEAVE", "Leave Management", "HRMS", "Leave request and approval management"),
    ("PAYROLL", "Payroll Management", "HRMS", "Payroll processing and management"),
    ("PAYSLIP", "Payslip Management", "HRMS", "Payslip generation and distribution"),
    ("ASSET", "Asset Management", "HRMS", "Company asset tracking and management"),
    ("HOLIDAY", "Holiday Calendar", "HRMS", "Holiday calendar and scheduling"),
]

SCHOOL_MODULES: List[Tuple[str, str, str, str]] = [
    ("STUDENT", "Student Management", "SCHOOL", "Student information and management"),
    ("ADMISSION", "Admissions Management", "SCHOOL", "Student admissions processing"),
    ("CLASS_SECTION", "Class & Section Management", "SCHOOL", "Class and section organization"),
    ("SUBJECT", "Subject Management", "SCHOOL", "Subject and curriculum management"),
    ("TIMETABLE", "Timetable Management", "SCHOOL", "Class timetable creation and management"),
    ("SCHEDULING", "Scheduling Management", "SCHOOL", "General scheduling and calendar management"),
    ("EXAM", "Exam Management", "SCHOOL", "Examination planning and management"),
    ("GRADEBOOK", "Gradebook", "SCHOOL", "Student grades and assessment tracking"),
    ("REPORT_CARD", "Report Cards", "SCHOOL", "Report card generation and distribution"),
    ("ASSIGNMENT", "Online Assignments", "SCHOOL", "Online assignment creation and submission"),
    ("HOMEWORK", "Homework Tracking", "SCHOOL", "Homework assignment and tracking"),
    ("PARENT_PORTAL", "Parent Portal", "SCHOOL", "Parent access portal for student information"),
    ("EVENT", "Event Management", "SCHOOL", "School events and activities management"),
    ("EMPLOYEE", "Employee Management (Teachers & Staff)", "SCHOOL", "Teacher and staff management"),
    ("TEACHER_TIMETABLE", "Teacher Timetable Allocation", "SCHOOL", "Teacher timetable assignment"),
    ("CLASS_ASSIGNMENT", "Subject / Class Assignment", "SCHOOL", "Subject and class assignment to teachers"),
    ("LESSON_PLANNING", "Lesson Planning", "SCHOOL", "Lesson plan creation and management"),
    ("CLASS_ATTENDANCE", "Class Attendance Management", "SCHOOL", "Student class attendance tracking"),
    ("GRADING_WORKFLOW", "Grading Workflow", "SCHOOL", "Grading and assessment workflow management"),
    ("LIBRARY", "Library Management", "SCHOOL", "Library books and resources management"),
    ("FEES", "Fee Management", "SCHOOL", "Student fee collection and management"),
    ("TRANSPORT", "Transport Tracking", "SCHOOL", "School transport and bus tracking"),
    ("CANTEEN", "Food & Canteen Management", "SCHOOL", "Canteen and food service management"),
]

ORGANIZATION_TYPE = "School"


async def seed_modules(db: AsyncSession) -> None:
    """Seed all modules and map them to organization type."""
    all_modules = HRMS_MODULES + SCHOOL_MODULES

    # Step 1: Insert or update modules in core.modules
    modules_created = 0
    modules_updated = 0

    for module_key, module_name, module_domain, description in all_modules:
        # Check if module already exists
        stmt = select(Module).where(Module.module_key == module_key)
        result = await db.execute(stmt)
        existing_module = result.scalar_one_or_none()

        if existing_module:
            # Update existing module
            existing_module.module_name = module_name
            existing_module.module_domain = module_domain
            existing_module.description = description
            existing_module.is_active = True
            modules_updated += 1
        else:
            # Create new module
            new_module = Module(
                module_key=module_key,
                module_name=module_name,
                module_domain=module_domain,
                description=description,
                is_active=True,
            )
            db.add(new_module)
            modules_created += 1

    await db.commit()

    # Step 2: Map all modules to organization_type = "School"
    org_type_mappings_created = 0
    org_type_mappings_updated = 0

    for module_key, _, _, _ in all_modules:
        # Check if mapping already exists
        stmt = select(OrganizationTypeModule).where(
            OrganizationTypeModule.organization_type == ORGANIZATION_TYPE,
            OrganizationTypeModule.module_key == module_key,
        )
        result = await db.execute(stmt)
        existing_mapping = result.scalar_one_or_none()

        if existing_mapping:
            # Update existing mapping
            existing_mapping.is_default = True
            existing_mapping.is_enabled = True
            org_type_mappings_updated += 1
        else:
            # Create new mapping
            new_mapping = OrganizationTypeModule(
                organization_type=ORGANIZATION_TYPE,
                module_key=module_key,
                is_default=True,
                is_enabled=True,
            )
            db.add(new_mapping)
            org_type_mappings_created += 1

    await db.commit()

    # Print summary
    print("=" * 60)
    print("Module Seeding Summary")
    print("=" * 60)
    print(f"Modules created: {modules_created}")
    print(f"Modules updated: {modules_updated}")
    print(f"Total modules: {len(all_modules)}")
    print()
    print(f"Organization type mappings created: {org_type_mappings_created}")
    print(f"Organization type mappings updated: {org_type_mappings_updated}")
    print(f"Organization type: {ORGANIZATION_TYPE}")
    print("=" * 60)
    print("✅ Seeding completed successfully!")


async def main() -> None:
    """Main entry point for the seed script."""
    async with AsyncSessionLocal() as db:
        try:
            await seed_modules(db)
        except Exception as e:
            print(f"❌ Error seeding modules: {e}")
            await db.rollback()
            raise


if __name__ == "__main__":
    asyncio.run(main())
