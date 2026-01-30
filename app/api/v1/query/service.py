"""Global query service: paginated, filterable, sortable queries across resources."""

from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.departments.schemas import DepartmentResponse
from app.api.v1.classes.schemas import ClassResponse
from app.api.v1.sections.schemas import SectionResponse
from app.api.v1.modules.users import service as user_service
from app.auth.models import StaffProfile, StudentProfile, User
from app.core.models import Department, SchoolClass, Section

from .schemas import FilterItem, FilterOperator, PaginatedResponse, SortDirection, SortItem


def _to_uuid(val) -> Optional[UUID]:
    if val is None:
        return None
    return val if isinstance(val, UUID) else UUID(str(val))


# ----- Resource registry -----
# (allowed_filter_fields, allowed_sort_fields, default_sort, searchable_fields)
# searchable_fields = text/string columns that can be used for global search (ilike).

_RESOURCE_CONFIG: Dict[
    str,
    Tuple[Set[str], Set[str], List[Tuple[str, SortDirection]], Set[str]],
] = {
    "departments": (
        {"code", "name", "description", "is_active", "created_at", "updated_at"},
        {"code", "name", "is_active", "created_at", "updated_at"},
        [("name", SortDirection.ASC)],
        {"code", "name", "description"},
    ),
    "classes": (
        {"name", "display_order", "is_active", "created_at", "updated_at"},
        {"name", "display_order", "is_active", "created_at", "updated_at"},
        [("display_order", SortDirection.ASC), ("name", SortDirection.ASC)],
        {"name"},
    ),
    "sections": (
        {"class_id", "name", "display_order", "is_active", "created_at", "updated_at"},
        {"class_id", "name", "display_order", "is_active", "created_at", "updated_at"},
        [("display_order", SortDirection.ASC), ("name", SortDirection.ASC)],
        {"name"},
    ),
    "employees": (
        # filter fields: User + StaffProfile
        {"full_name", "email", "mobile", "role", "role_id", "status", "created_at", "employee_code", "designation", "department_id", "join_date"},
        {"full_name", "email", "mobile", "role", "status", "created_at", "employee_code", "designation", "department_id", "join_date"},
        [("full_name", SortDirection.ASC)],
        {"full_name", "email", "mobile", "role", "employee_code", "designation"},
    ),
    "students": (
        # filter fields: User + StudentProfile
        {"full_name", "email", "mobile", "status", "created_at", "roll_number", "class_id", "section_id"},
        {"full_name", "email", "status", "created_at", "roll_number", "class_id", "section_id"},
        [("full_name", SortDirection.ASC)],
        {"full_name", "email", "mobile", "roll_number"},
    ),
}


def _get_model_and_tenant_attr(resource_type: str):
    """Return (model_class, tenant_column) for the resource. For User-based resources, tenant_column is User.tenant_id."""
    if resource_type == "departments":
        return Department, Department.tenant_id
    if resource_type == "classes":
        return SchoolClass, SchoolClass.tenant_id
    if resource_type == "sections":
        return Section, Section.tenant_id
    if resource_type in ("employees", "students"):
        return User, User.tenant_id
    return None, None


# Column resolver: for employees/students some fields are on User, some on StaffProfile/StudentProfile.
# Returns (column, None) for simple resources; for User+profile we use _get_column_for_resource.
def _get_column_for_resource(resource_type: str, field: str, allowed: Set[str]):
    """Return the SQLAlchemy column for the field on this resource, or None if not allowed or unknown."""
    if field not in allowed:
        return None
    if resource_type == "departments":
        return getattr(Department, field, None)
    if resource_type == "classes":
        return getattr(SchoolClass, field, None)
    if resource_type == "sections":
        return getattr(Section, field, None)
    if resource_type == "employees":
        user_fields = {"full_name", "email", "mobile", "role", "role_id", "status", "created_at"}
        if field in user_fields:
            return getattr(User, field, None)
        return getattr(StaffProfile, field, None)  # employee_code, designation, department_id, join_date
    if resource_type == "students":
        user_fields = {"full_name", "email", "mobile", "status", "created_at"}
        if field in user_fields:
            return getattr(User, field, None)
        return getattr(StudentProfile, field, None)  # roll_number, class_id, section_id
    return None


def _build_base_stmt(resource_type: str, tenant_id: UUID):
    """Build base select statement for the resource (tenant-scoped). Joins profile tables for employees/students so profile fields can be filtered/sorted."""
    if resource_type == "departments":
        return select(Department).where(Department.tenant_id == tenant_id)
    if resource_type == "classes":
        return select(SchoolClass).where(SchoolClass.tenant_id == tenant_id)
    if resource_type == "sections":
        return select(Section).where(Section.tenant_id == tenant_id)
    if resource_type == "employees":
        return (
            select(User)
            .join(StaffProfile, User.id == StaffProfile.user_id)
            .where(User.tenant_id == tenant_id, User.user_type == "employee")
            .options(selectinload(User.staff_profile))
        )
    if resource_type == "students":
        return (
            select(User)
            .join(StudentProfile, User.id == StudentProfile.user_id)
            .where(User.tenant_id == tenant_id, User.user_type == "student")
            .options(selectinload(User.student_profile))
        )
    return None


def _row_to_item(resource_type: str, row: Any) -> Dict[str, Any]:
    """Convert ORM row to response dict for PaginatedResponse.items."""
    if resource_type == "departments":
        d = row
        return DepartmentResponse(
            id=_to_uuid(d.id),
            tenant_id=_to_uuid(d.tenant_id),
            code=d.code,
            name=d.name,
            description=d.description,
            is_active=d.is_active,
            created_at=d.created_at,
            updated_at=d.updated_at,
        ).model_dump()
    if resource_type == "classes":
        c = row
        return ClassResponse(
            id=_to_uuid(c.id),
            tenant_id=_to_uuid(c.tenant_id),
            name=c.name,
            display_order=c.display_order,
            is_active=c.is_active,
            created_at=c.created_at,
            updated_at=c.updated_at,
        ).model_dump()
    if resource_type == "sections":
        s = row
        return SectionResponse(
            id=_to_uuid(s.id),
            tenant_id=_to_uuid(s.tenant_id),
            class_id=_to_uuid(s.class_id),
            name=s.name,
            display_order=s.display_order,
            is_active=s.is_active,
            created_at=s.created_at,
            updated_at=s.updated_at,
        ).model_dump()
    if resource_type == "employees":
        return user_service._user_to_employee_response(row).model_dump()
    if resource_type == "students":
        return user_service._user_to_student_response(row).model_dump()
    return {}


def _apply_filter(stmt, resource_type: str, filter_item: FilterItem, allowed: Set[str]):
    """Apply a single filter to the statement. Uses column resolver for this resource (User + profile for employees/students)."""
    col = _get_column_for_resource(resource_type, filter_item.field, allowed)
    if col is None:
        return stmt
    op = filter_item.operator
    val = filter_item.value
    if op == FilterOperator.IS_NULL:
        return stmt.where(col.is_(None))
    if op == FilterOperator.IS_NOT_NULL:
        return stmt.where(col.isnot(None))
    if op in (FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL):
        return stmt
    if val is None and op not in (FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL):
        return stmt
    if op == FilterOperator.EQ:
        return stmt.where(col == val)
    if op == FilterOperator.NE:
        return stmt.where(col != val)
    if op == FilterOperator.GT:
        return stmt.where(col > val)
    if op == FilterOperator.GTE:
        return stmt.where(col >= val)
    if op == FilterOperator.LT:
        return stmt.where(col < val)
    if op == FilterOperator.LTE:
        return stmt.where(col <= val)
    if op == FilterOperator.LIKE:
        return stmt.where(col.like(val))
    if op == FilterOperator.ILIKE:
        return stmt.where(col.ilike(val))
    if op == FilterOperator.IN:
        if not isinstance(val, list):
            val = [val]
        return stmt.where(col.in_(val))
    return stmt


def _apply_filters(stmt, resource_type: str, filters: Optional[List[FilterItem]], allowed: Set[str]):
    """Apply all filters to the statement."""
    if not filters or not allowed:
        return stmt
    for f in filters:
        stmt = _apply_filter(stmt, resource_type, f, allowed)
    return stmt


def _apply_search(stmt, resource_type: str, search_term: str, searchable: Set[str]) -> Tuple[Any, List[str]]:
    """
    Apply global search: term is matched (case-insensitive ilike %term%) on all
    searchable fields (defined by backend per resource). Returns (stmt, list of fields used).
    """
    term = (search_term or "").strip()
    if not term:
        return stmt, []
    pattern = f"%{term}%"
    clauses = []
    fields_used: List[str] = []
    for field in sorted(searchable):
        col = _get_column_for_resource(resource_type, field, searchable)
        if col is not None:
            clauses.append(col.ilike(pattern))
            fields_used.append(field)
    if not clauses:
        return stmt, []
    return stmt.where(or_(*clauses)), fields_used


def _apply_sort(stmt, resource_type: str, sort: Optional[List[SortItem]], allowed: Set[str], default_order: List[Tuple[str, SortDirection]]):
    """Apply sort to the statement using column resolver for this resource."""
    order_specs = []
    if sort:
        for s in sort:
            col = _get_column_for_resource(resource_type, s.field, allowed)
            if col is not None:
                order_specs.append((col, s.direction))
    if not order_specs and default_order:
        for field, direction in default_order:
            col = _get_column_for_resource(resource_type, field, allowed)
            if col is not None:
                order_specs.append((col, direction))
    if order_specs:
        order_clauses = [c.asc() if d == SortDirection.ASC else c.desc() for c, d in order_specs]
        stmt = stmt.order_by(*order_clauses)
    return stmt


async def run_global_query(
    db: AsyncSession,
    tenant_id: UUID,
    resource_type: str,
    page: int = 1,
    page_size: int = 20,
    sort: Optional[List[SortItem]] = None,
    filters: Optional[List[FilterItem]] = None,
    search: Optional[str] = None,
) -> PaginatedResponse:
    """
    Execute a global query for the given resource type with pagination, sort, filters, and optional search.
    When search is set, the backend searches (case-insensitive) across its configured searchable fields for that resource.
    Returns PaginatedResponse with items and, when search was used, search_fields (list of fields searched) set by backend.
    """
    resource_type = resource_type.strip().lower()
    if resource_type not in _RESOURCE_CONFIG:
        from app.core.exceptions import ServiceError
        from fastapi import status
        raise ServiceError(
            f"Unknown resource_type: {resource_type}. Allowed: {', '.join(_RESOURCE_CONFIG.keys())}",
            status.HTTP_400_BAD_REQUEST,
        )
    allowed_filter, allowed_sort, default_order, searchable_fields = _RESOURCE_CONFIG[resource_type]
    base = _build_base_stmt(resource_type, tenant_id)
    stmt = _apply_filters(base, resource_type, filters, allowed_filter)
    stmt, search_fields_used = _apply_search(stmt, resource_type, search or "", searchable_fields)
    stmt = _apply_sort(stmt, resource_type, sort, allowed_sort, default_order)

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    items = [_row_to_item(resource_type, row) for row in rows]
    total_pages = (total + page_size - 1) // page_size if page_size else 0

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        search_fields=search_fields_used if search_fields_used else None,
    )
