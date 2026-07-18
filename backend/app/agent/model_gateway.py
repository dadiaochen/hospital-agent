from __future__ import annotations

from collections.abc import Callable, Mapping
import json
from time import perf_counter
from typing import Any, Protocol, TypeVar, runtime_checkable

import httpx
from pydantic import BaseModel, ValidationError

from app.agent.model_gateway_schemas import (
    ModelCallRequest,
    ModelCallResult,
    ModelCallTrace,
    ModelProviderAttemptTrace,
    ProviderRawResponse,
)
from app.core.config import settings
from app.safety.model_output import (
    ModelOutputSafetyChecker,
    RuleBasedModelOutputSafetyChecker,
)


class ModelProviderError(RuntimeError):
    def __init__(self, error_type: str) -> None:
        super().__init__(error_type)
        self.error_type = error_type


class ModelProviderTimeout(ModelProviderError):
    def __init__(self) -> None:
        super().__init__("provider_timeout")


@runtime_checkable
class ModelProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def invoke(self, request: ModelCallRequest) -> ProviderRawResponse:
        """Return provider text; parsing and safety remain Gateway duties."""


DeterministicPayload = Mapping[str, Any] | BaseModel | str
DeterministicPayloadFactory = Callable[[ModelCallRequest], DeterministicPayload]


class DeterministicModelProvider:
    provider_name = "deterministic"

    def __init__(
        self,
        payload: DeterministicPayload | DeterministicPayloadFactory,
        *,
        model_name: str = "deterministic-local",
    ) -> None:
        self._payload = payload
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def invoke(self, request: ModelCallRequest) -> ProviderRawResponse:
        payload = self._payload(request) if callable(self._payload) else self._payload
        if isinstance(payload, BaseModel):
            content = payload.model_dump_json()
        elif isinstance(payload, str):
            content = payload
        else:
            content = json.dumps(dict(payload), ensure_ascii=False)
        return ProviderRawResponse(
            provider_name=self.provider_name,
            model_name=self.model_name,
            content=content,
            provider_request_id=f"deterministic:{request.run_id}",
        )


class OpenAICompatibleModelProvider:
    provider_name = "openai_compatible"

    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        model_name: str,
        timeout_ms: int,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_base.strip() or not api_key.strip() or not model_name.strip():
            raise ValueError("api_base, api_key and model_name are required")
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._model_name = model_name
        self._client = client or httpx.Client(timeout=timeout_ms / 1000)
        self._owns_client = client is None

    @property
    def model_name(self) -> str:
        return self._model_name

    def invoke(self, request: ModelCallRequest) -> ProviderRawResponse:
        try:
            response = self._client.post(
                f"{self._api_base}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self.model_name,
                    "messages": [message.model_dump() for message in request.messages],
                    "temperature": request.temperature,
                    "max_tokens": request.max_output_tokens,
                    "response_format": {"type": "json_object"},
                },
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ModelProviderTimeout() from exc
        except httpx.HTTPError as exc:
            raise ModelProviderError("provider_http_error") from exc

        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            request_id = payload.get("id") or response.headers.get("x-request-id")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ModelProviderError("provider_response_invalid") from exc
        if not isinstance(content, str) or not content.strip():
            raise ModelProviderError("provider_response_invalid")

        return ProviderRawResponse(
            provider_name=self.provider_name,
            model_name=self.model_name,
            content=content,
            provider_request_id=request_id,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


OutputT = TypeVar("OutputT", bound=BaseModel)


class ModelGateway:
    def __init__(
        self,
        primary_provider: ModelProvider,
        *,
        fallback_provider: ModelProvider | None = None,
        safety_checker: ModelOutputSafetyChecker | None = None,
    ) -> None:
        self._primary_provider = primary_provider
        self._fallback_provider = fallback_provider
        self._safety_checker = safety_checker or RuleBasedModelOutputSafetyChecker()

    def invoke(
        self,
        request: ModelCallRequest,
        response_model: type[OutputT],
    ) -> ModelCallResult[OutputT]:
        output, primary_attempt = self._attempt(
            self._primary_provider,
            request,
            response_model,
        )
        attempts = [primary_attempt]
        fallback_used = False
        fallback_reason: str | None = None

        if output is None and self._can_fallback():
            fallback_used = True
            fallback_reason = primary_attempt.error_type
            output, fallback_attempt = self._attempt(
                self._fallback_provider,
                request,
                response_model,
            )
            attempts.append(fallback_attempt)

        final_attempt = attempts[-1]
        success = output is not None
        trace = ModelCallTrace(
            run_id=request.run_id,
            task_id=request.task_id,
            member_id=request.member_id,
            purpose=request.purpose,
            requested_provider=self._primary_provider.provider_name,
            effective_provider=(final_attempt.provider_name if success else None),
            success=success,
            schema_valid=final_attempt.schema_valid,
            safety_passed=final_attempt.safety_passed,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            latency_ms=sum(attempt.latency_ms for attempt in attempts),
            attempts=tuple(attempts),
        )
        result_model = ModelCallResult[response_model]  # type: ignore[valid-type]
        return result_model(output=output, trace=trace)

    def _can_fallback(self) -> bool:
        return (
            self._fallback_provider is not None
            and self._fallback_provider is not self._primary_provider
        )

    def _attempt(
        self,
        provider: ModelProvider,
        request: ModelCallRequest,
        response_model: type[OutputT],
    ) -> tuple[OutputT | None, ModelProviderAttemptTrace]:
        started = perf_counter()
        try:
            response = provider.invoke(request)
        except ModelProviderError as exc:
            return None, _failed_attempt(
                provider,
                started,
                error_type=exc.error_type,
            )
        except Exception as exc:
            return None, _failed_attempt(
                provider,
                started,
                error_type=f"provider_error:{type(exc).__name__}",
            )

        try:
            payload = json.loads(response.content)
            output = response_model.model_validate(payload)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
            return None, _failed_attempt(
                provider,
                started,
                error_type="schema_validation_failed",
            )

        try:
            safety = self._safety_checker.check(output)
        except Exception as exc:
            return None, _failed_attempt(
                provider,
                started,
                error_type=f"safety_check_error:{type(exc).__name__}",
                schema_valid=True,
            )
        if not safety.passed:
            return None, _failed_attempt(
                provider,
                started,
                error_type="safety_check_failed",
                schema_valid=True,
                safety_flags=safety.flags,
            )

        return output, ModelProviderAttemptTrace(
            provider_name=provider.provider_name,
            model_name=provider.model_name,
            success=True,
            schema_valid=True,
            safety_passed=True,
            latency_ms=_elapsed_ms(started),
        )


def create_model_gateway(
    deterministic_provider: DeterministicModelProvider,
    *,
    safety_checker: ModelOutputSafetyChecker | None = None,
    http_client: httpx.Client | None = None,
) -> ModelGateway:
    if settings.model_provider == "deterministic":
        return ModelGateway(
            deterministic_provider,
            safety_checker=safety_checker,
        )
    if settings.model_provider != "openai_compatible":
        raise ValueError(f"unsupported MODEL_PROVIDER: {settings.model_provider}")
    if not settings.model_api_base or not settings.model_api_key:
        raise ValueError(
            "MODEL_API_BASE and MODEL_API_KEY are required for openai_compatible"
        )

    primary = OpenAICompatibleModelProvider(
        api_base=settings.model_api_base,
        api_key=settings.model_api_key.get_secret_value(),
        model_name=settings.model_name,
        timeout_ms=settings.model_timeout_ms,
        client=http_client,
    )
    return ModelGateway(
        primary,
        fallback_provider=deterministic_provider,
        safety_checker=safety_checker,
    )


def _failed_attempt(
    provider: ModelProvider,
    started: float,
    *,
    error_type: str,
    schema_valid: bool = False,
    safety_flags: tuple[str, ...] = (),
) -> ModelProviderAttemptTrace:
    return ModelProviderAttemptTrace(
        provider_name=provider.provider_name,
        model_name=provider.model_name,
        success=False,
        schema_valid=schema_valid,
        safety_passed=False,
        safety_flags=safety_flags,
        latency_ms=_elapsed_ms(started),
        error_type=error_type,
    )


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


__all__ = [
    "DeterministicModelProvider",
    "ModelGateway",
    "ModelProvider",
    "ModelProviderError",
    "ModelProviderTimeout",
    "OpenAICompatibleModelProvider",
    "create_model_gateway",
]
