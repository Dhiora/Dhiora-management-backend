from typing import Dict

from fastapi import Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser


async def require_platform_admin(
    current_user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Require PLATFORM_ADMIN or SUPER_ADMIN role. Used for platform-wide config (e.g. modules by org type)."""
    if current_user.role not in ("SUPER_ADMIN", "PLATFORM_ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Platform Admin can perform this action",
        )
    return current_user


def check_permission(module: str, action: str):
    """
    Dependency factory to enforce a specific permission.

    Example:
        Depends(check_permission("roles", "create"))
    """

    async def _checker(current_user: CurrentUser = Depends(get_current_user)) -> None:
        if current_user.role in ("SUPER_ADMIN", "PLATFORM_ADMIN"):
            return
        permissions: Dict[str, Dict[str, bool]] = current_user.permissions or {}
        module_perms = permissions.get(module, {})
        if not module_perms.get(action, False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

    return _checker

