from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import LoginRequest, LoginResponse, RegisterRequest, RegisterResponse
from app.auth.services import ServiceError, login_user, register_tenant_and_admin
from app.db.session import get_db
from fastapi.security import OAuth2PasswordRequestForm

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=http_status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    try:
        return await register_tenant_and_admin(db, payload)
    except ServiceError as e:
        # Map service errors to HTTP responses
        if e.status_code == http_status.HTTP_409_CONFLICT:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        if e.status_code == http_status.HTTP_400_BAD_REQUEST:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        if e.status_code == http_status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise HTTPException(status_code=e.status_code, detail="Internal server error")
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=http_status.HTTP_200_OK,
)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    try:
        return await login_user(db, payload)
    except ServiceError as e:
        if e.status_code in {
            http_status.HTTP_401_UNAUTHORIZED,
            http_status.HTTP_403_FORBIDDEN,
            http_status.HTTP_409_CONFLICT,
        }:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        if e.status_code == http_status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise HTTPException(status_code=e.status_code, detail="Internal server error")
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/login-oauth")
async def login_oauth(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    payload = LoginRequest(
        email=form_data.username.strip(),
        password=form_data.password,
    )
    try:
        result = await login_user(db, payload)
    except ServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {
        "access_token": result.access_token,
        "token_type": "bearer",
    }
