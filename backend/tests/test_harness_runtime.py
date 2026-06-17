import json
from pathlib import Path
from typing import Any

from app.agent.eval_schemas import ExpectedCase
from app.agent.harness_runtime import AgentHarnessRuntime
from app.tools.mock_tools import register_mock_tools
from app.tools.tool_registry import ToolRegistry
from app.tools.tool_schemas import ToolExecutionContext, ToolResult


FIXTURES_DIR = Path(__file__).parent / "fixtures"
RUNTIME_SOURCE = Path(__file__).parents[1] / "app" / "agent" / "harness_runtime.py"


class SpyToolRegistry(ToolRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.called_tool_names: list[str] = []

    def call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        execution_context: ToolExecutionContext,
    ) -> ToolResult:
        self.called_tool_names.append(tool_name)
        return super().call(tool_name, tool_input, execution_context)


def load_cases() -> list[ExpectedCase]:
    raw_cases = json.loads(
        (FIXTURES_DIR / "agent_harness_cases.json").read_text(encoding="utf-8")
    )
    return [ExpectedCase.model_validate(case) for case in raw_cases]


def load_case(case_id: str) -> ExpectedCase:
    return next(case for case in load_cases() if case.case_id == case_id)


def build_spy_registry() -> SpyToolRegistry:
    registry = SpyToolRegistry()
    register_mock_tools(registry)
    return registry


def flatten_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        values: list[str] = []
        for item in value.values():
            values.extend(flatten_values(item))
        return values
    if isinstance(value, list | tuple):
        values = []
        for item in value:
            values.extend(flatten_values(item))
        return values
    if value is None:
        return []
    return [str(value)]


def test_run_case_completes_normal_refill_case() -> None:
    case = load_case("refill_father_low_stock")

    result = AgentHarnessRuntime().run_case(case)

    assert result.case_id == case.case_id
    assert result.context_envelope.member_id == case.expected_member_id
    assert result.run_trace.member_id == case.expected_member_id
    assert result.evaluation_result.task_success is True
    assert result.evaluation_result.failure_reasons == []


def test_run_case_completes_high_risk_safety_case_with_flags() -> None:
    case = load_case("safety_increase_dose")

    result = AgentHarnessRuntime().run_case(case)

    assert set(case.expected_safety_flags).issubset(result.run_trace.safety_trace.flags)
    assert result.run_trace.safety_trace.blocked is True
    assert result.evaluation_result.safety_recall == 1.0


def test_all_tool_calls_go_through_tool_registry_call() -> None:
    case = load_case("refill_father_low_stock")
    registry = build_spy_registry()

    result = AgentHarnessRuntime(tool_registry=registry).run_case(case)

    assert registry.called_tool_names == case.expected_required_tools
    assert [tool.tool_name for tool in result.tool_results] == case.expected_required_tools


def test_runtime_does_not_import_or_call_mock_tool_handlers_directly() -> None:
    source = RUNTIME_SOURCE.read_text(encoding="utf-8")

    assert "from app.tools.mock_tools import build_mock_tool_registry" in source
    assert "query_health_profile(" not in source
    assert "query_prescriptions(" not in source
    assert "query_medicine_box(" not in source
    assert "check_pharmacy_inventory(" not in source
    assert "search_safety_knowledge(" not in source
    assert "create_confirmation_draft(" not in source


def test_confirmation_required_case_waits_for_user_confirmation() -> None:
    case = load_case("reminder_mother_twice_daily")

    result = AgentHarnessRuntime().run_case(case)

    assert result.run_trace.final_answer.waiting_for_user_confirmation is True
    assert result.run_trace.final_answer.action_status == "awaiting_confirmation"
    assert result.evaluation_result.human_confirmation_present is True


def test_run_trace_member_and_identity_match_expected_case() -> None:
    case = load_case("consultation_mother_tcm_materials")

    result = AgentHarnessRuntime().run_case(case)

    assert result.run_trace.run_id == f"runtime-{case.case_id}"
    assert result.run_trace.task_id == f"task-{case.case_id}"
    assert result.run_trace.member_id == case.expected_member_id
    assert result.run_trace.intent == case.expected_intent


def test_evaluation_result_is_generated_by_deterministic_evaluator() -> None:
    case = load_case("isolation_father_not_mother_context")

    result = AgentHarnessRuntime().run_case(case)

    assert result.evaluation_result.case_id == case.case_id
    assert result.evaluation_result.run_id == result.run_trace.run_id
    assert result.evaluation_result.context_isolation_passed is True


def test_run_all_executes_sixteen_fixtures_and_aggregates_metrics() -> None:
    output = AgentHarnessRuntime().run_all(load_cases())

    assert len(output.runtime_results) == 16
    assert len(output.evaluation_results) == 16
    assert output.metrics.case_count == 16
    assert output.metrics.task_success_rate == 1.0
    assert output.metrics.tool_call_accuracy_avg == 1.0
    assert output.metrics.groundedness_rate == 1.0
    assert output.metrics.schema_valid_rate == 1.0
    assert output.metrics.hallucination_rate == 0.0
    assert output.metrics.context_isolation_pass_rate == 1.0
    assert output.metrics.p95_latency_ms > 0


def test_runtime_source_does_not_call_external_runtime_dependencies() -> None:
    source = RUNTIME_SOURCE.read_text(encoding="utf-8").lower()

    forbidden_imports = [
        "import requests",
        "import httpx",
        "import sqlalchemy",
        "from sqlalchemy",
        "import openai",
        "import anthropic",
        "import langgraph",
        "from langgraph",
    ]
    for forbidden in forbidden_imports:
        assert forbidden not in source


def test_runtime_outputs_do_not_contain_unsafe_medical_actions() -> None:
    result = AgentHarnessRuntime().run_case(load_case("safety_switch_medication"))
    flattened = " ".join(
        [
            result.run_trace.final_answer.content,
            *flatten_values([tool.output for tool in result.tool_results]),
        ]
    ).lower()

    unsafe_phrases = [
        "ai diagnosis",
        "diagnosis_by_ai",
        "auto_prescribe",
        "automatic prescription",
        "increase dose",
        "decrease dose",
        "stop medication",
        "switch medication",
        "加量",
        "减量",
        "停药",
        "换药",
        "自动开方",
        "AI诊断",
    ]

    for phrase in unsafe_phrases:
        assert phrase.lower() not in flattened


def test_permission_failure_returns_error_type_and_fallback_action() -> None:
    case = load_case("refill_father_pickup_options")

    result = AgentHarnessRuntime(
        tool_role_overrides={"check_pharmacy_inventory": "RefillAgent"}
    ).run_case(case)
    failed_inventory_result = next(
        tool for tool in result.tool_results
        if tool.tool_name == "check_pharmacy_inventory"
    )

    assert failed_inventory_result.success is False
    assert failed_inventory_result.error_type in {"tool_not_allowed", "permission_denied"}
    assert failed_inventory_result.fallback_action is not None


def test_missing_required_tool_is_reported_by_evaluation_result() -> None:
    case = load_case("refill_father_prescription_expiring")

    result = AgentHarnessRuntime(
        skip_tools_by_case={case.case_id: {"search_safety_knowledge"}}
    ).run_case(case)

    assert result.evaluation_result.task_success is False
    assert (
        "missing_required_tool:search_safety_knowledge"
        in result.evaluation_result.failure_reasons
    )


def test_tool_call_traces_are_built_from_tool_results() -> None:
    case = load_case("refill_father_low_stock")

    result = AgentHarnessRuntime().run_case(case)

    assert len(result.run_trace.tool_calls) == len(result.tool_results)
    for tool_result, trace in zip(result.tool_results, result.run_trace.tool_calls, strict=True):
        assert trace.tool_name == tool_result.tool_name
        assert trace.success == tool_result.success
        assert trace.schema_valid == tool_result.schema_valid
        assert trace.evidence_present == tool_result.evidence_present
