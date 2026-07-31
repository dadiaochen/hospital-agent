from collections.abc import Callable
from time import perf_counter, sleep

from pydantic import ValidationError

from app.core.reliability import RETRYABLE_ERROR_CATEGORIES, classify_error
from app.providers.schemas import (
    ProviderAttemptTrace,
    ProviderRequest,
    ProviderResponse,
    ProviderRetryPolicy,
)


ProviderHandler = Callable[[ProviderRequest], ProviderResponse]


class ProviderInvocationError(Exception):
    """A normalized adapter failure safe to expose through provider traces."""

    def __init__(
        self,
        message: str,
        *,
        error_type: str,
        retryable: bool,
        fallback_reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable
        self.fallback_reason = fallback_reason or error_type


class ProviderRegistry:
    def __init__(self, *, sleeper: Callable[[float], None] = sleep) -> None:
        self._handlers: dict[str, ProviderHandler] = {}
        self._retry_policies: dict[str, ProviderRetryPolicy] = {}
        self._sleeper = sleeper

    def register(
        self,
        name: str,
        handler: ProviderHandler,
        *,
        retry_policy: ProviderRetryPolicy | None = None,
    ) -> None:
        if name in self._handlers:
            raise ValueError(f"provider already registered: {name}")
        self._handlers[name] = handler
        self._retry_policies[name] = retry_policy or ProviderRetryPolicy()

    def invoke(self, name: str, request: ProviderRequest) -> ProviderResponse:
        handler = self._handlers.get(name)
        if handler is None:
            return self._failure(
                name,
                request,
                error_type="provider_unavailable",
                message="provider is not registered",
                retryable=False,
                fallback_reason="provider_not_registered",
                attempts=[],
                latency_ms=0,
            )

        policy = self._retry_policies[name]
        attempts: list[ProviderAttemptTrace] = []
        total_started = perf_counter()
        last_failure: ProviderResponse | None = None

        for attempt_no in range(1, policy.max_attempts + 1):
            started = perf_counter()
            try:
                response = handler(request)
                response = self._validate_identity(name, request, response)
            except ProviderInvocationError as exc:
                response = self._failure(
                    name,
                    request,
                    error_type=exc.error_type,
                    message=self._safe_error_message(exc.error_type),
                    retryable=exc.retryable,
                    fallback_reason=exc.fallback_reason,
                    attempts=[],
                    latency_ms=self._elapsed_ms(started),
                )
            except ValidationError:
                response = self._failure(
                    name,
                    request,
                    error_type="schema_error",
                    message="provider response schema validation failed",
                    retryable=False,
                    fallback_reason="provider_schema_invalid",
                    attempts=[],
                    latency_ms=self._elapsed_ms(started),
                )
            except Exception:  # noqa: BLE001 - provider boundary hides raw errors.
                response = self._failure(
                    name,
                    request,
                    error_type="internal_error",
                    message="provider invocation failed",
                    retryable=False,
                    fallback_reason="provider_internal_error",
                    attempts=[],
                    latency_ms=self._elapsed_ms(started),
                )

            attempt_latency = self._elapsed_ms(started)
            attempts.append(
                ProviderAttemptTrace(
                    attempt_no=attempt_no,
                    success=response.success,
                    latency_ms=attempt_latency,
                    error_type=response.error_type,
                    error_category=response.error_category,
                    retryable=response.retryable,
                )
            )
            if response.success:
                return response.model_copy(
                    update={
                        "attempts": attempts,
                        "latency_ms": self._elapsed_ms(total_started),
                    }
                )

            last_failure = response
            can_retry = (
                response.retryable
                and response.error_category in RETRYABLE_ERROR_CATEGORIES
                and attempt_no < policy.max_attempts
            )
            if not can_retry:
                break
            if policy.backoff_ms:
                self._sleeper(policy.backoff_ms / 1000)

        assert last_failure is not None
        return last_failure.model_copy(
            update={
                "attempts": attempts,
                "latency_ms": self._elapsed_ms(total_started),
                "retryable": False,
            }
        )

    @staticmethod
    def _validate_identity(
        name: str,
        request: ProviderRequest,
        response: ProviderResponse,
    ) -> ProviderResponse:
        if any(
            (
                response.provider_name != name,
                response.provider_mode != request.provider_mode,
                response.operation != request.operation,
                any(
                    source.provider != name
                    or source.member_id != request.member_id
                    for source in response.source_refs
                ),
            )
        ):
            raise ProviderInvocationError(
                "provider response identity does not match the request",
                error_type="schema_error",
                retryable=False,
                fallback_reason="provider_identity_mismatch",
            )
        return response

    @staticmethod
    def _failure(
        name: str,
        request: ProviderRequest,
        *,
        error_type: str,
        message: str,
        retryable: bool,
        fallback_reason: str,
        attempts: list[ProviderAttemptTrace],
        latency_ms: int,
    ) -> ProviderResponse:
        error_category = classify_error(error_type)
        return ProviderResponse(
            provider_name=name,
            provider_mode=request.provider_mode,
            operation=request.operation,
            success=False,
            error_type=error_type,
            error_category=error_category,
            error_message=message,
            retryable=(
                retryable and error_category in RETRYABLE_ERROR_CATEGORIES
            ),
            degraded=True,
            fallback_reason=fallback_reason,
            attempts=attempts,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, int((perf_counter() - started) * 1000))

    @staticmethod
    def _safe_error_message(error_type: str) -> str:
        messages = {
            "timeout": "provider request timed out",
            "rate_limit": "provider rate limit reached",
            "provider_unavailable": "provider is temporarily unavailable",
            "business_conflict": "provider reported a business state conflict",
            "schema_error": "provider response schema validation failed",
        }
        return messages.get(error_type, "provider invocation failed")

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))


__all__ = [
    "ProviderHandler",
    "ProviderInvocationError",
    "ProviderRegistry",
]
