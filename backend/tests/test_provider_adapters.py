import pytest
from pydantic import ValidationError

from app.providers import (
    ProviderRegistry,
    ProviderRequest,
    ProviderResponse,
    build_mock_provider_registry,
)


PROVIDER_CASES = (
    ("hospital", "list_departments", "preconsultation"),
    ("pharmacy", "search_inventory", "chronic_care"),
    ("online_consultation", "prepare_draft", "chronic_care"),
    ("geo", "resolve", "preconsultation"),
    ("notification", "prepare_reminder", "chronic_care"),
    ("medical_document_parser", "parse", "health_record"),
    ("medical_vision", "inspect_quality", "health_record"),
)


def _request(*, operation: str, business_domain: str, provider_mode: str = "mock"):
    return ProviderRequest(
        operation=operation,
        business_domain=business_domain,
        provider_mode=provider_mode,
        user_id="user-1",
        member_id="member-1",
        payload={"text": "demo report", "city": "demo city"},
    )


def test_mock_registry_exposes_all_planned_provider_adapters() -> None:
    registry = build_mock_provider_registry()

    assert registry.names() == tuple(
        sorted(
            {
                "hospital",
                "pharmacy",
                "online_consultation",
                "geo",
                "notification",
                "medical_document_parser",
                "medical_vision",
            }
        )
    )


@pytest.mark.parametrize(
    ("provider_name", "operation", "business_domain"),
    PROVIDER_CASES,
)
def test_mock_provider_returns_member_scoped_traceable_evidence(
    provider_name: str,
    operation: str,
    business_domain: str,
) -> None:
    response = build_mock_provider_registry().invoke(
        provider_name,
        _request(operation=operation, business_domain=business_domain),
    )

    assert response.success is True
    assert response.provider_mode == "mock"
    assert response.degraded is False
    assert response.data
    assert len(response.source_refs) == 1
    source = response.source_refs[0]
    assert source.provider == provider_name
    assert source.member_id == "member-1"
    assert source.verified is False
    assert source.source_metadata["provider_mode"] == "mock"
    assert source.source_metadata["simulation"] is True
    assert response.data.get("diagnosis_provided") is not True


@pytest.mark.parametrize("provider_mode", ["sandbox", "real"])
def test_unconfigured_external_mode_is_explicitly_degraded(
    provider_mode: str,
) -> None:
    response = build_mock_provider_registry().invoke(
        "hospital",
        _request(
            operation="list_departments",
            business_domain="preconsultation",
            provider_mode=provider_mode,
        ),
    )

    assert response.success is False
    assert response.degraded is True
    assert response.fallback_reason == f"{provider_mode}_adapter_not_configured"
    assert response.data == {}
    assert response.source_refs == []


def test_unsupported_provider_operation_is_structured_failure() -> None:
    response = build_mock_provider_registry().invoke(
        "hospital",
        _request(operation="create_order", business_domain="chronic_care"),
    )

    assert response.success is False
    assert response.degraded is True
    assert response.fallback_reason == "unsupported_operation"


@pytest.mark.parametrize("mismatch", ["name", "mode"])
def test_registry_rejects_provider_response_identity_mismatch(mismatch: str) -> None:
    registry = ProviderRegistry()

    def handler(request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            provider_name="other" if mismatch == "name" else "demo",
            provider_mode="real" if mismatch == "mode" else request.provider_mode,
            operation=request.operation,
            success=True,
            data={"ok": True},
        )

    registry.register("demo", handler)

    response = registry.invoke(
        "demo",
        _request(operation="check", business_domain="health_record"),
    )

    assert response.success is False
    assert response.error_category == "schema"
    assert response.fallback_reason == "provider_identity_mismatch"
    assert len(response.attempts) == 1


def test_degraded_response_requires_a_fallback_reason() -> None:
    with pytest.raises(ValidationError):
        ProviderResponse(
            provider_name="demo",
            provider_mode="mock",
            operation="check",
            success=False,
            degraded=True,
        )

    with pytest.raises(ValidationError):
        ProviderResponse(
            provider_name="demo",
            provider_mode="mock",
            operation="check",
            success=True,
            fallback_reason="unexpected_fallback_reason",
        )
