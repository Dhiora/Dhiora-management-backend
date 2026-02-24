from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import FeeMode, PersonType
from app.core.exceptions import ServiceError
from app.core.models import (
    AcademicYear,
    TransportAssignment,
    TransportRoute,
    TransportSubscriptionPlan,
    TransportVehicle,
    TransportVehicleType,
)

from app.api.v1.academic_years import service as academic_year_service
from .integration_placeholders import create_salary_deduction_entry, create_student_fee_item
from .schemas import (
    TransportAssignCreate,
    TransportAssignmentResponse,
    TransportFeeResult,
    TransportRouteCreate,
    TransportRouteResponse,
    TransportSubscriptionPlanCreate,
    TransportSubscriptionPlanResponse,
    TransportVehicleCreate,
    TransportVehicleResponse,
    TransportVehicleTypeCreate,
    TransportVehicleTypeResponse,
    TransportVehicleTypeUpdate,
)


def _to_uuid(val):
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


def _to_decimal(val) -> Decimal:
    if val is None:
        return Decimal("0")
    return val if isinstance(val, Decimal) else Decimal(str(val))


# ----- Vehicle Types -----

def _vehicle_type_to_response(vt: TransportVehicleType) -> TransportVehicleTypeResponse:
    return TransportVehicleTypeResponse(
        id=vt.id,
        tenant_id=_to_uuid(vt.tenant_id),
        academic_year_id=_to_uuid(vt.academic_year_id),
        name=vt.name,
        description=vt.description,
        is_system_default=vt.is_system_default,
        is_active=vt.is_active,
        created_at=vt.created_at,
        updated_at=vt.updated_at,
    )


async def create_vehicle_type(
    db: AsyncSession,
    tenant_id: UUID,
    payload: TransportVehicleTypeCreate,
) -> TransportVehicleTypeResponse:
    if payload.is_system_default:
        raise ServiceError("Tenant cannot create system default types", status.HTTP_400_BAD_REQUEST)
    vt = TransportVehicleType(
        tenant_id=tenant_id,
        name=payload.name.strip(),
        description=payload.description.strip() if payload.description else None,
        is_system_default=False,
        is_active=True,
    )
    db.add(vt)
    try:
        await db.commit()
        await db.refresh(vt)
        return _vehicle_type_to_response(vt)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Vehicle type creation failed", status.HTTP_409_CONFLICT)


async def update_vehicle_type(
    db: AsyncSession,
    tenant_id: UUID,
    vehicle_type_id: UUID,
    payload: TransportVehicleTypeUpdate,
) -> Optional[TransportVehicleTypeResponse]:
    stmt = select(TransportVehicleType).where(
        TransportVehicleType.id == vehicle_type_id,
        (TransportVehicleType.tenant_id == tenant_id) | (TransportVehicleType.tenant_id.is_(None)),
    )
    result = await db.execute(stmt)
    vt = result.scalar_one_or_none()
    if not vt:
        return None
    if vt.is_system_default and vt.tenant_id is None:
        if payload.name is not None or payload.description is not None:
            raise ServiceError("Cannot modify system default vehicle type", status.HTTP_400_BAD_REQUEST)
        if payload.is_active is not None and not payload.is_active:
            raise ServiceError("Cannot deactivate system default vehicle type", status.HTTP_400_BAD_REQUEST)
    if payload.name is not None:
        vt.name = payload.name.strip()
    if payload.description is not None:
        vt.description = payload.description.strip() or None
    if payload.is_active is not None:
        vt.is_active = payload.is_active
    await db.commit()
    await db.refresh(vt)
    return _vehicle_type_to_response(vt)


async def list_vehicle_types(
    db: AsyncSession,
    tenant_id: UUID,
    active_only: bool = True,
) -> List[TransportVehicleTypeResponse]:
    stmt = select(TransportVehicleType).where(
        (TransportVehicleType.tenant_id == tenant_id) | (TransportVehicleType.tenant_id.is_(None))
    )
    if active_only:
        stmt = stmt.where(TransportVehicleType.is_active.is_(True))
    stmt = stmt.order_by(TransportVehicleType.is_system_default.desc(), TransportVehicleType.name)
    result = await db.execute(stmt)
    return [_vehicle_type_to_response(v) for v in result.scalars().all()]


async def delete_vehicle_type(
    db: AsyncSession,
    tenant_id: UUID,
    vehicle_type_id: UUID,
) -> bool:
    result = await db.execute(
        select(TransportVehicleType).where(
            TransportVehicleType.id == vehicle_type_id,
            TransportVehicleType.tenant_id == tenant_id,
        )
    )
    vt = result.scalar_one_or_none()
    if not vt:
        return False
    if vt.is_system_default:
        raise ServiceError("Cannot delete system default vehicle type", status.HTTP_400_BAD_REQUEST)
    vehicles_count = await db.execute(
        select(func.count()).select_from(TransportVehicle).where(
            TransportVehicle.vehicle_type_id == vehicle_type_id,
        )
    )
    if (vehicles_count.scalar() or 0) > 0:
        raise ServiceError("Cannot delete vehicle type: vehicles reference it", status.HTTP_409_CONFLICT)
    vt.is_active = False
    await db.commit()
    return True


# ----- Routes -----

def _route_to_response(r: TransportRoute) -> TransportRouteResponse:
    return TransportRouteResponse(
        id=r.id,
        tenant_id=_to_uuid(r.tenant_id),
        academic_year_id=_to_uuid(r.academic_year_id),
        route_name=r.route_name,
        route_code=r.route_code,
        start_location=r.start_location,
        end_location=r.end_location,
        total_distance_km=r.total_distance_km,
        is_active=r.is_active,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


async def create_route(
    db: AsyncSession,
    tenant_id: UUID,
    payload: TransportRouteCreate,
) -> TransportRouteResponse:
    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    existing = await db.execute(
        select(TransportRoute).where(
            TransportRoute.tenant_id == tenant_id,
            TransportRoute.route_code == payload.route_code.strip().upper(),
        )
    )
    if existing.scalar_one_or_none():
        raise ServiceError("Route code already exists for this tenant", status.HTTP_409_CONFLICT)
    route = TransportRoute(
        tenant_id=tenant_id,
        academic_year_id=payload.academic_year_id,
        route_name=payload.route_name.strip(),
        route_code=payload.route_code.strip().upper(),
        start_location=payload.start_location.strip(),
        end_location=payload.end_location.strip(),
        total_distance_km=payload.total_distance_km,
        is_active=True,
    )
    db.add(route)
    try:
        await db.commit()
        await db.refresh(route)
        return _route_to_response(route)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Route creation failed", status.HTTP_409_CONFLICT)


async def list_routes(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID] = None,
    active_only: bool = True,
) -> List[TransportRouteResponse]:
    stmt = select(TransportRoute).where(TransportRoute.tenant_id == tenant_id)
    if academic_year_id is not None:
        stmt = stmt.where(TransportRoute.academic_year_id == academic_year_id)
    if active_only:
        stmt = stmt.where(TransportRoute.is_active.is_(True))
    stmt = stmt.order_by(TransportRoute.route_name)
    result = await db.execute(stmt)
    return [_route_to_response(r) for r in result.scalars().all()]


async def delete_route(
    db: AsyncSession,
    tenant_id: UUID,
    route_id: UUID,
) -> bool:
    """Permanent delete. Fails if any student/staff is assigned to this route."""
    result = await db.execute(
        select(TransportRoute).where(
            TransportRoute.id == route_id,
            TransportRoute.tenant_id == tenant_id,
        )
    )
    route = result.scalar_one_or_none()
    if not route:
        return False
    assignment_count = await db.execute(
        select(func.count()).select_from(TransportAssignment).where(
            TransportAssignment.route_id == route_id,
        )
    )
    if (assignment_count.scalar() or 0) > 0:
        raise ServiceError(
            "Cannot delete route: students or staff are assigned to this route. Remove all assignments first.",
            status.HTTP_409_CONFLICT,
        )
    await db.delete(route)
    await db.commit()
    return True


# ----- Vehicles -----

def _vehicle_to_response(v: TransportVehicle) -> TransportVehicleResponse:
    return TransportVehicleResponse(
        id=v.id,
        tenant_id=_to_uuid(v.tenant_id),
        academic_year_id=_to_uuid(v.academic_year_id),
        vehicle_number=v.vehicle_number,
        vehicle_type_id=_to_uuid(v.vehicle_type_id),
        capacity=v.capacity,
        driver_name=v.driver_name,
        insurance_expiry=v.insurance_expiry,
        fitness_expiry=v.fitness_expiry,
        is_active=v.is_active,
        created_at=v.created_at,
        updated_at=v.updated_at,
    )


async def create_vehicle(
    db: AsyncSession,
    tenant_id: UUID,
    payload: TransportVehicleCreate,
) -> TransportVehicleResponse:
    vt = await db.get(TransportVehicleType, payload.vehicle_type_id)
    if not vt or (vt.tenant_id is not None and vt.tenant_id != tenant_id):
        raise ServiceError("Invalid vehicle type", status.HTTP_400_BAD_REQUEST)
    existing = await db.execute(
        select(TransportVehicle).where(
            TransportVehicle.tenant_id == tenant_id,
            TransportVehicle.vehicle_number == payload.vehicle_number.strip().upper(),
        )
    )
    if existing.scalar_one_or_none():
        raise ServiceError("Vehicle number already exists for this tenant", status.HTTP_409_CONFLICT)
    vehicle = TransportVehicle(
        tenant_id=tenant_id,
        academic_year_id=payload.academic_year_id,
        vehicle_number=payload.vehicle_number.strip().upper(),
        vehicle_type_id=payload.vehicle_type_id,
        capacity=payload.capacity,
        driver_name=payload.driver_name.strip() if payload.driver_name else None,
        insurance_expiry=payload.insurance_expiry,
        fitness_expiry=payload.fitness_expiry,
        is_active=True,
    )
    db.add(vehicle)
    try:
        await db.commit()
        await db.refresh(vehicle)
        return _vehicle_to_response(vehicle)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Vehicle creation failed", status.HTTP_409_CONFLICT)


async def list_vehicles(
    db: AsyncSession,
    tenant_id: UUID,
    academic_year_id: Optional[UUID] = None,
    active_only: bool = True,
) -> List[TransportVehicleResponse]:
    stmt = select(TransportVehicle).where(TransportVehicle.tenant_id == tenant_id)
    if academic_year_id is not None:
        stmt = stmt.where(TransportVehicle.academic_year_id == academic_year_id)
    if active_only:
        stmt = stmt.where(TransportVehicle.is_active.is_(True))
    stmt = stmt.order_by(TransportVehicle.vehicle_number)
    result = await db.execute(stmt)
    return [_vehicle_to_response(v) for v in result.scalars().all()]


# ----- Subscription Plans -----

def _plan_to_response(p: TransportSubscriptionPlan) -> TransportSubscriptionPlanResponse:
    return TransportSubscriptionPlanResponse(
        id=p.id,
        tenant_id=_to_uuid(p.tenant_id),
        academic_year_id=_to_uuid(p.academic_year_id),
        route_id=_to_uuid(p.route_id),
        plan_name=p.plan_name,
        description=p.description,
        fee_amount=_to_decimal(p.fee_amount),
        billing_cycle=p.billing_cycle,
        is_default=p.is_default,
        is_active=p.is_active,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


async def create_subscription_plan(
    db: AsyncSession,
    tenant_id: UUID,
    payload: TransportSubscriptionPlanCreate,
) -> TransportSubscriptionPlanResponse:
    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    route = await db.get(TransportRoute, payload.route_id)
    if not route or route.tenant_id != tenant_id:
        raise ServiceError("Invalid route", status.HTTP_400_BAD_REQUEST)
    plan = TransportSubscriptionPlan(
        tenant_id=tenant_id,
        academic_year_id=payload.academic_year_id,
        route_id=payload.route_id,
        plan_name=payload.plan_name.strip(),
        description=payload.description.strip() if payload.description else None,
        fee_amount=payload.fee_amount,
        billing_cycle=payload.billing_cycle.strip().lower(),
        is_default=payload.is_default,
        is_active=True,
    )
    db.add(plan)
    try:
        await db.commit()
        await db.refresh(plan)
        return _plan_to_response(plan)
    except IntegrityError:
        await db.rollback()
        raise ServiceError("Subscription plan creation failed", status.HTTP_409_CONFLICT)


async def list_subscription_plans_by_route(
    db: AsyncSession,
    tenant_id: UUID,
    route_id: UUID,
    active_only: bool = True,
) -> List[TransportSubscriptionPlanResponse]:
    stmt = select(TransportSubscriptionPlan).where(
        TransportSubscriptionPlan.tenant_id == tenant_id,
        TransportSubscriptionPlan.route_id == route_id,
    )
    if active_only:
        stmt = stmt.where(TransportSubscriptionPlan.is_active.is_(True))
    stmt = stmt.order_by(TransportSubscriptionPlan.plan_name)
    result = await db.execute(stmt)
    return [_plan_to_response(p) for p in result.scalars().all()]


# ----- Assignments -----

def _assignment_to_response(a: TransportAssignment) -> TransportAssignmentResponse:
    return TransportAssignmentResponse(
        id=a.id,
        tenant_id=_to_uuid(a.tenant_id),
        academic_year_id=_to_uuid(a.academic_year_id),
        person_type=a.person_type,
        person_id=_to_uuid(a.person_id),
        route_id=_to_uuid(a.route_id),
        vehicle_id=_to_uuid(a.vehicle_id),
        subscription_plan_id=_to_uuid(a.subscription_plan_id),
        pickup_point=a.pickup_point,
        drop_point=a.drop_point,
        custom_fee=_to_decimal(a.custom_fee) if a.custom_fee is not None else None,
        fee_mode=a.fee_mode,
        start_date=a.start_date,
        end_date=a.end_date,
        is_active=a.is_active,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


async def _count_vehicle_assignments(
    db: AsyncSession,
    vehicle_id: UUID,
    academic_year_id: UUID,
    exclude_assignment_id: Optional[UUID] = None,
) -> int:
    stmt = select(func.count()).select_from(TransportAssignment).where(
        TransportAssignment.vehicle_id == vehicle_id,
        TransportAssignment.academic_year_id == academic_year_id,
        TransportAssignment.is_active.is_(True),
    )
    if exclude_assignment_id is not None:
        stmt = stmt.where(TransportAssignment.id != exclude_assignment_id)
    result = await db.execute(stmt)
    return result.scalar() or 0


async def assign_transport(
    db: AsyncSession,
    tenant_id: UUID,
    payload: TransportAssignCreate,
) -> TransportAssignmentResponse:
    ay = await db.get(AcademicYear, payload.academic_year_id)
    if not ay or ay.tenant_id != tenant_id:
        raise ServiceError("Invalid academic year", status.HTTP_400_BAD_REQUEST)
    route = await db.get(TransportRoute, payload.route_id)
    if not route or route.tenant_id != tenant_id:
        raise ServiceError("Invalid route", status.HTTP_400_BAD_REQUEST)
    existing = await db.execute(
        select(TransportAssignment).where(
            TransportAssignment.tenant_id == tenant_id,
            TransportAssignment.academic_year_id == payload.academic_year_id,
            TransportAssignment.person_id == payload.person_id,
            TransportAssignment.person_type == payload.person_type.value,
            TransportAssignment.is_active.is_(True),
        )
    )
    if existing.scalar_one_or_none():
        raise ServiceError("Person already has an active transport assignment for this academic year", status.HTTP_409_CONFLICT)
    vehicle = None
    if payload.vehicle_id:
        vehicle = await db.get(TransportVehicle, payload.vehicle_id)
        if not vehicle or vehicle.tenant_id != tenant_id:
            raise ServiceError("Invalid vehicle", status.HTTP_400_BAD_REQUEST)
        current_count = await _count_vehicle_assignments(db, payload.vehicle_id, payload.academic_year_id, None)
        if current_count >= vehicle.capacity:
            raise ServiceError("Vehicle at capacity", status.HTTP_400_BAD_REQUEST)
    plan = None
    if payload.subscription_plan_id:
        plan = await db.get(TransportSubscriptionPlan, payload.subscription_plan_id)
        if not plan or plan.tenant_id != tenant_id:
            raise ServiceError("Invalid subscription plan", status.HTTP_400_BAD_REQUEST)
    assignment = TransportAssignment(
        tenant_id=tenant_id,
        academic_year_id=payload.academic_year_id,
        person_type=payload.person_type.value,
        person_id=payload.person_id,
        route_id=payload.route_id,
        vehicle_id=payload.vehicle_id,
        subscription_plan_id=payload.subscription_plan_id,
        pickup_point=payload.pickup_point.strip() if payload.pickup_point else None,
        drop_point=payload.drop_point.strip() if payload.drop_point else None,
        custom_fee=payload.custom_fee,
        fee_mode=payload.fee_mode.value,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_active=True,
    )
    db.add(assignment)
    await db.flush()
    if payload.person_type == PersonType.STUDENT and payload.fee_mode == FeeMode.STUDENT_FEE:
        amount = payload.custom_fee if payload.custom_fee is not None else (plan.fee_amount if plan else Decimal("0"))
        await create_student_fee_item(
            tenant_id=tenant_id,
            academic_year_id=payload.academic_year_id,
            student_id=payload.person_id,
            amount=amount,
            description=f"Transport: {route.route_name}",
        )
    if payload.person_type in (PersonType.TEACHER, PersonType.STAFF) and payload.fee_mode == FeeMode.SALARY_DEDUCTION:
        amount = payload.custom_fee if payload.custom_fee is not None else (plan.fee_amount if plan else Decimal("0"))
        await create_salary_deduction_entry(
            tenant_id=tenant_id,
            academic_year_id=payload.academic_year_id,
            person_id=payload.person_id,
            person_type=payload.person_type.value,
            amount=amount,
            description=f"Transport: {route.route_name}",
        )
    await db.commit()
    await db.refresh(assignment)
    return _assignment_to_response(assignment)


async def remove_assignment(
    db: AsyncSession,
    tenant_id: UUID,
    assignment_id: UUID,
) -> bool:
    result = await db.execute(
        select(TransportAssignment).where(
            TransportAssignment.id == assignment_id,
            TransportAssignment.tenant_id == tenant_id,
        )
    )
    a = result.scalar_one_or_none()
    if not a:
        return False
    a.is_active = False
    await db.commit()
    return True


async def get_person_transport(
    db: AsyncSession,
    tenant_id: UUID,
    person_type: str,
    person_id: UUID,
    academic_year_id: Optional[UUID] = None,
) -> Optional[TransportAssignmentResponse]:
    stmt = select(TransportAssignment).where(
        TransportAssignment.tenant_id == tenant_id,
        TransportAssignment.person_id == person_id,
        TransportAssignment.person_type == person_type.upper(),
        TransportAssignment.is_active.is_(True),
    )
    if academic_year_id is not None:
        stmt = stmt.where(TransportAssignment.academic_year_id == academic_year_id)
    result = await db.execute(stmt)
    a = result.scalar_one_or_none()
    return _assignment_to_response(a) if a else None


async def get_route_assignments(
    db: AsyncSession,
    tenant_id: UUID,
    route_id: UUID,
    academic_year_id: Optional[UUID] = None,
    active_only: bool = True,
) -> List[TransportAssignmentResponse]:
    stmt = select(TransportAssignment).where(
        TransportAssignment.tenant_id == tenant_id,
        TransportAssignment.route_id == route_id,
    )
    if academic_year_id is not None:
        stmt = stmt.where(TransportAssignment.academic_year_id == academic_year_id)
    if active_only:
        stmt = stmt.where(TransportAssignment.is_active.is_(True))
    stmt = stmt.order_by(TransportAssignment.person_type, TransportAssignment.person_id)
    result = await db.execute(stmt)
    return [_assignment_to_response(a) for a in result.scalars().all()]


async def calculate_transport_fee(
    db: AsyncSession,
    tenant_id: UUID,
    assignment_id: UUID,
) -> Optional[TransportFeeResult]:
    result = await db.execute(
        select(TransportAssignment).where(
            TransportAssignment.id == assignment_id,
            TransportAssignment.tenant_id == tenant_id,
            TransportAssignment.is_active.is_(True),
        )
    )
    a = result.scalar_one_or_none()
    if not a:
        return None
    plan = await db.get(TransportSubscriptionPlan, a.subscription_plan_id) if a.subscription_plan_id else None
    plan_fee = _to_decimal(plan.fee_amount) if plan else None
    effective = _to_decimal(a.custom_fee) if a.custom_fee is not None else (plan_fee or Decimal("0"))
    return TransportFeeResult(
        person_id=a.person_id,
        person_type=a.person_type,
        assignment_id=a.id,
        effective_fee=effective,
        fee_mode=a.fee_mode,
        custom_fee=_to_decimal(a.custom_fee) if a.custom_fee is not None else None,
        plan_fee=plan_fee,
    )
