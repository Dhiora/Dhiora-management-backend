from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import RegisterResponse
from app.core.config import settings
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import ResetDatabaseResponse, TestFullAccessRegisterRequest
from .service import register_organization_full_access_free, truncate_all_application_tables

router = APIRouter(prefix="/api/v1/test", tags=["test"])


def _ensure_test_access(x_test_api_key: Optional[str]) -> None:
    if not settings.enable_test_apis:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    secret = settings.test_api_secret
    if secret and x_test_api_key != secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-Test-Api-Key",
        )


@router.post(
    "/reset-database",
    response_model=ResetDatabaseResponse,
    summary="Truncate all application tables (destructive, test only)",
)
async def reset_database(
    db: AsyncSession = Depends(get_db),
    x_test_api_key: Optional[str] = Header(None, alias="X-Test-Api-Key"),
) -> ResetDatabaseResponse:
    _ensure_test_access(x_test_api_key)
    return await truncate_all_application_tables(db)


@router.post(
    "/register-organization-full-access",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register org with all modules + free ERP/AI subscriptions (test only)",
)
async def register_organization_full_access(
    payload: TestFullAccessRegisterRequest,
    db: AsyncSession = Depends(get_db),
    x_test_api_key: Optional[str] = Header(None, alias="X-Test-Api-Key"),
) -> RegisterResponse:
    _ensure_test_access(x_test_api_key)
    try:
        return await register_organization_full_access_free(db, payload)
    except ServiceError as e:
        if e.status_code == status.HTTP_409_CONFLICT:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        if e.status_code == status.HTTP_400_BAD_REQUEST:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        if e.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        if e.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise HTTPException(status_code=e.status_code, detail="Internal server error")
        raise HTTPException(status_code=e.status_code, detail=e.message)
