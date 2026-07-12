from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.confirmation_draft_service import (
    ConfirmationDraftAction,
    ConfirmationDraftServiceError,
    create_confirmation_draft,
)
from app.tools.tool_registry import ToolExecutionError, ToolRegistry
from app.tools.tool_schemas import ToolContractModel, ToolExecutionContext, ToolSpec


_ACTION_ROLES = {
    "refill_request": {"RefillAgent"},
    "consultation_request": {"RefillAgent"},
    "pharmacy_option": {"PharmacyAgent"},
    "reminder_create": {"ReminderAgent"},
}


class ConfirmationDraftInput(ToolContractModel):
    user_id: str = Field(min_length=1)
    member_id: str = Field(min_length=1)
    action_type: ConfirmationDraftAction
    idempotency_key: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)


class ConfirmationDraftOutput(ToolContractModel):
    source_id: str = Field(min_length=1)
    source_name: str = Field(min_length=1)
    evidence_present: bool
    draft_id: str = Field(min_length=1)
    draft_type: ConfirmationDraftAction
    member_id: str = Field(min_length=1)
    status: Literal["draft"]
    need_human_confirmation: bool
    confirmed_at: str | None = None
    created_by_run_id: str = Field(min_length=1)
    local_confirmation_recorded: Literal[True]
    external_action_status: Literal["not_submitted"]
    idempotent_replay: bool


def register_confirmation_draft_tool(registry: ToolRegistry, db: Session) -> None:
    registry.register(
        ToolSpec(
            name="create_confirmation_draft",
            description=(
                "Create a local draft after user confirmation without submitting any "
                "hospital, pharmacy, purchase, or reminder action."
            ),
            input_schema=ConfirmationDraftInput,
            output_schema=ConfirmationDraftOutput,
            permission_scope="draft:create",
            allowed_agent_roles=("RefillAgent", "PharmacyAgent", "ReminderAgent"),
            requires_human_confirmation=True,
            read_only=False,
        ),
        lambda tool_input, context: _create_confirmation_draft(
            db,
            tool_input,
            context,
        ),
    )


def _create_confirmation_draft(
    db: Session,
    tool_input,
    context: ToolExecutionContext,
) -> dict[str, Any]:
    parsed = cast(ConfirmationDraftInput, tool_input)
    _ensure_execution_scope(parsed, context)
    if context.agent_role not in _ACTION_ROLES[parsed.action_type]:
        raise ToolExecutionError(
            f"{context.agent_role} cannot create {parsed.action_type}",
            error_type="permission_denied",
            fallback_action="route_to_authorized_agent",
        )

    try:
        result = create_confirmation_draft(
            db,
            user_id=parsed.user_id,
            member_id=parsed.member_id,
            action_type=parsed.action_type,
            idempotency_key=parsed.idempotency_key,
            run_id=context.run_id,
            summary=parsed.summary,
            payload=parsed.payload,
        )
        validated = ConfirmationDraftOutput.model_validate(result)
        db.commit()
        return validated.model_dump(mode="json")
    except ConfirmationDraftServiceError as exc:
        db.rollback()
        raise ToolExecutionError(
            str(exc),
            error_type=exc.error_type,
            fallback_action=exc.fallback_action,
        ) from exc
    except ValidationError as exc:
        db.rollback()
        raise ToolExecutionError(
            "confirmation draft output failed schema validation",
            error_type="output_schema_error",
            fallback_action="manual_review",
            schema_valid=False,
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise ToolExecutionError(
            "failed to commit confirmation draft",
            error_type="database_write_error",
            fallback_action="manual_review",
        ) from exc


def _ensure_execution_scope(
    tool_input: ConfirmationDraftInput,
    context: ToolExecutionContext,
) -> None:
    if tool_input.member_id != context.member_id:
        raise ToolExecutionError(
            "member_id does not match the execution context",
            error_type="context_isolation_violation",
            fallback_action="manual_review",
        )
    if context.user_id is None or tool_input.user_id != context.user_id:
        raise ToolExecutionError(
            "user_id does not match the execution context",
            error_type="context_isolation_violation",
            fallback_action="manual_review",
        )


__all__ = [
    "ConfirmationDraftInput",
    "ConfirmationDraftOutput",
    "register_confirmation_draft_tool",
]
