from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ----- Asset Types -----
class AssetTypeCreate(BaseModel):
    name: str = Field(..., max_length=100)
    code: str = Field(..., max_length=50)
    description: Optional[str] = None
    is_active: bool = True


class AssetTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    code: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class AssetTypeResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    name: str
    code: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ----- Assets -----
class AssetCreate(BaseModel):
    asset_type_id: UUID
    asset_name: str = Field(..., max_length=255)
    asset_code: str = Field(..., max_length=100)
    serial_number: Optional[str] = Field(None, max_length=255)
    purchase_date: Optional[date] = None
    purchase_cost: Optional[Decimal] = Field(None, ge=0)
    warranty_expiry: Optional[date] = None
    status: str = Field("AVAILABLE", description="AVAILABLE, ASSIGNED, UNDER_MAINTENANCE, DAMAGED, LOST, RETIRED")
    location: Optional[str] = Field(None, max_length=255)


class AssetUpdate(BaseModel):
    asset_type_id: Optional[UUID] = None
    asset_name: Optional[str] = Field(None, max_length=255)
    asset_code: Optional[str] = Field(None, max_length=100)
    serial_number: Optional[str] = Field(None, max_length=255)
    purchase_date: Optional[date] = None
    purchase_cost: Optional[Decimal] = Field(None, ge=0)
    warranty_expiry: Optional[date] = None
    status: Optional[str] = Field(None, description="AVAILABLE, ASSIGNED, UNDER_MAINTENANCE, DAMAGED, LOST, RETIRED")
    location: Optional[str] = Field(None, max_length=255)


class AssetResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    asset_type_id: UUID
    asset_name: str
    asset_code: str
    serial_number: Optional[str] = None
    purchase_date: Optional[date] = None
    purchase_cost: Optional[Decimal] = None
    warranty_expiry: Optional[date] = None
    status: str
    location: Optional[str] = None
    created_by: UUID
    created_at: datetime

    class Config:
        from_attributes = True


# ----- Assignments -----
class AssetAssignRequest(BaseModel):
    asset_id: UUID
    asset_user_type: str = Field(..., description="EMPLOYEE or STUDENT")
    employee_id: Optional[UUID] = None
    student_id: Optional[UUID] = None
    expected_return_date: Optional[date] = None


class AssetReturnRequest(BaseModel):
    return_condition: Optional[str] = None


class AssetAssignmentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    asset_id: UUID
    asset_user_type: str
    employee_id: Optional[UUID] = None
    student_id: Optional[UUID] = None
    assigned_by: UUID
    assigned_at: datetime
    expected_return_date: Optional[date] = None
    returned_at: Optional[datetime] = None
    return_condition: Optional[str] = None
    status: str

    class Config:
        from_attributes = True


# ----- Maintenance -----
class AssetMaintenanceReportRequest(BaseModel):
    asset_id: UUID
    reported_issue: str
    maintenance_type: str = Field(..., description="REPAIR or SERVICE")
    assigned_technician: Optional[UUID] = None
    cost: Optional[Decimal] = Field(None, ge=0)


class AssetMaintenanceStartRequest(BaseModel):
    assigned_technician: Optional[UUID] = None


class AssetMaintenanceCompleteRequest(BaseModel):
    cost: Optional[Decimal] = Field(None, ge=0)


class AssetMaintenanceResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    asset_id: UUID
    reported_issue: str
    maintenance_type: str
    reported_by: UUID
    assigned_technician: Optional[UUID] = None
    maintenance_status: str
    cost: Optional[Decimal] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ----- Audit -----
class AssetAuditLogResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    asset_id: UUID
    action: str
    performed_by: UUID
    performed_by_role: Optional[str] = None
    remarks: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AssetHistoryResponse(BaseModel):
    asset: AssetResponse
    assignments: List[AssetAssignmentResponse]
    maintenance: List[AssetMaintenanceResponse]
    audit_logs: List[AssetAuditLogResponse]

