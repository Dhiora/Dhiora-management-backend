from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    database_url: str = Field(..., alias="DATABASE_URL")

    jwt_secret_key: str = Field(..., alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(15, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(7, alias="REFRESH_TOKEN_EXPIRE_DAYS")

    platform_admin_email: Optional[str] = Field(None, alias="PLATFORM_ADMIN_EMAIL")
    platform_admin_password: Optional[str] = Field(None, alias="PLATFORM_ADMIN_PASSWORD")

    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")

    razorpay_key_id: Optional[str] = Field(None, alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: Optional[str] = Field(None, alias="RAZORPAY_KEY_SECRET")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

