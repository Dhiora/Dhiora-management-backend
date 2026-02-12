import asyncio
from typing import Dict, List, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.tenant_service import generate_organization_code_candidate
from app.db.session import engine


REQUIRED_TABLES: List[Tuple[str, str]] = [
    ("core", "tenants"),
    ("core", "academic_years"),
    ("core", "departments"),
    ("school", "student_academic_records"),
    ("school", "admission_requests"),
    ("school", "admission_students"),
    ("school", "audit_logs"),
    ("leave", "leave_types"),
    ("leave", "leave_requests"),
    ("leave", "leave_audit_logs"),
    ("core", "classes"),
    ("core", "sections"),
    ("core", "tenant_modules"),
    ("core", "modules"),
    ("core", "organization_type_modules"),
    ("core", "subscription_plans"),
    ("auth", "users"),
    ("auth", "refresh_tokens"),
    ("auth", "roles"),
    ("auth", "staff_profiles"),
    ("auth", "student_profiles"),
]


CREATE_SCHEMA_SQL: Dict[str, str] = {
    "core": "CREATE SCHEMA IF NOT EXISTS core;",
    "auth": "CREATE SCHEMA IF NOT EXISTS auth;",
    "school": "CREATE SCHEMA IF NOT EXISTS school;",
    "hrms": "CREATE SCHEMA IF NOT EXISTS hrms;",
    "leave": "CREATE SCHEMA IF NOT EXISTS leave;",
}


CREATE_TABLE_SQL: Dict[Tuple[str, str], str] = {
    ("core", "modules"): """
        CREATE TABLE IF NOT EXISTS core.modules (
            id UUID PRIMARY KEY,
            module_key VARCHAR(100) UNIQUE NOT NULL,
            module_name VARCHAR(255) NOT NULL,
            module_domain VARCHAR(50) NOT NULL,
            description TEXT,
            price VARCHAR(100) NOT NULL DEFAULT '0',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL
        );
    """,
    ("core", "tenants"): """
        CREATE TABLE IF NOT EXISTS core.tenants (
            id UUID PRIMARY KEY,
            organization_code VARCHAR(20) NOT NULL UNIQUE,
            org_short_code VARCHAR(10),
            organization_name VARCHAR(255) NOT NULL,
            organization_type VARCHAR(100) NOT NULL,
            country VARCHAR(100) NOT NULL,
            timezone VARCHAR(100) NOT NULL,
            status VARCHAR(20) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
    """,
    ("core", "academic_years"): """
        CREATE TABLE IF NOT EXISTS core.academic_years (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
            name VARCHAR(50) NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            is_current BOOLEAN NOT NULL DEFAULT FALSE,
            status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
            admissions_allowed BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at TIMESTAMPTZ,
            closed_by UUID,
            CONSTRAINT uq_academic_year_tenant_name UNIQUE (tenant_id, name),
            CONSTRAINT chk_academic_year_dates CHECK (end_date > start_date)
        );
    """,
    ("core", "departments"): """
        CREATE TABLE IF NOT EXISTS core.departments (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES core.tenants(id),
            code VARCHAR(20) NOT NULL,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_department_tenant_code UNIQUE (tenant_id, code),
            CONSTRAINT uq_department_tenant_name UNIQUE (tenant_id, name)
        );
    """,
    ("core", "classes"): """
        CREATE TABLE IF NOT EXISTS core.classes (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES core.tenants(id),
            name VARCHAR(50) NOT NULL,
            display_order INTEGER,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_class_tenant_name UNIQUE (tenant_id, name)
        );
    """,
    ("core", "sections"): """
        CREATE TABLE IF NOT EXISTS core.sections (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES core.tenants(id),
            class_id UUID NOT NULL REFERENCES core.classes(id),
            academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
            name VARCHAR(50) NOT NULL,
            display_order INTEGER,
            capacity INTEGER NOT NULL DEFAULT 50,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_section_class_ay_name UNIQUE (class_id, academic_year_id, name)
        );
    """,
    ("core", "subjects"): """
        CREATE TABLE IF NOT EXISTS core.subjects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            code VARCHAR(50) NOT NULL,
            display_order INTEGER,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_subject_tenant_code UNIQUE (tenant_id, code)
        );
    """,
    ("core", "tenant_modules"): """
        CREATE TABLE IF NOT EXISTS core.tenant_modules (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES core.tenants(id),
            module_key VARCHAR(100) NOT NULL REFERENCES core.modules(module_key),
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            enabled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_tenant_module UNIQUE (tenant_id, module_key)
        );
    """,
    ("core", "organization_type_modules"): """
        CREATE TABLE IF NOT EXISTS core.organization_type_modules (
            id UUID PRIMARY KEY,
            organization_type VARCHAR(100) NOT NULL,
            module_key VARCHAR(100) NOT NULL REFERENCES core.modules(module_key),
            is_default BOOLEAN NOT NULL DEFAULT FALSE,
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            CONSTRAINT uq_org_type_module UNIQUE (organization_type, module_key)
        );
    """,
    ("core", "subscription_plans"): """
        CREATE TABLE IF NOT EXISTS core.subscription_plans (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            organization_type VARCHAR(100) NOT NULL,
            modules_include JSONB NOT NULL DEFAULT '[]',
            price VARCHAR(100) NOT NULL DEFAULT '',
            discount_price VARCHAR(100),
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_subscription_plan_name_org_type UNIQUE (name, organization_type)
        );
    """,
    ("auth", "users"): """
        CREATE TABLE IF NOT EXISTS auth.users (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES core.tenants(id),
            full_name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL,
            mobile VARCHAR(50),
            password_hash TEXT NOT NULL,
            role VARCHAR(50) NOT NULL,
            role_id UUID REFERENCES auth.roles(id),
            status VARCHAR(20) NOT NULL,
            source VARCHAR(50) NOT NULL,
            user_type VARCHAR(50),
            created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_user_tenant_email UNIQUE (tenant_id, email)
        );
    """,
    ("auth", "refresh_tokens"): """
        CREATE TABLE IF NOT EXISTS auth.refresh_tokens (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES auth.users(id),
            token VARCHAR(512) NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL
        );
    """,
    ("auth", "roles"): """
        CREATE TABLE IF NOT EXISTS auth.roles (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES core.tenants(id),
            name VARCHAR(100) NOT NULL,
            permissions JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_role_tenant_name UNIQUE (tenant_id, name)
        );
    """,
    ("auth", "staff_profiles"): """
        CREATE TABLE IF NOT EXISTS auth.staff_profiles (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            employee_code VARCHAR(50),
            department_id UUID REFERENCES core.departments(id),
            designation VARCHAR(100),
            join_date DATE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_staff_profile_user UNIQUE (user_id)
        );
    """,
    ("auth", "student_profiles"): """
        CREATE TABLE IF NOT EXISTS auth.student_profiles (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            roll_number VARCHAR(50),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_student_profile_user UNIQUE (user_id)
        );
    """,
    ("auth", "teacher_referrals"): """
        CREATE TABLE IF NOT EXISTS auth.teacher_referrals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            teacher_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
            tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
            referral_code VARCHAR(20) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_teacher_referral_tenant_code UNIQUE (tenant_id, referral_code)
        );
    """,
}


ALTER_TENANT_MODULES_ENABLED_AT: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='core' AND table_name='tenant_modules' AND column_name='enabled_at') THEN
            ALTER TABLE core.tenant_modules ADD COLUMN enabled_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
        END IF;
    END $$;
"""

ALTER_USERS_USER_TYPE: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'auth' AND table_name = 'users' AND column_name = 'user_type'
        ) THEN
            ALTER TABLE auth.users ADD COLUMN user_type VARCHAR(50);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'auth' AND table_name = 'users' AND column_name = 'role_id'
        ) THEN
            ALTER TABLE auth.users ADD COLUMN role_id UUID REFERENCES auth.roles(id);
        END IF;
    END $$;
"""

# Add organization_code to tenants (public identifier; tenant_id remains PK and only FK target)
ALTER_TENANTS_ORGANIZATION_CODE: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'core' AND table_name = 'tenants' AND column_name = 'organization_code'
        ) THEN
            ALTER TABLE core.tenants ADD COLUMN organization_code VARCHAR(20);
        END IF;
    END $$;
"""

# After backfill: set NOT NULL and add UNIQUE constraint
ALTER_TENANTS_ORGANIZATION_CODE_NOT_NULL: str = """
    DO $$
    BEGIN
        ALTER TABLE core.tenants ALTER COLUMN organization_code SET NOT NULL;
    EXCEPTION
        WHEN others THEN NULL;
    END $$;
"""

ALTER_TENANTS_ORGANIZATION_CODE_UNIQUE: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE n.nspname = 'core' AND t.relname = 'tenants' AND c.conname = 'uq_tenants_organization_code'
        ) THEN
            ALTER TABLE core.tenants ADD CONSTRAINT uq_tenants_organization_code UNIQUE (organization_code);
        END IF;
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END $$;
"""

# Add org_short_code to tenants (optional; for identification e.g. employee numbers)
ALTER_TENANTS_ORG_SHORT_CODE: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'core' AND table_name = 'tenants' AND column_name = 'org_short_code'
        ) THEN
            ALTER TABLE core.tenants ADD COLUMN org_short_code VARCHAR(10);
        END IF;
    END $$;
"""

# Add employee_code to staff_profiles (auto-generated employee code; identification only)
ALTER_STAFF_PROFILES_EMPLOYEE_CODE: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'auth' AND table_name = 'staff_profiles' AND column_name = 'employee_code'
        ) THEN
            ALTER TABLE auth.staff_profiles ADD COLUMN employee_code VARCHAR(50);
        END IF;
    END $$;
"""

ALTER_STAFF_PROFILES_DEPARTMENT_ID: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'auth' AND table_name = 'staff_profiles' AND column_name = 'department_id'
        ) THEN
            ALTER TABLE auth.staff_profiles ADD COLUMN department_id UUID REFERENCES core.departments(id);
        END IF;
    END $$;
"""

# Leave module: reporting manager for SOFTWARE tenant type (employee leave approver)
ALTER_STAFF_PROFILES_REPORTING_MANAGER: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'auth' AND table_name = 'staff_profiles' AND column_name = 'reporting_manager_id'
        ) THEN
            ALTER TABLE auth.staff_profiles ADD COLUMN reporting_manager_id UUID REFERENCES auth.users(id) ON DELETE SET NULL;
        END IF;
    END $$;
"""

ALTER_STUDENT_PROFILES_CLASS_SECTION: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'auth' AND table_name = 'student_profiles' AND column_name = 'class_id'
        ) THEN
            ALTER TABLE auth.student_profiles ADD COLUMN class_id UUID REFERENCES core.classes(id);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'auth' AND table_name = 'student_profiles' AND column_name = 'section_id'
        ) THEN
            ALTER TABLE auth.student_profiles ADD COLUMN section_id UUID REFERENCES core.sections(id);
        END IF;
    END $$;
"""

# Sections: add class_id for existing DBs (nullable so existing rows remain valid)
ALTER_SECTIONS_CLASS_ID: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'core' AND table_name = 'sections' AND column_name = 'class_id'
        ) THEN
            ALTER TABLE core.sections ADD COLUMN class_id UUID REFERENCES core.classes(id);
        END IF;
    END $$;
"""

# Sections: switch unique from (tenant_id, name) to (class_id, name) so same section name is allowed per class
ALTER_SECTIONS_DROP_OLD_UNIQUE: str = """
    ALTER TABLE core.sections DROP CONSTRAINT IF EXISTS uq_section_tenant_name;
"""

ALTER_SECTIONS_ADD_CLASS_NAME_UNIQUE: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_section_class_name'
              AND conrelid = 'core.sections'::regclass
        ) THEN
            ALTER TABLE core.sections ADD CONSTRAINT uq_section_class_name UNIQUE (class_id, name);
        END IF;
    END $$;
"""

# Add capacity to core.sections (default 50 per section; backfill existing rows to 50)
ALTER_SECTIONS_CAPACITY: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'core' AND table_name = 'sections' AND column_name = 'capacity'
        ) THEN
            ALTER TABLE core.sections ADD COLUMN capacity INTEGER NOT NULL DEFAULT 50;
        END IF;
    END $$;
"""

# Sections: add academic_year_id (sections are per class per academic year; copy to new year when year ends)
ALTER_SECTIONS_ACADEMIC_YEAR_ID: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'core' AND table_name = 'sections' AND column_name = 'academic_year_id'
        ) THEN
            ALTER TABLE core.sections ADD COLUMN academic_year_id UUID REFERENCES core.academic_years(id) ON DELETE RESTRICT;
        END IF;
    END $$;
"""

# Backfill academic_year_id: set to tenant's current academic year (or first by start_date) for existing sections
ALTER_SECTIONS_BACKFILL_ACADEMIC_YEAR: str = """
    UPDATE core.sections s
    SET academic_year_id = (
        SELECT ay.id FROM core.academic_years ay
        WHERE ay.tenant_id = s.tenant_id
        ORDER BY ay.is_current DESC NULLS LAST, ay.start_date DESC
        LIMIT 1
    )
    WHERE s.academic_year_id IS NULL;
"""

# Switch unique from (class_id, name) to (class_id, academic_year_id, name)
ALTER_SECTIONS_DROP_CLASS_NAME_UNIQUE: str = """
    ALTER TABLE core.sections DROP CONSTRAINT IF EXISTS uq_section_class_name;
"""
ALTER_SECTIONS_ADD_CLASS_AY_NAME_UNIQUE: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'uq_section_class_ay_name'
              AND conrelid = 'core.sections'::regclass
        ) THEN
            ALTER TABLE core.sections ADD CONSTRAINT uq_section_class_ay_name UNIQUE (class_id, academic_year_id, name);
        END IF;
    END $$;
"""

# Add price column to core.modules (for existing DBs)
ALTER_MODULES_PRICE: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'core' AND table_name = 'modules' AND column_name = 'price'
        ) THEN
            ALTER TABLE core.modules ADD COLUMN price VARCHAR(100) NOT NULL DEFAULT '0';
        END IF;
    END $$;
"""

# Random prices for backfilling existing modules (will be updated later)
MODULE_BACKFILL_PRICES: tuple = (
    "9", "19", "29", "49", "79", "99", "129", "199", "49", "79", "29", "99",
    "59", "39", "149", "69", "89", "109", "19", "249",
)

# Add organization_type to core.subscription_plans (for existing DBs)
ALTER_SUBSCRIPTION_PLANS_ORGANIZATION_TYPE: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'core' AND table_name = 'subscription_plans' AND column_name = 'organization_type'
        ) THEN
            ALTER TABLE core.subscription_plans ADD COLUMN organization_type VARCHAR(100) NOT NULL DEFAULT 'School';
        END IF;
    END $$;
"""
ALTER_SUBSCRIPTION_PLANS_DROP_OLD_UNIQUE: str = """
    ALTER TABLE core.subscription_plans DROP CONSTRAINT IF EXISTS subscription_plans_name_key;
"""
ALTER_SUBSCRIPTION_PLANS_ADD_NAME_ORG_UNIQUE: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE n.nspname = 'core' AND t.relname = 'subscription_plans' AND c.conname = 'uq_subscription_plan_name_org_type'
        ) THEN
            ALTER TABLE core.subscription_plans ADD CONSTRAINT uq_subscription_plan_name_org_type UNIQUE (name, organization_type);
        END IF;
    EXCEPTION
        WHEN duplicate_object THEN NULL;
    END $$;
"""

# Only one academic year per tenant can have is_current = true
CREATE_INDEX_ACADEMIC_YEAR_CURRENT: str = """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_current_academic_year
    ON core.academic_years (tenant_id) WHERE (is_current = true);
"""

# Add admissions_allowed, closed_at, closed_by to core.academic_years (for existing DBs)
ALTER_ACADEMIC_YEARS_EXTRA: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'core' AND table_name = 'academic_years' AND column_name = 'admissions_allowed'
        ) THEN
            ALTER TABLE core.academic_years ADD COLUMN admissions_allowed BOOLEAN NOT NULL DEFAULT TRUE;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'core' AND table_name = 'academic_years' AND column_name = 'closed_at'
        ) THEN
            ALTER TABLE core.academic_years ADD COLUMN closed_at TIMESTAMPTZ;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'core' AND table_name = 'academic_years' AND column_name = 'closed_by'
        ) THEN
            ALTER TABLE core.academic_years ADD COLUMN closed_by UUID;
        END IF;
    END $$;
"""
# Add FK for closed_by (runs after auth.users exists)
ALTER_ACADEMIC_YEARS_CLOSED_BY_FK: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE n.nspname = 'core' AND t.relname = 'academic_years' AND c.conname = 'fk_academic_years_closed_by'
        ) THEN
            ALTER TABLE core.academic_years ADD CONSTRAINT fk_academic_years_closed_by
            FOREIGN KEY (closed_by) REFERENCES auth.users(id) ON DELETE SET NULL;
        END IF;
    EXCEPTION
        WHEN others THEN NULL;
    END $$;
"""

# school.student_academic_records - student per academic year (promotion-safe)
STUDENT_ACADEMIC_RECORDS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.student_academic_records (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        student_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        class_id UUID NOT NULL REFERENCES core.classes(id),
        section_id UUID NOT NULL REFERENCES core.sections(id),
        roll_number VARCHAR(50),
        status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_student_academic_year UNIQUE (student_id, academic_year_id)
    );
"""

# school.referral_usage - teacher-referred students (immutable after admission)
REFERRAL_USAGE_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.referral_usage (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        referral_code VARCHAR(20) NOT NULL,
        teacher_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
        student_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        admission_id UUID NOT NULL REFERENCES school.student_academic_records(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_referral_usage_student UNIQUE (student_id),
        CONSTRAINT uq_referral_usage_admission UNIQUE (admission_id)
    );
"""

# school.teacher_class_assignments - which teacher teaches which class-section (for attendance scope)
TEACHER_CLASS_ASSIGNMENTS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.teacher_class_assignments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        teacher_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        class_id UUID NOT NULL REFERENCES core.classes(id),
        section_id UUID NOT NULL REFERENCES core.sections(id),
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_teacher_class_section_year UNIQUE (teacher_id, class_id, section_id, academic_year_id)
    );
"""

# school.student_attendance - one per student per day per academic year
STUDENT_ATTENDANCE_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.student_attendance (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        student_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        date DATE NOT NULL,
        status VARCHAR(20) NOT NULL,
        marked_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_student_attendance_day UNIQUE (student_id, academic_year_id, date),
        CONSTRAINT chk_student_attendance_status CHECK (status IN ('PRESENT', 'ABSENT', 'LATE', 'HALF_DAY'))
    );
"""

# ----- Daily + Subject Override Attendance -----
# school.student_daily_attendance - one per class/section/date (master)
STUDENT_DAILY_ATTENDANCE_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.student_daily_attendance (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        class_id UUID NOT NULL REFERENCES core.classes(id),
        section_id UUID NOT NULL REFERENCES core.sections(id),
        attendance_date DATE NOT NULL,
        marked_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
        status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_daily_attendance_class_section_date UNIQUE (academic_year_id, class_id, section_id, attendance_date),
        CONSTRAINT chk_daily_attendance_status CHECK (status IN ('DRAFT', 'SUBMITTED', 'LOCKED'))
    );
"""
# school.student_daily_attendance_records - one per student per daily master
STUDENT_DAILY_ATTENDANCE_RECORDS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.student_daily_attendance_records (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        daily_attendance_id UUID NOT NULL REFERENCES school.student_daily_attendance(id) ON DELETE CASCADE,
        student_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        status VARCHAR(20) NOT NULL,
        CONSTRAINT uq_daily_record_student UNIQUE (daily_attendance_id, student_id),
        CONSTRAINT chk_daily_record_status CHECK (status IN ('PRESENT', 'ABSENT', 'LATE', 'HALF_DAY', 'LEAVE'))
    );
"""
# school.student_subject_attendance_overrides - subject override per student per daily master (subject_id → school.subjects)
STUDENT_SUBJECT_ATTENDANCE_OVERRIDES_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.student_subject_attendance_overrides (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        daily_attendance_id UUID NOT NULL REFERENCES school.student_daily_attendance(id) ON DELETE CASCADE,
        subject_id UUID NOT NULL REFERENCES school.subjects(id) ON DELETE CASCADE,
        student_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        override_status VARCHAR(20) NOT NULL,
        reason TEXT,
        marked_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_subject_override_daily_subject_student UNIQUE (daily_attendance_id, subject_id, student_id),
        CONSTRAINT chk_override_status CHECK (override_status IN ('PRESENT', 'ABSENT', 'LATE', 'HALF_DAY', 'LEAVE'))
    );
"""

# Add subject_id to teacher_class_assignments (nullable; for subject-wise override scope)
ALTER_TEACHER_CLASS_ASSIGNMENTS_SUBJECT_ID: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'school' AND table_name = 'teacher_class_assignments' AND column_name = 'subject_id'
        ) THEN
            ALTER TABLE school.teacher_class_assignments ADD COLUMN subject_id UUID REFERENCES core.subjects(id) ON DELETE CASCADE;
        END IF;
    END $$;
"""
# Optional: unique including subject_id (allows same teacher/class/section/year for multiple subjects)
ALTER_TEACHER_CLASS_ASSIGNMENTS_UNIQUE_WITH_SUBJECT: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE n.nspname = 'school' AND t.relname = 'teacher_class_assignments' AND c.conname = 'uq_teacher_class_section_year_subject'
        ) THEN
            ALTER TABLE school.teacher_class_assignments DROP CONSTRAINT IF EXISTS uq_teacher_class_section_year;
            ALTER TABLE school.teacher_class_assignments ADD CONSTRAINT uq_teacher_class_section_year_subject
                UNIQUE (teacher_id, class_id, section_id, academic_year_id, subject_id);
        END IF;
    EXCEPTION
        WHEN others THEN NULL;
    END $$;
"""

# ----- Dhiora: school.subjects (year-agnostic, department_id → core.departments), class_subjects, teacher_subject_assignments, timetables -----
SCHOOL_SUBJECTS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.subjects (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        department_id UUID NOT NULL REFERENCES core.departments(id) ON DELETE RESTRICT,
        name VARCHAR(255) NOT NULL,
        code VARCHAR(50) NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        display_order INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_school_subject_tenant_dept_code UNIQUE (tenant_id, department_id, code)
    );
"""
# Migrate subject uniqueness from (tenant_id, code) to (tenant_id, department_id, code)
ALTER_SUBJECTS_UNIQUE_TENANT_DEPT_CODE: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'school' AND table_name = 'subjects') THEN
            RETURN;
        END IF;
        ALTER TABLE school.subjects DROP CONSTRAINT IF EXISTS uq_school_subject_tenant_code;
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE n.nspname = 'school' AND t.relname = 'subjects' AND c.conname = 'uq_school_subject_tenant_dept_code'
        ) THEN
            ALTER TABLE school.subjects ADD CONSTRAINT uq_school_subject_tenant_dept_code
                UNIQUE (tenant_id, department_id, code);
        END IF;
    EXCEPTION
        WHEN others THEN NULL;
    END $$;
"""
# For existing DBs: ensure school.subjects.department_id references core.departments(id).
# Drop all possible FK names (school_subjects_*, subjects_*) then add correct one to core.departments.
ALTER_SUBJECTS_DEPARTMENT_TO_CORE: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'school' AND table_name = 'subjects') THEN
            RETURN;
        END IF;
        ALTER TABLE school.subjects DROP CONSTRAINT IF EXISTS school_subjects_department_id_fkey;
        ALTER TABLE school.subjects DROP CONSTRAINT IF EXISTS subjects_department_id_fkey;
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE n.nspname = 'school' AND t.relname = 'subjects'
              AND c.conname = 'fk_school_subjects_department_core'
        ) THEN
            ALTER TABLE school.subjects
                ADD CONSTRAINT fk_school_subjects_department_core FOREIGN KEY (department_id) REFERENCES core.departments(id) ON DELETE RESTRICT;
        END IF;
    EXCEPTION
        WHEN others THEN NULL;
    END $$;
"""
CLASS_SUBJECTS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.class_subjects (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        class_id UUID NOT NULL REFERENCES core.classes(id),
        subject_id UUID NOT NULL REFERENCES school.subjects(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_class_subjects_ay_class_subject UNIQUE (academic_year_id, class_id, subject_id)
    );
"""
TEACHER_SUBJECT_ASSIGNMENTS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.teacher_subject_assignments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE CASCADE,
        teacher_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        class_id UUID NOT NULL REFERENCES core.classes(id),
        section_id UUID NOT NULL REFERENCES core.sections(id),
        subject_id UUID NOT NULL REFERENCES school.subjects(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_teacher_subject_assignment UNIQUE (academic_year_id, teacher_id, class_id, section_id, subject_id)
    );
"""
TIMETABLES_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.timetables (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        class_id UUID NOT NULL REFERENCES core.classes(id),
        section_id UUID NOT NULL REFERENCES core.sections(id),
        subject_id UUID NOT NULL REFERENCES school.subjects(id) ON DELETE CASCADE,
        teacher_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
        day_of_week INTEGER NOT NULL,
        start_time TIME NOT NULL,
        end_time TIME NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_timetable_day_of_week CHECK (day_of_week >= 0 AND day_of_week <= 6)
    );
"""

# Class Teacher Assignment: ONE teacher per class-section per academic year (attendance finalization, leave, etc.)
CLASS_TEACHER_ASSIGNMENTS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.class_teacher_assignments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE CASCADE,
        class_id UUID NOT NULL REFERENCES core.classes(id),
        section_id UUID NOT NULL REFERENCES core.sections(id),
        teacher_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_class_teacher_assignment UNIQUE (academic_year_id, class_id, section_id)
    );
"""

# Overrides: ensure FK to school.subjects. For existing DBs that had FK to core.subjects, drop and re-add.
ALTER_OVERRIDES_FK_TO_SCHOOL_SUBJECTS: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'school' AND table_name = 'subjects') THEN
            RETURN;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'school' AND table_name = 'student_subject_attendance_overrides') THEN
            RETURN;
        END IF;
        ALTER TABLE school.student_subject_attendance_overrides DROP CONSTRAINT IF EXISTS student_subject_attendance_overrides_subject_id_fkey;
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE n.nspname = 'school' AND t.relname = 'student_subject_attendance_overrides'
              AND c.conname = 'fk_overrides_school_subject'
        ) THEN
            ALTER TABLE school.student_subject_attendance_overrides
                ADD CONSTRAINT fk_overrides_school_subject FOREIGN KEY (subject_id) REFERENCES school.subjects(id) ON DELETE CASCADE;
        END IF;
    EXCEPTION
        WHEN others THEN NULL;
    END $$;
"""

# ----- Homework Management -----
HOMEWORKS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.homeworks (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        teacher_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        title VARCHAR(255) NOT NULL,
        description TEXT,
        status VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
        time_mode VARCHAR(20) NOT NULL DEFAULT 'NO_TIME',
        total_time_minutes INTEGER,
        per_question_time_seconds INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_homework_status CHECK (status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')),
        CONSTRAINT chk_homework_time_mode CHECK (time_mode IN ('NO_TIME', 'TOTAL_TIME', 'PER_QUESTION'))
    );
"""

HOMEWORK_QUESTIONS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.homework_questions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        homework_id UUID NOT NULL REFERENCES school.homeworks(id) ON DELETE CASCADE,
        question_text TEXT NOT NULL,
        question_type VARCHAR(20) NOT NULL,
        options JSONB,
        correct_answer JSONB,
        hints JSONB NOT NULL DEFAULT '[]',
        display_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_question_type CHECK (question_type IN ('MCQ', 'FILL_IN_BLANK', 'SHORT_ANSWER', 'LONG_ANSWER', 'MULTI_CHECK'))
    );
"""

# Alter existing homework_questions to support new question types (if table exists with old constraint)
ALTER_HOMEWORK_QUESTIONS_QUESTION_TYPES: str = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='school' AND table_name='homework_questions') THEN
            ALTER TABLE school.homework_questions DROP CONSTRAINT IF EXISTS chk_question_type;
            ALTER TABLE school.homework_questions ADD CONSTRAINT chk_question_type CHECK (question_type IN ('MCQ', 'FILL_IN_BLANK', 'SHORT_ANSWER', 'LONG_ANSWER', 'MULTI_CHECK'));
        END IF;
    EXCEPTION
        WHEN others THEN NULL;  -- Ignore if constraint already correct
    END $$;
"""

HOMEWORK_ASSIGNMENTS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.homework_assignments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        homework_id UUID NOT NULL REFERENCES school.homeworks(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        class_id UUID NOT NULL REFERENCES core.classes(id),
        section_id UUID REFERENCES core.sections(id),
        subject_id UUID NOT NULL REFERENCES school.subjects(id) ON DELETE RESTRICT,
        due_date TIMESTAMPTZ NOT NULL,
        assigned_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
"""
# Existing DBs: add subject_id if missing (nullable first for backfill; app requires it on create)
ALTER_HOMEWORK_ASSIGNMENTS_SUBJECT_ID: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'school'
              AND table_name = 'homework_assignments'
              AND column_name = 'subject_id'
        ) THEN
            ALTER TABLE school.homework_assignments
            ADD COLUMN subject_id UUID REFERENCES school.subjects(id) ON DELETE RESTRICT;
        END IF;
    END $$;
"""
# Optional: make subject_id NOT NULL after backfill (skip if you have existing rows with NULL)
# Here we do not force NOT NULL so existing rows are not broken; new assignments require subject_id in app.
IX_HOMEWORK_ASSIGNMENTS_SUBJECT_ID: str = """
    CREATE INDEX IF NOT EXISTS ix_homework_assignments_subject_id ON school.homework_assignments(subject_id);
"""
UQ_HOMEWORK_ASSIGNMENT_CONTEXT: str = """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            WHERE n.nspname = 'school' AND t.relname = 'homework_assignments'
              AND c.conname = 'uq_homework_assignment_context'
        ) THEN
            ALTER TABLE school.homework_assignments
            ADD CONSTRAINT uq_homework_assignment_context
            UNIQUE (homework_id, academic_year_id, class_id, section_id, subject_id);
        END IF;
    EXCEPTION
        WHEN others THEN NULL;
    END $$;
"""

HOMEWORK_ATTEMPTS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.homework_attempts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        homework_assignment_id UUID NOT NULL REFERENCES school.homework_assignments(id) ON DELETE CASCADE,
        student_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        attempt_number INTEGER NOT NULL DEFAULT 1,
        restart_reason TEXT,
        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
"""

HOMEWORK_SUBMISSIONS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.homework_submissions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        homework_assignment_id UUID NOT NULL REFERENCES school.homework_assignments(id) ON DELETE CASCADE,
        student_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        attempt_id UUID NOT NULL REFERENCES school.homework_attempts(id) ON DELETE CASCADE,
        answers JSONB NOT NULL DEFAULT '{}',
        submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_submission_per_attempt UNIQUE (attempt_id)
    );
"""

HOMEWORK_HINT_USAGE_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.homework_hint_usage (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        homework_question_id UUID NOT NULL REFERENCES school.homework_questions(id) ON DELETE CASCADE,
        homework_attempt_id UUID NOT NULL REFERENCES school.homework_attempts(id) ON DELETE CASCADE,
        student_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        hint_index INTEGER NOT NULL,
        viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
"""

# ----- Admission Management -----
# school.admission_requests - TRACK immutable, STATUS mutable; approval creates admission_student
ADMISSION_REQUESTS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.admission_requests (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        student_name VARCHAR(255) NOT NULL,
        parent_name VARCHAR(255),
        mobile VARCHAR(50),
        email VARCHAR(255),
        class_applied_for UUID NOT NULL REFERENCES core.classes(id),
        section_applied_for UUID REFERENCES core.sections(id),
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        track VARCHAR(50) NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'PENDING_APPROVAL',
        raised_by_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
        raised_by_role VARCHAR(50),
        referral_teacher_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
        approved_by_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
        approved_by_role VARCHAR(50),
        approved_at TIMESTAMPTZ,
        remarks TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
"""
# school.admission_students - created on approval; INACTIVE until activate (user + academic record)
ADMISSION_STUDENTS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.admission_students (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        admission_request_id UUID NOT NULL REFERENCES school.admission_requests(id) ON DELETE RESTRICT UNIQUE,
        user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL UNIQUE,
        student_name VARCHAR(255) NOT NULL,
        parent_name VARCHAR(255),
        mobile VARCHAR(50),
        email VARCHAR(255),
        class_id UUID NOT NULL REFERENCES core.classes(id),
        section_id UUID NOT NULL REFERENCES core.sections(id),
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        track VARCHAR(50) NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'INACTIVE',
        joined_date DATE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
"""
# school.audit_logs - state changes for admission/student
AUDIT_LOGS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.audit_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        entity_type VARCHAR(50) NOT NULL,
        entity_id UUID NOT NULL,
        track VARCHAR(50),
        from_status VARCHAR(50),
        to_status VARCHAR(50),
        action VARCHAR(100) NOT NULL,
        performed_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
        performed_by_role VARCHAR(50),
        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        remarks TEXT
    );
"""

# hrms.employee_attendance - one per employee per day
EMPLOYEE_ATTENDANCE_TABLE: str = """
    CREATE TABLE IF NOT EXISTS hrms.employee_attendance (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        employee_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        date DATE NOT NULL,
        status VARCHAR(20) NOT NULL,
        marked_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_employee_attendance_day UNIQUE (employee_id, date),
        CONSTRAINT chk_employee_attendance_status CHECK (status IN ('PRESENT', 'ABSENT', 'LATE', 'HALF_DAY', 'LEAVE'))
    );
"""

# ----- Global Leave Management -----
LEAVE_TYPES_TABLE: str = """
    CREATE TABLE IF NOT EXISTS leave.leave_types (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        name VARCHAR(100) NOT NULL,
        code VARCHAR(50) NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_leave_type_tenant_code UNIQUE (tenant_id, code)
    );
"""
LEAVE_REQUESTS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS leave.leave_requests (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        tenant_type VARCHAR(50) NOT NULL,
        applicant_type VARCHAR(50) NOT NULL,
        employee_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
        student_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
        leave_type_id UUID REFERENCES leave.leave_types(id) ON DELETE SET NULL,
        custom_reason TEXT,
        from_date DATE NOT NULL,
        to_date DATE NOT NULL,
        total_days INTEGER NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
        assigned_to_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
        approved_by_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
        approved_at TIMESTAMPTZ,
        created_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_leave_request_status CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
        CONSTRAINT chk_leave_applicant CHECK (
            (applicant_type = 'EMPLOYEE' AND employee_id IS NOT NULL AND student_id IS NULL) OR
            (applicant_type = 'STUDENT' AND student_id IS NOT NULL AND employee_id IS NULL)
        )
    );
"""
LEAVE_AUDIT_LOGS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS leave.leave_audit_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        leave_request_id UUID NOT NULL REFERENCES leave.leave_requests(id) ON DELETE CASCADE,
        action VARCHAR(50) NOT NULL,
        performed_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE SET NULL,
        performed_by_role VARCHAR(50),
        remarks TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
"""

# ----- Fee Management -----
FEE_COMPONENTS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.fee_components (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        name VARCHAR(100) NOT NULL,
        code VARCHAR(50) NOT NULL,
        description TEXT,
        component_category VARCHAR(50) NOT NULL,
        allow_discount BOOLEAN NOT NULL DEFAULT TRUE,
        is_mandatory_default BOOLEAN NOT NULL DEFAULT TRUE,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_fee_component_tenant_code UNIQUE (tenant_id, code),
        CONSTRAINT chk_fee_component_category CHECK (component_category IN ('ACADEMIC','TRANSPORT','HOSTEL','OTHER'))
    );
"""

ALTER_FEE_COMPONENTS_CATEGORY_CHECK: str = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='school' AND table_name='fee_components') THEN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                JOIN pg_namespace n ON t.relnamespace = n.oid
                WHERE n.nspname = 'school'
                  AND t.relname = 'fee_components'
                  AND c.conname = 'chk_fee_component_category'
            ) THEN
                ALTER TABLE school.fee_components
                ADD CONSTRAINT chk_fee_component_category
                CHECK (component_category IN ('ACADEMIC','TRANSPORT','HOSTEL','OTHER'));
            END IF;
        END IF;
    EXCEPTION
        WHEN others THEN NULL;
    END $$;
"""

CLASS_FEE_STRUCTURES_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.class_fee_structures (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        class_id UUID NOT NULL REFERENCES core.classes(id) ON DELETE CASCADE,
        fee_component_id UUID NOT NULL REFERENCES school.fee_components(id) ON DELETE RESTRICT,
        amount NUMERIC(12, 2) NOT NULL,
        frequency VARCHAR(30) NOT NULL,
        due_date DATE,
        is_mandatory BOOLEAN NOT NULL DEFAULT TRUE,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_class_fee_structure_ay_class_component UNIQUE (academic_year_id, class_id, fee_component_id)
    );
"""

STUDENT_FEE_ASSIGNMENTS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.student_fee_assignments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        student_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
        source_type VARCHAR(20) NOT NULL DEFAULT 'TEMPLATE',
        class_fee_structure_id UUID REFERENCES school.class_fee_structures(id) ON DELETE RESTRICT,
        custom_name VARCHAR(255),
        base_amount NUMERIC(12, 2) NOT NULL,
        total_discount NUMERIC(12, 2) NOT NULL DEFAULT 0,
        final_amount NUMERIC(12, 2) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'unpaid',
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT chk_student_fee_assignment_source_type CHECK (source_type IN ('TEMPLATE','CUSTOM')),
        CONSTRAINT chk_student_fee_assignment_source_fields CHECK (
            (source_type = 'TEMPLATE' AND class_fee_structure_id IS NOT NULL AND custom_name IS NULL)
            OR
            (source_type = 'CUSTOM' AND class_fee_structure_id IS NULL AND custom_name IS NOT NULL)
        ),
        CONSTRAINT chk_student_fee_assignment_status CHECK (status IN ('unpaid','partial','paid'))
    );
"""

ALTER_STUDENT_FEE_ASSIGNMENTS_UPGRADE: str = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='school' AND table_name='student_fee_assignments') THEN
            -- Add new columns (idempotent)
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='school' AND table_name='student_fee_assignments' AND column_name='source_type'
            ) THEN
                ALTER TABLE school.student_fee_assignments ADD COLUMN source_type VARCHAR(20) NOT NULL DEFAULT 'TEMPLATE';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='school' AND table_name='student_fee_assignments' AND column_name='custom_name'
            ) THEN
                ALTER TABLE school.student_fee_assignments ADD COLUMN custom_name VARCHAR(255);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='school' AND table_name='student_fee_assignments' AND column_name='base_amount'
            ) THEN
                ALTER TABLE school.student_fee_assignments ADD COLUMN base_amount NUMERIC(12, 2);
                -- Backfill base_amount from legacy original_amount if present
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='school' AND table_name='student_fee_assignments' AND column_name='original_amount'
                ) THEN
                    UPDATE school.student_fee_assignments SET base_amount = original_amount WHERE base_amount IS NULL;
                END IF;
                -- Ensure not-null if possible (skip if existing rows still null)
                BEGIN
                    ALTER TABLE school.student_fee_assignments ALTER COLUMN base_amount SET NOT NULL;
                EXCEPTION WHEN others THEN NULL;
                END;
            END IF;
            -- class_fee_structure_id: allow NULL for CUSTOM
            BEGIN
                ALTER TABLE school.student_fee_assignments ALTER COLUMN class_fee_structure_id DROP NOT NULL;
            EXCEPTION WHEN others THEN NULL;
            END;

            -- Add constraints if missing
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                JOIN pg_namespace n ON t.relnamespace = n.oid
                WHERE n.nspname = 'school' AND t.relname = 'student_fee_assignments'
                  AND c.conname = 'chk_student_fee_assignment_source_type'
            ) THEN
                ALTER TABLE school.student_fee_assignments
                ADD CONSTRAINT chk_student_fee_assignment_source_type CHECK (source_type IN ('TEMPLATE','CUSTOM'));
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                JOIN pg_namespace n ON t.relnamespace = n.oid
                WHERE n.nspname = 'school' AND t.relname = 'student_fee_assignments'
                  AND c.conname = 'chk_student_fee_assignment_source_fields'
            ) THEN
                ALTER TABLE school.student_fee_assignments
                ADD CONSTRAINT chk_student_fee_assignment_source_fields CHECK (
                    (source_type = 'TEMPLATE' AND class_fee_structure_id IS NOT NULL AND custom_name IS NULL)
                    OR
                    (source_type = 'CUSTOM' AND class_fee_structure_id IS NULL AND custom_name IS NOT NULL)
                );
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                JOIN pg_namespace n ON t.relnamespace = n.oid
                WHERE n.nspname = 'school' AND t.relname = 'student_fee_assignments'
                  AND c.conname = 'chk_student_fee_assignment_status'
            ) THEN
                ALTER TABLE school.student_fee_assignments
                ADD CONSTRAINT chk_student_fee_assignment_status CHECK (status IN ('unpaid','partial','paid'));
            END IF;
        END IF;
    EXCEPTION WHEN others THEN NULL;
    END $$;
"""

STUDENT_FEE_DISCOUNTS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.student_fee_discounts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        student_fee_assignment_id UUID NOT NULL REFERENCES school.student_fee_assignments(id) ON DELETE CASCADE,
        discount_name VARCHAR(100) NOT NULL,
        discount_category VARCHAR(30) NOT NULL,
        discount_type VARCHAR(20) NOT NULL,
        discount_value NUMERIC(12, 2) NOT NULL,
        calculated_discount_amount NUMERIC(12, 2) NOT NULL,
        reason TEXT,
        approved_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
"""

PAYMENT_TRANSACTIONS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.payment_transactions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        academic_year_id UUID NOT NULL REFERENCES core.academic_years(id) ON DELETE RESTRICT,
        student_fee_assignment_id UUID NOT NULL REFERENCES school.student_fee_assignments(id) ON DELETE RESTRICT,
        amount_paid NUMERIC(12, 2) NOT NULL,
        payment_mode VARCHAR(30) NOT NULL,
        transaction_reference VARCHAR(100),
        payment_status VARCHAR(20) NOT NULL,
        paid_at TIMESTAMPTZ NOT NULL,
        collected_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
"""

FEE_AUDIT_LOGS_TABLE: str = """
    CREATE TABLE IF NOT EXISTS school.fee_audit_logs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id UUID NOT NULL REFERENCES core.tenants(id) ON DELETE CASCADE,
        reference_table VARCHAR(50) NOT NULL,
        reference_id UUID NOT NULL,
        action_type VARCHAR(30) NOT NULL,
        old_value JSONB,
        new_value JSONB,
        changed_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
"""

# Drop class_id, section_id from student_profiles (after backfill)
ALTER_STUDENT_PROFILES_DROP_CLASS_SECTION: str = """
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='auth' AND table_name='student_profiles' AND column_name='class_id') THEN
            ALTER TABLE auth.student_profiles DROP COLUMN class_id;
        END IF;
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='auth' AND table_name='student_profiles' AND column_name='section_id') THEN
            ALTER TABLE auth.student_profiles DROP COLUMN section_id;
        END IF;
    END $$;
"""


async def ensure_tables(db_engine: AsyncEngine) -> None:
    """
    Ensure that all required schemas/tables exist in the connected database.
    If a table is missing, it will be created.
    """
    async with db_engine.begin() as conn:
        # Ensure schemas exist
        for schema, ddl in CREATE_SCHEMA_SQL.items():
            await conn.execute(text(ddl))

        # Create tables in dependency order: roles -> users -> refresh_tokens, staff_profiles, student_profiles
        missing: List[str] = []
        order_tables: List[Tuple[str, str]] = [
            ("core", "tenants"),
            ("core", "academic_years"),
            ("core", "departments"),
            ("core", "classes"),
            ("core", "sections"),
            ("core", "subjects"),
            ("core", "tenant_modules"),
            ("core", "modules"),
            ("core", "organization_type_modules"),
            ("core", "subscription_plans"),
            ("auth", "roles"),
            ("auth", "users"),
            ("auth", "refresh_tokens"),
            ("auth", "staff_profiles"),
            ("auth", "student_profiles"),
            ("auth", "teacher_referrals"),
        ]
        for schema, table in order_tables:
            full_name = f"{schema}.{table}"
            result = await conn.execute(
                text("SELECT to_regclass(:relname)"), {"relname": full_name}
            )
            exists = result.scalar()
            if exists is None:
                missing.append(full_name)
                create_sql = CREATE_TABLE_SQL[(schema, table)]
                await conn.execute(text(create_sql))

        # Add user_type and role_id to auth.users if columns are missing (existing DBs)
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_teacher_referrals_referral_code ON auth.teacher_referrals(referral_code)"))
        await conn.execute(text(ALTER_TENANT_MODULES_ENABLED_AT))
        await conn.execute(text(ALTER_USERS_USER_TYPE))

        # Add organization_code to core.tenants if column missing (existing DBs)
        await conn.execute(text(ALTER_TENANTS_ORGANIZATION_CODE))
        await conn.execute(text(ALTER_TENANTS_ORG_SHORT_CODE))
        await conn.execute(text(ALTER_STAFF_PROFILES_EMPLOYEE_CODE))
        await conn.execute(text(ALTER_STAFF_PROFILES_DEPARTMENT_ID))
        await conn.execute(text(ALTER_STAFF_PROFILES_REPORTING_MANAGER))
        await conn.execute(text(ALTER_STUDENT_PROFILES_CLASS_SECTION))
        await conn.execute(text(ALTER_SECTIONS_CLASS_ID))
        await conn.execute(text(ALTER_SECTIONS_DROP_OLD_UNIQUE))
        await conn.execute(text(ALTER_SECTIONS_ADD_CLASS_NAME_UNIQUE))
        await conn.execute(text(ALTER_SECTIONS_CAPACITY))
        await conn.execute(text(ALTER_SECTIONS_ACADEMIC_YEAR_ID))
        await conn.execute(text(ALTER_SECTIONS_BACKFILL_ACADEMIC_YEAR))
        await conn.execute(text(ALTER_SECTIONS_DROP_CLASS_NAME_UNIQUE))
        await conn.execute(text(ALTER_SECTIONS_ADD_CLASS_AY_NAME_UNIQUE))
        await conn.execute(text(ALTER_MODULES_PRICE))
        await conn.execute(text(ALTER_SUBSCRIPTION_PLANS_ORGANIZATION_TYPE))
        await conn.execute(text(ALTER_SUBSCRIPTION_PLANS_DROP_OLD_UNIQUE))
        await conn.execute(text(ALTER_SUBSCRIPTION_PLANS_ADD_NAME_ORG_UNIQUE))
        await conn.execute(text(CREATE_INDEX_ACADEMIC_YEAR_CURRENT))
        await conn.execute(text(ALTER_ACADEMIC_YEARS_EXTRA))
        await conn.execute(text(ALTER_ACADEMIC_YEARS_CLOSED_BY_FK))
        await conn.execute(text(STUDENT_ACADEMIC_RECORDS_TABLE))
        await conn.execute(text(REFERRAL_USAGE_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_referral_usage_tenant_id ON school.referral_usage(tenant_id)"))
        await conn.execute(text(ADMISSION_REQUESTS_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_admission_requests_tenant_id ON school.admission_requests(tenant_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_admission_requests_status ON school.admission_requests(status)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_admission_requests_created_at ON school.admission_requests(created_at)"))
        await conn.execute(text(ADMISSION_STUDENTS_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_admission_students_tenant_id ON school.admission_students(tenant_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_admission_students_status ON school.admission_students(status)"))
        await conn.execute(text(AUDIT_LOGS_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_id ON school.audit_logs(tenant_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_entity ON school.audit_logs(entity_type, entity_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_audit_logs_timestamp ON school.audit_logs(timestamp)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_referral_usage_referral_code ON school.referral_usage(referral_code)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_referral_usage_teacher_id ON school.referral_usage(teacher_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_referral_usage_academic_year_id ON school.referral_usage(academic_year_id)"))
        await conn.execute(text(TEACHER_CLASS_ASSIGNMENTS_TABLE))
        await conn.execute(text(ALTER_TEACHER_CLASS_ASSIGNMENTS_SUBJECT_ID))
        await conn.execute(text(ALTER_TEACHER_CLASS_ASSIGNMENTS_UNIQUE_WITH_SUBJECT))
        await conn.execute(text(SCHOOL_SUBJECTS_TABLE))
        await conn.execute(text(ALTER_SUBJECTS_DEPARTMENT_TO_CORE))
        await conn.execute(text(ALTER_SUBJECTS_UNIQUE_TENANT_DEPT_CODE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_school_subjects_tenant ON school.subjects(tenant_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_school_subjects_department ON school.subjects(department_id)"))
        await conn.execute(text(CLASS_SUBJECTS_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_class_subjects_ay ON school.class_subjects(academic_year_id)"))
        await conn.execute(text(TEACHER_SUBJECT_ASSIGNMENTS_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_teacher_subject_assignments_teacher ON school.teacher_subject_assignments(teacher_id)"))
        await conn.execute(text(TIMETABLES_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_timetables_ay_class_section ON school.timetables(academic_year_id, class_id, section_id)"))
        await conn.execute(text(CLASS_TEACHER_ASSIGNMENTS_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_class_teacher_assignments_tenant ON school.class_teacher_assignments(tenant_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_class_teacher_assignments_ay ON school.class_teacher_assignments(academic_year_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_class_teacher_assignments_teacher ON school.class_teacher_assignments(teacher_id)"))
        await conn.execute(text(STUDENT_ATTENDANCE_TABLE))
        await conn.execute(text(STUDENT_DAILY_ATTENDANCE_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_student_daily_attendance_tenant_date ON school.student_daily_attendance(tenant_id, attendance_date)"))
        await conn.execute(text(STUDENT_DAILY_ATTENDANCE_RECORDS_TABLE))
        await conn.execute(text(STUDENT_SUBJECT_ATTENDANCE_OVERRIDES_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_student_subject_overrides_tenant ON school.student_subject_attendance_overrides(tenant_id)"))
        await conn.execute(text(ALTER_OVERRIDES_FK_TO_SCHOOL_SUBJECTS))
        await conn.execute(text(EMPLOYEE_ATTENDANCE_TABLE))
        await conn.execute(text(LEAVE_TYPES_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_leave_types_tenant_id ON leave.leave_types(tenant_id)"))
        await conn.execute(text(LEAVE_REQUESTS_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_leave_requests_tenant_id ON leave.leave_requests(tenant_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_leave_requests_status ON leave.leave_requests(status)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_leave_requests_assigned_to ON leave.leave_requests(assigned_to_user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_leave_requests_created_by ON leave.leave_requests(created_by)"))
        await conn.execute(text(LEAVE_AUDIT_LOGS_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_leave_audit_logs_request_id ON leave.leave_audit_logs(leave_request_id)"))
        await conn.execute(text(HOMEWORKS_TABLE))
        await conn.execute(text(HOMEWORK_QUESTIONS_TABLE))
        await conn.execute(text(ALTER_HOMEWORK_QUESTIONS_QUESTION_TYPES))
        await conn.execute(text(HOMEWORK_ASSIGNMENTS_TABLE))
        await conn.execute(text(ALTER_HOMEWORK_ASSIGNMENTS_SUBJECT_ID))
        await conn.execute(text(IX_HOMEWORK_ASSIGNMENTS_SUBJECT_ID))
        await conn.execute(text(UQ_HOMEWORK_ASSIGNMENT_CONTEXT))
        await conn.execute(text(HOMEWORK_ATTEMPTS_TABLE))
        await conn.execute(text(HOMEWORK_SUBMISSIONS_TABLE))
        await conn.execute(text(HOMEWORK_HINT_USAGE_TABLE))
        await conn.execute(text(FEE_COMPONENTS_TABLE))
        await conn.execute(text(ALTER_FEE_COMPONENTS_CATEGORY_CHECK))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fee_components_tenant_id ON school.fee_components(tenant_id)"))
        await conn.execute(text(CLASS_FEE_STRUCTURES_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_class_fee_structures_tenant ON school.class_fee_structures(tenant_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_class_fee_structures_ay_class ON school.class_fee_structures(academic_year_id, class_id)"))
        await conn.execute(text(STUDENT_FEE_ASSIGNMENTS_TABLE))
        await conn.execute(text(ALTER_STUDENT_FEE_ASSIGNMENTS_UPGRADE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_student_fee_assignments_tenant ON school.student_fee_assignments(tenant_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_student_fee_assignments_student ON school.student_fee_assignments(student_id, academic_year_id)"))
        await conn.execute(text(STUDENT_FEE_DISCOUNTS_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_student_fee_discounts_tenant ON school.student_fee_discounts(tenant_id)"))
        await conn.execute(text(PAYMENT_TRANSACTIONS_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_payment_transactions_tenant ON school.payment_transactions(tenant_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_payment_transactions_assignment ON school.payment_transactions(student_fee_assignment_id)"))
        await conn.execute(text(FEE_AUDIT_LOGS_TABLE))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fee_audit_logs_tenant ON school.fee_audit_logs(tenant_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_fee_audit_logs_reference ON school.fee_audit_logs(reference_table, reference_id)"))

    # Backfill student_academic_records from existing student_profiles (class_id, section_id)
    # Idempotent: only inserts if no record exists for (student_id, current_academic_year_id)
    async with db_engine.connect() as sar_conn:
        ay_result = await sar_conn.execute(
            text("SELECT id, tenant_id FROM core.academic_years WHERE is_current = true AND status = 'ACTIVE'")
        )
        for ay_row in ay_result.mappings().all():
            ay_id, tenant_id = ay_row["id"], ay_row["tenant_id"]
            sp_result = await sar_conn.execute(
                text("""
                    SELECT sp.user_id, sp.class_id, sp.section_id, sp.roll_number
                    FROM auth.student_profiles sp
                    JOIN auth.users u ON u.id = sp.user_id
                    WHERE u.tenant_id = :tid
                      AND sp.class_id IS NOT NULL
                      AND sp.section_id IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1 FROM school.student_academic_records sar
                          WHERE sar.student_id = sp.user_id AND sar.academic_year_id = :ayid
                      )
                """),
                {"tid": tenant_id, "ayid": ay_id},
            )
            for sp_row in sp_result.mappings().all():
                await sar_conn.execute(
                    text("""
                        INSERT INTO school.student_academic_records (student_id, academic_year_id, class_id, section_id, roll_number, status)
                        VALUES (:sid, :ayid, :cid, :secid, :roll, 'ACTIVE')
                        ON CONFLICT (student_id, academic_year_id) DO NOTHING
                    """),
                    {
                        "sid": sp_row["user_id"],
                        "ayid": ay_id,
                        "cid": sp_row["class_id"],
                        "secid": sp_row["section_id"],
                        "roll": sp_row["roll_number"] or "",
                    },
                )
            await sar_conn.commit()
        await sar_conn.execute(text(ALTER_STUDENT_PROFILES_DROP_CLASS_SECTION))
        await sar_conn.commit()

    # Backfill module prices (assign random placeholder costs to modules with price='0')
    async with db_engine.connect() as module_conn:
        module_result = await module_conn.execute(
            text("SELECT id, module_key FROM core.modules WHERE price IS NULL OR price = '' OR price = '0'")
        )
        module_rows = module_result.mappings().all()
        for i, row in enumerate(module_rows):
            price = MODULE_BACKFILL_PRICES[i % len(MODULE_BACKFILL_PRICES)]
            await module_conn.execute(
                text("UPDATE core.modules SET price = :price WHERE id = :id"),
                {"price": price, "id": row["id"]},
            )
            await module_conn.commit()
    # Backfill subscription_plans: set organization_type = 'School' for existing plans with NULL or empty
    async with db_engine.connect() as sub_conn:
        await sub_conn.execute(
            text("""
                UPDATE core.subscription_plans
                SET organization_type = 'School'
                WHERE organization_type IS NULL OR organization_type = ''
            """)
        )
        await sub_conn.commit()
    # Backfill organization_code for existing tenants (requires Python loop; run outside begin if needed)
    async with db_engine.connect() as backfill_conn:
        result = await backfill_conn.execute(
            text("SELECT id, organization_type FROM core.tenants WHERE organization_code IS NULL")
        )
        rows = result.mappings().all()
        for row in rows:
            tenant_id, org_type = row["id"], row["organization_type"]
            for _ in range(20):
                code = generate_organization_code_candidate(org_type or "Other")
                check = await backfill_conn.execute(
                    text("SELECT 1 FROM core.tenants WHERE organization_code = :c"),
                    {"c": code},
                )
                if check.scalar() is None:
                    await backfill_conn.execute(
                        text("UPDATE core.tenants SET organization_code = :c WHERE id = :id"),
                        {"c": code, "id": tenant_id},
                    )
                    await backfill_conn.commit()
                    break

    async with db_engine.begin() as conn2:
        # Set NOT NULL and UNIQUE after backfill (idempotent)
        await conn2.execute(text(ALTER_TENANTS_ORGANIZATION_CODE_NOT_NULL))
        await conn2.execute(text(ALTER_TENANTS_ORGANIZATION_CODE_UNIQUE))

    if missing:
        print(
            "Created missing tables: "
            + ", ".join(missing)
        )
    else:
        print("All required auth/core tables already exist in the database.")


async def main() -> None:
    await ensure_tables(engine)


if __name__ == "__main__":
    asyncio.run(main())
