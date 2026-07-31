"""Best-effort Redis cache for PostgreSQL task checkpoint projections."""

from __future__ import annotations

import json
from typing import Any, Protocol

from redis import Redis, from_url

from app.core.config import settings
from app.schemas.checkpoint import TaskCheckpointPayload


class RedisLike(Protocol):
    def get(self, name: str) -> Any: ...

    def set(self, name: str, value: str, *, ex: int) -> Any: ...

    def delete(self, *names: str) -> Any: ...


class TaskCheckpointCache:
    """Cache only a versioned, scope-checked checkpoint projection.

    Every failure is treated as a cache miss.  The caller must then use the
    PostgreSQL checkpoint; a Redis outage must never change task correctness.
    """

    namespace = "family-health:task-checkpoint"

    def __init__(
        self,
        client: RedisLike | None = None,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        self.client: RedisLike = client or from_url(
            settings.redis_url,
            decode_responses=True,
        )
        self.ttl_seconds = ttl_seconds or settings.task_checkpoint_ttl_seconds

    @classmethod
    def key(
        cls,
        *,
        user_id: str,
        member_id: str,
        task_id: str,
        thread_id: str,
        checkpoint_version: int,
    ) -> str:
        # Keep all four scope dimensions visible in the key for operational
        # inspection and to prevent cross-member cache collisions.
        return (
            f"{cls.namespace}:user:{user_id}:member:{member_id}:task:{task_id}:"
            f"thread:{thread_id}:v:{checkpoint_version}"
        )

    def get(
        self,
        *,
        user_id: str,
        member_id: str,
        task_id: str,
        thread_id: str,
        checkpoint_version: int,
    ) -> TaskCheckpointPayload | None:
        key = self.key(
            user_id=user_id,
            member_id=member_id,
            task_id=task_id,
            thread_id=thread_id,
            checkpoint_version=checkpoint_version,
        )
        try:
            raw = self.client.get(key)
            if raw is None:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = TaskCheckpointPayload.model_validate(json.loads(str(raw)))
            if any(
                (
                    payload.user_id != user_id,
                    payload.member_id != member_id,
                    payload.task_id != task_id,
                    payload.thread_id != thread_id,
                    payload.checkpoint_version != checkpoint_version,
                )
            ):
                return None
            return payload
        except Exception:
            # Redis is explicitly non-authoritative.  Invalid or unavailable
            # cache data follows the same PostgreSQL fallback path as a miss.
            return None

    def set(self, payload: TaskCheckpointPayload) -> bool:
        key = self.key(
            user_id=payload.user_id,
            member_id=payload.member_id,
            task_id=payload.task_id,
            thread_id=payload.thread_id,
            checkpoint_version=payload.checkpoint_version,
        )
        try:
            result = self.client.set(
                key,
                json.dumps(payload.model_dump(mode="json"), ensure_ascii=False),
                ex=self.ttl_seconds,
            )
            return bool(result is None or result)
        except Exception:
            return False

    def delete(self, payload: TaskCheckpointPayload) -> bool:
        key = self.key(
            user_id=payload.user_id,
            member_id=payload.member_id,
            task_id=payload.task_id,
            thread_id=payload.thread_id,
            checkpoint_version=payload.checkpoint_version,
        )
        try:
            self.client.delete(key)
            return True
        except Exception:
            return False


__all__ = ["RedisLike", "TaskCheckpointCache"]
