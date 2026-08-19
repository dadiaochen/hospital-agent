import os
from functools import cached_property
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

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


def _env_optional_float(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return float(value)


class Settings(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

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
    task_checkpoint_ttl_seconds: int = Field(
        default_factory=lambda: int(os.getenv("TASK_CHECKPOINT_TTL_SECONDS", "900")),
        ge=1,
    )
    rag_vector_enabled: bool = Field(
        default_factory=lambda: _env_bool("RAG_VECTOR_ENABLED", False)
    )
    rag_embedding_provider: str = Field(
        default_factory=lambda: os.getenv("RAG_EMBEDDING_PROVIDER", "fastembed")
    )
    rag_embedding_model: str = Field(
        default_factory=lambda: os.getenv(
            "RAG_EMBEDDING_MODEL",
            "BAAI/bge-small-zh-v1.5",
        )
    )
    rag_embedding_dimensions: int = Field(
        default_factory=lambda: int(os.getenv("RAG_EMBEDDING_DIMENSIONS", "512")),
        ge=8,
    )
    rag_embedding_cache_dir: str = Field(
        default_factory=lambda: os.getenv(
            "FASTEMBED_CACHE_PATH",
            os.getenv("RAG_EMBEDDING_CACHE_DIR", "var/models/fastembed"),
        )
    )
    rag_embedding_device: Literal["cpu", "cuda", "auto"] = Field(
        default_factory=lambda: os.getenv("RAG_EMBEDDING_DEVICE", "cpu")
    )
    rag_vector_min_score: float = Field(
        default_factory=lambda: float(os.getenv("RAG_VECTOR_MIN_SCORE", "0.35")),
        ge=0.0,
        le=1.0,
    )
    rag_embedding_batch_size: int = Field(
        default_factory=lambda: int(os.getenv("RAG_EMBEDDING_BATCH_SIZE", "16")),
        ge=1,
        le=128,
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
    model_thinking_mode: Literal["default", "disabled", "enabled"] = Field(
        default_factory=lambda: os.getenv("MODEL_THINKING_MODE", "default")
    )
    model_timeout_ms: int = Field(
        default_factory=lambda: int(os.getenv("MODEL_TIMEOUT_MS", "10000")),
        ge=1,
    )
    model_input_price_per_1m_usd: float | None = Field(
        default_factory=lambda: _env_optional_float(
            "MODEL_INPUT_PRICE_PER_1M_USD"
        ),
        ge=0,
    )
    model_output_price_per_1m_usd: float | None = Field(
        default_factory=lambda: _env_optional_float(
            "MODEL_OUTPUT_PRICE_PER_1M_USD"
        ),
        ge=0,
    )
    ragas_enabled: bool = Field(
        default_factory=lambda: _env_bool("RAGAS_ENABLED", False)
    )
    ragas_version: str = Field(
        default_factory=lambda: os.getenv("RAGAS_VERSION", "0.2.9")
    )
    ragas_judge_api_base: str | None = Field(
        default_factory=lambda: os.getenv("RAGAS_JUDGE_API_BASE") or None
    )
    ragas_judge_api_key: SecretStr | None = Field(
        default_factory=lambda: SecretStr(value)
        if (value := os.getenv("RAGAS_JUDGE_API_KEY"))
        else None
    )
    ragas_judge_model: str | None = Field(
        default_factory=lambda: os.getenv("RAGAS_JUDGE_MODEL") or None
    )
    ragas_judge_thinking_mode: Literal["default", "disabled", "enabled"] = Field(
        default_factory=lambda: os.getenv(
            "RAGAS_JUDGE_THINKING_MODE", "disabled"
        )
    )
    ragas_embedding_provider: Literal["fastembed", "openai"] = Field(
        default_factory=lambda: os.getenv("RAGAS_EMBEDDING_PROVIDER", "fastembed")
    )
    ragas_embedding_model: str | None = Field(
        default_factory=lambda: os.getenv("RAGAS_EMBEDDING_MODEL") or None
    )
    ragas_batch_size: int = Field(
        default_factory=lambda: int(os.getenv("RAGAS_BATCH_SIZE", "16")),
        ge=1,
        le=128,
    )
    ragas_max_workers: int = Field(
        default_factory=lambda: int(os.getenv("RAGAS_MAX_WORKERS", "8")),
        ge=1,
        le=32,
    )
    ragas_timeout_seconds: int = Field(
        default_factory=lambda: int(os.getenv("RAGAS_TIMEOUT_SECONDS", "60")),
        ge=1,
        le=600,
    )
    cors_origins: str = Field(default_factory=lambda: os.getenv("CORS_ORIGINS", "http://localhost:3000"))
    demo_user_phone: str = Field(
        default_factory=lambda: os.getenv("DEMO_USER_PHONE", "13800000001")
    )

    @cached_property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
