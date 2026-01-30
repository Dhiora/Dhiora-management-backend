import asyncio
from typing import Dict, List, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.tenant_service import generate_organization_code_candidate
from app.db.session import engine


REQUIRED_TABLES: List[Tuple[str, str]] = [
    ("core", "tenants"),
    ("core", "departments"),
    ("core", "classes"),
    ("core", "sections"),
    ("core", "tenant_modules"),
    ("core", "modules"),
    ("core", "organization_type_modules"),
    ("auth", "users"),
    ("auth", "refresh_tokens"),
    ("auth", "roles"),
    ("auth", "staff_profiles"),
    ("auth", "student_profiles"),
]


CREATE_SCHEMA_SQL: Dict[str, str] = {
    "core": "CREATE SCHEMA IF NOT EXISTS core;",
    "auth": "CREATE SCHEMA IF NOT EXISTS auth;",
}


CREATE_TABLE_SQL: Dict[Tuple[str, str], str] = {
    ("core", "modules"): """
        CREATE TABLE IF NOT EXISTS core.modules (
            id UUID PRIMARY KEY,
            module_key VARCHAR(100) UNIQUE NOT NULL,
            module_name VARCHAR(255) NOT NULL,
            module_domain VARCHAR(50) NOT NULL,
            description TEXT,
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
            employee_number VARCHAR(50),
            employee_code VARCHAR(50),
            department_id UUID REFERENCES core.departments(id),
            department VARCHAR(100),
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
            class_id UUID REFERENCES core.classes(id),
            section_id UUID REFERENCES core.sections(id),
            class VARCHAR(50),
            section VARCHAR(50),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_student_profile_user UNIQUE (user_id)
        );
    """,
}


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

# Add employee_code to staff_profiles (auto-generated employee number; identification only)
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
            ("core", "departments"),
            ("core", "classes"),
            ("core", "sections"),
            ("core", "tenant_modules"),
            ("core", "modules"),
            ("core", "organization_type_modules"),
            ("auth", "roles"),
            ("auth", "users"),
            ("auth", "refresh_tokens"),
            ("auth", "staff_profiles"),
            ("auth", "student_profiles"),
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
