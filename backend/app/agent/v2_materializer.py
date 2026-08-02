"""Isolated WorldState materialization for the 4D-B2.5 local runner.

The production materializer described in the evaluation plan will eventually
write PostgreSQL rows, Provider sandbox state and a per-case RAG namespace.
This stage deliberately uses an in-memory adapter with the same boundary.
That gives us deterministic isolation and cleanup tests without modifying the
application database or requiring Docker during unit tests.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.agent.v2_benchmark_schemas import EvalQueryVariant, EvalWorldState
from app.agent.v2_eval_schemas import MaterializationReceipt


class MaterializationError(ValueError):
    """Raised when a WorldState cannot be isolated safely."""


@dataclass(frozen=True)
class MaterializedCase:
    """Read-only view handed to an evaluation executor."""

    world: EvalWorldState
    query: EvalQueryVariant
    receipt: MaterializationReceipt
    database_projection: dict[str, tuple[dict[str, Any], ...]]
    provider_projection: dict[str, Any]
    rag_projection: dict[str, tuple[str, ...]]


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class InMemoryProjectionBackend:
    """A per-run fake for DB, Provider and RAG namespaces.

    The dictionary belongs to one backend instance and is never shared with
    the application services.  A production adapter can implement the same
    three operations with a PostgreSQL transaction and a disposable RAG
    namespace.
    """

    def __init__(self) -> None:
        self._namespaces: dict[str, dict[str, Any]] = {}

    @property
    def active_namespaces(self) -> tuple[str, ...]:
        return tuple(sorted(self._namespaces))

    def create_namespace(
        self,
        *,
        namespace: str,
        world: EvalWorldState,
        query: EvalQueryVariant,
    ) -> MaterializedCase:
        if namespace in self._namespaces:
            raise MaterializationError(f"evaluation namespace already exists: {namespace}")
        if query.world_state_id != world.world_state_id:
            raise MaterializationError("query and WorldState IDs do not match")
        if query.dataset_split != world.dataset_split:
            raise MaterializationError("query and WorldState split do not match")
        if query.expected_member_id != world.gold.expected_member_id:
            raise MaterializationError("query expected_member_id does not match Gold")

        source_ids = self._source_ids(world)
        if world.fault_injection.fault_type == "no_source":
            source_ids = ()
        stale_source_ids = tuple(world.knowledge_state.stale_source_ids)
        receipt = MaterializationReceipt(
            world_state_id=world.world_state_id,
            query_id=query.query_id,
            namespace=namespace,
            member_ids=tuple(member.member_id for member in world.members),
            materialized_source_ids=source_ids,
            stale_source_ids=stale_source_ids,
            gold_hash=_canonical_hash(world.gold.model_dump(mode="json")),
            cleanup_succeeded=False,
        )
        database_projection = {
            "members": tuple(
                member.model_dump(mode="json") for member in world.members
            ),
            "prescriptions": tuple(
                item.model_dump(mode="json") for item in world.prescriptions
            ),
            "medicine_box": tuple(
                item.model_dump(mode="json") for item in world.medicine_box
            ),
            "health_records": tuple(
                item.model_dump(mode="json") for item in world.health_records
            ),
        }
        provider_projection = world.provider_state.model_dump(mode="json")
        rag_projection = {
            "namespace": (world.knowledge_state.namespace,),
            "current_source_ids": tuple(world.knowledge_state.current_source_ids),
            "stale_source_ids": stale_source_ids,
        }
        self._namespaces[namespace] = {
            "database": database_projection,
            "provider": provider_projection,
            "rag": rag_projection,
            "world_state_id": world.world_state_id,
            "query_id": query.query_id,
        }
        return MaterializedCase(
            world=world.model_copy(deep=True),
            query=query.model_copy(deep=True),
            receipt=receipt,
            database_projection=database_projection,
            provider_projection=provider_projection,
            rag_projection=rag_projection,
        )

    def cleanup(self, namespace: str) -> bool:
        """Delete one namespace; deleting an already-clean namespace is safe."""

        self._namespaces.pop(namespace, None)
        return namespace not in self._namespaces

    @staticmethod
    def _source_ids(world: EvalWorldState) -> tuple[str, ...]:
        values = [
            *(member.profile_source_id for member in world.members),
            *(item.source_id for item in world.prescriptions),
            *(item.source_id for item in world.medicine_box),
            *(item.source_id for item in world.health_records),
            *world.provider_state.source_ids,
            *world.knowledge_state.current_source_ids,
        ]
        return tuple(dict.fromkeys(values))


class WorldStateMaterializer:
    """Create one isolated in-memory case and always expose cleanup."""

    def __init__(self, backend: InMemoryProjectionBackend | None = None) -> None:
        self.backend = backend or InMemoryProjectionBackend()

    def materialize(
        self, world: EvalWorldState, query: EvalQueryVariant
    ) -> MaterializedCase:
        digest = hashlib.sha256(query.query_id.encode("utf-8")).hexdigest()[:16]
        namespace = f"eval-v2-{digest}"
        return self.backend.create_namespace(
            namespace=namespace,
            world=world,
            query=query,
        )

    def cleanup(self, materialized: MaterializedCase) -> MaterializationReceipt:
        succeeded = self.backend.cleanup(materialized.receipt.namespace)
        return materialized.receipt.model_copy(
            update={"cleanup_succeeded": succeeded}
        )

    def cleanup_all(self) -> bool:
        for namespace in self.backend.active_namespaces:
            self.backend.cleanup(namespace)
        return not self.backend.active_namespaces

__all__ = [
    "InMemoryProjectionBackend",
    "MaterializationError",
    "MaterializedCase",
    "WorldStateMaterializer",
]
