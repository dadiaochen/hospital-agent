from typing import Literal

from pydantic import Field, model_validator

from app.agent.context_schemas import (
    ContractModel,
    NonEmptyStr,
    RAGSourceRef,
    RunSummary,
    ToolEvidenceRef,
)
from app.agent.eval_schemas import EvaluationResult
from app.agent.model_gateway_schemas import ModelCallTrace
from app.agent.run_trace_schemas import RunTrace
from app.agent.workflow_schemas import WorkflowPlan, WorkflowResumeContext


RUNTIME_ARTIFACT_SCHEMA_VERSION = "2g2.v1"


class RuntimeRequestContext(ContractModel):
    medication_name: NonEmptyStr | None = None
    city: NonEmptyStr | None = None


class PersistedRunArtifacts(ContractModel):
    schema_version: Literal["2g2.v1"] = RUNTIME_ARTIFACT_SCHEMA_VERSION
    task_id: NonEmptyStr
    plan: WorkflowPlan
    run_trace: RunTrace
    model_call_trace: ModelCallTrace
    run_summary: RunSummary
    tool_evidence_refs: tuple[ToolEvidenceRef, ...] = Field(default_factory=tuple)
    rag_source_refs: tuple[RAGSourceRef, ...] = Field(default_factory=tuple)
    evaluation_result: EvaluationResult
    request_context: RuntimeRequestContext = Field(default_factory=RuntimeRequestContext)
    request_fingerprint: NonEmptyStr
    resumed_from_run_id: NonEmptyStr | None = None
    restored_source_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    external_action_status: Literal["not_submitted"] = "not_submitted"

    @model_validator(mode="after")
    def validate_frozen_artifact_scope(self) -> "PersistedRunArtifacts":
        run_id = self.run_trace.run_id
        if self.run_summary.run_id != run_id:
            raise ValueError("run summary must belong to the persisted run trace")
        if self.evaluation_result.run_id != run_id:
            raise ValueError("evaluation must belong to the persisted run trace")
        if self.run_summary.task_id != self.task_id:
            raise ValueError("run summary task_id must match persisted task_id")
        if self.run_trace.task_id != self.task_id:
            raise ValueError("run trace task_id must match persisted task_id")
        if self.model_call_trace.run_id != run_id:
            raise ValueError("model call trace must belong to the persisted run")
        if self.model_call_trace.task_id != self.task_id:
            raise ValueError("model call trace task_id must match persisted task_id")
        if self.model_call_trace.member_id != self.run_summary.member_id:
            raise ValueError("model call trace member_id must match run summary")
        return self

    def to_resume_context(self) -> WorkflowResumeContext:
        return WorkflowResumeContext(
            previous_run_id=self.run_trace.run_id,
            run_summary=self.run_summary,
            plan=self.plan,
        )


__all__ = [
    "PersistedRunArtifacts",
    "RUNTIME_ARTIFACT_SCHEMA_VERSION",
    "RuntimeRequestContext",
]
