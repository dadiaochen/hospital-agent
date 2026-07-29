from collections.abc import Callable
from typing import Any

from app.providers.registry import ProviderRegistry
from app.providers.reliable import (
    HospitalOrConsultationProvider,
    MedicalDocumentParserProvider,
    PharmacyProvider,
)
from app.providers.schemas import (
    ProviderRequest,
    ProviderResponse,
    ProviderRetryPolicy,
)
from app.core.reliability import classify_error
from app.schemas.business import SourceRef


def _source(provider_name: str, request: ProviderRequest) -> SourceRef:
    return SourceRef(
        source_id=f"provider:{provider_name}:{request.operation}:{request.member_id}",
        source_type="structured_database",
        provider=provider_name,
        member_id=request.member_id,
        verified=False,
        source_metadata={
            "provider_mode": request.provider_mode,
            "simulation": True,
        },
    )


def _handler(
    provider_name: str,
    operations: dict[str, Callable[[ProviderRequest], dict[str, Any]]],
) -> Callable[[ProviderRequest], ProviderResponse]:
    def invoke(request: ProviderRequest) -> ProviderResponse:
        if request.provider_mode != "mock":
            return ProviderResponse(
                provider_name=provider_name,
                provider_mode=request.provider_mode,
                operation=request.operation,
                success=False,
                error_type="provider_unavailable",
                error_category="provider_unavailable",
                error_message="external provider adapter is not configured",
                retryable=False,
                degraded=True,
                fallback_reason=(
                    f"{request.provider_mode}_adapter_not_configured"
                ),
            )
        operation = operations.get(request.operation)
        if operation is None:
            return ProviderResponse(
                provider_name=provider_name,
                provider_mode="mock",
                operation=request.operation,
                success=False,
                error_type="validation_error",
                error_category=classify_error("validation_error"),
                error_message="provider operation is not supported",
                retryable=False,
                degraded=True,
                fallback_reason="unsupported_operation",
            )
        return ProviderResponse(
            provider_name=provider_name,
            provider_mode="mock",
            operation=request.operation,
            success=True,
            data=operation(request),
            source_refs=[_source(provider_name, request)],
        )

    return invoke


def build_mock_provider_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register(
        "hospital",
        HospitalOrConsultationProvider("hospital"),
        retry_policy=ProviderRetryPolicy(max_attempts=3, backoff_ms=50),
    )
    registry.register(
        "pharmacy",
        PharmacyProvider(),
        retry_policy=ProviderRetryPolicy(max_attempts=3, backoff_ms=50),
    )
    registry.register(
        "online_consultation",
        HospitalOrConsultationProvider("online_consultation"),
        retry_policy=ProviderRetryPolicy(max_attempts=3, backoff_ms=50),
    )
    registry.register(
        "geo",
        _handler(
            "geo",
            {
                "resolve": lambda request: {
                    "city": request.payload.get("city", "demo_city"),
                    "precision": "city",
                    "realtime": False,
                }
            },
        ),
    )
    registry.register(
        "notification",
        _handler(
            "notification",
            {
                "prepare_reminder": lambda request: {
                    "draft": request.payload,
                    "scheduled": False,
                    "human_confirmation_required": True,
                }
            },
        ),
    )
    registry.register(
        "medical_document_parser",
        MedicalDocumentParserProvider(),
        retry_policy=ProviderRetryPolicy(max_attempts=3, backoff_ms=50),
    )
    registry.register(
        "medical_vision",
        _handler(
            "medical_vision",
            {
                "inspect_quality": lambda request: {
                    "image_quality": "readable",
                    "observable_features": request.payload.get(
                        "observable_features",
                        [],
                    ),
                    "medical_review_required": True,
                    "diagnosis_provided": False,
                }
            },
        ),
    )
    return registry
