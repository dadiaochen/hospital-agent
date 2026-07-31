import pytest
from pydantic import BaseModel

from app.tools.tool_registry import ToolExecutionError, ToolRegistry
from app.tools.tool_schemas import RetryPolicy, ToolExecutionContext, ToolResult, ToolSpec


class EchoInput(BaseModel):
    value: str


class EchoOutput(BaseModel):
    source_id: str
    source_name: str
    evidence_present: bool
    echoed: str


class BrokenOutput(BaseModel):
    required_value: str


def make_spec(
    *,
    name: str = "echo_tool",
    output_schema: type[BaseModel] = EchoOutput,
    allowed_agent_roles: list[str] | None = None,
    requires_human_confirmation: bool = False,
    retry_policy: RetryPolicy | None = None,
    read_only: bool = True,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description="Echo test tool.",
        input_schema=EchoInput,
        output_schema=output_schema,
        permission_scope="safety:read",
        allowed_agent_roles=allowed_agent_roles or ["SafetyAgent"],
        timeout_ms=100,
        retry_policy=retry_policy or RetryPolicy(max_attempts=1, backoff_ms=0),
        requires_human_confirmation=requires_human_confirmation,
        read_only=read_only,
    )


def make_context(
    *,
    agent_role: str = "SafetyAgent",
    allowed_tools: list[str] | None = None,
    human_confirmation_granted: bool = False,
) -> ToolExecutionContext:
    return ToolExecutionContext(
        run_id="run-tool-1",
        task_id="task-tool-1",
        member_id="member-father",
        agent_role=agent_role,
        allowed_tools=allowed_tools if allowed_tools is not None else ["echo_tool"],
        safety_flags=[],
        human_confirmation_granted=human_confirmation_granted,
    )


def echo_handler(tool_input: EchoInput, _: ToolExecutionContext) -> EchoOutput:
    return EchoOutput(
        source_id="source-echo",
        source_name="echo_tool",
        evidence_present=True,
        echoed=tool_input.value,
    )


def test_can_register_tool_and_list_allowed_tools() -> None:
    registry = ToolRegistry()
    spec = make_spec()

    registry.register(spec, echo_handler)

    assert registry.get_tool("echo_tool") == spec
    assert registry.list_tools() == [spec]
    assert registry.list_allowed_tools("SafetyAgent") == [spec]
    assert registry.list_allowed_tools("RefillAgent") == []


def test_duplicate_tool_registration_fails() -> None:
    registry = ToolRegistry()
    spec = make_spec()
    registry.register(spec, echo_handler)

    with pytest.raises(ValueError):
        registry.register(spec, echo_handler)


def test_unregistered_tool_call_fails_with_tool_result() -> None:
    result = ToolRegistry().call(
        "missing_tool",
        {"value": "hello"},
        make_context(allowed_tools=["missing_tool"]),
    )

    assert result.success is False
    assert result.error_type == "tool_not_found"
    assert result.error_category == "not_found"
    assert result.fallback_action == "check_tool_registry"
    assert result.schema_valid is False


def test_agent_role_without_permission_fails() -> None:
    registry = ToolRegistry()
    registry.register(make_spec(), echo_handler)

    result = registry.call(
        "echo_tool",
        {"value": "hello"},
        make_context(agent_role="RefillAgent", allowed_tools=["echo_tool"]),
    )

    assert result.success is False
    assert result.error_type == "permission_denied"
    assert result.error_category == "permission"
    assert result.fallback_action == "route_to_authorized_agent"


def test_tool_not_in_allowed_tools_fails() -> None:
    registry = ToolRegistry()
    registry.register(make_spec(), echo_handler)

    result = registry.call("echo_tool", {"value": "hello"}, make_context(allowed_tools=[]))

    assert result.success is False
    assert result.error_type == "tool_not_allowed"
    assert result.fallback_action == "use_allowed_tool_from_context"


def test_input_schema_validation_failure_returns_failure_result() -> None:
    registry = ToolRegistry()
    registry.register(make_spec(), echo_handler)

    result = registry.call("echo_tool", {"wrong": "hello"}, make_context())

    assert result.success is False
    assert result.error_type == "input_schema_error"
    assert result.error_category == "validation"
    assert result.schema_valid is False
    assert result.fallback_action == "fix_tool_input"


def test_output_schema_validation_failure_returns_failure_result() -> None:
    registry = ToolRegistry()

    def broken_handler(_: EchoInput, __: ToolExecutionContext) -> dict:
        return {"unexpected": "value"}

    registry.register(make_spec(output_schema=BrokenOutput), broken_handler)

    result = registry.call("echo_tool", {"value": "hello"}, make_context())

    assert result.success is False
    assert result.error_type == "output_schema_error"
    assert result.error_category == "schema"
    assert result.schema_valid is False
    assert result.fallback_action == "fix_tool_handler_output"


def test_human_confirmation_gate_blocks_handler_execution() -> None:
    registry = ToolRegistry()
    called = False

    def guarded_handler(tool_input: EchoInput, context: ToolExecutionContext) -> EchoOutput:
        nonlocal called
        called = True
        return echo_handler(tool_input, context)

    registry.register(
        make_spec(requires_human_confirmation=True),
        guarded_handler,
    )

    result = registry.call("echo_tool", {"value": "hello"}, make_context())

    assert called is False
    assert result.success is False
    assert result.requires_human_confirmation is True
    assert result.error_type == "human_confirmation_required"
    assert result.fallback_action == "require_human_confirmation"


def test_successful_call_returns_tool_result() -> None:
    registry = ToolRegistry()
    registry.register(make_spec(), echo_handler)

    result = registry.call("echo_tool", {"value": "hello"}, make_context())

    assert isinstance(result, ToolResult)
    assert result.success is True
    assert result.output["echoed"] == "hello"
    assert result.schema_valid is True
    assert result.evidence_present is True
    assert result.source_name == "echo_tool"


def test_failure_result_contains_error_type_and_fallback_action() -> None:
    registry = ToolRegistry()

    def failing_handler(_: EchoInput, __: ToolExecutionContext) -> EchoOutput:
        raise RuntimeError("mock failure")

    registry.register(make_spec(), failing_handler)

    result = registry.call("echo_tool", {"value": "hello"}, make_context())

    assert result.success is False
    assert result.error_type == "handler_error"
    assert result.error_category == "internal"
    assert result.fallback_action == "use_fallback_action"
    assert result.retryable is False
    assert len(result.attempts) == 1


def test_read_only_tool_retries_timeout_then_succeeds() -> None:
    calls = 0
    registry = ToolRegistry(sleeper=lambda _: None)

    def flaky_handler(tool_input: EchoInput, context: ToolExecutionContext) -> EchoOutput:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ToolExecutionError(
                "temporary timeout",
                error_type="timeout",
                fallback_action="retry_then_degrade",
            )
        return echo_handler(tool_input, context)

    registry.register(
        make_spec(retry_policy=RetryPolicy(max_attempts=3, backoff_ms=1)),
        flaky_handler,
    )

    result = registry.call("echo_tool", {"value": "hello"}, make_context())

    assert result.success is True
    assert calls == 3
    assert [attempt.success for attempt in result.attempts] == [False, False, True]
    assert result.attempts[0].error_category == "timeout"


def test_write_tool_never_retries_even_when_failure_is_retryable() -> None:
    calls = 0
    registry = ToolRegistry(sleeper=lambda _: None)

    def failing_handler(_: EchoInput, __: ToolExecutionContext) -> EchoOutput:
        nonlocal calls
        calls += 1
        raise ToolExecutionError(
            "temporary provider failure",
            error_type="provider_unavailable",
            fallback_action="manual_review",
        )

    registry.register(
        make_spec(
            retry_policy=RetryPolicy(max_attempts=3, backoff_ms=1),
            read_only=False,
        ),
        failing_handler,
    )

    result = registry.call("echo_tool", {"value": "hello"}, make_context())

    assert result.success is False
    assert calls == 1
    assert result.error_category == "provider_unavailable"
    assert len(result.attempts) == 1


def test_tool_result_maps_to_tool_call_trace() -> None:
    registry = ToolRegistry()
    registry.register(make_spec(), echo_handler)

    result = registry.call("echo_tool", {"value": "hello"}, make_context())
    trace = result.to_tool_call_trace(member_id="member-father")

    assert trace.tool_name == "echo_tool"
    assert trace.member_id == "member-father"
    assert trace.source_id == "source-echo"
    assert trace.source_name == "echo_tool"
    assert trace.success is True
    assert trace.schema_valid is True
    assert trace.evidence_present is True
