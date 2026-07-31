from collections.abc import Callable
from typing import Any

import pytest

from app.providers import (
    HospitalOrConsultationProvider,
    MedicalDocumentParserProvider,
    PharmacyProvider,
    ProviderInvocationError,
    ProviderRegistry,
    ProviderRequest,
    ProviderRetryPolicy,
)
from app.providers.schemas import ProviderResponse
from app.schemas.business import SourceRef


def _request(
    provider_mode: str = "mock",
    *,
    operation: str = "parse",
    business_domain: str = "health_record",
    payload: dict[str, Any] | None = None,
) -> ProviderRequest:
    return ProviderRequest(
        operation=operation,
        business_domain=business_domain,
        provider_mode=provider_mode,
        user_id="user-1",
        member_id="member-1",
        payload=payload or {},
    )


def _registry(
    name: str,
    handler: Callable,
    *,
    max_attempts: int = 3,
) -> ProviderRegistry:
    registry = ProviderRegistry(sleeper=lambda _: None)
    registry.register(
        name,
        handler,
        retry_policy=ProviderRetryPolicy(
            max_attempts=max_attempts,
            backoff_ms=1,
        ),
    )
    return registry


def test_medical_document_parser_preserves_source_locations_and_version() -> None:
    response = _registry(
        "medical_document_parser",
        MedicalDocumentParserProvider(),
    ).invoke(
        "medical_document_parser",
        _request(
            payload={
                "document_id": "report-1",
                "document_version": "v2",
                "document_type": "lab_report",
                "text": "blood pressure 120/80",
            }
        ),
    )

    assert response.success is True
    assert response.data["diagnosis_provided"] is False
    assert response.data["parser_version"] == "mock-parser-v1"
    source = response.source_refs[0]
    assert source.source_type == "medical_document"
    assert source.document_id == "report-1"
    assert source.document_version == "v2"
    assert source.member_id == "member-1"
    assert source.source_metadata["source_locations"][0] == {
        "section_id": "section-1",
        "start_char": 0,
        "end_char": 21,
    }


@pytest.mark.parametrize(
    ("name", "provider", "provider_request", "forbidden_success_field"),
    [
        (
            "pharmacy",
            PharmacyProvider(),
            _request(
                operation="search_inventory",
                business_domain="chronic_care",
            ),
            "order_created",
        ),
        (
            "hospital",
            HospitalOrConsultationProvider("hospital"),
            _request(
                operation="list_slots",
                business_domain="preconsultation",
            ),
            "appointment_created",
        ),
        (
            "online_consultation",
            HospitalOrConsultationProvider("online_consultation"),
            _request(
                operation="prepare_draft",
                business_domain="preconsultation",
            ),
            "submitted",
        ),
    ],
)
def test_operational_providers_never_claim_external_write_success(
    name: str,
    provider: Callable,
    provider_request: ProviderRequest,
    forbidden_success_field: str,
) -> None:
    response = _registry(name, provider).invoke(name, provider_request)

    assert response.success is True
    assert response.data[forbidden_success_field] is False
    assert response.source_refs[0].member_id == "member-1"
    assert response.source_refs[0].source_metadata["simulation"] is True


def test_rate_limit_is_retried_with_fixed_upper_bound_then_succeeds() -> None:
    calls = 0

    def transport(_: ProviderRequest, timeout_ms: int) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        assert timeout_ms == 250
        if calls < 3:
            raise ProviderInvocationError(
                "rate limited",
                error_type="rate_limit",
                retryable=True,
            )
        return {
            "candidates": [],
            "realtime": True,
            "order_created": False,
        }

    provider = PharmacyProvider(transport=transport, timeout_ms=250)
    response = _registry("pharmacy", provider).invoke(
        "pharmacy",
        _request(
            "sandbox",
            operation="search_inventory",
            business_domain="chronic_care",
        ),
    )

    assert response.success is True
    assert calls == 3
    assert [attempt.error_category for attempt in response.attempts] == [
        "rate_limit",
        "rate_limit",
        None,
    ]


def test_timeout_exhaustion_degrades_without_sources() -> None:
    def transport(_: ProviderRequest, __: int) -> dict[str, Any]:
        raise TimeoutError

    response = _registry(
        "hospital",
        HospitalOrConsultationProvider("hospital", transport=transport),
    ).invoke(
        "hospital",
        _request(
            "real",
            operation="list_departments",
            business_domain="preconsultation",
        ),
    )

    assert response.success is False
    assert response.degraded is True
    assert response.error_category == "timeout"
    assert response.retryable is False
    assert len(response.attempts) == 3
    assert response.source_refs == []


def test_schema_error_and_business_conflict_are_not_retried() -> None:
    schema_calls = 0

    def invalid_schema(_: ProviderRequest, __: int) -> dict[str, Any]:
        nonlocal schema_calls
        schema_calls += 1
        return {"order_created": True}

    schema_response = _registry(
        "pharmacy",
        PharmacyProvider(transport=invalid_schema),
    ).invoke(
        "pharmacy",
        _request(
            "sandbox",
            operation="search_inventory",
            business_domain="chronic_care",
        ),
    )
    assert schema_response.error_category == "schema"
    assert schema_calls == 1
    assert len(schema_response.attempts) == 1

    conflict_calls = 0

    def conflict(_: ProviderRequest, __: int) -> dict[str, Any]:
        nonlocal conflict_calls
        conflict_calls += 1
        raise ProviderInvocationError(
            "slot changed",
            error_type="business_conflict",
            retryable=False,
        )

    conflict_response = _registry(
        "hospital",
        HospitalOrConsultationProvider("hospital", transport=conflict),
    ).invoke(
        "hospital",
        _request(
            "real",
            operation="list_slots",
            business_domain="preconsultation",
        ),
    )
    assert conflict_response.error_category == "business_conflict"
    assert conflict_calls == 1


def test_unconfigured_external_provider_is_explicit_and_has_no_evidence() -> None:
    response = _registry("pharmacy", PharmacyProvider()).invoke(
        "pharmacy",
        _request(
            "real",
            operation="search_inventory",
            business_domain="chronic_care",
        ),
    )

    assert response.success is False
    assert response.error_category == "provider_unavailable"
    assert response.fallback_reason == "real_adapter_not_configured"
    assert response.source_refs == []
    assert len(response.attempts) == 1


def test_missing_provider_is_structured_not_registered_failure() -> None:
    response = ProviderRegistry().invoke(
        "missing",
        _request(operation="parse", business_domain="health_record"),
    )

    assert response.success is False
    assert response.error_category == "provider_unavailable"
    assert response.fallback_reason == "provider_not_registered"
    assert response.attempts == []


def test_provider_source_member_mismatch_is_rejected_as_schema_failure() -> None:
    registry = ProviderRegistry()
    registry.register(
        "pharmacy",
        lambda request: ProviderResponse(
            provider_name="pharmacy",
            provider_mode=request.provider_mode,
            operation=request.operation,
            success=True,
            data={"candidates": []},
            source_refs=[
                SourceRef(
                    source_id="wrong-member-source",
                    source_type="structured_database",
                    provider="pharmacy",
                    member_id="member-2",
                )
            ],
        ),
    )

    response = registry.invoke(
        "pharmacy",
        _request(
            operation="search_inventory",
            business_domain="chronic_care",
        ),
    )

    assert response.success is False
    assert response.error_category == "schema"
    assert response.source_refs == []
