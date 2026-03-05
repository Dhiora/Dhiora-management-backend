from datetime import datetime, date
from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ServiceError
from app.core.models import (
    Asset,
    AssetAssignment,
    AssetAuditLog,
    AssetMaintenance,
    AssetType,
    Tenant,
)

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


async def _get_tenant_type(db: AsyncSession, tenant_id: UUID) -> str:
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        return "SCHOOL"
    return (tenant.organization_type or "SCHOOL").upper()


async def _log_asset_audit(
    db: AsyncSession,
    tenant_id: UUID,
    asset_id: UUID,
    action: str,
    performed_by: UUID,
    performed_by_role: str,
    remarks: Optional[str] = None,
) -> None:
    entry = AssetAuditLog(
        tenant_id=tenant_id,
        asset_id=asset_id,
        action=action,
        performed_by=performed_by,
        performed_by_role=performed_by_role,
        remarks=remarks,
    )
    db.add(entry)


# ----- Asset Types -----
async def list_asset_types(
    db: AsyncSession,
    tenant_id: UUID,
    active_only: bool = True,
) -> List[AssetTypeResponse]:
    q = select(AssetType).where(AssetType.tenant_id == tenant_id)
    if active_only:
        q = q.where(AssetType.is_active.is_(True))
    q = q.order_by(AssetType.name)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        AssetTypeResponse(
            id=at.id,
            tenant_id=at.tenant_id,
            name=at.name,
            code=at.code,
            description=at.description,
            is_active=at.is_active,
            created_at=at.created_at,
        )
        for at in rows
    ]


async def create_asset_type(
    db: AsyncSession,
    tenant_id: UUID,
    payload: AssetTypeCreate,
) -> AssetTypeResponse:
    existing = (
        await db.execute(
            select(AssetType).where(
                AssetType.tenant_id == tenant_id,
                AssetType.code == payload.code.strip(),
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ServiceError(
            f"Asset type with code '{payload.code}' already exists for this tenant",
            status.HTTP_400_BAD_REQUEST,
        )
    at = AssetType(
        tenant_id=tenant_id,
        name=payload.name.strip(),
        code=payload.code.strip(),
        description=payload.description.strip() if payload.description else None,
        is_active=payload.is_active,
    )
    db.add(at)
    await db.commit()
    await db.refresh(at)
    return AssetTypeResponse(
        id=at.id,
        tenant_id=at.tenant_id,
        name=at.name,
        code=at.code,
        description=at.description,
        is_active=at.is_active,
        created_at=at.created_at,
    )


async def update_asset_type(
    db: AsyncSession,
    tenant_id: UUID,
    type_id: UUID,
    payload: AssetTypeUpdate,
) -> AssetTypeResponse:
    at = await db.get(AssetType, type_id)
    if not at or at.tenant_id != tenant_id:
        raise ServiceError("Asset type not found", status.HTTP_404_NOT_FOUND)
    if payload.name is not None:
        at.name = payload.name.strip()
    if payload.code is not None:
        new_code = payload.code.strip()
        if new_code != at.code:
            existing = (
                await db.execute(
                    select(AssetType).where(
                        AssetType.tenant_id == tenant_id,
                        AssetType.code == new_code,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                raise ServiceError(
                    f"Asset type with code '{new_code}' already exists for this tenant",
                    status.HTTP_400_BAD_REQUEST,
                )
            at.code = new_code
    if payload.description is not None:
        at.description = payload.description.strip() if payload.description else None
    if payload.is_active is not None:
        at.is_active = payload.is_active
    await db.commit()
    await db.refresh(at)
    return AssetTypeResponse(
        id=at.id,
        tenant_id=at.tenant_id,
        name=at.name,
        code=at.code,
        description=at.description,
        is_active=at.is_active,
        created_at=at.created_at,
    )


async def delete_asset_type(
    db: AsyncSession,
    tenant_id: UUID,
    type_id: UUID,
) -> None:
    at = await db.get(AssetType, type_id)
    if not at or at.tenant_id != tenant_id:
        raise ServiceError("Asset type not found", status.HTTP_404_NOT_FOUND)
    # Optional: prevent delete if assets exist
    asset_exists = (
        await db.execute(
            select(Asset.id).where(
                Asset.tenant_id == tenant_id,
                Asset.asset_type_id == type_id,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if asset_exists:
        raise ServiceError(
            "Cannot delete asset type while assets of this type exist",
            status.HTTP_400_BAD_REQUEST,
        )
    await db.delete(at)
    await db.commit()


# ----- Assets -----
async def list_assets(
    db: AsyncSession,
    tenant_id: UUID,
) -> List[AssetResponse]:
    result = await db.execute(
        select(Asset).where(Asset.tenant_id == tenant_id).order_by(Asset.created_at.desc())
    )
    rows = result.scalars().all()
    return [AssetResponse.from_orm(a) for a in rows]


async def create_asset(
    db: AsyncSession,
    tenant_id: UUID,
    current_user_id: UUID,
    payload: AssetCreate,
    current_user_role: str,
) -> AssetResponse:
    at = await db.get(AssetType, payload.asset_type_id)
    if not at or at.tenant_id != tenant_id or not at.is_active:
        raise ServiceError("Invalid or inactive asset type", status.HTTP_400_BAD_REQUEST)

    existing = (
        await db.execute(
            select(Asset).where(
                Asset.tenant_id == tenant_id,
                Asset.asset_code == payload.asset_code.strip(),
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ServiceError(
            f"Asset with code '{payload.asset_code}' already exists for this tenant",
            status.HTTP_400_BAD_REQUEST,
        )

    asset = Asset(
        tenant_id=tenant_id,
        asset_type_id=payload.asset_type_id,
        asset_name=payload.asset_name.strip(),
        asset_code=payload.asset_code.strip(),
        serial_number=payload.serial_number.strip() if payload.serial_number else None,
        purchase_date=payload.purchase_date,
        purchase_cost=payload.purchase_cost,
        warranty_expiry=payload.warranty_expiry,
        status=payload.status or "AVAILABLE",
        location=payload.location.strip() if payload.location else None,
        created_by=current_user_id,
    )
    db.add(asset)
    await db.flush()
    await _log_asset_audit(db, tenant_id, asset.id, "CREATED", current_user_id, current_user_role)
    await db.commit()
    await db.refresh(asset)
    return AssetResponse.from_orm(asset)


async def get_asset(
    db: AsyncSession,
    tenant_id: UUID,
    asset_id: UUID,
) -> AssetResponse:
    asset = await db.get(Asset, asset_id)
    if not asset or asset.tenant_id != tenant_id:
        raise ServiceError("Asset not found", status.HTTP_404_NOT_FOUND)
    return AssetResponse.from_orm(asset)


async def update_asset(
    db: AsyncSession,
    tenant_id: UUID,
    asset_id: UUID,
    payload: AssetUpdate,
    current_user_id: UUID,
    current_user_role: str,
) -> AssetResponse:
    asset = await db.get(Asset, asset_id)
    if not asset or asset.tenant_id != tenant_id:
        raise ServiceError("Asset not found", status.HTTP_404_NOT_FOUND)

    if payload.asset_type_id is not None:
        at = await db.get(AssetType, payload.asset_type_id)
        if not at or at.tenant_id != tenant_id or not at.is_active:
            raise ServiceError("Invalid or inactive asset type", status.HTTP_400_BAD_REQUEST)
        asset.asset_type_id = payload.asset_type_id
    if payload.asset_name is not None:
        asset.asset_name = payload.asset_name.strip()
    if payload.asset_code is not None:
        new_code = payload.asset_code.strip()
        if new_code != asset.asset_code:
            existing = (
                await db.execute(
                    select(Asset).where(
                        Asset.tenant_id == tenant_id,
                        Asset.asset_code == new_code,
                        Asset.id != asset.id,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                raise ServiceError(
                    f"Asset with code '{new_code}' already exists for this tenant",
                    status.HTTP_400_BAD_REQUEST,
                )
            asset.asset_code = new_code
    if payload.serial_number is not None:
        asset.serial_number = payload.serial_number.strip() if payload.serial_number else None
    if payload.purchase_date is not None:
        asset.purchase_date = payload.purchase_date
    if payload.purchase_cost is not None:
        asset.purchase_cost = payload.purchase_cost
    if payload.warranty_expiry is not None:
        asset.warranty_expiry = payload.warranty_expiry
    if payload.status is not None:
        asset.status = payload.status
    if payload.location is not None:
        asset.location = payload.location.strip() if payload.location else None

    await _log_asset_audit(db, tenant_id, asset.id, "UPDATED", current_user_id, current_user_role)
    await db.commit()
    await db.refresh(asset)
    return AssetResponse.from_orm(asset)


async def delete_asset(
    db: AsyncSession,
    tenant_id: UUID,
    asset_id: UUID,
) -> None:
    asset = await db.get(Asset, asset_id)
    if not asset or asset.tenant_id != tenant_id:
        raise ServiceError("Asset not found", status.HTTP_404_NOT_FOUND)
    # Optional: prevent delete if assignments exist
    assignment_exists = (
        await db.execute(
            select(AssetAssignment.id).where(
                AssetAssignment.tenant_id == tenant_id,
                AssetAssignment.asset_id == asset_id,
            ).limit(1)
        )
    ).scalar_one_or_none()
    if assignment_exists:
        raise ServiceError(
            "Cannot delete asset with assignment history",
            status.HTTP_400_BAD_REQUEST,
        )
    await db.delete(asset)
    await db.commit()


# ----- Assignments -----
async def assign_asset(
    db: AsyncSession,
    tenant_id: UUID,
    current_user_id: UUID,
    current_user_role: str,
    payload: AssetAssignRequest,
) -> AssetAssignmentResponse:
    asset = await db.get(Asset, payload.asset_id)
    if not asset or asset.tenant_id != tenant_id:
        raise ServiceError("Asset not found", status.HTTP_404_NOT_FOUND)
    if asset.status != "AVAILABLE":
        raise ServiceError("Only AVAILABLE assets can be assigned", status.HTTP_400_BAD_REQUEST)

    tenant_type = await _get_tenant_type(db, tenant_id)
    _ = tenant_type  # Placeholder for future tenant-specific behavior

    if payload.asset_user_type not in ("EMPLOYEE", "STUDENT"):
        raise ServiceError("asset_user_type must be EMPLOYEE or STUDENT", status.HTTP_400_BAD_REQUEST)
    if payload.asset_user_type == "EMPLOYEE":
        if not payload.employee_id or payload.student_id:
            raise ServiceError(
                "For EMPLOYEE assignments, employee_id is required and student_id must be null",
                status.HTTP_400_BAD_REQUEST,
            )
    else:
        if not payload.student_id or payload.employee_id:
            raise ServiceError(
                "For STUDENT assignments, student_id is required and employee_id must be null",
                status.HTTP_400_BAD_REQUEST,
            )

    assignment = AssetAssignment(
        tenant_id=tenant_id,
        asset_id=asset.id,
        asset_user_type=payload.asset_user_type,
        employee_id=payload.employee_id,
        student_id=payload.student_id,
        assigned_by=current_user_id,
        expected_return_date=payload.expected_return_date,
        status="ASSIGNED",
    )
    asset.status = "ASSIGNED"
    db.add(assignment)
    await db.flush()
    await _log_asset_audit(db, tenant_id, asset.id, "ASSIGNED", current_user_id, current_user_role)
    await db.commit()
    await db.refresh(assignment)
    return AssetAssignmentResponse.from_orm(assignment)


async def return_asset(
    db: AsyncSession,
    tenant_id: UUID,
    assignment_id: UUID,
    current_user_id: UUID,
    current_user_role: str,
    payload: AssetReturnRequest,
) -> AssetAssignmentResponse:
    assignment = await db.get(AssetAssignment, assignment_id)
    if not assignment or assignment.tenant_id != tenant_id:
        raise ServiceError("Assignment not found", status.HTTP_404_NOT_FOUND)
    if assignment.status not in ("ASSIGNED", "OVERDUE"):
        raise ServiceError("Only ASSIGNED or OVERDUE assets can be returned", status.HTTP_400_BAD_REQUEST)

    asset = await db.get(Asset, assignment.asset_id)
    if not asset or asset.tenant_id != tenant_id:
        raise ServiceError("Asset not found", status.HTTP_404_NOT_FOUND)

    assignment.status = "RETURNED"
    assignment.returned_at = datetime.utcnow()
    assignment.return_condition = payload.return_condition.strip() if payload.return_condition else None
    if asset.status in ("ASSIGNED", "UNDER_MAINTENANCE"):
        asset.status = "AVAILABLE"

    await _log_asset_audit(db, tenant_id, asset.id, "RETURNED", current_user_id, current_user_role)
    await db.commit()
    await db.refresh(assignment)
    return AssetAssignmentResponse.from_orm(assignment)


async def list_my_assets(
    db: AsyncSession,
    tenant_id: UUID,
    current_user_id: UUID,
    asset_user_type: str,
) -> List[AssetAssignmentResponse]:
    if asset_user_type not in ("EMPLOYEE", "STUDENT"):
        raise ServiceError("asset_user_type must be EMPLOYEE or STUDENT", status.HTTP_400_BAD_REQUEST)

    cond = [
        AssetAssignment.tenant_id == tenant_id,
    ]
    if asset_user_type == "EMPLOYEE":
        cond.append(AssetAssignment.employee_id == current_user_id)
    else:
        cond.append(AssetAssignment.student_id == current_user_id)

    result = await db.execute(
        select(AssetAssignment)
        .where(and_(*cond))
        .order_by(AssetAssignment.assigned_at.desc())
    )
    rows = result.scalars().all()
    return [AssetAssignmentResponse.from_orm(a) for a in rows]


async def list_assigned_assets(
    db: AsyncSession,
    tenant_id: UUID,
) -> List[AssetAssignmentResponse]:
    result = await db.execute(
        select(AssetAssignment)
        .where(
            AssetAssignment.tenant_id == tenant_id,
            AssetAssignment.status.in_(["ASSIGNED", "OVERDUE"]),
        )
        .order_by(AssetAssignment.assigned_at.desc())
    )
    rows = result.scalars().all()
    return [AssetAssignmentResponse.from_orm(a) for a in rows]


async def refresh_overdue_assignments(
    db: AsyncSession,
    tenant_id: UUID,
    today: Optional[date] = None,
) -> None:
    """Mark assignments as OVERDUE when expected_return_date < today and still ASSIGNED."""
    today = today or date.today()
    result = await db.execute(
        select(AssetAssignment).where(
            AssetAssignment.tenant_id == tenant_id,
            AssetAssignment.status == "ASSIGNED",
            AssetAssignment.expected_return_date.is_not(None),
            AssetAssignment.expected_return_date < today,
        )
    )
    rows = result.scalars().all()
    for a in rows:
        a.status = "OVERDUE"
    if rows:
        await db.commit()


# ----- Maintenance -----
async def report_maintenance(
    db: AsyncSession,
    tenant_id: UUID,
    current_user_id: UUID,
    current_user_role: str,
    payload: AssetMaintenanceReportRequest,
) -> AssetMaintenanceResponse:
    asset = await db.get(Asset, payload.asset_id)
    if not asset or asset.tenant_id != tenant_id:
        raise ServiceError("Asset not found", status.HTTP_404_NOT_FOUND)
    if asset.status == "LOST" or asset.status == "RETIRED":
        raise ServiceError("Cannot create maintenance for lost or retired assets", status.HTTP_400_BAD_REQUEST)

    record = AssetMaintenance(
        tenant_id=tenant_id,
        asset_id=asset.id,
        reported_issue=payload.reported_issue.strip(),
        maintenance_type=payload.maintenance_type,
        reported_by=current_user_id,
        assigned_technician=payload.assigned_technician,
        maintenance_status="OPEN",
        cost=payload.cost,
    )
    if asset.status == "AVAILABLE":
        asset.status = "UNDER_MAINTENANCE"
    db.add(record)
    await db.flush()
    await _log_asset_audit(db, tenant_id, asset.id, "MAINTENANCE_STARTED", current_user_id, current_user_role)
    await db.commit()
    await db.refresh(record)
    return AssetMaintenanceResponse.from_orm(record)


async def start_maintenance(
    db: AsyncSession,
    tenant_id: UUID,
    maintenance_id: UUID,
    current_user_id: UUID,
    current_user_role: str,
    payload: AssetMaintenanceStartRequest,
) -> AssetMaintenanceResponse:
    record = await db.get(AssetMaintenance, maintenance_id)
    if not record or record.tenant_id != tenant_id:
        raise ServiceError("Maintenance record not found", status.HTTP_404_NOT_FOUND)
    if record.maintenance_status != "OPEN":
        raise ServiceError("Only OPEN maintenance can be started", status.HTTP_400_BAD_REQUEST)
    record.maintenance_status = "IN_PROGRESS"
    record.started_at = datetime.utcnow()
    if payload.assigned_technician is not None:
        record.assigned_technician = payload.assigned_technician
    await _log_asset_audit(db, tenant_id, record.asset_id, "MAINTENANCE_STARTED", current_user_id, current_user_role)
    await db.commit()
    await db.refresh(record)
    return AssetMaintenanceResponse.from_orm(record)


async def complete_maintenance(
    db: AsyncSession,
    tenant_id: UUID,
    maintenance_id: UUID,
    current_user_id: UUID,
    current_user_role: str,
    payload: AssetMaintenanceCompleteRequest,
) -> AssetMaintenanceResponse:
    record = await db.get(AssetMaintenance, maintenance_id)
    if not record or record.tenant_id != tenant_id:
        raise ServiceError("Maintenance record not found", status.HTTP_404_NOT_FOUND)
    if record.maintenance_status not in ("OPEN", "IN_PROGRESS"):
        raise ServiceError("Only OPEN or IN_PROGRESS maintenance can be completed", status.HTTP_400_BAD_REQUEST)
    record.maintenance_status = "COMPLETED"
    record.completed_at = datetime.utcnow()
    if payload.cost is not None:
        record.cost = payload.cost

    asset = await db.get(Asset, record.asset_id)
    if asset and asset.tenant_id == tenant_id and asset.status == "UNDER_MAINTENANCE":
        asset.status = "AVAILABLE"

    await _log_asset_audit(db, tenant_id, record.asset_id, "MAINTENANCE_COMPLETED", current_user_id, current_user_role)
    await db.commit()
    await db.refresh(record)
    return AssetMaintenanceResponse.from_orm(record)


async def list_maintenance(
    db: AsyncSession,
    tenant_id: UUID,
) -> List[AssetMaintenanceResponse]:
    result = await db.execute(
        select(AssetMaintenance)
        .where(AssetMaintenance.tenant_id == tenant_id)
        .order_by(AssetMaintenance.created_at.desc())
    )
    rows = result.scalars().all()
    return [AssetMaintenanceResponse.from_orm(r) for r in rows]


# ----- History & Audit -----
async def get_asset_history(
    db: AsyncSession,
    tenant_id: UUID,
    asset_id: UUID,
) -> AssetHistoryResponse:
    asset = await db.get(Asset, asset_id)
    if not asset or asset.tenant_id != tenant_id:
        raise ServiceError("Asset not found", status.HTTP_404_NOT_FOUND)

    assignments_result = await db.execute(
        select(AssetAssignment)
        .where(
            AssetAssignment.tenant_id == tenant_id,
            AssetAssignment.asset_id == asset_id,
        )
        .order_by(AssetAssignment.assigned_at.desc())
    )
    assignments = assignments_result.scalars().all()

    maint_result = await db.execute(
        select(AssetMaintenance)
        .where(
            AssetMaintenance.tenant_id == tenant_id,
            AssetMaintenance.asset_id == asset_id,
        )
        .order_by(AssetMaintenance.created_at.desc())
    )
    maintenance = maint_result.scalars().all()

    audit_result = await db.execute(
        select(AssetAuditLog)
        .where(
            AssetAuditLog.tenant_id == tenant_id,
            AssetAuditLog.asset_id == asset_id,
        )
        .order_by(AssetAuditLog.created_at.desc())
    )
    audit_logs = audit_result.scalars().all()

    return AssetHistoryResponse(
        asset=AssetResponse.from_orm(asset),
        assignments=[AssetAssignmentResponse.from_orm(a) for a in assignments],
        maintenance=[AssetMaintenanceResponse.from_orm(m) for m in maintenance],
        audit_logs=[
            AssetAuditLogResponse(
                id=log.id,
                tenant_id=log.tenant_id,
                asset_id=log.asset_id,
                action=log.action,
                performed_by=log.performed_by,
                performed_by_role=log.performed_by_role,
                remarks=log.remarks,
                created_at=log.created_at,
            )
            for log in audit_logs
        ],
    )


async def get_asset_audit_logs(
    db: AsyncSession,
    tenant_id: UUID,
    asset_id: UUID,
) -> List[AssetAuditLogResponse]:
    result = await db.execute(
        select(AssetAuditLog)
        .where(
            AssetAuditLog.tenant_id == tenant_id,
            AssetAuditLog.asset_id == asset_id,
        )
        .order_by(AssetAuditLog.created_at.desc())
    )
    logs = result.scalars().all()
    return [
        AssetAuditLogResponse(
            id=log.id,
            tenant_id=log.tenant_id,
            asset_id=log.asset_id,
            action=log.action,
            performed_by=log.performed_by,
            performed_by_role=log.performed_by_role,
            remarks=log.remarks,
            created_at=log.created_at,
        )
        for log in logs
    ]

