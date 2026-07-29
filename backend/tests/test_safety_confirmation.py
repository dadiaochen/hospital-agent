from __future__ import annotations

from app.agent.safety import SafetyDecision
from app.agent.safety_confirmation import (
    ConfirmationStateMachine,
    ConfirmationTransitionRequest,
    ThreeLayerSafetyGuard,
    build_confirmation_scope,
)
from app.agent.workflow_schemas import WorkflowFinalAnswerDraft


USER_ID = "user-task7"
MEMBER_ID = "member-task7"


def _scope():
    return build_confirmation_scope(
        task_id="task-task7",
        user_id=USER_ID,
        member_id=MEMBER_ID,
        action_type="reminder_create",
        idempotency_key="idem-task7",
        request_payload={"schedule": ["08:00", "20:00"]},
    )


def _decision() -> SafetyDecision:
    return SafetyDecision(stage="action", member_id=MEMBER_ID)


def _request(*, state: str, action: str, scope=None, confirmed: bool = False):
    return ConfirmationTransitionRequest(
        current_state=state,
        action=action,
        scope=scope or _scope(),
        current_scope=scope if state != "NONE" else None,
        actor_user_id=USER_ID,
        actor_member_id=MEMBER_ID,
        human_confirmation_present=confirmed,
        safety_decision=_decision(),
    )


def test_three_layers_distinguish_request_action_and_final_output() -> None:
    guard = ThreeLayerSafetyGuard()

    request = guard.request(
        message="我胸痛，能不能把降压药加量？",
        member_id=MEMBER_ID,
    )
    assert request.stage == "request"
    assert request.blocked is True
    assert "urgent_symptom" in request.flags

    action = guard.action(
        message="创建本地用药提醒草稿",
        user_id=USER_ID,
        member_id=MEMBER_ID,
        expected_user_id=USER_ID,
        expected_member_id=MEMBER_ID,
        confirmation_state="NONE",
        human_confirmation_present=False,
    )
    assert action.stage == "action"
    assert action.blocked is False
    assert action.requires_human_confirmation is True

    answer = WorkflowFinalAnswerDraft(
        content="已生成本地提醒草稿，执行前需要你的确认。",
        contains_factual_claims=False,
        waiting_for_user_confirmation=True,
        action_status="awaiting_confirmation",
    )
    final_decision, final_audit = guard.final_output(
        output=answer,
        member_id=MEMBER_ID,
    )
    assert final_decision.stage == "final_output"
    assert final_audit.passed is True


def test_confirmation_state_machine_auto_draft_then_requires_explicit_execution() -> None:
    machine = ConfirmationStateMachine()
    scope = _scope()

    draft = machine.transition(_request(state="NONE", action="create_draft"))
    assert draft.allowed is True
    assert draft.state == "DRAFT"
    assert draft.requires_human_confirmation is False
    assert draft.external_action_status == "not_submitted"

    missing_confirmation = machine.transition(
        _request(state="DRAFT", action="confirm", scope=scope)
    )
    assert missing_confirmation.allowed is False
    assert missing_confirmation.failure_code == "human_confirmation_required"
    assert missing_confirmation.state == "DRAFT"

    confirmed = machine.transition(
        _request(state="DRAFT", action="confirm", scope=scope, confirmed=True)
    )
    assert confirmed.allowed is True
    assert confirmed.state == "CONFIRMED"

    executed = machine.transition(
        _request(state="CONFIRMED", action="execute", scope=scope, confirmed=True)
    )
    assert executed.allowed is True
    assert executed.state == "EXECUTED"
    assert executed.external_action_status == "not_submitted"

    replay = machine.transition(
        _request(state="EXECUTED", action="execute", scope=scope, confirmed=True)
    )
    assert replay.allowed is True
    assert replay.idempotent_replay is True


def test_scope_member_version_and_idempotency_conflicts_are_blocked() -> None:
    machine = ConfirmationStateMachine()
    scope = _scope()

    wrong_actor = machine.transition(
        ConfirmationTransitionRequest(
            current_state="DRAFT",
            action="confirm",
            scope=scope,
            current_scope=scope,
            actor_user_id=USER_ID,
            actor_member_id="member-other",
            human_confirmation_present=True,
            safety_decision=_decision(),
        )
    )
    assert wrong_actor.allowed is False
    assert wrong_actor.failure_code == "context_isolation_violation"

    wrong_key = scope.model_copy(update={"idempotency_key": "idem-other"})
    key_conflict = machine.transition(
        ConfirmationTransitionRequest(
            current_state="DRAFT",
            action="confirm",
            scope=wrong_key,
            current_scope=scope,
            actor_user_id=USER_ID,
            actor_member_id=MEMBER_ID,
            human_confirmation_present=True,
            safety_decision=_decision(),
        )
    )
    assert key_conflict.failure_code == "idempotency_conflict"

    wrong_version = scope.model_copy(update={"draft_version": 2})
    version_conflict = machine.transition(
        ConfirmationTransitionRequest(
            current_state="DRAFT",
            action="confirm",
            scope=wrong_version,
            current_scope=scope,
            actor_user_id=USER_ID,
            actor_member_id=MEMBER_ID,
            human_confirmation_present=True,
            safety_decision=_decision(),
        )
    )
    assert version_conflict.failure_code == "draft_version_conflict"


def test_safety_block_and_dangerous_final_output_cannot_be_overridden() -> None:
    machine = ConfirmationStateMachine()
    scope = _scope()
    blocked = machine.transition(
        ConfirmationTransitionRequest(
            current_state="NONE",
            action="create_draft",
            scope=scope,
            actor_user_id=USER_ID,
            actor_member_id=MEMBER_ID,
            safety_decision=SafetyDecision(
                stage="request",
                blocked=True,
                flags=["urgent_symptom"],
                message="manual review",
                member_id=MEMBER_ID,
            ),
        )
    )
    assert blocked.allowed is False
    assert blocked.state == "BLOCKED"
    assert blocked.failure_code == "safety_blocked"

    guard = ThreeLayerSafetyGuard()
    dangerous = WorkflowFinalAnswerDraft(
        content="建议自行加量并停掉原来的药。",
        contains_factual_claims=True,
        waiting_for_user_confirmation=False,
        human_confirmation_present=True,
        action_status="executed",
    )
    decision, audit = guard.final_output(output=dangerous, member_id=MEMBER_ID)
    assert decision.blocked is True
    assert audit.passed is False
    assert "unsafe_medication_instruction" in audit.flags
