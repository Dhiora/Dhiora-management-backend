from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import FeeMode, PersonType


class TransportVehicleTypeCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_system_default: bool = False


class TransportVehicleTypeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class TransportVehicleTypeResponse(BaseModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    academic_year_id: Optional[UUID] = None
    name: str
    description: Optional[str] = None
    is_system_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransportRouteCreate(BaseModel):
    academic_year_id: UUID
    route_name: str = Field(..., min_length=1, max_length=255)
    route_code: str = Field(..., min_length=1, max_length=50)
    start_location: str = Field(..., min_length=1, max_length=255)
    end_location: str = Field(..., min_length=1, max_length=255)
    total_distance_km: Optional[float] = Field(None, ge=0)


class TransportRouteResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    route_name: str
    route_code: str
    start_location: str
    end_location: str
    total_distance_km: Optional[float] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransportVehicleCreate(BaseModel):
    academic_year_id: Optional[UUID] = None
    vehicle_number: str = Field(..., min_length=1, max_length=50)
    vehicle_type_id: UUID
    capacity: int = Field(..., ge=1)
    driver_name: Optional[str] = Field(None, max_length=255)
    insurance_expiry: Optional[date] = None
    fitness_expiry: Optional[date] = None


class TransportVehicleResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: Optional[UUID] = None
    vehicle_number: str
    vehicle_type_id: UUID
    capacity: int
    driver_name: Optional[str] = None
    insurance_expiry: Optional[date] = None
    fitness_expiry: Optional[date] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransportSubscriptionPlanCreate(BaseModel):
    academic_year_id: UUID
    route_id: UUID
    plan_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    fee_amount: Decimal = Field(..., ge=0)
    billing_cycle: str = Field(..., description="monthly, quarterly, yearly")
    is_default: bool = False


class TransportSubscriptionPlanResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    route_id: UUID
    plan_name: str
    description: Optional[str] = None
    fee_amount: Decimal
    billing_cycle: str
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransportAssignCreate(BaseModel):
    academic_year_id: UUID
    person_type: PersonType
    person_id: UUID
    route_id: UUID
    vehicle_id: Optional[UUID] = None
    subscription_plan_id: Optional[UUID] = None
    pickup_point: Optional[str] = Field(None, max_length=255)
    drop_point: Optional[str] = Field(None, max_length=255)
    custom_fee: Optional[Decimal] = Field(None, ge=0)
    fee_mode: FeeMode
    start_date: date
    end_date: Optional[date] = None


class TransportAssignmentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    academic_year_id: UUID
    person_type: str
    person_id: UUID
    route_id: UUID
    vehicle_id: Optional[UUID] = None
    subscription_plan_id: Optional[UUID] = None
    pickup_point: Optional[str] = None
    drop_point: Optional[str] = None
    custom_fee: Optional[Decimal] = None
    fee_mode: str
    start_date: date
    end_date: Optional[date] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransportFeeResult(BaseModel):
    person_id: UUID
    person_type: str
    assignment_id: UUID
    effective_fee: Decimal
    fee_mode: str
    custom_fee: Optional[Decimal] = None
    plan_fee: Optional[Decimal] = None
