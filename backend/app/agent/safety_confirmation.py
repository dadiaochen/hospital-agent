"""Deterministic safety gates and confirmation-state transitions.

This module is deliberately side-effect free.  It does not persist a draft,
call a provider, or execute a medical action.  The application service owns
the transaction; this module only answers whether a transition is allowed.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Literal

from pydantic import Field, model_validator

from app.agent.context_schemas import ContractModel, NonEmptyStr
from app.agent.safety import SafetyDecision, evaluate_safety
from app.safety.model_output import RuleBasedModelOutputSafetyChecker as OutputChecker


ConfirmationState = Literal[
    "NONE",
    "DRAFT",
    "CONFIRMED",
    "EXECUTED",
    "REJECTED",
    "EXPIRED",
    "FAILED",
    "BLOCKED",
]
ConfirmationAction = Literal["create_draft", "confirm", "execute", "reject"]
ExternalActionStatus = Literal["not_submitted"]


class ConfirmationScope(ContractModel):
    """Immutable identity of the draft a caller is attempting to change."""

    draft_id: NonEmptyStr
    task_id: NonEmptyStr
    user_id: NonEmptyStr
    member_id: NonEmptyStr
    action_type: NonEmptyStr
    idempotency_key: NonEmptyStr
    request_fingerprint: NonEmptyStr
    draft_version: int = Field(default=1, ge=1)


class ConfirmationTransitionRequest(ContractModel):
    """Input to one deterministic state transition."""

    current_state: ConfirmationState
    action: ConfirmationAction
    scope: ConfirmationScope
    current_scope: ConfirmationScope | None = None
    actor_user_id: NonEmptyStr
    actor_member_id: NonEmptyStr
    human_confirmation_present: bool = False
    safety_decision: SafetyDecision


class ConfirmationTransitionResult(ContractModel):
    """Auditable result of a state-machine decision."""

    state: ConfirmationState
    allowed: bool
    idempotent_replay: bool = False
    requires_human_confirmation: bool = False
    external_action_status: ExternalActionStatus = "not_submitted"
    scope: ConfirmationScope
    failure_code: NonEmptyStr | None = None
    failure_reason: str | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "ConfirmationTransitionResult":
        if self.allowed and self.failure_code is not None:
            raise ValueError("allowed transition cannot contain failure_code")
        if not self.allowed and self.failure_code is None:
            raise ValueError("blocked transition must contain failure_code")
        if self.state == "BLOCKED" and self.allowed:
            raise ValueError("blocked state cannot be an allowed transition")
        if self.idempotent_replay and not self.allowed:
            raise ValueError("idempotent replay must be allowed")
        return self


class FinalOutputSafetyResult(ContractModel):
    """Small serializable audit record for the final-output gate."""

    passed: bool
    blocked: bool
    flags: list[NonEmptyStr] = Field(default_factory=list)
    member_id: NonEmptyStr


def build_confirmation_scope(
    *,
    task_id: str,
    user_id: str,
    member_id: str,
    action_type: str,
    idempotency_key: str,
    request_payload: object,
    draft_version: int = 1,
) -> ConfirmationScope:
    """Build a stable scope and request fingerprint for idempotency checks."""

    normalized = json.dumps(
        request_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    fingerprint = sha256(normalized).hexdigest()
    draft_id = "draft:" + sha256(
        f"{task_id}:{idempotency_key}".encode("utf-8")
    ).hexdigest()[:24]
    return ConfirmationScope(
        draft_id=draft_id,
        task_id=task_id,
        user_id=user_id,
        member_id=member_id,
        action_type=action_type,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        draft_version=draft_version,
    )


class ThreeLayerSafetyGuard:
    """Request, action and final-output safety gates.

    The guard is a policy object, not an Agent.  It never changes business
    state and never decides a diagnosis or a medication plan.
    """

    _DANGEROUS_OUTPUT_FLAGS = {
        "unsafe_medication_instruction",
        "confirmation_bypass",
        "auto_prescription_claim",
        "external_action_claim",
    }

    def __init__(self) -> None:
        self._output_checker = OutputChecker()

    def request(
        self,
        *,
        message: str,
        member_id: str,
    ) -> SafetyDecision:
        """Run before any ordinary business tool or provider call."""

        return evaluate_safety(
            message,
            stage="request",
        ).model_copy(update={"member_id": member_id})

    def action(
        self,
        *,
        message: str,
        user_id: str,
        member_id: str,
        expected_user_id: str,
        expected_member_id: str,
        confirmation_state: ConfirmationState,
        human_confirmation_present: bool,
    ) -> SafetyDecision:
        """Check scope, medical safety and confirmation before a protected action."""

        if user_id != expected_user_id or member_id != expected_member_id:
            return SafetyDecision(
                stage="action",
                blocked=True,
                flags=["context_isolation_violation", "manual_review_required"],
                message="用户或家庭成员作用域不一致，系统拒绝继续执行。",
                member_id=member_id,
            )

        decision = evaluate_safety(message, stage="action").model_copy(
            update={"member_id": member_id}
        )
        if decision.blocked:
            return decision

        if confirmation_state in {"BLOCKED", "REJECTED", "EXPIRED", "FAILED"}:
            return SafetyDecision(
                stage="action",
                blocked=True,
                flags=["invalid_confirmation_state", "manual_review_required"],
                message="当前草稿状态不允许继续执行。",
                member_id=member_id,
            )

        if not human_confirmation_present:
            return SafetyDecision(
                stage="action",
                requires_human_confirmation=True,
                flags=["human_confirmation_required"],
                message="本地草稿可以自动生成；真正执行前需要用户明确确认。",
                member_id=member_id,
            )

        return decision

    def final_output(
        self,
        *,
        output: object,
        member_id: str,
    ) -> tuple[SafetyDecision, FinalOutputSafetyResult]:
        """Check the frozen candidate immediately before it becomes user-visible."""

        text = self._output_text(output)
        rule_flags: list[str] = []
        if hasattr(output, "model_dump"):
            result = self._output_checker.check(output)
            rule_flags.extend(result.flags)

        semantic = evaluate_safety(text, stage="final_output")
        flags = list(dict.fromkeys([*semantic.flags, *rule_flags]))
        blocked = semantic.blocked or bool(
            set(rule_flags) & self._DANGEROUS_OUTPUT_FLAGS
        )
        if blocked:
            decision = SafetyDecision(
                stage="final_output",
                blocked=True,
                flags=flags or ["unsafe_final_output"],
                message="候选回答未通过安全检查，不能直接发送，请转人工复核。",
                requires_human_confirmation=True,
                member_id=member_id,
            )
        else:
            decision = SafetyDecision(
                stage="final_output",
                flags=flags,
                member_id=member_id,
            )
        return decision, FinalOutputSafetyResult(
            passed=not blocked,
            blocked=blocked,
            flags=flags,
            member_id=member_id,
        )

    @staticmethod
    def _output_text(output: object) -> str:
        if isinstance(output, str):
            return output
        content = getattr(output, "content", None)
        if isinstance(content, str):
            return content
        model_dump = getattr(output, "model_dump", None)
        if callable(model_dump):
            return str(model_dump(mode="json"))
        return str(output)


class ConfirmationStateMachine:
    """Pure transition rules for local drafts and confirmation continuations."""

    def transition(
        self,
        request: ConfirmationTransitionRequest,
    ) -> ConfirmationTransitionResult:
        scope = request.scope
        if (
            request.actor_user_id != scope.user_id
            or request.actor_member_id != scope.member_id
        ):
            return self._failure(
                scope,
                state="BLOCKED",
                code="context_isolation_violation",
                reason="actor scope does not match the draft scope",
            )

        if request.current_scope is not None:
            mismatch = self._scope_mismatch(request.current_scope, scope)
            if mismatch is not None:
                return self._failure(
                    scope,
                    state="BLOCKED",
                    code=mismatch,
                    reason="draft identity, version, or idempotency scope changed",
                )

        if request.safety_decision.blocked:
            return self._failure(
                scope,
                state="BLOCKED",
                code="safety_blocked",
                reason=request.safety_decision.message or "safety policy blocked action",
            )

        current = request.current_state
        action = request.action
        if action == "create_draft":
            if current == "NONE":
                return self._success(scope, state="DRAFT")
            if current == "DRAFT":
                return self._success(scope, state="DRAFT", replay=True)
            return self._failure(
                scope,
                state=current,
                code="invalid_state_transition",
                reason="a draft cannot be recreated after leaving DRAFT",
            )

        if action == "confirm":
            if current == "CONFIRMED":
                return self._success(scope, state="CONFIRMED", replay=True)
            if current != "DRAFT":
                return self._failure(
                    scope,
                    state=current,
                    code="invalid_state_transition",
                    reason="only a DRAFT can be confirmed",
                )
            if not request.human_confirmation_present:
                return self._failure(
                    scope,
                    state="DRAFT",
                    code="human_confirmation_required",
                    reason="explicit user confirmation is required",
                    requires_confirmation=True,
                )
            return self._success(scope, state="CONFIRMED")

        if action == "execute":
            if current == "EXECUTED":
                return self._success(scope, state="EXECUTED", replay=True)
            if current != "CONFIRMED":
                return self._failure(
                    scope,
                    state=current,
                    code="invalid_state_transition",
                    reason="only a CONFIRMED draft can be executed",
                )
            if not request.human_confirmation_present:
                return self._failure(
                    scope,
                    state="CONFIRMED",
                    code="human_confirmation_required",
                    reason="explicit user confirmation is required before execution",
                    requires_confirmation=True,
                )
            return self._success(scope, state="EXECUTED")

        if current == "REJECTED":
            return self._success(scope, state="REJECTED", replay=True)
        if current != "DRAFT":
            return self._failure(
                scope,
                state=current,
                code="invalid_state_transition",
                reason="only a DRAFT can be rejected",
            )
        if not request.human_confirmation_present:
            return self._failure(
                scope,
                state="DRAFT",
                code="human_confirmation_required",
                reason="explicit user decision is required",
                requires_confirmation=True,
            )
        return self._success(scope, state="REJECTED")

    @staticmethod
    def _scope_mismatch(
        current: ConfirmationScope,
        requested: ConfirmationScope,
    ) -> str | None:
        if current.idempotency_key != requested.idempotency_key:
            return "idempotency_conflict"
        if current.user_id != requested.user_id or current.member_id != requested.member_id:
            return "context_isolation_violation"
        if current.task_id != requested.task_id or current.draft_id != requested.draft_id:
            return "draft_scope_conflict"
        if current.action_type != requested.action_type:
            return "action_type_conflict"
        if current.request_fingerprint != requested.request_fingerprint:
            return "request_fingerprint_conflict"
        if current.draft_version != requested.draft_version:
            return "draft_version_conflict"
        return None

    @staticmethod
    def _success(
        scope: ConfirmationScope,
        *,
        state: ConfirmationState,
        replay: bool = False,
    ) -> ConfirmationTransitionResult:
        return ConfirmationTransitionResult(
            state=state,
            allowed=True,
            idempotent_replay=replay,
            scope=scope,
        )

    @staticmethod
    def _failure(
        scope: ConfirmationScope,
        *,
        state: ConfirmationState,
        code: str,
        reason: str,
        requires_confirmation: bool = False,
    ) -> ConfirmationTransitionResult:
        return ConfirmationTransitionResult(
            state=state,
            allowed=False,
            requires_human_confirmation=requires_confirmation,
            scope=scope,
            failure_code=code,
            failure_reason=reason,
        )


__all__ = [
    "ConfirmationAction",
    "ConfirmationScope",
    "ConfirmationState",
    "ConfirmationStateMachine",
    "ConfirmationTransitionRequest",
    "ConfirmationTransitionResult",
    "FinalOutputSafetyResult",
    "ThreeLayerSafetyGuard",
    "build_confirmation_scope",
]
