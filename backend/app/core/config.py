import os
from functools import cached_property

from pydantic import BaseModel, Field, SecretStr

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional during bare local imports
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(".env")
    load_dotenv("../.env")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    app_name: str = Field(default_factory=lambda: os.getenv("APP_NAME", "Family Health Agent API"))
    app_version: str = Field(default_factory=lambda: os.getenv("APP_VERSION", "0.1.0"))
    environment: str = Field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://hospital:hospital@localhost:5432/family_health",
        )
    )
    redis_url: str = Field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    rag_vector_enabled: bool = Field(
        default_factory=lambda: _env_bool("RAG_VECTOR_ENABLED")
    )
    model_provider: str = Field(
        default_factory=lambda: os.getenv("MODEL_PROVIDER", "deterministic")
    )
    model_api_base: str | None = Field(
        default_factory=lambda: os.getenv("MODEL_API_BASE") or None
    )
    model_api_key: SecretStr | None = Field(
        default_factory=lambda: (
            SecretStr(value) if (value := os.getenv("MODEL_API_KEY")) else None
        )
    )
    model_name: str = Field(
        default_factory=lambda: os.getenv("MODEL_NAME", "deterministic-local")
    )
    model_timeout_ms: int = Field(
        default_factory=lambda: int(os.getenv("MODEL_TIMEOUT_MS", "10000")),
        ge=1,
    )
    cors_origins: str = Field(default_factory=lambda: os.getenv("CORS_ORIGINS", "http://localhost:3000"))
    demo_user_phone: str = Field(
        default_factory=lambda: os.getenv("DEMO_USER_PHONE", "13800000001")
    )

    @cached_property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
