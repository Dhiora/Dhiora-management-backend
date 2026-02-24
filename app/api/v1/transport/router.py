from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_writable_academic_year
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

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
from . import service

router = APIRouter(prefix="/api/v1/transport", tags=["transport"])


# ----- Vehicle Types -----

@router.post(
    "/vehicle-types",
    response_model=TransportVehicleTypeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("transport", "create"))],
)
async def create_vehicle_type(
    payload: TransportVehicleTypeCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TransportVehicleTypeResponse:
    try:
        return await service.create_vehicle_type(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/vehicle-types",
    response_model=List[TransportVehicleTypeResponse],
    dependencies=[Depends(check_permission("transport", "read"))],
)
async def list_vehicle_types(
    active_only: bool = Query(True, description="Return only active types"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[TransportVehicleTypeResponse]:
    return await service.list_vehicle_types(db, current_user.tenant_id, active_only=active_only)


@router.put(
    "/vehicle-types/{vehicle_type_id}",
    response_model=TransportVehicleTypeResponse,
    dependencies=[Depends(check_permission("transport", "update"))],
)
async def update_vehicle_type(
    vehicle_type_id: UUID,
    payload: TransportVehicleTypeUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TransportVehicleTypeResponse:
    result = await service.update_vehicle_type(db, current_user.tenant_id, vehicle_type_id, payload)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle type not found")
    return result


@router.delete(
    "/vehicle-types/{vehicle_type_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("transport", "delete"))],
)
async def delete_vehicle_type(
    vehicle_type_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        deleted = await service.delete_vehicle_type(db, current_user.tenant_id, vehicle_type_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle type not found")
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Routes -----

@router.post(
    "/routes",
    response_model=TransportRouteResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("transport", "create")), Depends(require_writable_academic_year)],
)
async def create_route(
    payload: TransportRouteCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TransportRouteResponse:
    try:
        return await service.create_route(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/routes",
    response_model=List[TransportRouteResponse],
    dependencies=[Depends(check_permission("transport", "read"))],
)
async def list_routes(
    academic_year_id: Optional[UUID] = Query(None),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[TransportRouteResponse]:
    return await service.list_routes(
        db, current_user.tenant_id, academic_year_id=academic_year_id, active_only=active_only
    )


@router.delete(
    "/routes/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("transport", "delete")), Depends(require_writable_academic_year)],
)
async def delete_route(
    route_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Permanent delete. Returns 409 if any student or staff is assigned to this route."""
    try:
        deleted = await service.delete_route(db, current_user.tenant_id, route_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Route not found")
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ----- Vehicles -----

@router.post(
    "/vehicles",
    response_model=TransportVehicleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("transport", "create"))],
)
async def create_vehicle(
    payload: TransportVehicleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TransportVehicleResponse:
    try:
        return await service.create_vehicle(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/vehicles",
    response_model=List[TransportVehicleResponse],
    dependencies=[Depends(check_permission("transport", "read"))],
)
async def list_vehicles(
    academic_year_id: Optional[UUID] = Query(None),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[TransportVehicleResponse]:
    return await service.list_vehicles(
        db, current_user.tenant_id, academic_year_id=academic_year_id, active_only=active_only
    )


# ----- Subscription Plans -----

@router.post(
    "/subscription-plans",
    response_model=TransportSubscriptionPlanResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("transport", "create")), Depends(require_writable_academic_year)],
)
async def create_subscription_plan(
    payload: TransportSubscriptionPlanCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TransportSubscriptionPlanResponse:
    try:
        return await service.create_subscription_plan(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/subscription-plans/{route_id}",
    response_model=List[TransportSubscriptionPlanResponse],
    dependencies=[Depends(check_permission("transport", "read"))],
)
async def list_subscription_plans_by_route(
    route_id: UUID,
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[TransportSubscriptionPlanResponse]:
    return await service.list_subscription_plans_by_route(
        db, current_user.tenant_id, route_id, active_only=active_only
    )


# ----- Assignments -----

@router.post(
    "/assign",
    response_model=TransportAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("transport", "create")), Depends(require_writable_academic_year)],
)
async def assign_transport(
    payload: TransportAssignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TransportAssignmentResponse:
    try:
        return await service.assign_transport(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/assign/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("transport", "delete")), Depends(require_writable_academic_year)],
)
async def remove_assignment(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    removed = await service.remove_assignment(db, current_user.tenant_id, assignment_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")


@router.get(
    "/person/{person_type}/{person_id}",
    response_model=TransportAssignmentResponse,
    dependencies=[Depends(check_permission("transport", "read"))],
)
async def get_person_transport(
    person_type: str,
    person_id: UUID,
    academic_year_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> TransportAssignmentResponse:
    result = await service.get_person_transport(
        db, current_user.tenant_id, person_type, person_id, academic_year_id=academic_year_id
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No transport assignment found for this person")
    return result


@router.get(
    "/route/{route_id}/assignments",
    response_model=List[TransportAssignmentResponse],
    dependencies=[Depends(check_permission("transport", "read"))],
)
async def get_route_assignments(
    route_id: UUID,
    academic_year_id: Optional[UUID] = Query(None),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[TransportAssignmentResponse]:
    return await service.get_route_assignments(
        db, current_user.tenant_id, route_id, academic_year_id=academic_year_id, active_only=active_only
    )


@router.get(
    "/assignment/{assignment_id}/fee",
    response_model=Optional[TransportFeeResult],
    dependencies=[Depends(check_permission("transport", "read"))],
)
async def calculate_transport_fee(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Optional[TransportFeeResult]:
    result = await service.calculate_transport_fee(db, current_user.tenant_id, assignment_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return result
