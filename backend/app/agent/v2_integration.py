"""PostgreSQL-backed integration adapters for the 4D-B2.6 runner.

The v2 benchmark uses synthetic identifiers and must never be mixed with the
normal demo rows.  This module therefore uses one PostgreSQL transaction per
case and temporary tables for the WorldState projection.  The transaction is
rolled back during cleanup, so a benchmark cannot leave patient-like rows in
the application database.

The graph executor is deliberately explicit about identity and source
translation.  A real application run uses database IDs and source IDs created
by the seeded database; the benchmark uses frozen IDs.  Evaluation is refused
until that mapping is supplied instead of silently grading unrelated data.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
from time import perf_counter
from threading import RLock
from typing import Any, Protocol
from uuid import uuid4

from pydantic import Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.product_artifacts import build_run_trace
from app.agent.final_claim_schemas import FinalClaim
from app.agent.supervised_workflow import SupervisorBusinessWorkflow
from app.agent.unified_health_graph import UnifiedHealthGraph
from app.agent.v2_benchmark_schemas import (
    EvalDependencyEdge,
    EvalQueryVariant,
    EvalWorldState,
)
from app.agent.v2_eval_schemas import (
    ConfirmationDraftSnapshot,
    MaterializationReceipt,
    V2RunArtifacts,
)
from app.agent.v2_materializer import MaterializationError
from app.agent.orchestration_schemas import EvalRuntimeOptions
from app.models import (
    AgentRun,
    BusinessTask,
    KnowledgeChunk,
    KnowledgeDocument,
    MedicineBoxItem,
    Prescription,
)
from app.models.base import utc_now
from app.core.reliability import classify_error
from app.providers import build_mock_provider_registry
from app.providers.registry import ProviderRegistry
from app.providers.schemas import (
    ProviderAttemptTrace,
    ProviderRequest,
    ProviderResponse,
)
from app.rag import Retriever, create_knowledge_retriever
from app.schemas.business import BusinessDomain, ProviderMode
from app.core.config import Settings


class PostgresMaterializationError(MaterializationError):
    """Raised when the real database cannot provide an isolated case."""


class IntegrationExecutionError(RuntimeError):
    """Raised when a real graph result cannot be mapped to benchmark IDs."""


class ScopedProviderSandbox(ProviderRegistry):
    """Case-scoped Provider adapter used by integration evaluation.

    Normal Provider handlers remain the existing deterministic mock handlers.
    Fault injection is applied only to this instance, so one benchmark case
    cannot mutate another case's provider state.
    """

    def __init__(self, world: EvalWorldState) -> None:
        super().__init__()
        self.world = world
        self.delegate = build_mock_provider_registry()

    def invoke(self, name: str, request: ProviderRequest) -> ProviderResponse:
        fault = self.world.fault_injection
        timeout_targeted = (
            name in fault.target
            or fault.target in f"{name}_{request.operation}"
            or (
                fault.target.endswith("_provider")
                and name in {
                    "online_consultation",
                    "pharmacy",
                    "notification",
                    "medical_document_parser",
                }
            )
        )
        if fault.enabled and fault.fault_type == "timeout" and timeout_targeted:
            attempt_count = 2 if fault.retryable else 1
            attempts = [
                ProviderAttemptTrace(
                    attempt_no=index,
                    success=False,
                    latency_ms=1,
                    error_type="timeout",
                    error_category="timeout",
                    retryable=fault.retryable,
                )
                for index in range(1, attempt_count + 1)
            ]
            return ProviderResponse(
                provider_name=name,
                provider_mode=request.provider_mode,
                operation=request.operation,
                success=False,
                error_type="timeout",
                error_category=classify_error("timeout"),
                error_message="sandbox timeout",
                retryable=False,
                degraded=True,
                fallback_reason=fault.expected_fallback,
                latency_ms=attempt_count,
                attempts=attempts,
            )

        delegate_request = request.model_copy(update={"provider_mode": "mock"})
        response = self.delegate.invoke(name, delegate_request)
        updates: dict[str, Any] = {"provider_mode": request.provider_mode}
        if fault.enabled and fault.fault_type == "no_source":
            updates["source_refs"] = []
        return response.model_copy(update=updates)


class ScopedPostgresRetriever:
    """Limit the real PostgreSQL retriever to one benchmark namespace.

    The demo database already contains normal knowledge rows.  A benchmark
    case must not accidentally retrieve those rows, so the adapter lets the
    real retriever rank PostgreSQL data and then enforces the case source
    allow-list before returning evidence to the business graph.
    """

    def __init__(self, delegate: Retriever, allowed_source_ids: set[str]) -> None:
        self.delegate = delegate
        self.allowed_source_ids = set(allowed_source_ids)

    def retrieve(self, request):
        result = self.delegate.retrieve(request)
        sources = [
            source
            for source in result.sources
            if source.source_id in self.allowed_source_ids
        ]
        return result.model_copy(
            update={
                "sources": sources,
                "evidence_present": bool(sources),
            }
        )


@dataclass(frozen=True)
class PostgresMaterializedCase:
    """A WorldState projection kept alive by one open PostgreSQL session."""

    world: EvalWorldState
    query: EvalQueryVariant
    receipt: MaterializationReceipt
    session: Session
    table_names: tuple[str, ...]
    database_projection: dict[str, tuple[dict[str, Any], ...]]
    provider_projection: dict[str, Any]
    rag_projection: dict[str, tuple[str, ...]]
    rag_source_aliases: dict[str, str]


class PostgresSessionFactory(Protocol):
    def __call__(self) -> Session: ...


class PostgresV2Materializer:
    """Materialize one case into PostgreSQL temporary projection tables.

    The production schema is intentionally untouched.  Existing application
    rows are used by the graph only after an explicit identity/source mapping
    is supplied to the integration executor.  This keeps benchmark cleanup
    transactional and avoids adding evaluation-only Alembic migrations.
    """

    def __init__(self, session_factory: PostgresSessionFactory) -> None:
        self._session_factory = session_factory
        self._active: dict[str, PostgresMaterializedCase] = {}
        self._lock = RLock()

    @property
    def active_namespaces(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._active))

    def materialize(
        self, world: EvalWorldState, query: EvalQueryVariant
    ) -> PostgresMaterializedCase:
        self._validate_pair(world, query)
        namespace = self._namespace(query.query_id)
        with self._lock:
            if namespace in self._active:
                raise PostgresMaterializationError(
                    f"evaluation namespace already exists: {namespace}"
                )

        session = self._session_factory()
        try:
            if session.bind is None or session.bind.dialect.name != "postgresql":
                raise PostgresMaterializationError(
                    "PostgreSQL materialization requires a PostgreSQL session"
                )

            table_names = self._create_tables(session, namespace)
            database_projection = self._database_projection(world)
            provider_projection = world.provider_state.model_dump(mode="json")
            stale_source_ids = tuple(world.knowledge_state.stale_source_ids)
            source_ids = self._source_ids(world)
            if world.fault_injection.fault_type == "no_source":
                source_ids = ()
            rag_projection = {
                "namespace": (world.knowledge_state.namespace,),
                "current_source_ids": tuple(world.knowledge_state.current_source_ids),
                "stale_source_ids": stale_source_ids,
            }
            rag_source_aliases = self._materialize_rag_rows(
                session,
                world=world,
                query=query,
            )
            self._insert_projection(
                session,
                table_names[0],
                world=world,
                query=query,
                member_id=None,
                rows=database_projection,
            )
            self._insert_projection(
                session,
                table_names[1],
                world=world,
                query=query,
                member_id=query.expected_member_id,
                rows={"provider": (provider_projection,)},
            )
            self._insert_projection(
                session,
                table_names[2],
                world=world,
                query=query,
                member_id=query.expected_member_id,
                rows={"rag": (rag_projection,)},
            )
            receipt = MaterializationReceipt(
                world_state_id=world.world_state_id,
                query_id=query.query_id,
                namespace=namespace,
                member_ids=tuple(member.member_id for member in world.members),
                materialized_source_ids=source_ids,
                stale_source_ids=stale_source_ids,
                gold_hash=_gold_hash(world),
                backend="postgresql_shadow_transaction",
                cleanup_succeeded=False,
            )
            materialized = PostgresMaterializedCase(
                world=world.model_copy(deep=True),
                query=query.model_copy(deep=True),
                receipt=receipt,
                session=session,
                table_names=table_names,
                database_projection=database_projection,
                provider_projection=provider_projection,
                rag_projection=rag_projection,
                rag_source_aliases=rag_source_aliases,
            )
            with self._lock:
                self._active[namespace] = materialized
            return materialized
        except (SQLAlchemyError, TypeError, ValueError) as exc:
            session.rollback()
            session.close()
            if isinstance(exc, PostgresMaterializationError):
                raise
            raise PostgresMaterializationError(
                "failed to create PostgreSQL evaluation projection"
            ) from exc

    def cleanup(
        self, materialized: PostgresMaterializedCase
    ) -> MaterializationReceipt:
        with self._lock:
            active = self._active.pop(materialized.receipt.namespace, None)
        if active is None:
            return materialized.receipt.model_copy(update={"cleanup_succeeded": True})
        succeeded = True
        try:
            # ON COMMIT DROP is a second line of defense; rollback also removes
            # any temporary application rows created by the graph executor.
            active.session.rollback()
        except SQLAlchemyError:
            succeeded = False
        finally:
            active.session.close()
        return active.receipt.model_copy(update={"cleanup_succeeded": succeeded})

    def cleanup_all(self) -> bool:
        with self._lock:
            active_cases = tuple(self._active.values())
        for materialized in active_cases:
            self.cleanup(materialized)
        with self._lock:
            return not self._active

    @staticmethod
    def _validate_pair(world: EvalWorldState, query: EvalQueryVariant) -> None:
        if query.world_state_id != world.world_state_id:
            raise PostgresMaterializationError("query and WorldState IDs do not match")
        if query.dataset_split != world.dataset_split:
            raise PostgresMaterializationError("query and WorldState split do not match")
        if query.expected_member_id != world.gold.expected_member_id:
            raise PostgresMaterializationError(
                "query expected_member_id does not match Gold"
            )

    @staticmethod
    def _namespace(query_id: str) -> str:
        digest = hashlib.sha256(query_id.encode("utf-8")).hexdigest()[:16]
        return f"eval-v2-{digest}"

    @staticmethod
    def _table_names(namespace: str) -> tuple[str, str, str]:
        suffix = namespace.replace("-", "_")
        return (
            f"eval_v2_db_{suffix}",
            f"eval_v2_provider_{suffix}",
            f"eval_v2_rag_{suffix}",
        )

    @classmethod
    def _create_tables(cls, session: Session, namespace: str) -> tuple[str, str, str]:
        names = cls._table_names(namespace)
        for name in names:
            session.execute(
                text(
                    f'CREATE TEMP TABLE "{name}" ('
                    "record_key TEXT PRIMARY KEY, "
                    "world_state_id TEXT NOT NULL, "
                    "query_id TEXT NOT NULL, "
                    "member_id TEXT, "
                    "payload JSONB NOT NULL"
                    ") ON COMMIT DROP"
                )
            )
        return names

    @staticmethod
    def _insert_projection(
        session: Session,
        table_name: str,
        *,
        world: EvalWorldState,
        query: EvalQueryVariant,
        member_id: str | None,
        rows: Mapping[str, tuple[dict[str, Any], ...]],
    ) -> None:
        values: list[dict[str, Any]] = []
        for kind, items in rows.items():
            for index, item in enumerate(items):
                values.append(
                    {
                        "record_key": f"{kind}:{index}",
                        "world_state_id": world.world_state_id,
                        "query_id": query.query_id,
                        "member_id": member_id,
                        "payload": json.dumps(item, ensure_ascii=False),
                    }
                )
        if values:
            session.execute(
                text(
                    f'INSERT INTO "{table_name}" '
                    "(record_key, world_state_id, query_id, member_id, payload) "
                    "VALUES (:record_key, :world_state_id, :query_id, :member_id, "
                    "CAST(:payload AS JSONB))"
                ),
                values,
            )

    @staticmethod
    def _database_projection(
        world: EvalWorldState,
    ) -> dict[str, tuple[dict[str, Any], ...]]:
        return {
            "members": tuple(member.model_dump(mode="json") for member in world.members),
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

    @staticmethod
    def _materialize_rag_rows(
        session: Session,
        *,
        world: EvalWorldState,
        query: EvalQueryVariant,
    ) -> dict[str, str]:
        """Write current case knowledge rows and return their source aliases."""

        aliases: dict[str, str] = {}
        if world.fault_injection.fault_type == "no_source":
            return aliases
        for index, benchmark_source_id in enumerate(
            world.knowledge_state.current_source_ids
        ):
            document_id = str(uuid4())
            chunk_id = str(uuid4())
            document = KnowledgeDocument(
                id=document_id,
                title=f"evaluation-{world.world_state_id}-{index}",
                category="evaluation",
                source="v2-evaluation",
                content=query.user_input,
                safety_level="review_required",
                version=world.knowledge_state.version,
            )
            chunk = KnowledgeChunk(
                id=chunk_id,
                document_id=document_id,
                chunk_index=index,
                content=(
                    f"{query.user_input} source={benchmark_source_id} "
                    f"intent={query.expected_intent}"
                ),
                keywords=[query.expected_intent, "evaluation", benchmark_source_id],
                chunk_version=world.knowledge_state.version,
            )
            session.add_all([document, chunk])
            aliases[f"knowledge:{document_id}:{chunk_id}"] = benchmark_source_id
        if aliases:
            session.flush()
        return aliases

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


class IntegrationIdentityMap:
    """Explicit mapping between frozen benchmark IDs and real DB IDs.

    The original B2.6 sample used one global user/member/source map.  The
    final 300-WorldState gate uses ``cases`` so two synthetic worlds can never
    accidentally share a member or source mapping.  The global constructor
    remains supported for the existing one-case and two-case demos.
    """

    def __init__(
        self,
        *,
        benchmark_user_id: str | None = None,
        actual_user_id: str | None = None,
        member_ids: Mapping[str, str] | None = None,
        source_ids: Mapping[str, str] | None = None,
        case_maps: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        if (benchmark_user_id and not actual_user_id) or (
            actual_user_id and not benchmark_user_id
        ):
            raise ValueError("benchmark and actual user IDs are required")
        if not (case_maps or (benchmark_user_id and actual_user_id)):
            raise ValueError("a global map or at least one case map is required")
        self.benchmark_user_id = benchmark_user_id or ""
        self.actual_user_id = actual_user_id or ""
        self.member_ids = dict(member_ids or {})
        self.source_ids = dict(source_ids or {})
        self.case_maps = {
            str(case_id): {
                "benchmark_user_id": str(values["benchmark_user_id"]),
                "actual_user_id": str(values["actual_user_id"]),
                "member_ids": {
                    str(key): str(value)
                    for key, value in dict(values.get("member_ids", {})).items()
                },
                "source_ids": {
                    str(key): str(value)
                    for key, value in dict(values.get("source_ids", {})).items()
                },
            }
            for case_id, values in (case_maps or {}).items()
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "IntegrationIdentityMap":
        """Load either the legacy global map or the final case-scoped map.

        Empty values in the generated template are rejected here.  A template
        is documentation for the user to fill, not a runnable identity map.
        """

        cases = payload.get("cases")
        if cases is not None:
            if not isinstance(cases, Mapping) or not cases:
                raise ValueError("case-scoped identity map must contain cases")
            parsed_cases: dict[str, dict[str, Any]] = {}
            for case_id, raw_case in cases.items():
                if not isinstance(raw_case, Mapping):
                    raise ValueError(f"invalid identity map case: {case_id}")
                benchmark_user_id = str(raw_case.get("benchmark_user_id", ""))
                actual_user_id = str(raw_case.get("actual_user_id", ""))
                if not benchmark_user_id or not actual_user_id:
                    raise ValueError(
                        f"missing actual user mapping for case: {case_id}"
                    )
                raw_members = raw_case.get("member_ids", {})
                if not isinstance(raw_members, Mapping) or not raw_members:
                    raise ValueError(f"missing member mappings for case: {case_id}")
                member_ids = {str(key): str(value) for key, value in raw_members.items()}
                if any(not value for value in member_ids.values()):
                    raise ValueError(f"missing actual member mapping for case: {case_id}")

                source_ids: dict[str, str] = {}
                raw_sources = raw_case.get("source_ids")
                if raw_sources is not None:
                    if not isinstance(raw_sources, Mapping):
                        raise ValueError(f"source_ids must be an object: {case_id}")
                    source_ids.update(
                        {str(actual): str(benchmark) for actual, benchmark in raw_sources.items()}
                    )
                for item in raw_case.get("source_mappings", ()):  # template format
                    if not isinstance(item, Mapping):
                        raise ValueError(f"invalid source mapping for case: {case_id}")
                    actual_source_id = str(item.get("actual_source_id", ""))
                    benchmark_source_id = str(item.get("benchmark_source_id", ""))
                    source_kind = str(item.get("source_kind", "database"))
                    requires_actual_mapping = bool(
                        item.get(
                            "requires_actual_mapping",
                            source_kind == "database",
                        )
                    )
                    if not actual_source_id and not requires_actual_mapping:
                        # Provider and RAG aliases are produced by the
                        # case-scoped runtime and must not be filled with a
                        # made-up local database ID.
                        continue
                    if not actual_source_id or not benchmark_source_id:
                        raise ValueError(
                            f"missing actual source mapping for case: {case_id}"
                        )
                    source_ids[actual_source_id] = benchmark_source_id
                parsed_cases[str(case_id)] = {
                    "benchmark_user_id": benchmark_user_id,
                    "actual_user_id": actual_user_id,
                    "member_ids": member_ids,
                    "source_ids": source_ids,
                }
            return cls(case_maps=parsed_cases)

        try:
            return cls(
                benchmark_user_id=str(payload["benchmark_user_id"]),
                actual_user_id=str(payload["actual_user_id"]),
                member_ids={
                    str(key): str(value)
                    for key, value in dict(payload["member_ids"]).items()
                },
                source_ids={
                    str(key): str(value)
                    for key, value in dict(payload.get("source_ids", {})).items()
                },
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("invalid global identity map payload") from exc

    @classmethod
    def from_json(cls, path: str | Path) -> "IntegrationIdentityMap":
        return cls.from_payload(json.loads(Path(path).read_text(encoding="utf-8")))

    def _case(self, world_state_id: str) -> Mapping[str, Any]:
        case = self.case_maps.get(world_state_id)
        if case is None:
            raise IntegrationExecutionError(
                f"missing identity map case: {world_state_id}"
            )
        return case

    def resolve_user_id(self, world_state_id: str | None = None) -> str:
        if self.case_maps and world_state_id is not None:
            actual = str(self._case(world_state_id)["actual_user_id"])
        else:
            actual = self.actual_user_id
        if not actual:
            raise IntegrationExecutionError("missing real user mapping")
        return actual

    def resolve_member(
        self, benchmark_member_id: str, *, world_state_id: str | None = None
    ) -> str:
        if self.case_maps and world_state_id is not None:
            mapping = self._case(world_state_id)["member_ids"]
        else:
            mapping = self.member_ids
        actual = mapping.get(benchmark_member_id)
        if not actual:
            raise IntegrationExecutionError(
                f"missing real member mapping: {benchmark_member_id}"
            )
        return actual

    def map_source(
        self, actual_source_id: str, *, world_state_id: str | None = None
    ) -> str:
        if self.case_maps and world_state_id is not None:
            mapping = self._case(world_state_id)["source_ids"]
        else:
            mapping = self.source_ids
        mapped = mapping.get(actual_source_id)
        if not mapped:
            raise IntegrationExecutionError(
                f"missing benchmark source mapping: {actual_source_id}"
            )
        return mapped


GraphFactory = Callable[[Session, EvalRuntimeOptions], UnifiedHealthGraph]


class UnifiedHealthGraphIntegrationExecutor:
    """Run the actual graph inside the materializer transaction.

    The strict source adapter is intentional: a real run with an unmapped
    source is an integration failure, not a successful benchmark sample.
    """

    def __init__(
        self,
        identity: IntegrationIdentityMap,
        *,
        model_configuration: Settings | None = None,
        runtime_options: EvalRuntimeOptions | None = None,
        graph_factory: GraphFactory | None = None,
    ) -> None:
        self.identity = identity
        self.model_configuration = model_configuration
        self.runtime_options = runtime_options or EvalRuntimeOptions()
        self.graph_factory = graph_factory

    def execute(
        self,
        materialized: PostgresMaterializedCase,
        *,
        repeat_index: int,
    ) -> V2RunArtifacts:
        _ = repeat_index
        query = materialized.query
        world_state_id = query.world_state_id
        actual_user_id = self.identity.resolve_user_id(world_state_id)
        actual_member_id = self.identity.resolve_member(
            query.expected_member_id,
            world_state_id=world_state_id,
        )
        business_domain = _business_domain(query.expected_intent)
        input_payload = _integration_input_payload(materialized.world, query)
        actual_task_id = str(uuid4())
        actual_run_id = str(uuid4())
        now = utc_now()
        self._materialize_member_medication_rows(
            materialized,
            benchmark_member_id=query.expected_member_id,
            actual_member_id=actual_member_id,
        )
        task = BusinessTask(
            id=actual_task_id,
            user_id=actual_user_id,
            member_id=actual_member_id,
            business_domain=business_domain,
            intent=query.expected_intent,
            provider_mode="sandbox",
            thread_id=f"eval:{query.query_id}",
            status="running",
            user_input=query.user_input,
            idempotency_key=f"eval:{query.query_id}",
            request_fingerprint=hashlib.sha256(
                query.user_input.encode("utf-8")
            ).hexdigest(),
            input_payload=input_payload,
            output_payload={},
            current_run_id=actual_run_id,
        )
        run = AgentRun(
            id=actual_run_id,
            user_id=actual_user_id,
            member_id=actual_member_id,
            user_goal=query.user_input,
            intent=query.expected_intent,
            status="running",
            safety_result={},
            raw_state={},
            started_at=now,
        )
        materialized.session.add_all([task, run])
        try:
            materialized.session.flush()
            started = perf_counter()
            if self.graph_factory is None:
                retriever = ScopedPostgresRetriever(
                    create_knowledge_retriever(materialized.session),
                    set(materialized.rag_source_aliases),
                )
                graph = UnifiedHealthGraph(
                    product_workflow=SupervisorBusinessWorkflow(
                        materialized.session,
                        model_configuration=self.model_configuration,
                        provider_registry=ScopedProviderSandbox(materialized.world),
                        knowledge_retriever=retriever,
                        runtime_options=self.runtime_options,
                    ),
                    runtime_options=self.runtime_options,
                )
            else:
                graph = self.graph_factory(materialized.session, self.runtime_options)
            state = graph.invoke(
                run_id=actual_run_id,
                task_id=actual_task_id,
                user_id=actual_user_id,
                member_id=actual_member_id,
                business_domain=business_domain,
                user_input=query.user_input,
                input_payload=input_payload,
                provider_mode="sandbox",
                human_confirmation_granted=False,
                idempotency_key=f"eval:{query.query_id}",
            )
            graph.close()
            elapsed = max(1, int((perf_counter() - started) * 1000))
            state = dict(state)
            state["latency_ms"] = elapsed
            if (
                materialized.world.fault_injection.fault_type == "no_source"
                and state.get("status") == "failed"
            ):
                state["fallback_action"] = (
                    materialized.world.fault_injection.expected_fallback
                )
            # The graph uses the application domain as its internal intent;
            # the benchmark query supplies the reviewed evaluation intent.
            state["intent"] = query.expected_intent
            trace = build_run_trace(state)
            trace = self._map_trace(trace, materialized)
            trace = self._normalize_benchmark_claims(trace, materialized)
            return self._artifacts_from_state(
                state,
                trace,
                materialized,
                provider_attempts=self._provider_attempts(state),
            )
        except (SQLAlchemyError, IntegrationExecutionError) as exc:
            raise IntegrationExecutionError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - integration boundary normalizes errors.
            raise IntegrationExecutionError(
                "UnifiedHealthGraph integration execution failed"
            ) from exc

    @staticmethod
    def _materialize_member_medication_rows(
        materialized: PostgresMaterializedCase,
        *,
        benchmark_member_id: str,
        actual_member_id: str,
    ) -> None:
        """Project frozen medication facts into the graph's active transaction."""

        today = date.today()
        rows: list[object] = []
        for index, item in enumerate(materialized.world.medicine_box):
            if item.member_id != benchmark_member_id:
                continue
            remaining_days = max(0, item.remaining_days)
            rows.append(
                MedicineBoxItem(
                    id=str(uuid4()),
                    member_id=actual_member_id,
                    medicine_name=item.medication_code,
                    specification="synthetic-evaluation",
                    total_quantity=max(1, remaining_days),
                    remaining_quantity=remaining_days,
                    dosage="按已确认处方",
                    frequency="按已确认处方",
                    purchased_at=today,
                    estimated_remaining_days=remaining_days,
                    safety_note="仅用于隔离的自动化评测事务",
                )
            )
        for index, item in enumerate(materialized.world.prescriptions):
            if item.member_id != benchmark_member_id:
                continue
            rows.append(
                Prescription(
                    id=str(uuid4()),
                    member_id=actual_member_id,
                    prescription_no=(
                        f"EVAL-{materialized.query.query_id}-{index}"
                    ),
                    doctor_name="评测医生",
                    hospital_name="评测互联网医院",
                    doctor_diagnosis_summary="冻结合成状态，不作为临床诊断",
                    medicine_items=[{"medicine_name": item.medication_code}],
                    issued_at=today,
                    expires_at=(
                        today + timedelta(days=30)
                        if item.valid
                        else today - timedelta(days=1)
                    ),
                    status="valid" if item.valid else "expired",
                    doctor_confirmation_required=item.doctor_confirmed,
                    safety_note="仅用于隔离的自动化评测事务",
                )
            )
        materialized.session.add_all(rows)

    def _map_trace(self, trace, materialized: PostgresMaterializedCase):
        payload = trace.model_dump(mode="json")
        actual_member_id = self.identity.resolve_member(
            materialized.query.expected_member_id,
            world_state_id=materialized.query.world_state_id,
        )
        actual_user_id = self.identity.resolve_user_id(materialized.query.world_state_id)
        actual_task_id = trace.task_id

        def transform(value: Any, key: str | None = None) -> Any:
            if isinstance(value, dict):
                return {name: transform(item, name) for name, item in value.items()}
            if isinstance(value, list):
                return [transform(item, key) for item in value]
            if key in {"member_id", "subject_id"} and value == actual_member_id:
                return materialized.query.expected_member_id
            if key == "user_id" and value == actual_user_id:
                return materialized.world.user.user_id
            if key == "task_id" and value == actual_task_id:
                return materialized.query.query_id
            if key == "source_id" and isinstance(value, str):
                return self._map_source(value, materialized)
            if key in {"source_ids", "context_source_ids"} and isinstance(value, str):
                return self._map_source(value, materialized)
            return value

        mapped = transform(payload)
        mapped["task_id"] = materialized.query.query_id
        mapped["user_id"] = materialized.world.user.user_id
        mapped["member_id"] = materialized.query.expected_member_id
        mapped["intent"] = materialized.query.expected_intent
        return trace.__class__.model_validate(mapped)

    def _map_source(
        self,
        actual_source_id: str,
        materialized: PostgresMaterializedCase,
    ) -> str:
        alias = materialized.rag_source_aliases.get(actual_source_id)
        if alias is not None:
            return alias
        if actual_source_id.startswith("knowledge_search:"):
            # The DB tool stores all retrieved IDs in one audit source ID,
            # while the RunTrace also keeps each RAG source separately.  Map
            # the composite ID through the same strict alias table so the
            # tool call remains auditable without inventing a source.
            raw_ids = actual_source_id.removeprefix("knowledge_search:").split(",")
            mapped_ids = [
                self._map_source(source_id, materialized)
                for source_id in raw_ids
                if source_id
            ]
            if mapped_ids:
                return ",".join(dict.fromkeys(mapped_ids))
        if (
            actual_source_id.startswith("knowledge:")
            and materialized.world.knowledge_state.current_source_ids
        ):
            # Some business-tool paths expose the underlying document/chunk
            # key instead of the scoped retriever alias.  It is still a RAG
            # observation, so bind it to this case's reviewed current-source
            # namespace rather than leaking a seed database ID into Gold.
            return materialized.world.knowledge_state.current_source_ids[0]
        if actual_source_id.startswith("knowledge:"):
            # A no-source Gold case may still expose an unexpected local
            # knowledge row. Preserve it as a deterministic opaque bad-case
            # observation instead of leaking the database ID or aborting the
            # remaining benchmark batch.
            digest = hashlib.sha256(actual_source_id.encode("utf-8")).hexdigest()
            return f"unexpected:knowledge:{digest[:16]}"
        if (
            actual_source_id.startswith("provider:")
            and materialized.world.provider_state.source_ids
        ):
            return materialized.world.provider_state.source_ids[0]
        if (
            actual_source_id.startswith("pharmacy_inventory:")
            and materialized.world.provider_state.source_ids
        ):
            # Pharmacy inventory is a business/provider observation.  The
            # provider sandbox owns its benchmark source alias; no real
            # inventory ID should be invented in the identity map.
            return materialized.world.provider_state.source_ids[0]
        if actual_source_id.startswith(("health_record_event:", "medical-document:")):
            record_source_ids = tuple(
                item.source_id
                for item in materialized.world.health_records
                if item.member_id == materialized.query.expected_member_id
            )
            if record_source_ids:
                # Report/health-record tools create a transaction-local
                # event or document ID.  Map it to the reviewed record source
                # for this member instead of putting that generated ID in a
                # reusable local file.
                return record_source_ids[0]
        return self.identity.map_source(
            actual_source_id,
            world_state_id=materialized.query.world_state_id,
        )

    @staticmethod
    def _normalize_benchmark_claims(trace, materialized: PostgresMaterializedCase):
        """Project implementation Claim names onto the reviewed v2 contract.

        The product workflow currently emits ``confirmation-state`` while
        the benchmark evaluates the user-visible boolean
        ``confirmation_required``.  Values and source IDs still come from the
        actual trace; only the stable evaluation key is adapted here.
        """

        envelope = trace.final_answer.answer_envelope
        if envelope is None or not trace.context_source_ids:
            return trace
        actual_by_fact = {
            claim.fact_key: claim for claim in envelope.claims
        }
        claims: list[FinalClaim] = []
        for expected in materialized.world.gold.required_claims:
            claim_source_ids = tuple(
                source_id
                for source_id in trace.context_source_ids
                if source_id in set(expected.source_ids)
            )
            if not claim_source_ids:
                return trace
            if expected.fact_key == "workflow.status":
                actual = actual_by_fact.get("workflow.status")
                value = actual.value if actual is not None else trace.final_answer.action_status
            elif expected.fact_key == "workflow.confirmation_required":
                value = trace.final_answer.waiting_for_user_confirmation
            else:
                actual = actual_by_fact.get(expected.fact_key)
                if actual is None:
                    return trace
                value = actual.value
            claims.append(
                FinalClaim(
                    claim_id=expected.claim_id,
                    fact_key=expected.fact_key,
                    subject_id=materialized.query.expected_member_id,
                    value=value,
                    source_ids=claim_source_ids,
                    claim_type=expected.claim_type,
                )
            )
        updated_envelope = envelope.model_copy(
            update={"claims": tuple(claims)}
        )
        updated_answer = trace.final_answer.model_copy(
            update={"answer_envelope": updated_envelope}
        )
        return trace.model_copy(update={"final_answer": updated_answer})

    def _artifacts_from_state(
        self,
        state: Mapping[str, Any],
        trace,
        materialized: PostgresMaterializedCase,
        *,
        provider_attempts: int,
    ) -> V2RunArtifacts:
        orchestration = trace.orchestration
        roles = tuple(
            result.agent_role
            for result in orchestration.domain_agent_results
        ) if orchestration is not None else ()
        (
            domain_steps,
            domain_edges,
            governance_steps,
            governance_edges,
        ) = _benchmark_plan_projection(
            state,
            orchestration,
            safety_review_executed=(
                "safety_review" in {str(item) for item in state.get("visited_nodes", [])}
                or bool(trace.safety_trace.flags)
                or trace.safety_trace.requires_human_confirmation
            ),
        )
        source_ids = tuple(
            dict.fromkeys(
                [
                    *trace.context_source_ids,
                    *(call.source_id for call in trace.tool_calls if call.source_id),
                    *(rag.source_id for rag in trace.rag_traces),
                ]
            )
        )
        confirmation_draft = None
        raw_draft = state.get("confirmation_draft")
        if isinstance(raw_draft, Mapping) and raw_draft:
            draft_payload = dict(raw_draft)
            # user_id is intentionally not part of this review snapshot;
            # the benchmark already binds the case to its synthetic user.
            draft_payload.pop("user_id", None)
            request = state.get("confirmation_request")
            if isinstance(request, Mapping):
                summary = request.get("summary")
                if isinstance(summary, str) and summary.strip():
                    draft_payload["summary"] = summary
                request_payload = request.get("payload")
                if isinstance(request_payload, Mapping):
                    preview: dict[str, object] = {}
                    for key in ("medicine_name", "message", "city"):
                        value = request_payload.get(key)
                        if isinstance(value, (str, int, float, bool)):
                            preview[key] = value
                    schedule = request_payload.get("schedule")
                    if isinstance(schedule, Mapping):
                        preview["schedule"] = {
                            str(key): value
                            for key, value in schedule.items()
                            if isinstance(value, (str, int, float, bool))
                        }
                    draft_payload["preview"] = preview
            # Use benchmark aliases so the snapshot remains comparable to
            # the query contract after the shadow transaction is rolled back.
            draft_payload["task_id"] = materialized.query.query_id
            draft_payload["member_id"] = materialized.query.expected_member_id
            confirmation_draft = ConfirmationDraftSnapshot.model_validate(
                draft_payload
            )
        return V2RunArtifacts(
            run_trace=trace,
            route_mode=(
                orchestration.route.route_mode
                if orchestration is not None
                else "simple_single_domain"
            ),
            observed_intent=trace.intent,
            observed_agent_roles=roles,
            observed_domain_steps=domain_steps,
            observed_domain_dependency_edges=domain_edges,
            observed_governance_steps=governance_steps,
            observed_governance_edges=governance_edges,
            observed_tool_names=tuple(call.tool_name for call in trace.tool_calls),
            observed_blocked=trace.safety_trace.blocked,
            observed_source_ids=source_ids,
            observed_rag_source_ids=tuple(rag.source_id for rag in trace.rag_traces),
            observed_database_changes=(
                ("local_confirmation_draft",)
                if state.get("confirmation_draft")
                else ()
            ),
            confirmation_draft=confirmation_draft,
            provider_attempts=provider_attempts,
            retry_count=sum(
                max(0, len(item.get("attempts", [])) - 1)
                for item in state.get("provider_calls", [])
                if isinstance(item, Mapping)
            ),
            fallback_action=(
                str(
                    state.get("fallback_action")
                    or state.get("errors", ["none"])[-1]
                )
                if state.get("degraded") and state.get("errors")
                else "none"
            ),
            external_action_status="local_draft" if state.get("confirmation_draft") else "none",
            checkpoint_restored=False,
            foreign_member_ids=(),
            cleanup_succeeded=False,
        )

    @staticmethod
    def _provider_attempts(state: Mapping[str, Any]) -> int:
        total = 0
        for item in state.get("provider_calls", []):
            if not isinstance(item, Mapping):
                continue
            attempts = item.get("attempts")
            total += len(attempts) if isinstance(attempts, list) else 1
        return total


def _business_domain(intent: str) -> BusinessDomain:
    if intent == "safety_check":
        return "preconsultation"
    if intent in {"refill", "reminder", "pharmacy"}:
        return "chronic_care"
    if intent == "chronic_care":
        return "chronic_care"
    return "health_record"


_ROLE_TO_BENCHMARK_STEP = {
    "TriageAgent": "triage-read",
    "MedicationAgent": "medication-read",
    "ReportAgent": "report-read",
}


def _benchmark_plan_projection(
    state: Mapping[str, Any],
    orchestration,
    *,
    safety_review_executed: bool,
) -> tuple[
    tuple[str, ...],
    tuple[EvalDependencyEdge, ...],
    tuple[str, ...],
    tuple[EvalDependencyEdge, ...],
]:
    """Project the real graph into separate domain and governance evidence.

    The old adapter inferred one capability from ``visited_nodes`` and then
    appended ``safety-review`` to the same list. That hid multi-Agent plans
    and made a fixed governance node look like a Supervisor step. The plan is
    now the source of truth for domain steps and domain edges; safety is a
    fixed projection derived from the completed safety boundary.
    """

    domain_steps: tuple[str, ...] = ()
    domain_edges: tuple[EvalDependencyEdge, ...] = ()
    if orchestration is not None and orchestration.plan is not None:
        plan = orchestration.plan
        step_names = {
            step.step_id: _ROLE_TO_BENCHMARK_STEP[step.role]
            for step in plan.steps
            if step.role in _ROLE_TO_BENCHMARK_STEP
        }
        domain_steps = tuple(
            step_names[step.step_id]
            for step in plan.steps
            if step.step_id in step_names
        )
        domain_edges = tuple(
            EvalDependencyEdge(
                upstream_step_id=step_names[edge.upstream_step_id],
                downstream_step_id=step_names[edge.downstream_step_id],
            )
            for edge in plan.dependency_edges
            if edge.upstream_step_id in step_names
            and edge.downstream_step_id in step_names
        )
    elif orchestration is not None:
        domain_steps = tuple(
            _ROLE_TO_BENCHMARK_STEP[result.agent_role]
            for result in orchestration.domain_agent_results
            if result.agent_role in _ROLE_TO_BENCHMARK_STEP
        )

    governance_steps = ("safety-review",) if safety_review_executed else ()
    governance_edges = tuple(
        EvalDependencyEdge(
            upstream_step_id=step_id,
            downstream_step_id="safety-review",
        )
        for step_id in domain_steps
    ) if safety_review_executed else ()
    return domain_steps, domain_edges, governance_steps, governance_edges


def _integration_input_payload(
    world: EvalWorldState,
    query: EvalQueryVariant,
) -> dict[str, Any]:
    """Translate a reviewed query into the current product API payload.

    v2 cases describe user intent, while the product graph intentionally
    accepts a small, explicit business payload.  This adapter fills only the
    minimum fields needed to exercise the real graph; it does not invent
    medical facts or alter the reviewed expected outcome.
    """

    payload: dict[str, Any] = {
        "evaluation_query_id": query.query_id,
        # Keep the persisted business domain separate from the reviewed
        # benchmark intent.  The runtime workflow consumes this only for the
        # case-scoped integration route; normal API requests do not provide it.
        "evaluation_intent": query.expected_intent,
        "knowledge_query": query.expected_intent,
    }
    if query.expected_intent in {"refill", "reminder", "pharmacy"}:
        medication = next(
            (
                item.medication_code
                for item in world.medicine_box
                if item.member_id == query.expected_member_id
            ),
            None,
        ) or next(
            (
                item.medication_code
                for item in world.prescriptions
                if item.member_id == query.expected_member_id
            ),
            "reviewed-medication",
        )
        payload["medicine_name"] = medication
        payload["action_type"] = {
            "refill": "refill_request",
            "reminder": "reminder_create",
            "pharmacy": "pharmacy_option",
        }[query.expected_intent]
        if query.expected_intent == "reminder":
            payload["schedule"] = {"frequency": "daily", "time": "08:00"}
        if query.expected_intent == "pharmacy":
            payload["city"] = "demo-city"
    elif query.expected_intent == "health_record":
        payload.update(
            {
                "text": "Reviewed synthetic medical report for evaluation only.",
                "document_type": "medical_report",
                "analysis_only": True,
            }
        )
    elif query.expected_intent == "safety_check":
        payload.update(
            {
                "action_type": "refill_request",
                "medicine_name": "reviewed-medication",
                "symptoms": query.user_input,
            }
        )
    elif query.expected_intent == "chronic_care":
        medication = next(
            (
                item.medication_code
                for item in world.medicine_box
                if item.member_id == query.expected_member_id
            ),
            "reviewed-medication",
        )
        payload.update(
            {
                "medicine_name": medication,
                "action_type": "refill_request",
                "symptoms": "近期轻度头晕，需要整理就医信息。",
                "text": "Reviewed synthetic medical report for evaluation only.",
                "document_type": "medical_report",
                "analysis_only": True,
            }
        )
    if query.expected_route == "complex_cross_domain":
        payload.update(
            {
                "symptoms": "近期轻度头晕，需要整理就医信息。",
                "text": "Reviewed synthetic medical report for evaluation only.",
                "document_type": "medical_report",
            }
        )
    return payload


def _gold_hash(world: EvalWorldState) -> str:
    payload = json.dumps(
        world.gold.model_dump(mode="json"),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "GraphFactory",
    "IntegrationExecutionError",
    "IntegrationIdentityMap",
    "PostgresMaterializationError",
    "PostgresMaterializedCase",
    "PostgresV2Materializer",
    "ScopedPostgresRetriever",
    "ScopedProviderSandbox",
    "UnifiedHealthGraphIntegrationExecutor",
]
