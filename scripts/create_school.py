"""
Internal School Provisioning Script
====================================
Creates a fully provisioned school tenant in one shot:

  • Tenant (organization)
  • ALL platform modules enabled
  • "Full Access" subscription plan (created if not present)
  • ACTIVE TenantSubscription  (no Razorpay — internal only)
  • SUPER_ADMIN admin user
  • Default roles: ADMIN, TEACHER, STUDENT — each with full permissions
  • Current academic year  (e.g. 2025-2026)

Usage
-----
  python -m scripts.create_school               # interactive prompts
  python -m scripts.create_school \\
      --name "Springfield High" \\
      --email admin@springfield.edu \\
      --password s3cur3P@ss \\
      --country India \\
      --timezone "Asia/Kolkata" \\
      --short-code SFH

Run from the project root.  Requires a working DATABASE_URL in .env.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import secrets
import sys
from datetime import date, datetime, timezone
from typing import Dict, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# ── bring app into scope ──────────────────────────────────────────────────────
# All models must be imported so SQLAlchemy registers the metadata.
from app.auth.models import Role, User  # noqa: F401
from app.auth.security import hash_password
from app.core.models import (  # noqa: F401
    AcademicYear,
    Module,
    OnlineAssessment,
    SubscriptionPlan,
    Tenant,
    TenantModule,
    TenantSubscription,
)
from app.core.tenant_service import generate_organization_code_candidate
from app.db.session import AsyncSessionLocal

# ── full permissions granted to every default role ───────────────────────────
# These keys map to the `module` argument in check_permission() across all routers.
# SUPER_ADMIN bypasses all checks entirely, so this only applies to ADMIN / TEACHER / STUDENT.
ALL_PERMISSIONS: Dict[str, Dict[str, bool]] = {
    # Core platform
    "roles":                  {"create": True, "read": True, "update": True, "delete": True},
    "departments":            {"create": True, "read": True, "update": True, "delete": True},
    "academic_years":         {"create": True, "read": True, "update": True, "delete": True},
    # People
    "students":               {"create": True, "read": True, "update": True, "delete": True},
    "employees":              {"create": True, "read": True, "update": True, "delete": True},
    "admissions":             {"create": True, "read": True, "update": True, "delete": True},
    # School structure
    "classes":                {"create": True, "read": True, "update": True, "delete": True},
    "sections":               {"create": True, "read": True, "update": True, "delete": True},
    "subjects":               {"create": True, "read": True, "update": True, "delete": True},
    "timetables":             {"create": True, "read": True, "update": True, "delete": True},
    "schedules":              {"create": True, "read": True, "update": True, "delete": True},
    # Academics
    "attendance":             {"create": True, "read": True, "update": True, "delete": True},
    "exams":                  {"create": True, "read": True, "update": True, "delete": True},
    "homework":               {"create": True, "read": True, "update": True, "delete": True},
    "assessments":            {"create": True, "read": True, "update": True, "delete": True},
    # Finance & operations
    "fees":                   {"create": True, "read": True, "update": True, "delete": True},
    "transport":              {"create": True, "read": True, "update": True, "delete": True},
    "assets":                 {"create": True, "read": True, "update": True, "delete": True},
    "leaves":                 {"create": True, "read": True, "update": True, "delete": True},
    "holiday_calendar":       {"create": True, "read": True, "update": True, "delete": True},
    # AI classroom
    "ai_classroom":           {
        "create_lecture":  True,
        "read":            True,
        "update_lecture":  True,
        "delete_lecture":  True,
        "ask_doubt":       True,
    },
    # Subscriptions / plans (admin visibility)
    "subscription_plans":     {"create": True, "read": True, "update": True, "delete": True},
    "subscriptions":          {"create": True, "read": True, "update": True, "delete": True},
}

# All module_keys from seed_modules.py — every one will be enabled for the tenant.
ALL_MODULE_KEYS: List[str] = [
    # HRMS
    "USER_ROLE", "ATTENDANCE", "LEAVE", "PAYROLL", "PAYSLIP", "ASSET", "HOLIDAY",
    # School
    "STUDENT", "ADMISSION", "CLASS_SECTION", "SUBJECT", "TIMETABLE", "SCHEDULING",
    "EXAM", "GRADEBOOK", "REPORT_CARD", "ASSIGNMENT", "HOMEWORK", "PARENT_PORTAL",
    "EVENT", "EMPLOYEE", "TEACHER_TIMETABLE", "CLASS_ASSIGNMENT", "LESSON_PLANNING",
    "CLASS_ATTENDANCE", "GRADING_WORKFLOW", "LIBRARY", "FEES", "TRANSPORT", "CANTEEN",
]

FULL_ACCESS_PLAN_NAME = "Full Access (Internal)"


# ── helpers ───────────────────────────────────────────────────────────────────

def _current_ay_name() -> str:
    today = date.today()
    year = today.year if today.month >= 6 else today.year - 1
    return f"{year}-{year + 1}"


def _ay_dates() -> tuple[date, date]:
    today = date.today()
    year = today.year if today.month >= 6 else today.year - 1
    return date(year, 6, 1), date(year + 1, 5, 31)


async def _unique_org_code(db: AsyncSession, org_type: str) -> str:
    for _ in range(30):
        code = generate_organization_code_candidate(org_type)
        exists = await db.execute(
            select(Tenant.id).where(Tenant.organization_code == code)
        )
        if exists.scalar_one_or_none() is None:
            return code
    raise RuntimeError("Could not generate a unique organization code after 30 attempts.")


async def _get_or_create_full_access_plan(db: AsyncSession) -> SubscriptionPlan:
    """Return the Full Access plan, creating it if it doesn't exist yet."""
    result = await db.execute(
        select(SubscriptionPlan).where(
            SubscriptionPlan.name == FULL_ACCESS_PLAN_NAME,
            SubscriptionPlan.organization_type == "School",
        )
    )
    plan = result.scalar_one_or_none()
    if plan:
        return plan

    # Fetch all active module IDs so the plan includes them
    mod_result = await db.execute(
        select(Module.id).where(Module.is_active == True)  # noqa: E712
    )
    module_ids = [str(row[0]) for row in mod_result.all()]

    plan = SubscriptionPlan(
        name=FULL_ACCESS_PLAN_NAME,
        organization_type="School",
        modules_include=module_ids,
        price="0",
        discount_price=None,
        description="Internal full-access plan — all modules, no payment required.",
    )
    db.add(plan)
    await db.flush()
    return plan


# ── main provisioning logic ───────────────────────────────────────────────────

async def create_school(
    *,
    school_name: str,
    admin_email: str,
    admin_password: str,
    admin_name: str,
    country: str,
    timezone_name: str,
    short_code: str | None,
) -> None:
    async with AsyncSessionLocal() as db:
        # ── 0. pre-flight: check email is not already taken ───────────────────
        existing = await db.execute(
            select(User).where(User.email == admin_email)
        )
        if existing.scalar_one_or_none():
            print(f"\n[ERROR] Email '{admin_email}' is already in use. Aborting.")
            return

        print("\n── Creating school tenant …")

        # ── 1. Tenant ─────────────────────────────────────────────────────────
        org_code = await _unique_org_code(db, "School")
        org_short = short_code.strip().upper()[:10] if short_code and short_code.strip() else None

        tenant = Tenant(
            organization_code=org_code,
            organization_name=school_name,
            organization_type="School",
            country=country,
            timezone=timezone_name,
            status="ACTIVE",
            org_short_code=org_short,
        )
        db.add(tenant)
        await db.flush()  # populate tenant.id
        print(f"   Tenant           : {tenant.organization_name}  [{org_code}]")

        # ── 2. Enable ALL modules ──────────────────────────────────────────────
        # Use keys we know from the seed list; any extra active modules in DB
        # are also added automatically.
        db_mod_result = await db.execute(
            select(Module.module_key).where(Module.is_active == True)  # noqa: E712
        )
        db_module_keys = {row[0] for row in db_mod_result.all()}
        # Union of known seed keys + whatever is in the DB
        keys_to_enable = list(set(ALL_MODULE_KEYS) | db_module_keys)

        for key in keys_to_enable:
            db.add(TenantModule(tenant_id=tenant.id, module_key=key, is_enabled=True))
        print(f"   Modules enabled  : {len(keys_to_enable)}")

        # ── 3. SUPER_ADMIN user ───────────────────────────────────────────────
        admin_user = User(
            tenant_id=tenant.id,
            full_name=admin_name,
            email=admin_email,
            password_hash=hash_password(admin_password),
            role="SUPER_ADMIN",
            status="ACTIVE",
            source="SYSTEM",
            user_type=None,
        )
        db.add(admin_user)
        print(f"   Admin user       : {admin_email}  (SUPER_ADMIN)")

        # ── 4. Default roles with full permissions ────────────────────────────
        for role_name in ("ADMIN", "TEACHER", "STUDENT"):
            db.add(Role(
                tenant_id=tenant.id,
                name=role_name,
                permissions=ALL_PERMISSIONS,
            ))
        print("   Default roles    : ADMIN, TEACHER, STUDENT  (all permissions)")

        # ── 5. Full Access subscription plan (shared, created once) ───────────
        plan = await _get_or_create_full_access_plan(db)
        print(f"   Subscription plan: {plan.name}")

        # ── 6. ACTIVE TenantSubscription (no payment gateway) ─────────────────
        subscription = TenantSubscription(
            tenant_id=tenant.id,
            subscription_plan_id=plan.id,
            category="ERP",
            status="ACTIVE",
            activated_at=datetime.now(timezone.utc),
        )
        db.add(subscription)
        print("   Subscription     : ACTIVE  (ERP / Full Access)")

        # ── 7. Current academic year ──────────────────────────────────────────
        ay_name = _current_ay_name()
        start, end = _ay_dates()
        academic_year = AcademicYear(
            tenant_id=tenant.id,
            name=ay_name,
            start_date=start,
            end_date=end,
            is_current=True,
            status="ACTIVE",
            admissions_allowed=True,
        )
        db.add(academic_year)
        print(f"   Academic year    : {ay_name}  ({start} → {end})")

        # ── commit everything in one transaction ──────────────────────────────
        await db.commit()
        await db.refresh(tenant)

        print("\n✓ School provisioned successfully!")
        print("─" * 50)
        print(f"  School name      : {tenant.organization_name}")
        print(f"  Organization code: {tenant.organization_code}")
        if tenant.org_short_code:
            print(f"  Short code       : {tenant.org_short_code}")
        print(f"  Tenant ID        : {tenant.id}")
        print(f"  Admin email      : {admin_email}")
        print(f"  Admin password   : {'*' * len(admin_password)}")
        print(f"  Academic year    : {ay_name}")
        print("─" * 50)
        print("  Login at /api/v1/auth/login with the admin credentials above.")
        print()


# ── CLI ───────────────────────────────────────────────────────────────────────

def _prompt(label: str, default: str | None = None, secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    prompt_text = f"{label}{suffix}: "
    while True:
        if secret:
            value = getpass.getpass(prompt_text)
        else:
            value = input(prompt_text).strip()
        if value:
            return value
        if default:
            return default
        print(f"  ↳ '{label}' is required.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Provision a new school tenant with full access (internal use only).",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--name",      help="School / organization name")
    parser.add_argument("--email",     help="Admin email address")
    parser.add_argument("--password",  help="Admin password (min 8 chars)")
    parser.add_argument("--admin-name",help="Admin full name", default=None)
    parser.add_argument("--country",   help="Country",   default=None)
    parser.add_argument("--timezone",  help="Timezone",  default=None)
    parser.add_argument("--short-code",help="Org short code (max 10 chars, e.g. SFH)", default=None)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    print("=" * 50)
    print("  School Provisioning  —  Internal Use Only")
    print("=" * 50)
    print("  Fill in the details below. Press Enter to accept")
    print("  any default shown in [brackets].")
    print()

    school_name    = args.name       or _prompt("School name")
    admin_email    = args.email      or _prompt("Admin email")
    admin_password = args.password   or _prompt("Admin password (min 8 chars)", secret=True)
    admin_name     = args.admin_name or _prompt("Admin full name", default="School Admin")
    country        = args.country    or _prompt("Country",  default="India")
    tz             = args.timezone   or _prompt("Timezone", default="Asia/Kolkata")
    short_code     = args.short_code  # optional; no prompt if not passed

    if len(admin_password) < 8:
        print("[ERROR] Password must be at least 8 characters.")
        sys.exit(1)

    await create_school(
        school_name=school_name,
        admin_email=admin_email,
        admin_password=admin_password,
        admin_name=admin_name,
        country=country,
        timezone_name=tz,
        short_code=short_code,
    )


if __name__ == "__main__":
    asyncio.run(main())
