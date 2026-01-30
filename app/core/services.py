from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import ServiceError
from app.core.models import Module, OrganizationTypeModule
from app.core.schemas import (
    ModuleInfo,
    ModulesByOrganizationTypeResponse,
    OrganizationTypeModuleInfo,
)


def _build_module_info(module: Module) -> ModuleInfo:
    """Helper to build ModuleInfo from Module model."""
    return ModuleInfo(
        id=module.id,
        module_key=module.module_key,
        module_name=module.module_name,
        module_domain=module.module_domain,
        description=module.description,
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
