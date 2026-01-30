from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Tenant, TenantModule
from app.auth.models import User


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient, db_session: AsyncSession) -> None:
    payload = {
        "organization_name": "Acme School",
        "organization_type": "School",
        "country": "IN",
        "timezone": "Asia/Kolkata",
        "selected_modules": ["STUDENT", "ADMISSION", "TIMETABLE"],
        "admin_full_name": "Jane Doe",
        "admin_email": "jane@example.com",
        "admin_mobile": "+911234567890",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
        "accept_terms": True,
        "accept_privacy": True,
    }

    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()

    assert data["success"] is True
    assert data["message"] == "Account created successfully"
    assert "tenant_id" in data
    # Ensure tenant_id is a valid UUID
    UUID(data["tenant_id"])

    tenant_id = data["tenant_id"]

    # Verify tenant created
    tenant_result = await db_session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    tenant = tenant_result.scalar_one_or_none()
    assert tenant is not None
    assert tenant.organization_name == payload["organization_name"]
    assert tenant.status == "ACTIVE"

    # Verify admin user created
    user_result = await db_session.execute(
        select(User).where(User.email == payload["admin_email"])
    )
    user = user_result.scalar_one_or_none()
    assert user is not None
    assert user.role == "SUPER_ADMIN"
    assert user.tenant_id == tenant.id

    # Verify modules created
    modules_result = await db_session.execute(
        select(TenantModule).where(TenantModule.tenant_id == tenant.id)
    )
    modules = modules_result.scalars().all()
    module_keys = {m.module_key for m in modules}
    assert module_keys == set(payload["selected_modules"])


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    # First register a tenant and admin user
    register_payload = {
        "organization_name": "Acme HR",
        "organization_type": "Software Company",
        "country": "IN",
        "timezone": "Asia/Kolkata",
        "selected_modules": ["USER_ROLE", "ATTENDANCE"],
        "admin_full_name": "John Admin",
        "admin_email": "john.admin@example.com",
        "admin_mobile": "+911234567891",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
        "accept_terms": True,
        "accept_privacy": True,
    }
    register_resp = await client.post("/api/v1/auth/register", json=register_payload)
    assert register_resp.status_code == 201

    # Then login with same credentials
    login_payload = {
        "email": register_payload["admin_email"],
        "password": register_payload["password"],
    }
    response = await client.post("/api/v1/auth/login", json=login_payload)
    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"

    user = data["user"]
    tenant = data["tenant"]
    modules = data["modules"]

    assert user["email"] == register_payload["admin_email"]
    assert user["role"] == "SUPER_ADMIN"
    assert "id" in user

    assert "id" in tenant
    assert tenant["organization_name"] == register_payload["organization_name"]
    assert tenant["organization_type"] == register_payload["organization_type"]

    assert set(modules) == set(register_payload["selected_modules"])

