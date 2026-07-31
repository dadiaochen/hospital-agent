from __future__ import annotations

from typing import Any, cast

from pydantic import Field, model_validator
from sqlalchemy.orm import Session

from app.services.agent_tool_query_service import (
    get_health_profile_context,
    get_medicine_box_context,
    get_pharmacy_inventory_context,
    get_prescription_context,
    search_safety_knowledge_context,
)
from app.tools.tool_registry import ToolExecutionError, ToolRegistry
from app.tools.tool_schemas import ToolContractModel, ToolExecutionContext, ToolSpec


class HealthProfileInput(ToolContractModel):
    user_id: str = Field(min_length=1)
    member_id: str = Field(min_length=1)


class HealthProfileOutput(ToolContractModel):
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    evidence_present: bool
    member_id: str = Field(min_length=1)
    profile: dict[str, Any]


class PrescriptionsInput(ToolContractModel):
    member_id: str = Field(min_length=1)


class PrescriptionsOutput(ToolContractModel):
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    evidence_present: bool
    member_id: str = Field(min_length=1)
    prescriptions: list[dict[str, Any]]
    purchase_records: list[dict[str, Any]]


class MedicineBoxInput(ToolContractModel):
    member_id: str = Field(min_length=1)


class MedicineBoxOutput(ToolContractModel):
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    evidence_present: bool
    member_id: str = Field(min_length=1)
    items: list[dict[str, Any]]


class PharmacyInventoryInput(ToolContractModel):
    medicine_name: str | None = None
    city: str | None = None

    @model_validator(mode="after")
    def require_at_least_one_filter(self) -> "PharmacyInventoryInput":
        if not self.medicine_name and not self.city:
            raise ValueError("medicine_name or city is required")
        return self


class PharmacyInventoryOutput(ToolContractModel):
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    evidence_present: bool
    medicine_name: str | None = None
    city: str | None = None
    inventory_items: list[dict[str, Any]]


class SafetyKnowledgeInput(ToolContractModel):
    query: str = Field(min_length=1)


class SafetyKnowledgeOutput(ToolContractModel):
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    evidence_present: bool
    query: str = Field(min_length=1)
    requested_mode: str = Field(min_length=1)
    effective_mode: str = Field(min_length=1)
    fallback_used: bool
    fallback_reason: str | None = None
    sources: list[dict[str, Any]]


def create_db_tool_registry(
    db: Session,
    *,
    include_confirmation_tools: bool = False,
) -> ToolRegistry:
    registry = ToolRegistry()
    register_db_tools(registry, db)
    if include_confirmation_tools:
        from app.tools.confirmation_tools import register_confirmation_draft_tool

        register_confirmation_draft_tool(registry, db)
    return registry


def register_db_tools(registry: ToolRegistry, db: Session) -> None:
    registry.register(
        ToolSpec(
            name="query_health_profile",
            description="Read the selected family member health profile and safety notes.",
            input_schema=HealthProfileInput,
            output_schema=HealthProfileOutput,
            permission_scope="health_profile:read",
            allowed_agent_roles=("ProfileAgent", "SafetyAgent"),
            read_only=True,
        ),
        lambda tool_input, context: _query_health_profile(db, tool_input, context),
    )
    registry.register(
        ToolSpec(
            name="query_prescriptions",
            description="Read doctor prescription snapshots and purchase history.",
            input_schema=PrescriptionsInput,
            output_schema=PrescriptionsOutput,
            permission_scope="prescriptions:read",
            allowed_agent_roles=("RefillAgent", "SafetyAgent"),
            read_only=True,
        ),
        lambda tool_input, context: _query_prescriptions(db, tool_input, context),
    )
    registry.register(
        ToolSpec(
            name="query_medicine_box",
            description="Read family medicine box inventory and remaining days.",
            input_schema=MedicineBoxInput,
            output_schema=MedicineBoxOutput,
            permission_scope="medicine_box:read",
            allowed_agent_roles=("RefillAgent", "ReminderAgent", "SafetyAgent"),
            read_only=True,
        ),
        lambda tool_input, context: _query_medicine_box(db, tool_input, context),
    )
    registry.register(
        ToolSpec(
            name="check_pharmacy_inventory",
            description="Read pharmacy inventory, delivery and pickup candidates.",
            input_schema=PharmacyInventoryInput,
            output_schema=PharmacyInventoryOutput,
            permission_scope="pharmacy_inventory:read",
            allowed_agent_roles=("PharmacyAgent", "SafetyAgent"),
            read_only=True,
        ),
        lambda tool_input, context: _check_pharmacy_inventory(db, tool_input, context),
    )
    registry.register(
        ToolSpec(
            name="search_safety_knowledge",
            description="Read SOP, confirmation and medical safety boundary knowledge.",
            input_schema=SafetyKnowledgeInput,
            output_schema=SafetyKnowledgeOutput,
            permission_scope="safety_knowledge:read",
            allowed_agent_roles=("SafetyAgent", "RefillAgent", "ReminderAgent"),
            read_only=True,
        ),
        lambda tool_input, context: _search_safety_knowledge(db, tool_input, context),
    )


def _query_health_profile(
    db: Session,
    tool_input,
    context: ToolExecutionContext,
) -> dict[str, Any]:
    parsed = cast(HealthProfileInput, tool_input)
    _ensure_member_scope(parsed.member_id, context)
    if parsed.user_id != context.user_id:
        raise ToolExecutionError(
            "user_id does not match the execution context",
            error_type="context_isolation_violation",
            fallback_action="manual_review",
        )
    result = get_health_profile_context(db, parsed.user_id, parsed.member_id)
    return _require_evidence(result, "health profile not found")


def _query_prescriptions(
    db: Session,
    tool_input,
    context: ToolExecutionContext,
) -> dict[str, Any]:
    parsed = cast(PrescriptionsInput, tool_input)
    _ensure_member_scope(parsed.member_id, context)
    user_id = _require_user_scope(context)
    result = get_prescription_context(db, user_id, parsed.member_id)
    return _require_evidence(result, "prescription context not found")


def _query_medicine_box(
    db: Session,
    tool_input,
    context: ToolExecutionContext,
) -> dict[str, Any]:
    parsed = cast(MedicineBoxInput, tool_input)
    _ensure_member_scope(parsed.member_id, context)
    user_id = _require_user_scope(context)
    result = get_medicine_box_context(db, user_id, parsed.member_id)
    return _require_evidence(result, "medicine box context not found")


def _check_pharmacy_inventory(
    db: Session,
    tool_input,
    context: ToolExecutionContext,
) -> dict[str, Any]:
    parsed = cast(PharmacyInventoryInput, tool_input)
    result = get_pharmacy_inventory_context(db, parsed.medicine_name, parsed.city)
    return _require_evidence(
        result,
        "pharmacy inventory not found",
        fallback_action="manual_review",
    )


def _search_safety_knowledge(
    db: Session,
    tool_input,
    context: ToolExecutionContext,
) -> dict[str, Any]:
    parsed = cast(SafetyKnowledgeInput, tool_input)
    result = search_safety_knowledge_context(db, parsed.query)
    return _require_evidence(
        result,
        "safety knowledge not found",
        fallback_action="manual_review",
    )


def _ensure_member_scope(member_id: str, context: ToolExecutionContext) -> None:
    if member_id != context.member_id:
        raise ToolExecutionError(
            "member_id does not match the execution context",
            error_type="context_isolation_violation",
            fallback_action="manual_review",
        )


def _require_user_scope(context: ToolExecutionContext) -> str:
    if not context.user_id:
        raise ToolExecutionError(
            "user_id is required for member resource access",
            error_type="context_isolation_violation",
            fallback_action="manual_review",
        )
    return context.user_id


def _require_evidence(
    result: dict[str, Any] | None,
    message: str,
    *,
    fallback_action: str = "ask_user_clarification",
) -> dict[str, Any]:
    if result is None:
        raise ToolExecutionError(
            message,
            error_type="not_found",
            fallback_action=fallback_action,
        )
    return result


__all__ = [
    "HealthProfileInput",
    "HealthProfileOutput",
    "MedicineBoxInput",
    "MedicineBoxOutput",
    "PharmacyInventoryInput",
    "PharmacyInventoryOutput",
    "PrescriptionsInput",
    "PrescriptionsOutput",
    "SafetyKnowledgeInput",
    "SafetyKnowledgeOutput",
    "create_db_tool_registry",
    "register_db_tools",
]
