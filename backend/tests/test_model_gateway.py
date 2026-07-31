from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agent.model_gateway import (
    DeterministicModelProvider,
    ModelGateway,
    ModelProviderError,
    ModelProviderTimeout,
    OpenAICompatibleModelProvider,
    create_model_gateway,
)
from app.agent.model_gateway_schemas import (
    ModelCallRequest,
    ModelMessage,
    ProviderRawResponse,
)
from app.core.config import Settings, settings


class StructuredAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1)
    requires_human_confirmation: bool


class StaticProvider:
    def __init__(
        self,
        content: str,
        *,
        provider_name: str = "static-primary",
        model_name: str = "static-model",
    ) -> None:
        self.provider_name = provider_name
        self.model_name = model_name
        self._content = content

    def invoke(self, request: ModelCallRequest) -> ProviderRawResponse:
        return ProviderRawResponse(
            provider_name=self.provider_name,
            model_name=self.model_name,
            content=self._content,
            provider_request_id=f"static:{request.run_id}",
        )


class FailingProvider:
    provider_name = "failing-primary"
    model_name = "failing-model"

    def __init__(self, error: Exception) -> None:
        self._error = error

    def invoke(self, request: ModelCallRequest) -> ProviderRawResponse:
        raise self._error


@pytest.fixture()
def model_request() -> ModelCallRequest:
    return ModelCallRequest(
        run_id="run-model-1",
        task_id="task-model-1",
        member_id="member-father",
        purpose="final_answer_draft",
        messages=(
            ModelMessage(role="system", content="Return the declared JSON schema."),
            ModelMessage(role="user", content="Organize refill materials."),
        ),
    )


@pytest.fixture()
def safe_fallback() -> DeterministicModelProvider:
    return DeterministicModelProvider(
        {
            "content": "I can organize the local draft for your confirmation.",
            "requires_human_confirmation": True,
        }
    )


def test_deterministic_provider_returns_parsed_output_and_trace(
    model_request: ModelCallRequest,
    safe_fallback: DeterministicModelProvider,
) -> None:
    result = ModelGateway(safe_fallback).invoke(model_request, StructuredAnswer)

    assert result.output is not None
    assert result.output.requires_human_confirmation is True
    assert result.trace.success is True
    assert result.trace.requested_provider == "deterministic"
    assert result.trace.effective_provider == "deterministic"
    assert result.trace.fallback_used is False
    assert len(result.trace.attempts) == 1


def test_provider_timeout_uses_deterministic_fallback(
    model_request: ModelCallRequest,
    safe_fallback: DeterministicModelProvider,
) -> None:
    gateway = ModelGateway(
        FailingProvider(ModelProviderTimeout()),
        fallback_provider=safe_fallback,
    )

    result = gateway.invoke(model_request, StructuredAnswer)

    assert result.output is not None
    assert result.trace.success is True
    assert result.trace.fallback_used is True
    assert result.trace.fallback_reason == "provider_timeout"
    assert [attempt.provider_name for attempt in result.trace.attempts] == [
        "failing-primary",
        "deterministic",
    ]


def test_provider_error_records_type_and_uses_fallback(
    model_request: ModelCallRequest,
    safe_fallback: DeterministicModelProvider,
) -> None:
    gateway = ModelGateway(
        FailingProvider(ModelProviderError("provider_http_error")),
        fallback_provider=safe_fallback,
    )

    result = gateway.invoke(model_request, StructuredAnswer)

    assert result.trace.fallback_reason == "provider_http_error"
    assert result.trace.attempts[0].success is False
    assert result.trace.attempts[0].error_type == "provider_http_error"


def test_failed_schema_attempt_preserves_usage_without_claiming_partial_total(
    model_request: ModelCallRequest,
    safe_fallback: DeterministicModelProvider,
) -> None:
    class InvalidUsageProvider(StaticProvider):
        def invoke(self, request: ModelCallRequest) -> ProviderRawResponse:
            return ProviderRawResponse(
                provider_name=self.provider_name,
                model_name=self.model_name,
                content="not-json",
                input_tokens=9,
                output_tokens=2,
                total_tokens=11,
            )

    result = ModelGateway(
        InvalidUsageProvider("not-json"),
        fallback_provider=safe_fallback,
    ).invoke(model_request, StructuredAnswer)

    assert result.trace.attempts[0].total_tokens == 11
    assert result.trace.attempts[0].error_type == "schema_validation_failed"
    assert result.trace.success is True
    assert result.trace.token_usage_available is False
    assert result.trace.total_tokens is None


@pytest.mark.parametrize(
    "primary_content",
    [
        "not-json",
        '{"content":"missing confirmation field"}',
        '{"content":"ok","requires_human_confirmation":true,"extra":"no"}',
    ],
)
def test_invalid_provider_output_schema_uses_fallback(
    model_request: ModelCallRequest,
    safe_fallback: DeterministicModelProvider,
    primary_content: str,
) -> None:
    gateway = ModelGateway(
        StaticProvider(primary_content),
        fallback_provider=safe_fallback,
    )

    result = gateway.invoke(model_request, StructuredAnswer)

    assert result.output is not None
    assert result.trace.fallback_reason == "schema_validation_failed"
    assert result.trace.attempts[0].schema_valid is False
    assert result.trace.attempts[1].schema_valid is True


def test_unsafe_parsed_output_is_blocked_before_fallback(
    model_request: ModelCallRequest,
    safe_fallback: DeterministicModelProvider,
) -> None:
    unsafe = StaticProvider(
        json.dumps(
            {
                "content": "建议自行停药，无需医生确认。",
                "requires_human_confirmation": False,
            },
            ensure_ascii=False,
        )
    )
    gateway = ModelGateway(unsafe, fallback_provider=safe_fallback)

    result = gateway.invoke(model_request, StructuredAnswer)

    assert result.output is not None
    assert "停药" not in result.output.content
    assert result.trace.fallback_reason == "safety_check_failed"
    assert set(result.trace.attempts[0].safety_flags) == {
        "unsafe_medication_instruction",
        "confirmation_bypass",
    }


def test_safe_refusal_can_mention_the_prohibited_action(
    model_request: ModelCallRequest,
) -> None:
    provider = DeterministicModelProvider(
        {
            "content": "不能自行停药，请联系医生并等待确认。",
            "requires_human_confirmation": True,
        }
    )

    result = ModelGateway(provider).invoke(model_request, StructuredAnswer)

    assert result.trace.success is True
    assert result.trace.safety_passed is True


def test_failed_fallback_returns_no_output_and_two_attempts(
    model_request: ModelCallRequest,
) -> None:
    gateway = ModelGateway(
        StaticProvider("not-json"),
        fallback_provider=DeterministicModelProvider("also-not-json"),
    )

    result = gateway.invoke(model_request, StructuredAnswer)

    assert result.output is None
    assert result.trace.success is False
    assert result.trace.effective_provider is None
    assert result.trace.fallback_used is True
    assert len(result.trace.attempts) == 2
    assert all(
        attempt.error_type == "schema_validation_failed"
        for attempt in result.trace.attempts
    )


def test_call_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ModelCallRequest.model_validate(
            {
                "run_id": "run-1",
                "task_id": "task-1",
                "member_id": "member-1",
                "purpose": "test",
                "messages": [{"role": "user", "content": "hello"}],
                "api_key": "must-not-enter-request-contract",
            }
        )


def test_openai_compatible_provider_uses_structured_http_contract(
    model_request: ModelCallRequest,
) -> None:
    def handler(http_request: httpx.Request) -> httpx.Response:
        assert http_request.url == "https://model.example/v1/chat/completions"
        assert http_request.headers["authorization"] == "Bearer secret-from-env"
        body = json.loads(http_request.content)
        assert body["model"] == "example-model"
        assert body["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "id": "provider-request-1",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "content": "Structured response.",
                                    "requires_human_confirmation": True,
                                }
                            )
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                },
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleModelProvider(
        api_base="https://model.example/v1",
        api_key="secret-from-env",
        model_name="example-model",
        timeout_ms=1000,
        client=client,
    )

    result = ModelGateway(provider).invoke(model_request, StructuredAnswer)

    assert result.trace.success is True
    assert result.trace.requested_provider == "openai_compatible"
    assert result.trace.token_usage_available is True
    assert result.trace.input_tokens == 11
    assert result.trace.output_tokens == 7
    assert result.trace.total_tokens == 18
    assert "secret-from-env" not in repr(provider)
    client.close()


def test_openai_compatible_timeout_is_normalized(
    model_request: ModelCallRequest,
) -> None:
    def handler(http_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("test timeout", request=http_request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleModelProvider(
        api_base="https://model.example/v1",
        api_key="secret-from-env",
        model_name="example-model",
        timeout_ms=1000,
        client=client,
    )

    with pytest.raises(ModelProviderTimeout):
        provider.invoke(model_request)
    client.close()


def test_model_settings_are_loaded_only_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_PROVIDER", "openai_compatible")
    monkeypatch.setenv("MODEL_API_BASE", "https://model.example/v1")
    monkeypatch.setenv("MODEL_API_KEY", "environment-secret")
    monkeypatch.setenv("MODEL_NAME", "environment-model")
    monkeypatch.setenv("MODEL_TIMEOUT_MS", "2500")

    configured = Settings()

    assert configured.model_provider == "openai_compatible"
    assert configured.model_api_base == "https://model.example/v1"
    assert configured.model_api_key is not None
    assert configured.model_api_key.get_secret_value() == "environment-secret"
    assert "environment-secret" not in repr(configured)
    assert configured.model_name == "environment-model"
    assert configured.model_timeout_ms == 2500


def test_gateway_factory_defaults_to_deterministic_provider(
    model_request: ModelCallRequest,
    safe_fallback: DeterministicModelProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "model_provider", "deterministic")

    result = create_model_gateway(safe_fallback).invoke(
        model_request,
        StructuredAnswer,
    )

    assert result.trace.requested_provider == "deterministic"
    assert result.trace.fallback_used is False


def test_gateway_factory_rejects_missing_http_configuration(
    safe_fallback: DeterministicModelProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "model_provider", "openai_compatible")
    monkeypatch.setattr(settings, "model_api_base", None)
    monkeypatch.setattr(settings, "model_api_key", None)

    with pytest.raises(ValueError, match="MODEL_API_BASE"):
        create_model_gateway(safe_fallback)
