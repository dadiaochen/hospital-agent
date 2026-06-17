from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.agent.context_schemas import ContractModel, Intent, NonEmptyStr


Score = Annotated[float, Field(ge=0.0, le=1.0)]
HarnessCaseCategory = Literal[
    "refill",
    "consultation",
    "reminder",
    "safety",
    "tool_failure",
    "isolation",
    "no_source",
]
ExpectedSourceType = Literal["tool_evidence", "rag_source"]


class ExpectedSource(ContractModel):
    source_type: ExpectedSourceType
    source_name: NonEmptyStr
    required: bool = True


class ExpectedCase(ContractModel):
    case_id: NonEmptyStr
    input_category: HarnessCaseCategory
    user_input: NonEmptyStr
    expected_intent: Intent
    expected_member_id: NonEmptyStr
    expected_required_tools: list[NonEmptyStr] = Field(default_factory=list)
    expected_safety_flags: list[NonEmptyStr] = Field(default_factory=list)
    expected_human_confirmation_required: bool
    forbidden_phrases: list[NonEmptyStr] = Field(default_factory=list)
    expected_sources: list[ExpectedSource] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_case_safety_and_source_rules(self) -> "ExpectedCase":
        if self.input_category == "safety" and not self.expected_safety_flags:
            raise ValueError("safety cases must declare at least one expected safety flag")
        if self.input_category == "no_source" and self.expected_sources:
            raise ValueError("no_source cases cannot declare expected sources")
        return self


class EvaluationResult(ContractModel):
    case_id: NonEmptyStr
    run_id: NonEmptyStr
    task_success: bool
    tool_call_accuracy: Score | None
    groundedness: Score | None
    schema_valid: bool
    hallucination_detected: bool
    safety_recall: Score | None
    human_confirmation_required: bool
    human_confirmation_present: bool
    context_isolation_passed: bool
    latency_ms: int = Field(ge=0)
    failure_reasons: list[NonEmptyStr]

    @model_validator(mode="after")
    def require_failure_reason_for_failed_task(self) -> "EvaluationResult":
        if not self.task_success and not self.failure_reasons:
            raise ValueError("failed evaluations must include failure_reasons")
        return self
