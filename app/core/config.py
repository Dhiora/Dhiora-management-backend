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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

