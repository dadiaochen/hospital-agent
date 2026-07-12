from typing import Any, Literal

from pydantic import Field

from app.agent.context_schemas import ContractModel, NonEmptyStr
from app.tools.tool_registry import ToolRegistry
from app.tools.tool_schemas import RetryPolicy, ToolExecutionContext, ToolSpec


class MemberToolInput(ContractModel):
    member_id: NonEmptyStr


class MedicationToolInput(MemberToolInput):
    medication_name: NonEmptyStr | None = None


class PharmacyInventoryInput(MedicationToolInput):
    city: NonEmptyStr | None = None


class SafetyKnowledgeInput(ContractModel):
    query: NonEmptyStr
    member_id: NonEmptyStr | None = None


ConfirmationActionType = Literal["refill_request", "pharmacy_option", "reminder_create"]


class ConfirmationDraftInput(MemberToolInput):
    action_type: ConfirmationActionType
    summary: NonEmptyStr


class EvidenceOutput(ContractModel):
    source_id: NonEmptyStr
    source_name: NonEmptyStr
    member_id: NonEmptyStr | None = None
    evidence_present: bool = True


class HealthProfileOutput(EvidenceOutput):
    chronic_condition_tags: list[NonEmptyStr] = Field(default_factory=list)
    allergy_notes: list[NonEmptyStr] = Field(default_factory=list)
    safety_notes: list[NonEmptyStr] = Field(default_factory=list)


class PrescriptionOutput(EvidenceOutput):
    prescriptions: list[dict[str, Any]] = Field(default_factory=list)


class MedicineBoxOutput(EvidenceOutput):
    medicines: list[dict[str, Any]] = Field(default_factory=list)


class PharmacyInventoryOutput(EvidenceOutput):
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class SafetyKnowledgeOutput(EvidenceOutput):
    rules: list[dict[str, Any]] = Field(default_factory=list)


class ConfirmationDraftOutput(EvidenceOutput):
    draft_id: NonEmptyStr
    action_type: ConfirmationActionType
    status: Literal["draft"]
    summary: NonEmptyStr


def build_mock_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    register_mock_tools(registry)
    return registry


def register_mock_tools(registry: ToolRegistry) -> ToolRegistry:
    registry.register(
        ToolSpec(
            name="query_health_profile",
            description="Return fixed mock member health profile evidence.",
            input_schema=MemberToolInput,
            output_schema=HealthProfileOutput,
            permission_scope="profile:read",
            allowed_agent_roles=["ProfileAgent", "SafetyAgent"],
            timeout_ms=500,
            retry_policy=RetryPolicy(max_attempts=1, backoff_ms=0),
            requires_human_confirmation=False,
        ),
        query_health_profile,
    )
    registry.register(
        ToolSpec(
            name="query_prescriptions",
            description="Return fixed mock prescription evidence for refill preparation.",
            input_schema=MedicationToolInput,
            output_schema=PrescriptionOutput,
            permission_scope="prescription:read",
            allowed_agent_roles=["RefillAgent", "SafetyAgent"],
            timeout_ms=500,
            retry_policy=RetryPolicy(max_attempts=1, backoff_ms=0),
            requires_human_confirmation=False,
        ),
        query_prescriptions,
    )
    registry.register(
        ToolSpec(
            name="query_medicine_box",
            description="Return fixed mock medicine box evidence.",
            input_schema=MedicationToolInput,
            output_schema=MedicineBoxOutput,
            permission_scope="medicine_box:read",
            allowed_agent_roles=["RefillAgent", "ReminderAgent", "SafetyAgent"],
            timeout_ms=500,
            retry_policy=RetryPolicy(max_attempts=1, backoff_ms=0),
            requires_human_confirmation=False,
        ),
        query_medicine_box,
    )
    registry.register(
        ToolSpec(
            name="check_pharmacy_inventory",
            description="Return fixed mock pharmacy inventory candidates.",
            input_schema=PharmacyInventoryInput,
            output_schema=PharmacyInventoryOutput,
            permission_scope="pharmacy:read",
            allowed_agent_roles=["PharmacyAgent"],
            timeout_ms=500,
            retry_policy=RetryPolicy(max_attempts=1, backoff_ms=0),
            requires_human_confirmation=False,
        ),
        check_pharmacy_inventory,
    )
    registry.register(
        ToolSpec(
            name="search_safety_knowledge",
            description="Return fixed mock safety rule snippets.",
            input_schema=SafetyKnowledgeInput,
            output_schema=SafetyKnowledgeOutput,
            permission_scope="safety:read",
            allowed_agent_roles=["SafetyAgent", "RefillAgent", "ReminderAgent"],
            timeout_ms=500,
            retry_policy=RetryPolicy(max_attempts=1, backoff_ms=0),
            requires_human_confirmation=False,
        ),
        search_safety_knowledge,
    )
    registry.register(
        ToolSpec(
            name="create_confirmation_draft",
            description="Return a fixed mock confirmation draft.",
            input_schema=ConfirmationDraftInput,
            output_schema=ConfirmationDraftOutput,
            permission_scope="draft:create",
            allowed_agent_roles=["RefillAgent", "PharmacyAgent", "ReminderAgent"],
            timeout_ms=500,
            retry_policy=RetryPolicy(max_attempts=1, backoff_ms=0),
            requires_human_confirmation=True,
        ),
        create_confirmation_draft,
    )
    return registry


def query_health_profile(
    tool_input: MemberToolInput,
    execution_context: ToolExecutionContext,
) -> HealthProfileOutput:
    return HealthProfileOutput(
        source_id=f"mock-profile-{execution_context.run_id}",
        source_name="query_health_profile",
        member_id=tool_input.member_id,
        chronic_condition_tags=["hypertension_followup"],
        allergy_notes=["penicillin_allergy_reported_by_user"],
        safety_notes=["doctor_confirmation_required_for_clinical_decisions"],
    )


def query_prescriptions(
    tool_input: MedicationToolInput,
    execution_context: ToolExecutionContext,
) -> PrescriptionOutput:
    return PrescriptionOutput(
        source_id=f"mock-prescription-{execution_context.run_id}",
        source_name="query_prescriptions",
        member_id=tool_input.member_id,
        prescriptions=[
            {
                "prescription_id": "mock-rx-001",
                "medication_name": tool_input.medication_name or "amlodipine tablets",
                "dosage_text": "5 mg",
                "frequency_text": "once daily",
                "status": "active_record",
                "hospital_name": "mock community hospital",
                "doctor_name": "mock attending doctor",
            }
        ],
    )


def query_medicine_box(
    tool_input: MedicationToolInput,
    execution_context: ToolExecutionContext,
) -> MedicineBoxOutput:
    return MedicineBoxOutput(
        source_id=f"mock-medicine-box-{execution_context.run_id}",
        source_name="query_medicine_box",
        member_id=tool_input.member_id,
        medicines=[
            {
                "medicine_box_item_id": "mock-box-001",
                "medication_name": tool_input.medication_name or "amlodipine tablets",
                "remaining_days": 5,
                "reminder_enabled": True,
            }
        ],
    )


def check_pharmacy_inventory(
    tool_input: PharmacyInventoryInput,
    execution_context: ToolExecutionContext,
) -> PharmacyInventoryOutput:
    return PharmacyInventoryOutput(
        source_id=f"mock-pharmacy-{execution_context.run_id}",
        source_name="check_pharmacy_inventory",
        member_id=tool_input.member_id,
        candidates=[
            {
                "pharmacy_id": "mock-pharmacy-001",
                "pharmacy_name": "mock nearby pharmacy",
                "city": tool_input.city or "mock city",
                "medication_name": tool_input.medication_name or "amlodipine tablets",
                "stock_status": "available",
                "delivery_options": ["pickup", "delivery"],
            }
        ],
    )


def search_safety_knowledge(
    tool_input: SafetyKnowledgeInput,
    execution_context: ToolExecutionContext,
) -> SafetyKnowledgeOutput:
    return SafetyKnowledgeOutput(
        source_id=f"mock-safety-{execution_context.run_id}",
        source_name="search_safety_knowledge",
        member_id=tool_input.member_id or execution_context.member_id,
        rules=[
            {
                "rule_id": "mock-safety-001",
                "topic": tool_input.query,
                "rule_text": "clinical decisions require licensed clinician confirmation",
            },
            {
                "rule_id": "mock-safety-002",
                "topic": "confirmation",
                "rule_text": "critical actions must remain in draft state before user approval",
            },
        ],
    )


def create_confirmation_draft(
    tool_input: ConfirmationDraftInput,
    execution_context: ToolExecutionContext,
) -> ConfirmationDraftOutput:
    return ConfirmationDraftOutput(
        source_id=f"mock-draft-{execution_context.run_id}",
        source_name="create_confirmation_draft",
        member_id=tool_input.member_id,
        draft_id=f"draft-{execution_context.run_id}",
        action_type=tool_input.action_type,
        status="draft",
        summary=tool_input.summary,
    )
