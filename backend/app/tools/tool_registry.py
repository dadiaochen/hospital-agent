from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

from app.tools.tool_schemas import ToolExecutionContext, ToolResult, ToolSpec


ToolHandler = Callable[[BaseModel, ToolExecutionContext], BaseModel | dict[str, Any]]


class ToolExecutionError(Exception):
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
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def get_spec(self, name: str) -> ToolSpec:
        return self._specs[name]

    def get_definition(self, name: str) -> ToolSpec:
        return self.get_spec(name)

    def list_specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def list_definitions(self) -> list[ToolSpec]:
        return self.list_specs()

    def list_tool_names(self) -> list[str]:
        return list(self._specs)

    def call(
        self,
        name: str,
        tool_input: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        started = perf_counter()
        if name not in self._specs:
            return self._failure(
                name=name,
                context=context,
                tool_input=tool_input,
                started=started,
                error_message=f"tool is not registered: {name}",
                error_type="tool_not_registered",
                fallback_action="manual_review",
                schema_valid=False,
                permission_scope="unknown",
                read_only=True,
                requires_human_confirmation=False,
            )

        spec = self._specs[name]
        if name not in context.allowed_tools:
            return self._failure(
                name=name,
                context=context,
                tool_input=tool_input,
                started=started,
                error_message=f"tool is not allowed in this context: {name}",
                error_type="allowed_tools_exclusion",
                fallback_action="ask_user_clarification",
                schema_valid=True,
                permission_scope=spec.permission_scope,
                read_only=spec.read_only,
                requires_human_confirmation=spec.requires_human_confirmation,
            )

        if spec.allowed_agent_roles and context.agent_role not in spec.allowed_agent_roles:
            return self._failure(
                name=name,
                context=context,
                tool_input=tool_input,
                started=started,
                error_message=(
                    f"{context.agent_role} does not have permission for tool {name}"
                ),
                error_type="permission_denied",
                fallback_action="manual_review",
                schema_valid=True,
                permission_scope=spec.permission_scope,
                read_only=spec.read_only,
                requires_human_confirmation=spec.requires_human_confirmation,
            )

        try:
            parsed_input = spec.input_schema.model_validate(tool_input)
        except ValidationError as exc:
            return self._failure(
                name=name,
                context=context,
                tool_input=tool_input,
                started=started,
                error_message=str(exc),
                error_type="input_schema_invalid",
                fallback_action="ask_user_clarification",
                schema_valid=False,
                permission_scope=spec.permission_scope,
                read_only=spec.read_only,
                requires_human_confirmation=spec.requires_human_confirmation,
            )

        try:
            raw_output = self._handlers[name](parsed_input, context)
        except ToolExecutionError as exc:
            return self._failure(
                name=name,
                context=context,
                tool_input=parsed_input.model_dump(mode="json"),
                started=started,
                error_message=str(exc),
                error_type=exc.error_type,
                fallback_action=exc.fallback_action,
                schema_valid=exc.schema_valid,
                permission_scope=spec.permission_scope,
                read_only=spec.read_only,
                requires_human_confirmation=spec.requires_human_confirmation,
            )
        except Exception as exc:  # pragma: no cover - defensive boundary
            return self._failure(
                name=name,
                context=context,
                tool_input=parsed_input.model_dump(mode="json"),
                started=started,
                error_message=str(exc),
                error_type="handler_error",
                fallback_action="manual_review",
                schema_valid=True,
                permission_scope=spec.permission_scope,
                read_only=spec.read_only,
                requires_human_confirmation=spec.requires_human_confirmation,
            )

        output_payload = (
            raw_output.model_dump(mode="json")
            if isinstance(raw_output, BaseModel)
            else raw_output
        )
        try:
            output = spec.output_schema.model_validate(output_payload)
        except ValidationError as exc:
            return self._failure(
                name=name,
                context=context,
                tool_input=parsed_input.model_dump(mode="json"),
                started=started,
                error_message=str(exc),
                error_type="output_schema_invalid",
                fallback_action="manual_review",
                schema_valid=False,
                permission_scope=spec.permission_scope,
                read_only=spec.read_only,
                requires_human_confirmation=spec.requires_human_confirmation,
            )

        dumped_output = output.model_dump(mode="json")
        return ToolResult(
            tool_name=name,
            run_id=context.run_id,
            agent_role=context.agent_role,
            member_id=context.member_id,
            tool_input=parsed_input.model_dump(mode="json"),
            tool_output=dumped_output,
            latency_ms=self._elapsed_ms(started),
            success=True,
            error_message=None,
            error_type=None,
            fallback_action="not_required",
            schema_valid=True,
            evidence_present=bool(dumped_output.get("evidence_present", True)),
            source_id=dumped_output.get("source_id"),
            source_name=dumped_output.get("source_name") or name,
            permission_scope=spec.permission_scope,
            requires_human_confirmation=spec.requires_human_confirmation,
            read_only=spec.read_only,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, int((perf_counter() - started) * 1000))

    def _failure(
        self,
        *,
        name: str,
        context: ToolExecutionContext,
        tool_input: dict[str, Any],
        started: float,
        error_message: str,
        error_type: str,
        fallback_action: str,
        schema_valid: bool,
        permission_scope: str,
        read_only: bool,
        requires_human_confirmation: bool,
    ) -> ToolResult:
        return ToolResult(
            tool_name=name,
            run_id=context.run_id,
            agent_role=context.agent_role,
            member_id=context.member_id,
            tool_input=tool_input,
            tool_output=None,
            latency_ms=self._elapsed_ms(started),
            success=False,
            error_message=error_message,
            error_type=error_type,
            fallback_action=fallback_action,
            schema_valid=schema_valid,
            evidence_present=False,
            source_id=None,
            source_name=name,
            permission_scope=permission_scope,
            requires_human_confirmation=requires_human_confirmation,
            read_only=read_only,
        )
