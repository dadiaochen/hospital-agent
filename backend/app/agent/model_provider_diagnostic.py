from __future__ import annotations

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.agent.model_gateway import (
    DeterministicModelProvider,
    ModelGateway,
    create_model_gateway,
)
from app.agent.model_gateway_schemas import ModelCallRequest, ModelMessage
from app.core.config import Settings, settings


class ProviderCheckOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^ok$")
    mode: str = Field(pattern="^connectivity_check$")
    message: str = Field(min_length=1)


class ModelProviderDiagnosticReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    configured_provider: str
    model_name: str
    configuration_valid: bool
    api_base_configured: bool
    api_key_configured: bool
    live_call_requested: bool
    external_call_performed: bool
    primary_provider_verified: bool
    deterministic_self_check_passed: bool
    fallback_used: bool
    effective_provider: str | None = None
    schema_valid: bool | None = None
    safety_passed: bool | None = None
    latency_ms: int = Field(default=0, ge=0)
    error_type: str | None = None


def run_model_provider_diagnostic(
    *,
    live: bool = False,
    configuration: Settings | None = None,
    http_client: httpx.Client | None = None,
) -> ModelProviderDiagnosticReport:
    configured = configuration or settings
    api_base_configured = bool(
        configured.model_api_base and configured.model_api_base.strip()
    )
    api_key_configured = bool(
        configured.model_api_key
        and configured.model_api_key.get_secret_value().strip()
    )
    provider_supported = configured.model_provider in {
        "deterministic",
        "openai_compatible",
    }
    configuration_valid = provider_supported and (
        configured.model_provider == "deterministic"
        or (
            api_base_configured
            and api_key_configured
            and bool(configured.model_name.strip())
            and configured.model_name != "deterministic-local"
        )
    )
    deterministic = _diagnostic_deterministic_provider()
    deterministic_result = ModelGateway(deterministic).invoke(
        _diagnostic_request(),
        ProviderCheckOutput,
    )
    deterministic_passed = deterministic_result.trace.success

    if not configuration_valid:
        return ModelProviderDiagnosticReport(
            configured_provider=configured.model_provider,
            model_name=configured.model_name,
            configuration_valid=False,
            api_base_configured=api_base_configured,
            api_key_configured=api_key_configured,
            live_call_requested=live,
            external_call_performed=False,
            primary_provider_verified=False,
            deterministic_self_check_passed=deterministic_passed,
            fallback_used=False,
            error_type=(
                "unsupported_model_provider"
                if not provider_supported
                else "missing_openai_compatible_configuration"
            ),
        )

    if configured.model_provider == "deterministic":
        return ModelProviderDiagnosticReport(
            configured_provider=configured.model_provider,
            model_name=configured.model_name,
            configuration_valid=True,
            api_base_configured=api_base_configured,
            api_key_configured=api_key_configured,
            live_call_requested=live,
            external_call_performed=False,
            primary_provider_verified=False,
            deterministic_self_check_passed=deterministic_passed,
            fallback_used=False,
            effective_provider=deterministic_result.trace.effective_provider,
            schema_valid=deterministic_result.trace.schema_valid,
            safety_passed=deterministic_result.trace.safety_passed,
            latency_ms=deterministic_result.trace.latency_ms,
        )

    if not live:
        return ModelProviderDiagnosticReport(
            configured_provider=configured.model_provider,
            model_name=configured.model_name,
            configuration_valid=True,
            api_base_configured=True,
            api_key_configured=True,
            live_call_requested=False,
            external_call_performed=False,
            primary_provider_verified=False,
            deterministic_self_check_passed=deterministic_passed,
            fallback_used=False,
        )

    gateway = create_model_gateway(
        deterministic,
        http_client=http_client,
        configuration=configured,
    )
    try:
        result = gateway.invoke(_diagnostic_request(), ProviderCheckOutput)
    finally:
        gateway.close()
    primary_attempt = result.trace.attempts[0]
    primary_verified = (
        primary_attempt.provider_name == "openai_compatible"
        and primary_attempt.success
    )
    return ModelProviderDiagnosticReport(
        configured_provider=configured.model_provider,
        model_name=configured.model_name,
        configuration_valid=True,
        api_base_configured=True,
        api_key_configured=True,
        live_call_requested=True,
        external_call_performed=True,
        primary_provider_verified=primary_verified,
        deterministic_self_check_passed=deterministic_passed,
        fallback_used=result.trace.fallback_used,
        effective_provider=result.trace.effective_provider,
        schema_valid=result.trace.schema_valid,
        safety_passed=result.trace.safety_passed,
        latency_ms=result.trace.latency_ms,
        error_type=None if primary_verified else primary_attempt.error_type,
    )


def diagnostic_exit_code(report: ModelProviderDiagnosticReport) -> int:
    if not report.configuration_valid or not report.deterministic_self_check_passed:
        return 2
    if report.external_call_performed and not report.primary_provider_verified:
        return 1
    return 0


def _diagnostic_deterministic_provider() -> DeterministicModelProvider:
    return DeterministicModelProvider(
        {
            "status": "ok",
            "mode": "connectivity_check",
            "message": "Deterministic provider contract is available.",
        }
    )


def _diagnostic_request() -> ModelCallRequest:
    return ModelCallRequest(
        run_id="diagnostic-run",
        task_id="diagnostic-task",
        member_id="diagnostic-member",
        purpose="provider_connectivity_check",
        messages=(
            ModelMessage(
                role="system",
                content=(
                    "Return JSON only with status='ok', mode='connectivity_check', "
                    "and a short non-medical message."
                ),
            ),
            ModelMessage(
                role="user",
                content="Verify structured JSON connectivity without medical advice.",
            ),
        ),
        temperature=0.0,
        max_output_tokens=128,
    )


__all__ = [
    "ModelProviderDiagnosticReport",
    "ProviderCheckOutput",
    "diagnostic_exit_code",
    "run_model_provider_diagnostic",
]
