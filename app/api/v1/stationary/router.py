"""Stationary router.

School management items:
  POST   /api/v1/stationary/items               (admin)
  GET    /api/v1/stationary/items               (all)
  GET    /api/v1/stationary/items/{item_id}     (all)
  PUT    /api/v1/stationary/items/{item_id}     (admin)
  DELETE /api/v1/stationary/items/{item_id}     (admin)

Resell marketplace:
  POST   /api/v1/stationary/resell/payments/create-order
  POST   /api/v1/stationary/resell/payments/verify
  POST   /api/v1/stationary/resell
  GET    /api/v1/stationary/resell
  GET    /api/v1/stationary/resell/{item_id}
  PUT    /api/v1/stationary/resell/{item_id}
  DELETE /api/v1/stationary/resell/{item_id}
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.rbac import check_permission
from app.auth.schemas import CurrentUser
from app.core.exceptions import ServiceError
from app.db.session import get_db

from . import service
from .schemas import (
    CreateOrderRequest,
    ResellItemDetailResponse,
    ResellItemListResponse,
    ResellItemResponse,
    ResellItemUpdate,
    StationaryItemCreate,
    StationaryItemDetailResponse,
    StationaryItemListResponse,
    StationaryItemResponse,
    StationaryItemUpdate,
    VerifyPaymentRequest,
)

router = APIRouter(prefix="/api/v1/stationary", tags=["stationary-resell"])

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB per image


# ---------------------------------------------------------------------------
# Payment endpoints
# ---------------------------------------------------------------------------


@router.post("/resell/payments/create-order")
async def create_order(
    payload: CreateOrderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Create a Razorpay listing-fee order for a stationery resell item."""
    try:
        data = await service.create_resell_payment_order(
            db=db,
            tenant_id=current_user.tenant_id,
            seller_type=payload.seller_type,
            seller_id=payload.seller_id,
            amount=payload.amount,
            currency=payload.currency,
        )
        return {"success": True, "data": data}
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail={"success": False, "message": e.message})


@router.post("/resell/payments/verify")
async def verify_payment(
    payload: VerifyPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Verify Razorpay signature and mark payment as PAID. Returns payment_txn_id."""
    try:
        data = await service.verify_resell_payment(
            db=db,
            tenant_id=current_user.tenant_id,
            order_id=payload.order_id,
            payment_id=payload.payment_id,
            signature=payload.signature,
            seller_id=payload.seller_id,
        )
        return {"success": True, "data": data}
    except ServiceError as e:
        error_code = "PAYMENT_INVALID_SIGNATURE" if e.status_code == http_status.HTTP_400_BAD_REQUEST else None
        raise HTTPException(
            status_code=e.status_code,
            detail={"success": False, "message": e.message, "error_code": error_code},
        )


# ---------------------------------------------------------------------------
# Resell item endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/resell",
    response_model=ResellItemDetailResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def create_resell_item(
    title: str = Form(..., max_length=255),
    category: str = Form(..., max_length=100),
    condition: str = Form(...),
    price: float = Form(..., gt=0),
    seller_type: str = Form(...),
    seller_id: str = Form(..., max_length=100),
    payment_txn_id: str = Form(...),
    description: Optional[str] = Form(None),
    images: List[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ResellItemDetailResponse:
    """Create a resale listing. Requires a verified payment_txn_id. Max 5 images."""
    if len(images) > 5:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "message": "Maximum 5 images allowed"},
        )

    image_files = []
    for upload in images:
        content = await upload.read()
        if len(content) > MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail={"success": False, "message": f"Image '{upload.filename}' exceeds 5 MB limit"},
            )
        image_files.append((upload.filename or "image.jpg", content))

    try:
        item = await service.create_resell_item(
            db=db,
            tenant_id=current_user.tenant_id,
            title=title,
            description=description,
            category=category,
            condition=condition,
            price=price,
            seller_type=seller_type,
            seller_id=seller_id,
            payment_txn_id=payment_txn_id,
            image_files=image_files,
        )
        return ResellItemDetailResponse(data=ResellItemResponse.model_validate(item))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail={"success": False, "message": e.message})


@router.get("/resell", response_model=ResellItemListResponse)
async def list_resell_items(
    status: Optional[str] = Query(None, description="Filter by status: APPROVED, PENDING_APPROVAL, etc."),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search in title, description, category"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ResellItemListResponse:
    """List resale items for the tenant with optional filters and pagination."""
    try:
        items, total = await service.list_resell_items(
            db=db,
            tenant_id=current_user.tenant_id,
            item_status=status,
            page=page,
            limit=limit,
            search=search,
        )
        return ResellItemListResponse(
            data=[ResellItemResponse.model_validate(i) for i in items],
            total=total,
            page=page,
            limit=limit,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail={"success": False, "message": e.message})


@router.get("/resell/{item_id}", response_model=ResellItemDetailResponse)
async def get_resell_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ResellItemDetailResponse:
    """Get a single resale listing by ID."""
    try:
        item = await service.get_resell_item(db, current_user.tenant_id, item_id)
        return ResellItemDetailResponse(data=ResellItemResponse.model_validate(item))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail={"success": False, "message": e.message})


@router.put("/resell/{item_id}", response_model=ResellItemDetailResponse)
async def update_resell_item(
    item_id: UUID,
    payload: ResellItemUpdate,
    seller_id: str = Query(..., description="Seller's ID for ownership check"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> ResellItemDetailResponse:
    """Update own listing. Admins can update any listing."""
    is_admin = current_user.role in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN")
    try:
        item = await service.update_resell_item(
            db=db,
            tenant_id=current_user.tenant_id,
            item_id=item_id,
            seller_id=seller_id,
            payload=payload,
            is_admin=is_admin,
        )
        return ResellItemDetailResponse(data=ResellItemResponse.model_validate(item))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail={"success": False, "message": e.message})


@router.delete("/resell/{item_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_resell_item(
    item_id: UUID,
    seller_id: str = Query(..., description="Seller's ID for ownership check"),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Soft-delete own listing. Admins can delete any listing."""
    is_admin = current_user.role in ("SUPER_ADMIN", "PLATFORM_ADMIN", "ADMIN")
    try:
        await service.delete_resell_item(
            db=db,
            tenant_id=current_user.tenant_id,
            item_id=item_id,
            seller_id=seller_id,
            is_admin=is_admin,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail={"success": False, "message": e.message})


# ---------------------------------------------------------------------------
# School management items
# ---------------------------------------------------------------------------


@router.post(
    "/items",
    response_model=StationaryItemDetailResponse,
    status_code=http_status.HTTP_201_CREATED,
    dependencies=[Depends(check_permission("stationary", "manage"))],
)
async def create_stationary_item(
    payload: StationaryItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StationaryItemDetailResponse:
    """Admin: create a stationary item in the school catalog (JSON body). Use POST /items/{id}/images to upload images."""
    try:
        item = await service.create_stationary_item(
            db=db,
            tenant_id=current_user.tenant_id,
            payload=payload,
            image_files=[],
        )
        return StationaryItemDetailResponse(data=StationaryItemResponse.model_validate(item))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail={"success": False, "message": e.message})


@router.post(
    "/items/{item_id}/images",
    response_model=StationaryItemDetailResponse,
    dependencies=[Depends(check_permission("stationary", "manage"))],
)
async def upload_stationary_item_images(
    item_id: UUID,
    images: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StationaryItemDetailResponse:
    """Admin: upload up to 5 images for a stationary item (multipart/form-data)."""
    if len(images) > 5:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail={"success": False, "message": "Maximum 5 images allowed"},
        )
    image_files = []
    for upload in images:
        content = await upload.read()
        if len(content) > MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail={"success": False, "message": f"Image '{upload.filename}' exceeds 5 MB limit"},
            )
        image_files.append((upload.filename or "image.jpg", content))

    try:
        item = await service.upload_stationary_item_images(
            db=db,
            tenant_id=current_user.tenant_id,
            item_id=item_id,
            image_files=image_files,
        )
        return StationaryItemDetailResponse(data=StationaryItemResponse.model_validate(item))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail={"success": False, "message": e.message})


@router.get(
    "/items",
    response_model=StationaryItemListResponse,
)
async def list_stationary_items(
    category: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StationaryItemListResponse:
    """List school catalog stationary items with optional filters."""
    try:
        items, total = await service.list_stationary_items(
            db=db,
            tenant_id=current_user.tenant_id,
            category=category,
            page=page,
            limit=limit,
            search=search,
            active_only=active_only,
        )
        return StationaryItemListResponse(
            data=[StationaryItemResponse.model_validate(i) for i in items],
            total=total,
            page=page,
            limit=limit,
        )
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail={"success": False, "message": e.message})


@router.get(
    "/items/{item_id}",
    response_model=StationaryItemDetailResponse,
)
async def get_stationary_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StationaryItemDetailResponse:
    """Get a single school catalog item by ID."""
    try:
        item = await service.get_stationary_item(db, current_user.tenant_id, item_id)
        return StationaryItemDetailResponse(data=StationaryItemResponse.model_validate(item))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail={"success": False, "message": e.message})


@router.put(
    "/items/{item_id}",
    response_model=StationaryItemDetailResponse,
    dependencies=[Depends(check_permission("stationary", "manage"))],
)
async def update_stationary_item(
    item_id: UUID,
    payload: StationaryItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> StationaryItemDetailResponse:
    """Admin: update a school catalog stationary item."""
    try:
        item = await service.update_stationary_item(db, current_user.tenant_id, item_id, payload)
        return StationaryItemDetailResponse(data=StationaryItemResponse.model_validate(item))
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail={"success": False, "message": e.message})


@router.delete(
    "/items/{item_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(check_permission("stationary", "manage"))],
)
async def delete_stationary_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> None:
    """Admin: soft-delete a school catalog stationary item."""
    try:
        await service.delete_stationary_item(db, current_user.tenant_id, item_id)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail={"success": False, "message": e.message})
