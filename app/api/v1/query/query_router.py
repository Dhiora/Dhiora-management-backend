"""Global query API: POST /api/v1/query with pagination, filters, and sort."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from .schemas import GlobalQueryRequest, PaginatedResponse
from . import service

router = APIRouter(prefix="/api/v1/query", tags=["query"])


def _check_read_permission(current_user: CurrentUser, resource_type: str) -> None:
    """Raise 403 if current user does not have read permission for the resource type."""
    if current_user.role in ("SUPER_ADMIN", "PLATFORM_ADMIN"):
        return
    module_perms = (current_user.permissions or {}).get(resource_type, {})
    if not module_perms.get("read", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to query this resource",
        )


@router.post("", response_model=PaginatedResponse)
async def global_query(
    body: GlobalQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> PaginatedResponse:
    """
    Query a resource with pagination, filters, and sort.

    - **resource_type**: one of `departments`, `classes`, `sections`, `employees`, `students`
    - **pagination**: optional; defaults to page=1, page_size=20 (max 100)
    - **sort**: optional list of { field, direction }; resource default if omitted
    - **filters**: optional list of { field, operator, value }; operators: eq, ne, gt, gte, lt, lte, like, ilike, in, is_null, is_not_null
    - **search**: optional text; backend searches (case-insensitive) across its configured fields for this resource. Response includes **search_fields** (list of fields searched) set by the backend.
    """
    _check_read_permission(current_user, body.resource_type)

    pagination = body.pagination
    page = pagination.page if pagination else 1
    page_size = pagination.page_size if pagination else 20

    try:
        return await service.run_global_query(
            db,
            current_user.tenant_id,
            resource_type=body.resource_type,
            page=page,
            page_size=page_size,
            sort=body.sort,
            filters=body.filters,
            search=body.search,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
