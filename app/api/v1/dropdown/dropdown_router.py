"""Global dropdown API: classes and classes-with-sections."""

from typing import List, Union

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.db.session import get_db

from .schemas import ClassOnlyDropdownItem, ClassWithSectionsDropdownItem
from . import service

router = APIRouter(prefix="/api/v1/dropdown", tags=["dropdown"])


@router.get(
    "/classes-and-sections",
    response_model=List[Union[ClassOnlyDropdownItem, ClassWithSectionsDropdownItem]],
    dependencies=[Depends(check_permission("classes", "read"))],
)
async def get_classes_sections_dropdown(
    indicator: str = Query(
        ...,
        description="C = classes only (no sections key); CS = classes with sections nested",
        min_length=1,
        max_length=5,
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Global dropdown: classes and optionally their sections.
    - **indicator=C**: Returns [{ className, classId }, ...] (no sections key).
    - **indicator=CS**: Returns [{ className, classId, sections: [{ sectionName, sectionId }, ...] }, ...].
    """
    return await service.get_classes_sections_dropdown(
        db, current_user.tenant_id, indicator
    )
