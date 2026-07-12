from collections.abc import Iterable
from typing import Any

from app.tools.mock_tools import build_mock_tool_registry
from app.tools.tool_schemas import ToolExecutionContext, ToolResult


def make_context(
    *,
    agent_role: str,
    allowed_tools: list[str],
    human_confirmation_granted: bool = False,
) -> ToolExecutionContext:
    return ToolExecutionContext(
        run_id="run-mock-1",
        task_id="task-mock-1",
        member_id="member-father",
        agent_role=agent_role,
        allowed_tools=allowed_tools,
        safety_flags=[],
        human_confirmation_granted=human_confirmation_granted,
    )


def flatten_values(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for nested in value.values():
            yield from flatten_values(nested)
    elif isinstance(value, list | tuple):
        for nested in value:
            yield from flatten_values(nested)
    elif value is not None:
        yield str(value)


def call_mock_tool(tool_name: str) -> ToolResult:
    registry = build_mock_tool_registry()
    if tool_name == "query_health_profile":
        return registry.call(
            tool_name,
            {"member_id": "member-father"},
            make_context(agent_role="ProfileAgent", allowed_tools=[tool_name]),
        )
    if tool_name == "query_prescriptions":
        return registry.call(
            tool_name,
            {"member_id": "member-father", "medication_name": "amlodipine tablets"},
            make_context(agent_role="RefillAgent", allowed_tools=[tool_name]),
        )
    if tool_name == "query_medicine_box":
        return registry.call(
            tool_name,
            {"member_id": "member-father", "medication_name": "amlodipine tablets"},
            make_context(agent_role="ReminderAgent", allowed_tools=[tool_name]),
        )
    if tool_name == "check_pharmacy_inventory":
        return registry.call(
            tool_name,
            {
                "member_id": "member-father",
                "medication_name": "amlodipine tablets",
                "city": "Shanghai",
            },
            make_context(agent_role="PharmacyAgent", allowed_tools=[tool_name]),
        )
    if tool_name == "search_safety_knowledge":
        return registry.call(
            tool_name,
            {"query": "refill safety", "member_id": "member-father"},
            make_context(agent_role="SafetyAgent", allowed_tools=[tool_name]),
        )
    if tool_name == "create_confirmation_draft":
        return registry.call(
            tool_name,
            {
                "member_id": "member-father",
                "action_type": "refill_request",
                "summary": "Prepare a refill request draft for user review.",
            },
            make_context(
                agent_role="RefillAgent",
                allowed_tools=[tool_name],
                human_confirmation_granted=True,
            ),
        )
    raise AssertionError(f"unknown mock tool in test: {tool_name}")


def test_mock_registry_registers_six_tools() -> None:
    registry = build_mock_tool_registry()

    assert [tool.name for tool in registry.list_tools()] == [
        "query_health_profile",
        "query_prescriptions",
        "query_medicine_box",
        "check_pharmacy_inventory",
        "search_safety_knowledge",
        "create_confirmation_draft",
    ]


def test_mock_tool_allowed_roles_match_contract() -> None:
    registry = build_mock_tool_registry()

    expected = {
        "query_health_profile": ["ProfileAgent", "SafetyAgent"],
        "query_prescriptions": ["RefillAgent", "SafetyAgent"],
        "query_medicine_box": ["RefillAgent", "ReminderAgent", "SafetyAgent"],
        "check_pharmacy_inventory": ["PharmacyAgent"],
        "search_safety_knowledge": ["SafetyAgent", "RefillAgent", "ReminderAgent"],
        "create_confirmation_draft": ["RefillAgent", "PharmacyAgent", "ReminderAgent"],
    }

    for tool_name, roles in expected.items():
        assert registry.get_tool(tool_name).allowed_agent_roles == roles


def test_all_mock_tools_return_successful_tool_results() -> None:
    for tool_name in [
        "query_health_profile",
        "query_prescriptions",
        "query_medicine_box",
        "check_pharmacy_inventory",
        "search_safety_knowledge",
        "create_confirmation_draft",
    ]:
        result = call_mock_tool(tool_name)

        assert result.success is True
        assert result.schema_valid is True
        assert result.evidence_present is True
        assert result.source_name == tool_name
        assert result.output["source_id"].startswith("mock-")


def test_create_confirmation_draft_requires_confirmation_before_handler_runs() -> None:
    registry = build_mock_tool_registry()

    result = registry.call(
        "create_confirmation_draft",
        {
            "member_id": "member-father",
            "action_type": "refill_request",
            "summary": "Prepare a refill request draft for user review.",
        },
        make_context(
            agent_role="RefillAgent",
            allowed_tools=["create_confirmation_draft"],
            human_confirmation_granted=False,
        ),
    )

    assert result.success is False
    assert result.error_type == "human_confirmation_required"
    assert result.fallback_action == "require_human_confirmation"
    assert result.output == {}


def test_create_confirmation_draft_returns_draft_status_only() -> None:
    result = call_mock_tool("create_confirmation_draft")

    assert result.output["status"] == "draft"
    assert result.output["action_type"] == "refill_request"
    assert "submitted" not in set(flatten_values(result.output))
    assert "completed" not in set(flatten_values(result.output))


def test_mock_tools_do_not_return_unsafe_medical_actions() -> None:
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

    for tool_name in [
        "query_health_profile",
        "query_prescriptions",
        "query_medicine_box",
        "check_pharmacy_inventory",
        "search_safety_knowledge",
        "create_confirmation_draft",
    ]:
        result = call_mock_tool(tool_name)
        flattened_output = " ".join(flatten_values(result.output)).lower()

        for phrase in unsafe_phrases:
            assert phrase.lower() not in flattened_output


def test_mock_permission_denial_uses_tool_result_failure() -> None:
    registry = build_mock_tool_registry()

    result = registry.call(
        "check_pharmacy_inventory",
        {"member_id": "member-father", "medication_name": "amlodipine tablets"},
        make_context(
            agent_role="RefillAgent",
            allowed_tools=["check_pharmacy_inventory"],
        ),
    )

    assert result.success is False
    assert result.error_type == "permission_denied"
    assert result.fallback_action == "route_to_authorized_agent"
