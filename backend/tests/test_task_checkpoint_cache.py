from __future__ import annotations

import json

from app.schemas.checkpoint import TaskCheckpointPayload
from app.services.task_checkpoint_cache import TaskCheckpointCache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}
        self.fail = False

    def get(self, name: str):
        if self.fail:
            raise RuntimeError("redis unavailable")
        return self.values.get(name)

    def set(self, name: str, value: str, *, ex: int):
        if self.fail:
            raise RuntimeError("redis unavailable")
        self.values[name] = value
        self.ttls[name] = ex
        return True

    def delete(self, *names: str):
        for name in names:
            self.values.pop(name, None)


def _payload(version: int = 1) -> TaskCheckpointPayload:
    return TaskCheckpointPayload(
        task_id="task-1",
        user_id="user-1",
        member_id="member-1",
        thread_id="thread-1",
        run_id="run-1",
        checkpoint_version=version,
        status="needs_confirmation",
        business_domain="chronic_care",
        intent="chronic_care",
        confirmation_state="DRAFT",
        confirmation_version=1,
        request_fingerprint="fingerprint-1",
        frozen_artifacts={"confirmation": {"state": "DRAFT"}},
    )


def test_checkpoint_cache_key_is_scoped_and_ttl_is_applied() -> None:
    redis = FakeRedis()
    cache = TaskCheckpointCache(redis, ttl_seconds=37)
    payload = _payload()

    assert cache.set(payload) is True
    key = cache.key(
        user_id="user-1",
        member_id="member-1",
        task_id="task-1",
        thread_id="thread-1",
        checkpoint_version=1,
    )
    assert "user:user-1" in key
    assert "member:member-1" in key
    assert "task:task-1" in key
    assert "thread:thread-1" in key
    assert redis.ttls[key] == 37
    assert cache.get(
        user_id="user-1",
        member_id="member-1",
        task_id="task-1",
        thread_id="thread-1",
        checkpoint_version=1,
    ) == payload


def test_cache_miss_or_stale_payload_is_safe() -> None:
    redis = FakeRedis()
    cache = TaskCheckpointCache(redis, ttl_seconds=10)
    payload = _payload()
    cache.set(payload)

    assert cache.get(
        user_id="user-1",
        member_id="member-1",
        task_id="task-1",
        thread_id="thread-1",
        checkpoint_version=2,
    ) is None

    key = cache.key(
        user_id="user-1",
        member_id="member-1",
        task_id="task-1",
        thread_id="thread-1",
        checkpoint_version=1,
    )
    redis.values[key] = json.dumps({"scratchpad": "must not be accepted"})
    assert cache.get(
        user_id="user-1",
        member_id="member-1",
        task_id="task-1",
        thread_id="thread-1",
        checkpoint_version=1,
    ) is None

    redis.fail = True
    assert cache.get(
        user_id="user-1",
        member_id="member-1",
        task_id="task-1",
        thread_id="thread-1",
        checkpoint_version=1,
    ) is None
    assert cache.set(payload) is False


def test_cross_member_payload_left_under_expected_cache_key_is_a_miss() -> None:
    redis = FakeRedis()
    cache = TaskCheckpointCache(redis, ttl_seconds=10)
    expected = _payload()
    key = cache.key(
        user_id=expected.user_id,
        member_id=expected.member_id,
        task_id=expected.task_id,
        thread_id=expected.thread_id,
        checkpoint_version=expected.checkpoint_version,
    )
    polluted = expected.model_copy(update={"member_id": "member-other"})
    redis.values[key] = json.dumps(polluted.model_dump(mode="json"))

    restored = cache.get(
        user_id=expected.user_id,
        member_id=expected.member_id,
        task_id=expected.task_id,
        thread_id=expected.thread_id,
        checkpoint_version=expected.checkpoint_version,
    )

    assert restored is None
