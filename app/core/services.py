from typing import Optional
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ServiceError
from app.core.models import Module, OrganizationTypeModule, SubscriptionPlan
from app.core.schemas import (
    ModuleInfo,
    ModulesByOrganizationTypeResponse,
    OrganizationTypeModuleInfo,
    OrganizationTypeModuleCreate,
    OrganizationTypeModuleResponse,
    OrganizationTypeModuleUpdate,
    SubscriptionPlanCreate,
    SubscriptionPlanResponse,
    SubscriptionPlanUpdate,
)


def _build_module_info(module: Module) -> ModuleInfo:
    """Helper to build ModuleInfo from Module model."""
    return ModuleInfo(
        id=module.id,
        module_key=module.module_key,
        module_name=module.module_name,
        module_domain=module.module_domain,
        description=module.description,
        price=getattr(module, "price", None) or "0",
        is_active=module.is_active,
    )


async def get_modules_by_organization_type(
    db: AsyncSession, organization_type: str
) -> ModulesByOrganizationTypeResponse:
    """Fetch all modules for an organization type (HRMS + org-specific)."""
    modules_dict: dict[str, OrganizationTypeModuleInfo] = {}

    # Get all HRMS modules (always included)
    hrms_modules = await db.execute(
        select(Module).where(Module.module_domain == "HRMS", Module.is_active == True).order_by(Module.module_key)  # noqa: E712
    )
    for module in hrms_modules.scalars().all():
        org_mapping = await db.execute(
            select(OrganizationTypeModule).where(
                OrganizationTypeModule.organization_type == organization_type,
                OrganizationTypeModule.module_key == module.module_key,
            )
        )
        mapping = org_mapping.scalar_one_or_none()
        modules_dict[module.module_key] = OrganizationTypeModuleInfo(
            module=_build_module_info(module),
            is_default=mapping.is_default if mapping else True,
            is_enabled=mapping.is_enabled if mapping else True,
        )

    # Get organization-specific modules (excluding HRMS)
    org_modules = await db.execute(
        select(OrganizationTypeModule)
        .options(joinedload(OrganizationTypeModule.module))
        .where(
            OrganizationTypeModule.organization_type == organization_type,
            OrganizationTypeModule.is_enabled == True,  # noqa: E712
        )
        .order_by(OrganizationTypeModule.module_key)
    )
    for otm in org_modules.unique().scalars().all():
        module = otm.module
        if module and module.is_active and module.module_domain != "HRMS":
            modules_dict[module.module_key] = OrganizationTypeModuleInfo(
                module=_build_module_info(module),
                is_default=otm.is_default,
                is_enabled=otm.is_enabled,
            )

    if not modules_dict:
        raise ServiceError(
            f"No modules found for organization type: {organization_type}",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return ModulesByOrganizationTypeResponse(
        organization_type=organization_type,
        modules=sorted(modules_dict.values(), key=lambda x: x.module.module_key),
    )


async def create_organization_type_module(
    db: AsyncSession, payload: OrganizationTypeModuleCreate
) -> OrganizationTypeModuleResponse:
    """Create a mapping of a module to an organization type. Module must exist in core.modules."""
    # Ensure module exists
    mod_result = await db.execute(
        select(Module).where(
            Module.module_key == payload.module_key,
            Module.is_active == True,  # noqa: E712
        )
    )
    module = mod_result.scalar_one_or_none()
    if not module:
        raise ServiceError(
            f"Module '{payload.module_key}' not found or inactive",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    # Check duplicate mapping
    existing = await db.execute(
        select(OrganizationTypeModule).where(
            OrganizationTypeModule.organization_type == payload.organization_type,
            OrganizationTypeModule.module_key == payload.module_key,
        )
    )
    if existing.scalar_one_or_none():
        raise ServiceError(
            f"Mapping already exists for organization_type={payload.organization_type}, module_key={payload.module_key}",
            status_code=status.HTTP_409_CONFLICT,
        )
    mapping = OrganizationTypeModule(
        organization_type=payload.organization_type,
        module_key=payload.module_key,
        is_default=payload.is_default,
        is_enabled=payload.is_enabled,
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    return OrganizationTypeModuleResponse(
        id=mapping.id,
        organization_type=mapping.organization_type,
        module_key=mapping.module_key,
        is_default=mapping.is_default,
        is_enabled=mapping.is_enabled,
    )


async def update_organization_type_module(
    db: AsyncSession, mapping_id: "UUID", payload: OrganizationTypeModuleUpdate
) -> OrganizationTypeModuleResponse:
    """Update is_default and/or is_enabled for an organization-type-module mapping."""
    result = await db.execute(
        select(OrganizationTypeModule).where(OrganizationTypeModule.id == mapping_id)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise ServiceError(
            f"Organization-type-module mapping not found: {mapping_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if payload.is_default is not None:
        mapping.is_default = payload.is_default
    if payload.is_enabled is not None:
        mapping.is_enabled = payload.is_enabled
    await db.commit()
    await db.refresh(mapping)
    return OrganizationTypeModuleResponse(
        id=mapping.id,
        organization_type=mapping.organization_type,
        module_key=mapping.module_key,
        is_default=mapping.is_default,
        is_enabled=mapping.is_enabled,
    )


async def delete_organization_type_module(
    db: AsyncSession, mapping_id: "UUID"
) -> None:
    """Delete an organization-type-module mapping by id."""
    result = await db.execute(
        select(OrganizationTypeModule).where(OrganizationTypeModule.id == mapping_id)
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise ServiceError(
            f"Organization-type-module mapping not found: {mapping_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await db.delete(mapping)
    await db.commit()


# --- Subscription plans ---


def _subscription_plan_to_response(plan: SubscriptionPlan) -> SubscriptionPlanResponse:
    """Build SubscriptionPlanResponse from model. Coerce modules_include to List[UUID]."""
    raw = plan.modules_include or []
    module_ids = [UUID(str(x)) for x in raw] if raw else []
    return SubscriptionPlanResponse(
        id=plan.id,
        name=plan.name,
        organization_type=getattr(plan, "organization_type", "School") or "School",
        modules_include=module_ids,
        price=plan.price or "",
        discount_price=plan.discount_price,
        description=plan.description,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


async def list_subscription_plans(
    db: AsyncSession,
    organization_type: Optional[str] = None,
) -> list[SubscriptionPlanResponse]:
    """List subscription plans, optionally filtered by organization type (School, College, etc.). No auth required."""
    stmt = select(SubscriptionPlan).order_by(SubscriptionPlan.organization_type, SubscriptionPlan.name)
    if organization_type:
        stmt = stmt.where(SubscriptionPlan.organization_type == organization_type)
    result = await db.execute(stmt)
    plans = result.scalars().all()
    return [_subscription_plan_to_response(p) for p in plans]


async def get_subscription_plan(
    db: AsyncSession, plan_id: UUID
) -> SubscriptionPlanResponse:
    """Get a single subscription plan by id. No auth required."""
    result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise ServiceError(
            f"Subscription plan not found: {plan_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return _subscription_plan_to_response(plan)


async def create_subscription_plan(
    db: AsyncSession, payload: SubscriptionPlanCreate
) -> SubscriptionPlanResponse:
    """Create a subscription plan. Platform Admin only."""
    # Optional: validate all module IDs exist
    if payload.modules_include:
        mod_result = await db.execute(
            select(Module.id).where(
                Module.id.in_(payload.modules_include),
                Module.is_active == True,  # noqa: E712
            )
        )
        found_ids = {row[0] for row in mod_result.all()}
        missing = set(payload.modules_include) - found_ids
        if missing:
            raise ServiceError(
                f"Module(s) not found or inactive: {list(missing)}",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    # Check duplicate (name, organization_type)
    existing = await db.execute(
        select(SubscriptionPlan).where(
            SubscriptionPlan.name == payload.name,
            SubscriptionPlan.organization_type == payload.organization_type,
        )
    )
    if existing.scalar_one_or_none():
        raise ServiceError(
            f"Subscription plan '{payload.name}' already exists for organization type '{payload.organization_type}'",
            status_code=status.HTTP_409_CONFLICT,
        )
    plan = SubscriptionPlan(
        name=payload.name,
        organization_type=payload.organization_type,
        modules_include=[str(u) for u in payload.modules_include],
        price=payload.price,
        discount_price=payload.discount_price,
        description=payload.description,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return _subscription_plan_to_response(plan)


async def update_subscription_plan(
    db: AsyncSession, plan_id: UUID, payload: SubscriptionPlanUpdate
) -> SubscriptionPlanResponse:
    """Update a subscription plan. Platform Admin only."""
    result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise ServiceError(
            f"Subscription plan not found: {plan_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    org_type = payload.organization_type if payload.organization_type is not None else plan.organization_type
    plan_name = payload.name if payload.name is not None else plan.name
    if payload.name is not None or payload.organization_type is not None:
        # Check (name, organization_type) unique when changing
        if plan_name != plan.name or org_type != plan.organization_type:
            existing = await db.execute(
                select(SubscriptionPlan).where(
                    SubscriptionPlan.name == plan_name,
                    SubscriptionPlan.organization_type == org_type,
                    SubscriptionPlan.id != plan_id,
                )
            )
            if existing.scalar_one_or_none():
                raise ServiceError(
                    f"Subscription plan '{plan_name}' already exists for organization type '{org_type}'",
                    status_code=status.HTTP_409_CONFLICT,
                )
        if payload.name is not None:
            plan.name = payload.name
        if payload.organization_type is not None:
            plan.organization_type = payload.organization_type
    if payload.modules_include is not None:
        # Validate module IDs exist
        if payload.modules_include:
            mod_result = await db.execute(
                select(Module.id).where(
                    Module.id.in_(payload.modules_include),
                    Module.is_active == True,  # noqa: E712
                )
            )
            found_ids = {row[0] for row in mod_result.all()}
            missing = set(payload.modules_include) - found_ids
            if missing:
                raise ServiceError(
                    f"Module(s) not found or inactive: {list(missing)}",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        plan.modules_include = [str(u) for u in payload.modules_include]
    if payload.price is not None:
        plan.price = payload.price
    if payload.discount_price is not None:
        plan.discount_price = payload.discount_price
    if payload.description is not None:
        plan.description = payload.description
    await db.commit()
    await db.refresh(plan)
    return _subscription_plan_to_response(plan)


async def delete_subscription_plan(db: AsyncSession, plan_id: UUID) -> None:
    """Delete a subscription plan. Platform Admin only."""
    result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise ServiceError(
            f"Subscription plan not found: {plan_id}",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await db.delete(plan)
    await db.commit()
