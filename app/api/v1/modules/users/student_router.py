from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from app.api.v1.query import service as query_service
from app.api.v1.query.schemas import ResourceQueryRequest

from .schemas import (
    StudentPromote,
    StudentBulkPromote,
    StudentBulkPromoteResult,
    StudentBulkCreate,
    StudentBulkFailureItem,
    StudentBulkItem,
    StudentBulkResponse,
    StudentCreate,
    StudentPaginatedResponse,
    StudentResponse,
    StudentUpdate,
)
from . import service

router = APIRouter(prefix="/api/v1/students", tags=["students"])


@router.post(
    "",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("students", "create"))],
)
async def create_student(
    payload: StudentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StudentResponse:
    try:
        return await service.create_student(db, current_user.tenant_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/bulk",
    response_model=StudentBulkResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("students", "create"))],
)
async def create_students_bulk_json(
    payload: StudentBulkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StudentBulkResponse:
    """Bulk create students from JSON body. Valid rows are created; failed rows are returned with reasons in `failed`."""
    try:
        items_with_row_data = [
            (item, {"full_name": item.full_name, "email": item.email, "mobile": item.mobile or ""})
            for item in payload.students
        ]
        created_list, failed_list = await service.create_students_bulk_with_failures(
            db, current_user.tenant_id, items_with_row_data
        )
        failed_response = None
        if failed_list:
            def _index_for(rd: dict) -> int:
                for i, s in enumerate(payload.students):
                    if s.email == rd.get("email") and s.full_name == rd.get("full_name"):
                        return i
                return len(payload.students)
            failed_response = [
                StudentBulkFailureItem(
                    index=_index_for(rd),
                    full_name=rd.get("full_name", ""),
                    email=rd.get("email", ""),
                    reason=reason,
                )
                for rd, reason in failed_list
            ]
            failed_response.sort(key=lambda x: x.index)
        return StudentBulkResponse(
            students=created_list,
            created=len(created_list),
            failed=failed_response,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/bulk-excel/template",
    dependencies=[Depends(check_permission("students", "create"))],
)
async def download_student_upload_template(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Response:
    """Download sample Excel template with Classes and Sections dropdowns. Fill the Students sheet and upload via POST /bulk-excel."""
    try:
        content = await service.build_student_upload_template(db, current_user.tenant_id)
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=student_upload_template.xlsx"},
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/bulk-excel",
    dependencies=[Depends(check_permission("students", "create"))],
)
async def create_students_bulk_excel(
    file: UploadFile = File(
        ...,
        description="Excel from template (class/section dropdowns) or with columns: full_name, email, mobile, password, roll_number, class_id, section_id",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Bulk create students from Excel. Use template from GET /bulk-excel/template for dropdowns.
    Valid rows are created; if any row fails, returns an Excel file with failed rows and reason column.
    """
    try:
        success_list, parse_failures = await service.parse_students_excel_with_errors(
            file, db, current_user.tenant_id
        )
        if not success_list and not parse_failures:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Excel file has no data rows")
        items_with_row_data = [(item, row_dict) for item, row_dict in success_list]
        created, validation_failures = await service.create_students_bulk_with_failures(
            db, current_user.tenant_id, items_with_row_data
        )
        all_failed = parse_failures + validation_failures
        if all_failed:
            headers = list(all_failed[0][0].keys()) if all_failed[0][0] else []
            error_excel = service._build_error_excel(all_failed, headers=headers)
            return Response(
                content=error_excel,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": "attachment; filename=students_upload_errors.xlsx"},
            )
        return StudentBulkResponse(students=created, created=len(created))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "",
    response_model=List[StudentResponse],
    dependencies=[Depends(check_permission("students", "read"))],
)
async def list_students(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> List[StudentResponse]:
    return await service.list_students(db, current_user.tenant_id)


@router.post(
    "/query",
    response_model=StudentPaginatedResponse,
    dependencies=[Depends(check_permission("students", "read"))],
)
async def query_students(
    body: ResourceQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StudentPaginatedResponse:
    """
    Query students with pagination, filters, sort, and search.
    Same capabilities as global query for resource_type=students; dedicated endpoint for students.
    """
    try:
        result = await query_service.run_global_query(
            db,
            current_user.tenant_id,
            resource_type="students",
            page=body.pagination.page if body.pagination else 1,
            page_size=body.pagination.page_size if body.pagination else 20,
            sort=body.sort,
            filters=body.filters,
            search=body.search,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return StudentPaginatedResponse(
        items=result.items,
        total=result.total,
        page=result.page,
        page_size=result.page_size,
        total_pages=result.total_pages,
        search_fields=result.search_fields,
    )


@router.get(
    "/{user_id}",
    response_model=StudentResponse,
    dependencies=[Depends(check_permission("students", "read"))],
)
async def get_student(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StudentResponse:
    student = await service.get_student(db, current_user.tenant_id, user_id)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


@router.post(
    "/promote-bulk",
    response_model=StudentBulkPromoteResult,
    dependencies=[Depends(check_permission("students", "update"))],
)
async def promote_students_bulk(
    payload: StudentBulkPromote,
    preview: bool = Query(False, description="If true, return actions without committing"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StudentBulkPromoteResult:
    """
    Promote students from source to target academic year.
    RETAIN=same class/section; PROMOTE=new class/section.
    Use ?preview=true to see actions without committing.
    """
    try:
        return await service.promote_students_bulk(db, current_user.tenant_id, payload, preview=preview)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/{user_id}/promote",
    response_model=StudentResponse,
    dependencies=[Depends(check_permission("students", "update"))],
)
async def promote_student(
    user_id: UUID,
    payload: StudentPromote,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StudentResponse:
    """Promote student to new academic year. Old record → PROMOTED; creates new record (promotion-safe)."""
    try:
        return await service.promote_student(db, current_user.tenant_id, user_id, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put(
    "/{user_id}",
    response_model=StudentResponse,
    dependencies=[Depends(check_permission("students", "update"))],
)
async def update_student(
    user_id: UUID,
    payload: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StudentResponse:
    try:
        student = await service.update_student(db, current_user.tenant_id, user_id, payload)
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
        return student
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("students", "delete"))],
)
async def delete_student(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    deleted = await service.delete_student(db, current_user.tenant_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
