from __future__ import annotations

from typing import Any

from app.agent.domain_agents import DomainAgentInput
from app.agent.orchestration_schemas import ComplexityRoute, PlanStep
from app.agent.runtime_domain_agents import RuntimeMedicationAgent
from app.agent.supervised_workflow import SupervisorAgentRuntime
from app.tools.tool_schemas import ToolResult


def _success(tool_name: str, *, agent_role: str = "MedicationAgent") -> ToolResult:
    return ToolResult(
        tool_name=tool_name,
        success=True,
        output={"ok": True},
        agent_role=agent_role,
        member_id="member-1",
        latency_ms=0,
        schema_valid=True,
        requires_human_confirmation=False,
        evidence_present=False,
    )


class FakeWorkflow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def _call(
        self,
        state: dict[str, Any],
        *,
        tool_name: str,
        agent_role: str,
        payload: dict[str, Any],
    ) -> ToolResult:
        self.calls.append((agent_role, tool_name))
        if agent_role == "TriageAgent" and tool_name == "query_medicine_box":
            return ToolResult.failure(
                tool_name=tool_name,
                error_type="permission_denied",
                error_message="role cannot call this tool",
                fallback_action="stop",
                latency_ms=0,
                agent_role=agent_role,
                member_id="member-1",
                tool_input=payload,
            )
        return _success(tool_name, agent_role=agent_role)


def _runtime(workflow: FakeWorkflow) -> SupervisorAgentRuntime:
    state = {
        "run_id": "run-1",
        "task_id": "task-1",
        "user_id": "user-1",
        "member_id": "member-1",
        "business_domain": "chronic_care",
        "input_payload": {},
        "human_confirmation_granted": False,
    }
    return SupervisorAgentRuntime(workflow, state, is_confirmation_run=False)  # type: ignore[arg-type]


def test_plan_allowlist_is_forwarded_by_runtime_domain_agent() -> None:
    class CaptureRuntime:
        def __init__(self) -> None:
            self.kwargs: dict[str, Any] = {}

        def call_tool(self, **kwargs: Any) -> ToolResult:
            self.kwargs = kwargs
            return _success(kwargs["tool_name"])

    runtime = CaptureRuntime()
    agent = RuntimeMedicationAgent(runtime)  # type: ignore[arg-type]
    route = ComplexityRoute(
        task_id="task-1",
        user_id="user-1",
        member_id="member-1",
        route_mode="simple_single_domain",
        intent="refill",
        target_role="MedicationAgent",
        target_roles=("MedicationAgent",),
        reason_code="single_domain_signal",
        requires_planner=False,
    )
    step = PlanStep(
        step_id="step-1",
        role="MedicationAgent",
        objective="Read medication facts.",
        allowed_tools=("query_medicine_box",),
    )
    agent_input = DomainAgentInput(
        route=route,
        step=step,
        user_input_summary="Read medication facts.",
        allowed_tools=step.allowed_tools,
    )

    result = agent._call(
        agent_input,
        tool_name="query_medicine_box",
        payload={"member_id": "member-1"},
    )

    assert isinstance(result, ToolResult)
    assert runtime.kwargs["step_id"] == "step-1"
    assert runtime.kwargs["allowed_tools"] == ("query_medicine_box",)


def test_plan_forbidden_tool_fails_closed_before_handler() -> None:
    workflow = FakeWorkflow()
    runtime = _runtime(workflow)

    result = runtime.call_tool(
        agent_role="MedicationAgent",
        tool_name="query_medicine_box",
        payload={},
        step_id="step-1",
        allowed_tools=("query_prescriptions",),
    )

    assert result.success is False
    assert result.error_type == "tool_not_allowed_by_plan"
    assert result.error_category == "permission"
    assert workflow.calls == []
    assert result.evidence_refs == []


def test_missing_step_context_fails_closed() -> None:
    workflow = FakeWorkflow()
    runtime = _runtime(workflow)

    result = runtime.call_tool(
        agent_role="MedicationAgent",
        tool_name="query_medicine_box",
        payload={},
        step_id="",
        allowed_tools=("query_medicine_box",),
    )

    assert result.success is False
    assert result.error_type == "tool_not_allowed_by_plan"
    assert workflow.calls == []


def test_role_permission_is_checked_after_plan_permission() -> None:
    workflow = FakeWorkflow()
    runtime = _runtime(workflow)

    result = runtime.call_tool(
        agent_role="TriageAgent",
        tool_name="query_medicine_box",
        payload={},
        step_id="step-1",
        allowed_tools=("query_medicine_box",),
    )

    assert result.success is False
    assert result.error_type == "permission_denied"
    assert workflow.calls == [("TriageAgent", "query_medicine_box")]
