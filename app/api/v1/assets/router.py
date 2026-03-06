from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import (
    AssetAssignRequest,
    AssetAssignmentResponse,
    AssetAuditLogResponse,
    AssetCreate,
    AssetHistoryResponse,
    AssetMaintenanceCompleteRequest,
    AssetMaintenanceReportRequest,
    AssetMaintenanceResponse,
    AssetMaintenanceStartRequest,
    AssetResponse,
    AssetReturnRequest,
    AssetTypeCreate,
    AssetTypeResponse,
    AssetTypeUpdate,
    AssetUpdate,
)
from . import service

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])


# ----- Asset Types -----
@router.get(
    "/types",
    response_model=List[AssetTypeResponse],
    dependencies=[Depends(check_permission("asset", "read"))],
)
async def list_asset_types(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[AssetTypeResponse]:
    return await service.list_asset_types(db, current_user.tenant_id, active_only=active_only)


@router.post(
    "/types",
    response_model=AssetTypeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("asset", "manage_types"))],
)
async def create_asset_type(
    payload: AssetTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AssetTypeResponse:
    try:
        return await service.create_asset_type(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put(
    "/types/{type_id}",
    response_model=AssetTypeResponse,
    dependencies=[Depends(check_permission("asset", "manage_types"))],
)
async def update_asset_type(
    type_id: UUID,
    payload: AssetTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AssetTypeResponse:
    try:
        return await service.update_asset_type(db, current_user.tenant_id, type_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/types/{type_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("asset", "manage_types"))],
)
async def delete_asset_type(
    type_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    try:
        await service.delete_asset_type(db, current_user.tenant_id, type_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


"""
Asset routes are defined so that static paths (e.g. /my, /assigned, /maintenance)
are registered before dynamic ones like /{asset_id}. This avoids FastAPI
trying to parse strings such as 'my' as a UUID.
"""

# ----- Assets -----
@router.get(
    "",
    response_model=List[AssetResponse],
    dependencies=[Depends(check_permission("asset", "read"))],
)
async def list_assets(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[AssetResponse]:
    return await service.list_assets(db, current_user.tenant_id)


@router.post(
    "",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("asset", "manage_assets"))],
)
async def create_asset(
    payload: AssetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AssetResponse:
    try:
        return await service.create_asset(
            db,
            current_user.tenant_id,
            current_user.id,
            payload,
            current_user.role,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Assignments -----
@router.post(
    "/assign",
    response_model=AssetAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("asset", "assign"))],
)
async def assign_asset(
    payload: AssetAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AssetAssignmentResponse:
    try:
        return await service.assign_asset(
            db,
            current_user.tenant_id,
            current_user.id,
            current_user.role,
            payload,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/return/{assignment_id}",
    response_model=AssetAssignmentResponse,
    dependencies=[Depends(check_permission("asset", "return"))],
)
async def return_asset(
    assignment_id: UUID,
    payload: AssetReturnRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AssetAssignmentResponse:
    try:
        return await service.return_asset(
            db,
            current_user.tenant_id,
            assignment_id,
            current_user.id,
            current_user.role,
            payload,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/my",
    response_model=List[AssetAssignmentResponse],
    dependencies=[Depends(check_permission("asset", "read"))],
)
async def list_my_assets(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[AssetAssignmentResponse]:
    # Determine asset_user_type from user_type
    user_type = (current_user.user_type or "").lower() if hasattr(current_user, "user_type") else ""
    asset_user_type = "STUDENT" if user_type == "student" else "EMPLOYEE"
    return await service.list_my_assets(db, current_user.tenant_id, current_user.id, asset_user_type)


@router.get(
    "/assigned",
    response_model=List[AssetAssignmentResponse],
    dependencies=[Depends(check_permission("asset", "view_all"))],
)
async def list_assigned_assets(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[AssetAssignmentResponse]:
    await service.refresh_overdue_assignments(db, current_user.tenant_id)
    return await service.list_assigned_assets(db, current_user.tenant_id)


@router.get(
    "/history/{asset_id}",
    response_model=AssetHistoryResponse,
    dependencies=[Depends(check_permission("asset", "audit"))],
)
async def get_asset_history(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AssetHistoryResponse:
    try:
        return await service.get_asset_history(db, current_user.tenant_id, asset_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Maintenance -----
@router.post(
    "/maintenance/report",
    response_model=AssetMaintenanceResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("asset", "manage_assets"))],
)
async def report_maintenance(
    payload: AssetMaintenanceReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AssetMaintenanceResponse:
    try:
        return await service.report_maintenance(
            db,
            current_user.tenant_id,
            current_user.id,
            current_user.role,
            payload,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put(
    "/maintenance/{maintenance_id}/start",
    response_model=AssetMaintenanceResponse,
    dependencies=[Depends(check_permission("asset", "manage_assets"))],
)
async def start_maintenance(
    maintenance_id: UUID,
    payload: AssetMaintenanceStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AssetMaintenanceResponse:
    try:
        return await service.start_maintenance(
            db,
            current_user.tenant_id,
            maintenance_id,
            current_user.id,
            current_user.role,
            payload,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put(
    "/maintenance/{maintenance_id}/complete",
    response_model=AssetMaintenanceResponse,
    dependencies=[Depends(check_permission("asset", "manage_assets"))],
)
async def complete_maintenance(
    maintenance_id: UUID,
    payload: AssetMaintenanceCompleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AssetMaintenanceResponse:
    try:
        return await service.complete_maintenance(
            db,
            current_user.tenant_id,
            maintenance_id,
            current_user.id,
            current_user.role,
            payload,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/maintenance",
    response_model=List[AssetMaintenanceResponse],
    dependencies=[Depends(check_permission("asset", "read"))],
)
async def list_maintenance(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[AssetMaintenanceResponse]:
    return await service.list_maintenance(db, current_user.tenant_id)


@router.get(
    "/{asset_id}",
    response_model=AssetResponse,
    dependencies=[Depends(check_permission("asset", "read"))],
)
async def get_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AssetResponse:
    try:
        return await service.get_asset(db, current_user.tenant_id, asset_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put(
    "/{asset_id}",
    response_model=AssetResponse,
    dependencies=[Depends(check_permission("asset", "manage_assets"))],
)
async def update_asset(
    asset_id: UUID,
    payload: AssetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AssetResponse:
    try:
        return await service.update_asset(
            db,
            current_user.tenant_id,
            asset_id,
            payload,
            current_user.id,
            current_user.role,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("asset", "manage_assets"))],
)
async def delete_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    try:
        await service.delete_asset(db, current_user.tenant_id, asset_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Audit -----
@router.get(
    "/audit/{asset_id}",
    response_model=List[AssetAuditLogResponse],
    dependencies=[Depends(check_permission("asset", "audit"))],
)
async def get_asset_audit_logs(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[AssetAuditLogResponse]:
    try:
        return await service.get_asset_audit_logs(db, current_user.tenant_id, asset_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

