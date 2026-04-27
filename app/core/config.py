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
    parent_jwt_expiry_minutes: int = Field(60, alias="PARENT_JWT_EXPIRY_MINUTES")
    parent_invite_token_expiry_hours: int = Field(48, alias="PARENT_INVITE_TOKEN_EXPIRY_HOURS")

    platform_admin_email: Optional[str] = Field(None, alias="PLATFORM_ADMIN_EMAIL")
    platform_admin_password: Optional[str] = Field(None, alias="PLATFORM_ADMIN_PASSWORD")

    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")

    # Realtime AI Classroom streaming (defaults are safe; override via env if needed)
    ai_realtime_enabled: bool = Field(True, alias="AI_REALTIME_ENABLED")
    ai_realtime_max_frame_bytes: int = Field(80_000, alias="AI_REALTIME_MAX_FRAME_BYTES")
    ai_realtime_target_chunk_bytes: int = Field(800_000, alias="AI_REALTIME_TARGET_CHUNK_BYTES")
    ai_realtime_min_chunk_bytes: int = Field(200_000, alias="AI_REALTIME_MIN_CHUNK_BYTES")
    ai_realtime_max_chunk_bytes: int = Field(1_200_000, alias="AI_REALTIME_MAX_CHUNK_BYTES")
    ai_realtime_overlap_bytes: int = Field(120_000, alias="AI_REALTIME_OVERLAP_BYTES")
    ai_realtime_max_buffer_size_bytes: int = Field(3_000_000, alias="AI_REALTIME_MAX_BUFFER_SIZE_BYTES")
    ai_realtime_max_queue_size: int = Field(8, alias="AI_REALTIME_MAX_QUEUE_SIZE")
    ai_realtime_workers: int = Field(1, alias="AI_REALTIME_WORKERS")
    ai_realtime_whisper_timeout_s: float = Field(35.0, alias="AI_REALTIME_WHISPER_TIMEOUT_S")
    ai_realtime_whisper_rps_limit: float = Field(0.8, alias="AI_REALTIME_WHISPER_RPS_LIMIT")
    ai_realtime_enable_adaptive_chunking: bool = Field(True, alias="AI_REALTIME_ADAPTIVE_CHUNKING")
    ai_realtime_lag_soft_ms: int = Field(1500, alias="AI_REALTIME_LAG_SOFT_MS")
    ai_realtime_lag_hard_ms: int = Field(3500, alias="AI_REALTIME_LAG_HARD_MS")
    ai_realtime_buffer_health_every_n_frames: int = Field(8, alias="AI_REALTIME_BUFFER_HEALTH_EVERY_N_FRAMES")

    razorpay_key_id: Optional[str] = Field(None, alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: Optional[str] = Field(None, alias="RAZORPAY_KEY_SECRET")
    gradebook_enabled: bool = Field(False, alias="GRADEBOOK_ENABLED")
    parent_portal_enabled: bool = Field(True, alias="PARENT_PORTAL_ENABLED")
    sms_gateway: Optional[str] = Field(None, alias="SMS_GATEWAY")
    sms_api_key: Optional[str] = Field(None, alias="SMS_API_KEY")

    # AWS S3 — board image storage
    aws_access_key_id: Optional[str] = Field(None, alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(None, alias="AWS_SECRET_ACCESS_KEY")
    aws_region: str = Field("ap-south-1", alias="AWS_REGION")
    s3_bucket_name: Optional[str] = Field(None, alias="S3_BUCKET_NAME")
    s3_base_url: Optional[str] = Field(None, alias="S3_BASE_URL")  # optional CDN prefix; falls back to default S3 URL

    redis_url: str = Field("redis://localhost:6379/0", alias="REDIS_URL")
    redis_cache_ttl_seconds: int = Field(300, alias="REDIS_CACHE_TTL_SECONDS")

    # Dangerous test-only endpoints (DB wipe, seeded org). Keep disabled in production.
    enable_test_apis: bool = Field(False, alias="ENABLE_TEST_APIS")
    # If set, callers must send header X-Test-Api-Key with this value.
    test_api_secret: Optional[str] = Field(None, alias="TEST_API_SECRET")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

