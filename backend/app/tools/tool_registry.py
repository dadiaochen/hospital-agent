from collections.abc import Callable
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

from app.schemas.business import SourceRef
from app.tools.tool_schemas import ToolExecutionContext, ToolResult, ToolSpec


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
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.fallback_action = fallback_action
        self.schema_valid = schema_valid


class ToolRegistry:
    """Deterministic tool registry contract layer."""

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}

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

        try:
            raw_output = self._handlers[tool_name](validated_input, execution_context)
        except ToolExecutionError as exc:
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
                retryable=exc.error_type in {"timeout", "provider_unavailable"},
            )
        except Exception as exc:  # noqa: BLE001 - registry normalizes handler failures.
            return self._failure(
                tool_name=tool_name,
                started=started,
                error_type="handler_error",
                error_message=str(exc),
                fallback_action="use_fallback_action",
                requires_human_confirmation=spec.requires_human_confirmation,
                execution_context=execution_context,
                tool_version=spec.tool_version,
                retryable=True,
            )

        try:
            validated_output = spec.output_schema.model_validate(raw_output)
        except ValidationError as exc:
            return self._failure(
                tool_name=tool_name,
                started=started,
                error_type="output_schema_error",
                error_message=str(exc),
                fallback_action="fix_tool_handler_output",
                schema_valid=False,
                requires_human_confirmation=spec.requires_human_confirmation,
                execution_context=execution_context,
                tool_version=spec.tool_version,
            )

        output = validated_output.model_dump()
        evidence_refs = [
            SourceRef.model_validate(item)
            for item in output.get("source_refs", [])
        ]
        return ToolResult(
            tool_name=tool_name,
            tool_version=spec.tool_version,
            provider_mode=execution_context.provider_mode,
            success=True,
            output=output,
            run_id=execution_context.run_id,
            agent_role=execution_context.agent_role,
            member_id=execution_context.member_id,
            tool_input=validated_input.model_dump(mode="json"),
            error_type=None,
            error_message=None,
            fallback_action=None,
            latency_ms=self._elapsed_ms(started),
            schema_valid=True,
            requires_human_confirmation=spec.requires_human_confirmation,
            evidence_present=bool(output.get("evidence_present", False))
            or bool(evidence_refs),
            evidence_refs=evidence_refs,
            retryable=False,
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
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, int((perf_counter() - started) * 1000))
