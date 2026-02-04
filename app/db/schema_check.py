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
            name VARCHAR(50) NOT NULL,
            display_order INTEGER,
            capacity INTEGER NOT NULL DEFAULT 50,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_section_class_name UNIQUE (class_id, name)
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
        due_date TIMESTAMPTZ NOT NULL,
        assigned_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE RESTRICT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
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
        await conn.execute(text(ALTER_STUDENT_PROFILES_CLASS_SECTION))
        await conn.execute(text(ALTER_SECTIONS_CLASS_ID))
        await conn.execute(text(ALTER_SECTIONS_DROP_OLD_UNIQUE))
        await conn.execute(text(ALTER_SECTIONS_ADD_CLASS_NAME_UNIQUE))
        await conn.execute(text(ALTER_SECTIONS_CAPACITY))
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
        await conn.execute(text(STUDENT_ATTENDANCE_TABLE))
        await conn.execute(text(EMPLOYEE_ATTENDANCE_TABLE))
        await conn.execute(text(HOMEWORKS_TABLE))
        await conn.execute(text(HOMEWORK_QUESTIONS_TABLE))
        await conn.execute(text(ALTER_HOMEWORK_QUESTIONS_QUESTION_TYPES))
        await conn.execute(text(HOMEWORK_ASSIGNMENTS_TABLE))
        await conn.execute(text(HOMEWORK_ATTEMPTS_TABLE))
        await conn.execute(text(HOMEWORK_SUBMISSIONS_TABLE))
        await conn.execute(text(HOMEWORK_HINT_USAGE_TABLE))

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
