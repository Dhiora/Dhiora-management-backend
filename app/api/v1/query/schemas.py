"""Global query API: pagination, filters, and sort schemas."""

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class FilterOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    LIKE = "like"
    ILIKE = "ilike"
    IN = "in"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class FilterItem(BaseModel):
    """Single filter: field, operator, and optional value (not used for is_null / is_not_null)."""

    field: str = Field(..., min_length=1, description="Column name to filter on")
    operator: FilterOperator
    value: Optional[Any] = Field(None, description="Value for comparison; omit for is_null / is_not_null")


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class SortItem(BaseModel):
    """Sort by one field."""

    field: str = Field(..., min_length=1, description="Column name to sort by")
    direction: SortDirection = SortDirection.ASC


class PaginationParams(BaseModel):
    """Pagination for query results."""

    page: int = Field(1, ge=1, description="1-based page number")
    page_size: int = Field(20, ge=1, le=100, description="Items per page (max 100)")


class ResourceQueryRequest(BaseModel):
    """POST body for resource-specific query (employees/students): pagination, sort, filters, and search. No resource_type."""

    pagination: Optional[PaginationParams] = Field(
        None,
        description="Pagination; defaults to page=1, page_size=20",
    )
    sort: Optional[List[SortItem]] = Field(
        None,
        description="Sort order; resource-specific default if omitted",
    )
    filters: Optional[List[FilterItem]] = Field(
        None,
        description="Filters to apply (field, operator, value)",
    )
    search: Optional[str] = Field(
        None,
        description="Search term: matches (case-insensitive) across fields defined by the backend. Ignored if empty.",
    )


class GlobalQueryRequest(ResourceQueryRequest):
    """POST body for the global query endpoint: resource type + pagination, sort, filters, and search."""

    resource_type: str = Field(
        ...,
        description="Resource to query: departments, classes, sections, employees, students",
    )


class PaginatedResponse(BaseModel):
    """Generic paginated response: items plus total and page info."""

    items: List[Any] = Field(..., description="List of resource items (shape depends on resource_type)")
    total: int = Field(..., ge=0, description="Total number of items matching the query")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Page size used")
    total_pages: int = Field(..., ge=0, description="Total number of pages")
    search_fields: Optional[List[str]] = Field(
        None,
        description="Fields that were searched (set by backend when 'search' was used). Sent by backend for display only.",
    )
