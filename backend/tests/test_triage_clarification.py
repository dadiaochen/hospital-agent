from sqlalchemy import select

from app.models import AgentRun, TaskCheckpoint
from tests.test_business_task_api import FATHER_ID, business_client


def test_triage_missing_slots_checkpoint_then_resumes_with_clarification(
    business_client,
) -> None:
    client, session = business_client

    first_response = client.post(
        "/api/business-tasks",
        json={
            "business_domain": "preconsultation",
            "member_id": FATHER_ID,
            "user_input": "请帮父亲整理复诊准备材料",
            "input_payload": {},
            "idempotency_key": "triage-clarification-1",
        },
    )

    assert first_response.status_code == 201
    first = first_response.json()
    assert first["status"] == "needs_clarification"
    assert first["need_human_confirmation"] is False
    assert first["checkpoint_version"] == 1
    assert first["task"]["member_id"] == FATHER_ID
    first_checkpoint = session.scalar(
        select(TaskCheckpoint).where(
            TaskCheckpoint.task_id == first["task"]["id"],
            TaskCheckpoint.checkpoint_version == 1,
        )
    )
    assert first_checkpoint is not None
    assert first_checkpoint.frozen_artifacts["triage_state"]["missing_slots"] == [
        "symptoms"
    ]
    first_run_id = first["run_id"]

    second_response = client.post(
        f"/api/business-tasks/{first['task']['id']}/clarify",
        json={
            "user_input": "父亲近两天咳嗽，想整理就医准备信息",
            "input_payload": {"symptoms": "近两天咳嗽"},
            "idempotency_key": "triage-clarification-1",
            "checkpoint_version": 1,
        },
    )

    assert second_response.status_code == 200
    second = second_response.json()
    assert second["status"] == "needs_confirmation"
    assert second["task"]["member_id"] == FATHER_ID
    assert second["resumed_from_run_id"] == first_run_id
    assert second["checkpoint_version"] == 2
    second_run = session.scalar(select(AgentRun).where(AgentRun.id == second["run_id"]))
    assert second_run is not None
    assert second_run.parent_run_id == first_run_id
    assert all(ref["member_id"] == FATHER_ID for ref in second["source_refs"])


def test_triage_clarification_rejects_stale_checkpoint_version(business_client) -> None:
    client, _ = business_client
    response = client.post(
        "/api/business-tasks",
        json={
            "business_domain": "preconsultation",
            "member_id": FATHER_ID,
            "user_input": "请整理复诊准备",
            "idempotency_key": "triage-clarification-stale",
        },
    )
    first = response.json()

    stale = client.post(
        f"/api/business-tasks/{first['task']['id']}/clarify",
        json={
            "user_input": "补充症状",
            "input_payload": {"symptoms": "咳嗽"},
            "idempotency_key": "triage-clarification-stale",
            "checkpoint_version": 99,
        },
    )

    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "checkpoint_version_conflict"
