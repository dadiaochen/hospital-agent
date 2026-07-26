from collections.abc import Callable
from typing import Any

from app.providers.registry import ProviderRegistry
from app.providers.schemas import ProviderRequest, ProviderResponse
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
        _handler(
            "hospital",
            {
                "list_departments": lambda request: {
                    "candidates": [
                        {
                            "department": "general_medicine",
                            "reason": "general_review_first",
                        },
                        {
                            "department": "specialist_review",
                            "reason": "doctor_reviews_submitted_materials",
                        },
                    ],
                    "diagnosis_provided": False,
                },
                "list_slots": lambda request: {
                    "slots": [
                        {
                            "date": "demo-next-day",
                            "period": "morning",
                            "mode": "online",
                        }
                    ],
                    "realtime": False,
                },
            },
        ),
    )
    registry.register(
        "pharmacy",
        _handler(
            "pharmacy",
            {
                "search_inventory": lambda request: {
                    "candidates": [
                        {
                            "pharmacy": "demo_pharmacy",
                            "availability": "recheck_before_order",
                            "fulfillment": ["delivery", "pickup"],
                        }
                    ],
                    "order_created": False,
                }
            },
        ),
    )
    registry.register(
        "online_consultation",
        _handler(
            "online_consultation",
            {
                "prepare_draft": lambda request: {
                    "draft": {
                        "chief_complaint": request.payload.get(
                            "chief_complaint",
                            "",
                        ),
                        "materials": request.payload.get("materials", []),
                    },
                    "submitted": False,
                    "doctor_confirmation_required": True,
                }
            },
        ),
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
        _handler(
            "medical_document_parser",
            {
                "parse": lambda request: {
                    "document_type": request.payload.get(
                        "document_type",
                        "medical_report",
                    ),
                    "sections": request.payload.get("sections", []),
                    "raw_text": request.payload.get("text", ""),
                    "medical_review_required": True,
                    "diagnosis_provided": False,
                }
            },
        ),
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
