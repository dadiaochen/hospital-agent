from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

import app.agent.langgraph_workflow as workflow_module
from app.agent.langgraph_workflow import LangGraphAgentWorkflow
from app.agent.model_gateway import DeterministicModelProvider, ModelGateway
from app.agent.model_provider_diagnostic import (
    diagnostic_exit_code,
    run_model_provider_diagnostic,
)
from app.core.config import Settings


def test_deterministic_diagnostic_is_offline_and_successful() -> None:
    report = run_model_provider_diagnostic(
        configuration=Settings(
            model_provider="deterministic",
            model_name="deterministic-local",
        )
    )

    assert report.configuration_valid is True
    assert report.external_call_performed is False
    assert report.deterministic_self_check_passed is True
    assert report.effective_provider == "deterministic"
    assert diagnostic_exit_code(report) == 0


def test_openai_compatible_readiness_check_does_not_call_http() -> None:
    def fail_if_called(request: httpx.Request) -> httpx.Response:
        raise AssertionError("readiness mode must not call HTTP")

    client = httpx.Client(transport=httpx.MockTransport(fail_if_called))
    report = run_model_provider_diagnostic(
        configuration=_openai_settings(),
        http_client=client,
    )

    assert report.configuration_valid is True
    assert report.live_call_requested is False
    assert report.external_call_performed is False
    assert report.primary_provider_verified is False
    assert diagnostic_exit_code(report) == 0
    client.close()


def test_live_openai_compatible_diagnostic_verifies_primary_provider() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://model.example/v1/chat/completions"
        return httpx.Response(
            200,
            json={
                "id": "diagnostic-provider-request",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "ok",
                                    "mode": "connectivity_check",
                                    "message": "Provider is reachable.",
                                }
                            )
                        }
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    report = run_model_provider_diagnostic(
        live=True,
        configuration=_openai_settings(),
        http_client=client,
    )

    assert report.external_call_performed is True
    assert report.primary_provider_verified is True
    assert report.fallback_used is False
    assert report.effective_provider == "openai_compatible"
    assert diagnostic_exit_code(report) == 0
    assert "local-secret" not in report.model_dump_json()
    client.close()


def test_live_provider_failure_is_not_hidden_by_successful_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    report = run_model_provider_diagnostic(
        live=True,
        configuration=_openai_settings(),
        http_client=client,
    )

    assert report.primary_provider_verified is False
    assert report.fallback_used is True
    assert report.effective_provider == "deterministic"
    assert report.error_type == "provider_http_error"
    assert diagnostic_exit_code(report) == 1
    client.close()


def test_missing_live_configuration_returns_safe_report_without_secret() -> None:
    report = run_model_provider_diagnostic(
        live=True,
        configuration=Settings(
            model_provider="openai_compatible",
            model_api_base=None,
            model_api_key=None,
            model_name="example-model",
        ),
    )

    assert report.configuration_valid is False
    assert report.external_call_performed is False
    assert report.error_type == "missing_openai_compatible_configuration"
    assert diagnostic_exit_code(report) == 2


def test_default_deterministic_model_name_is_not_accepted_for_live_provider() -> None:
    report = run_model_provider_diagnostic(
        configuration=Settings(
            model_provider="openai_compatible",
            model_api_base="https://model.example/v1",
            model_api_key=SecretStr("local-secret"),
            model_name="deterministic-local",
        )
    )

    assert report.configuration_valid is False
    assert report.error_type == "missing_openai_compatible_configuration"


def test_default_workflow_uses_the_environment_aware_gateway_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_gateway = ModelGateway(
        DeterministicModelProvider(
            {
                "content": "safe",
                "contains_factual_claims": False,
                "waiting_for_user_confirmation": False,
                "human_confirmation_present": False,
                "action_status": "none",
            }
        )
    )
    calls: list[DeterministicModelProvider] = []

    def configured_factory(
        fallback: DeterministicModelProvider,
    ) -> ModelGateway:
        calls.append(fallback)
        return expected_gateway

    monkeypatch.setattr(
        workflow_module,
        "create_model_gateway",
        configured_factory,
    )

    workflow = LangGraphAgentWorkflow()

    assert workflow.model_gateway is expected_gateway
    assert len(calls) == 1


def test_workflow_only_closes_a_gateway_that_it_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned_gateway = ModelGateway(DeterministicModelProvider({"status": "ok"}))
    owned_close_calls: list[bool] = []
    injected_gateway = ModelGateway(DeterministicModelProvider({"status": "ok"}))
    injected_close_calls: list[bool] = []

    monkeypatch.setattr(
        workflow_module,
        "create_model_gateway",
        lambda fallback: owned_gateway,
    )
    monkeypatch.setattr(
        owned_gateway,
        "close",
        lambda: owned_close_calls.append(True),
    )
    monkeypatch.setattr(
        injected_gateway,
        "close",
        lambda: injected_close_calls.append(True),
    )

    owned_workflow = LangGraphAgentWorkflow()
    injected_workflow = LangGraphAgentWorkflow(model_gateway=injected_gateway)
    owned_workflow.close()
    injected_workflow.close()

    assert owned_close_calls == [True]
    assert injected_close_calls == []


def _openai_settings() -> Settings:
    return Settings(
        model_provider="openai_compatible",
        model_api_base="https://model.example/v1",
        model_api_key=SecretStr("local-secret"),
        model_name="example-model",
        model_timeout_ms=1000,
    )
