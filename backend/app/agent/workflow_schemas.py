from typing import Any, Literal

from pydantic import Field, model_validator

from app.agent.context_schemas import (
    ActionType,
    ContextEnvelope,
    ContractModel,
    Intent,
    NonEmptyStr,
    RoleSpecificContextView,
    RunSummary,
)
from app.agent.eval_schemas import EvaluationResult, ExpectedCase, HarnessCaseCategory
from app.agent.model_gateway_schemas import ModelCallResult
from app.agent.run_trace_schemas import ActionTraceStatus, RunTrace
from app.tools.tool_schemas import ToolResult


DraftActionType = Literal[
    "refill_request",
    "consultation_request",
    "pharmacy_option",
    "reminder_create",
]


class WorkflowRunRequest(ContractModel):
    run_id: NonEmptyStr
    task_id: NonEmptyStr
    user_id: NonEmptyStr
    member_id: NonEmptyStr
    user_input: NonEmptyStr
    medication_name: NonEmptyStr | None = None
    city: NonEmptyStr | None = None
    human_confirmation_granted: bool = False


class WorkflowPlan(ContractModel):
    intent: Intent
    input_category: HarnessCaseCategory
    action_type: ActionType
    required_tools: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    safety_flags: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    human_confirmation_required: bool
    draft_action_type: DraftActionType | None = None

    @model_validator(mode="after")
    def validate_draft_contract(self) -> "WorkflowPlan":
        has_draft_tool = "create_confirmation_draft" in self.required_tools
        if has_draft_tool != (self.draft_action_type is not None):
            raise ValueError(
                "draft_action_type must be set exactly when the draft tool is required"
            )
        if has_draft_tool and not self.human_confirmation_required:
            raise ValueError("draft tool plans must require human confirmation")
        return self


class WorkflowFinalAnswerDraft(ContractModel):
    content: NonEmptyStr
    contains_factual_claims: bool
    waiting_for_user_confirmation: bool
    action_status: ActionTraceStatus


class WorkflowRunResult(ContractModel):
    request: WorkflowRunRequest
    plan: WorkflowPlan
    context_envelope: ContextEnvelope
    role_views: dict[str, RoleSpecificContextView]
    tool_results: list[ToolResult]
    model_result: ModelCallResult[WorkflowFinalAnswerDraft]
    run_trace: RunTrace
    run_summary: RunSummary
    reset_state: dict[str, Any]
    evaluation_case: ExpectedCase
    evaluation_result: EvaluationResult
    visited_nodes: tuple[NonEmptyStr, ...] = Field(min_length=1)


__all__ = [
    "DraftActionType",
    "WorkflowFinalAnswerDraft",
    "WorkflowPlan",
    "WorkflowRunRequest",
    "WorkflowRunResult",
]
