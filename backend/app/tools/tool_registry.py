from collections.abc import Callable
from time import perf_counter, sleep
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.reliability import RETRYABLE_ERROR_CATEGORIES, classify_error
from app.schemas.business import SourceRef
from app.tools.tool_schemas import (
    ToolAttemptTrace,
    ToolExecutionContext,
    ToolResult,
    ToolSpec,
)


ToolHandler = Callable[[BaseModel, ToolExecutionContext], BaseModel | dict[str, Any]]


class ToolExecutionError(Exception):
    """Expected handler failure normalized into a structured ToolResult."""

    def __init__(
        self,
        message: str,
        *,
        error_type: str = "handler_error",
        fallback_action: str = "manual_review",
        schema_valid: bool = True,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.fallback_action = fallback_action
        self.schema_valid = schema_valid
        self.retryable = (
            classify_error(error_type) in RETRYABLE_ERROR_CATEGORIES
            if retryable is None
            else retryable
        )


class ToolRegistry:
    """Deterministic tool registry contract layer."""

    def __init__(self, *, sleeper: Callable[[float], None] = sleep) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}
        self._sleeper = sleeper

    def register(self, tool_spec: ToolSpec, handler: ToolHandler) -> None:
        if tool_spec.name in self._specs:
            raise ValueError(f"tool already registered: {tool_spec.name}")
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._specs[tool_spec.name] = tool_spec
        self._handlers[tool_spec.name] = handler

    def get_tool(self, name: str) -> ToolSpec:
        return self._specs[name]

    def get_definition(self, name: str) -> ToolSpec:
        return self.get_tool(name)

    def get_spec(self, name: str) -> ToolSpec:
        return self.get_tool(name)

    def list_tools(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def list_definitions(self) -> list[ToolSpec]:
        return self.list_tools()

    def list_specs(self) -> list[ToolSpec]:
        return self.list_tools()

    def list_tool_names(self) -> list[str]:
        return list(self._specs)

    def list_allowed_tools(self, agent_role: str) -> list[ToolSpec]:
        return [
            spec
            for spec in self._specs.values()
            if agent_role in spec.allowed_agent_roles
        ]

    def call(
        self,
        tool_name: str,
        tool_input: dict[str, Any] | BaseModel,
        execution_context: ToolExecutionContext,
    ) -> ToolResult:
        started = perf_counter()
        spec = self._specs.get(tool_name)
        if spec is None:
            return self._failure(
                tool_name=tool_name,
                started=started,
                error_type="tool_not_found",
                error_message=f"tool is not registered: {tool_name}",
                fallback_action="check_tool_registry",
                schema_valid=False,
                execution_context=execution_context,
            )

        if tool_name not in execution_context.allowed_tools:
            return self._failure(
                tool_name=tool_name,
                started=started,
                error_type="tool_not_allowed",
                error_message=f"tool is not in execution_context.allowed_tools: {tool_name}",
                fallback_action="use_allowed_tool_from_context",
                requires_human_confirmation=spec.requires_human_confirmation,
                execution_context=execution_context,
                tool_version=spec.tool_version,
            )

        if execution_context.agent_role not in spec.allowed_agent_roles:
            return self._failure(
                tool_name=tool_name,
                started=started,
                error_type="permission_denied",
                error_message=(
                    f"{execution_context.agent_role} is not allowed to call {tool_name}"
                ),
                fallback_action="route_to_authorized_agent",
                requires_human_confirmation=spec.requires_human_confirmation,
                execution_context=execution_context,
                tool_version=spec.tool_version,
            )

        if spec.requires_human_confirmation and not execution_context.human_confirmation_granted:
            return self._failure(
                tool_name=tool_name,
                started=started,
                error_type="human_confirmation_required",
                error_message=f"{tool_name} requires human confirmation before execution",
                fallback_action="require_human_confirmation",
                requires_human_confirmation=True,
                execution_context=execution_context,
                tool_version=spec.tool_version,
            )

        try:
            validated_input = spec.input_schema.model_validate(tool_input)
        except ValidationError as exc:
            return self._failure(
                tool_name=tool_name,
                started=started,
                error_type="input_schema_error",
                error_message=str(exc),
                fallback_action="fix_tool_input",
                schema_valid=False,
                requires_human_confirmation=spec.requires_human_confirmation,
                execution_context=execution_context,
                tool_version=spec.tool_version,
            )

        attempts: list[ToolAttemptTrace] = []
        raw_output: BaseModel | dict[str, Any] | None = None
        max_attempts = spec.retry_policy.max_attempts if spec.read_only else 1
        for attempt_no in range(1, max_attempts + 1):
            attempt_started = perf_counter()
            try:
                raw_output = self._handlers[tool_name](
                    validated_input,
                    execution_context,
                )
            except ToolExecutionError as exc:
                category = classify_error(exc.error_type)
                can_retry = (
                    spec.read_only
                    and exc.retryable
                    and category in RETRYABLE_ERROR_CATEGORIES
                    and attempt_no < max_attempts
                )
                attempts.append(
                    ToolAttemptTrace(
                        attempt_no=attempt_no,
                        success=False,
                        latency_ms=self._elapsed_ms(attempt_started),
                        error_type=exc.error_type,
                        error_category=category,
                        retryable=can_retry,
                    )
                )
                if can_retry:
                    if spec.retry_policy.backoff_ms:
                        self._sleeper(spec.retry_policy.backoff_ms / 1000)
                    continue
                return self._failure(
                    tool_name=tool_name,
                    started=started,
                    error_type=exc.error_type,
                    error_message=str(exc),
                    fallback_action=exc.fallback_action,
                    schema_valid=exc.schema_valid,
                    requires_human_confirmation=spec.requires_human_confirmation,
                    execution_context=execution_context,
                    tool_input=validated_input.model_dump(mode="json"),
                    permission_scope=spec.permission_scope,
                    read_only=spec.read_only,
                    tool_version=spec.tool_version,
                    retryable=False,
                    attempts=attempts,
                )
            except Exception:  # noqa: BLE001 - registry hides raw handler errors.
                attempts.append(
                    ToolAttemptTrace(
                        attempt_no=attempt_no,
                        success=False,
                        latency_ms=self._elapsed_ms(attempt_started),
                        error_type="handler_error",
                        error_category="internal",
                        retryable=False,
                    )
                )
                return self._failure(
                    tool_name=tool_name,
                    started=started,
                    error_type="handler_error",
                    error_message="tool handler failed",
                    fallback_action="use_fallback_action",
                    requires_human_confirmation=spec.requires_human_confirmation,
                    execution_context=execution_context,
                    tool_input=validated_input.model_dump(mode="json"),
                    permission_scope=spec.permission_scope,
                    read_only=spec.read_only,
                    tool_version=spec.tool_version,
                    retryable=False,
                    attempts=attempts,
                )
            else:
                attempts.append(
                    ToolAttemptTrace(
                        attempt_no=attempt_no,
                        success=True,
                        latency_ms=self._elapsed_ms(attempt_started),
                    )
                )
                break

        try:
            validated_output = spec.output_schema.model_validate(raw_output)
        except ValidationError as exc:
            attempts[-1] = ToolAttemptTrace(
                attempt_no=attempts[-1].attempt_no,
                success=False,
                latency_ms=attempts[-1].latency_ms,
                error_type="output_schema_error",
                error_category="schema",
                retryable=False,
            )
            return self._failure(
                tool_name=tool_name,
                started=started,
                error_type="output_schema_error",
                error_message=str(exc),
                fallback_action="fix_tool_handler_output",
                schema_valid=False,
                requires_human_confirmation=spec.requires_human_confirmation,
                execution_context=execution_context,
                tool_input=validated_input.model_dump(mode="json"),
                permission_scope=spec.permission_scope,
                read_only=spec.read_only,
                tool_version=spec.tool_version,
                attempts=attempts,
            )

        output = validated_output.model_dump()
        evidence_refs = [
            SourceRef.model_validate(item)
            for item in output.get("source_refs", [])
        ]
        semantic_success = output.get("success") is not False
        if not semantic_success:
            error_type = str(output.get("error_type") or "provider_unavailable")
            attempts[-1] = ToolAttemptTrace(
                attempt_no=attempts[-1].attempt_no,
                success=False,
                latency_ms=attempts[-1].latency_ms,
                error_type=error_type,
                error_category=classify_error(error_type),
                retryable=False,
            )
        else:
            error_type = None

        return ToolResult(
            tool_name=tool_name,
            tool_version=spec.tool_version,
            provider_mode=execution_context.provider_mode,
            success=semantic_success,
            output=output,
            run_id=execution_context.run_id,
            agent_role=execution_context.agent_role,
            member_id=execution_context.member_id,
            tool_input=validated_input.model_dump(mode="json"),
            error_type=error_type,
            error_category=(classify_error(error_type) if error_type else None),
            error_message=(
                str(output.get("error_message"))
                if output.get("error_message")
                else None
            ),
            fallback_action=(
                str(output.get("fallback_reason"))
                if output.get("fallback_reason")
                else None
            ),
            latency_ms=self._elapsed_ms(started),
            schema_valid=True,
            requires_human_confirmation=spec.requires_human_confirmation,
            evidence_present=bool(output.get("evidence_present", False))
            or bool(evidence_refs),
            evidence_refs=evidence_refs,
            retryable=False,
            attempts=attempts,
            source_name=output.get("source_name", tool_name),
            permission_scope=spec.permission_scope,
            read_only=spec.read_only,
        )

    @classmethod
    def _failure(
        cls,
        *,
        tool_name: str,
        started: float,
        error_type: str,
        error_message: str,
        fallback_action: str,
        schema_valid: bool = True,
        requires_human_confirmation: bool = False,
        execution_context: ToolExecutionContext | None = None,
        tool_input: dict[str, Any] | None = None,
        permission_scope: str | None = None,
        read_only: bool = True,
        tool_version: str = "v1",
        retryable: bool = False,
        attempts: list[ToolAttemptTrace] | None = None,
    ) -> ToolResult:
        return ToolResult.failure(
            tool_name=tool_name,
            tool_version=tool_version,
            provider_mode=(
                execution_context.provider_mode if execution_context else "mock"
            ),
            error_type=error_type,
            error_message=error_message,
            fallback_action=fallback_action,
            latency_ms=cls._elapsed_ms(started),
            schema_valid=schema_valid,
            requires_human_confirmation=requires_human_confirmation,
            run_id=execution_context.run_id if execution_context else None,
            agent_role=execution_context.agent_role if execution_context else None,
            member_id=execution_context.member_id if execution_context else None,
            tool_input=tool_input,
            permission_scope=permission_scope,
            read_only=read_only,
            retryable=retryable,
            attempts=attempts,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, int((perf_counter() - started) * 1000))
