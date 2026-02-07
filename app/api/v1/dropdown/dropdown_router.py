"""Global dropdown API: academic years, classes, and classes-with-sections."""

from typing import List, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.schemas import CurrentUser
from app.db.session import get_db

from .schemas import (
    AcademicYearDropdownItem,
    ClassOnlyDropdownItem,
    ClassWithSectionsDropdownItem,
)
from . import service

router = APIRouter(prefix="/api/v1/dropdown", tags=["dropdown"])


async def get_dropdown_indicator_and_check_permission(
    indicator: str = Query(
        ...,
        description="AY = academic years; C = classes only; CS = classes with sections nested",
        min_length=1,
        max_length=5,
    ),
    current_user: CurrentUser = Depends(get_current_user),
) -> str:
    """Validate indicator and enforce permission: academic_years read for AY, classes read for C/CS."""
    if current_user.role in ("SUPER_ADMIN", "PLATFORM_ADMIN"):
        return indicator
    ind = (indicator or "").strip().upper()
    if ind == "AY":
        perms = (current_user.permissions or {}).get("academic_years") or {}
        if not perms.get("read", False):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    else:
        perms = (current_user.permissions or {}).get("classes") or {}
        if not perms.get("read", False):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return indicator


@router.get(
    "/classes-and-sections",
    response_model=List[
        Union[AcademicYearDropdownItem, ClassOnlyDropdownItem, ClassWithSectionsDropdownItem]
    ],
)
async def get_classes_sections_dropdown(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
    indicator: str = Depends(get_dropdown_indicator_and_check_permission),
):
    """
    Global dropdown by indicator.
    - **indicator=AY**: Returns [{ academicYearId, academicYearName }, ...].
    - **indicator=C**: Returns [{ className, classId }, ...] (no sections key).
    - **indicator=CS**: Returns [{ className, classId, sections: [{ sectionName, sectionId }, ...] }, ...].
    """
    return await service.get_classes_sections_dropdown(
        db, current_user.tenant_id, indicator, academic_year_id=current_user.academic_year_id
    )
