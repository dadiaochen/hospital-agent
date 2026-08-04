from app.agent.workflow_planning import (
    DeterministicWorkflowPlanner,
    WorkflowToolInputBuilder,
)
from app.agent.workflow_schemas import WorkflowRunRequest
from app.tools.db_tools import (
    PharmacyInventoryInput,
    PharmacyInventoryOutput,
)
from app.tools.tool_registry import ToolRegistry
from app.tools.tool_schemas import ToolResult, ToolSpec


def test_pharmacy_input_uses_member_records_when_request_has_no_medicine_name():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="check_pharmacy_inventory",
            description="Read pharmacy inventory.",
            input_schema=PharmacyInventoryInput,
            output_schema=PharmacyInventoryOutput,
            permission_scope="pharmacy_inventory:read",
            allowed_agent_roles=("PharmacyAgent",),
        ),
        lambda tool_input, context: {},
    )
    request = WorkflowRunRequest(
        run_id="run-ux09",
        task_id="task-ux09",
        user_id="user-ux09",
        member_id="member-father",
        user_input="我爸的降压药快吃完了，帮我看看能不能续方。",
    )
    plan = DeterministicWorkflowPlanner().plan(request)
    prior_results = [
        ToolResult(
            tool_name="query_medicine_box",
            success=True,
            output={"items": [{"medicine_name": "苯磺酸氨氯地平片"}]},
            latency_ms=0,
            schema_valid=True,
            requires_human_confirmation=False,
            evidence_present=True,
        )
    ]

    tool_input = WorkflowToolInputBuilder().build(
        "check_pharmacy_inventory",
        request=request,
        plan=plan,
        registry=registry,
        tool_results=prior_results,
    )

    assert tool_input["medicine_name"] == "苯磺酸氨氯地平片"
    assert PharmacyInventoryInput.model_validate(tool_input).medicine_name == "苯磺酸氨氯地平片"
