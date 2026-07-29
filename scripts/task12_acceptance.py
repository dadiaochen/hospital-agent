"""Run the 4B Task 12 acceptance checks against a real local stack.

This is an operator-facing smoke test, not application business logic. It does
not call an LLM or bypass the HTTP boundary for business operations. The small
database queries are read-only checks that prove the Docker migration, seed,
pgvector, checkpoint, and confirmation state are actually available.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import httpx
from redis import from_url
from sqlalchemy import create_engine, inspect, text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402


class AcceptanceReport:
    def __init__(self, *, mode: str, base_url: str) -> None:
        self.mode = mode
        self.base_url = base_url.rstrip("/")
        self.started_at = datetime.now(timezone.utc)
        self.checks: list[dict[str, Any]] = []
        self.latencies_ms: list[float] = []

    def check(
        self,
        name: str,
        passed: bool,
        detail: str,
        *,
        skipped: bool = False,
    ) -> None:
        self.checks.append(
            {
                "name": name,
                "status": "SKIP" if skipped else ("PASS" if passed else "FAIL"),
                "detail": detail,
            }
        )

    def http_latency(self, value: float) -> None:
        self.latencies_ms.append(value)

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [item for item in self.checks if item["status"] == "FAIL"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "task": "4B-12 PostgreSQL/Redis/Docker backend acceptance",
            "mode": self.mode,
            "base_url": self.base_url,
            "started_at": self.started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "checks": self.checks,
            "summary": {
                "passed": sum(item["status"] == "PASS" for item in self.checks),
                "failed": sum(item["status"] == "FAIL" for item in self.checks),
                "skipped": sum(item["status"] == "SKIP" for item in self.checks),
                "p95_wall_clock_ms": _p95(self.latencies_ms),
                "sample_count": len(self.latencies_ms),
            },
        }


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) * 0.95) + 0.9999) - 1))
    return round(ordered[index], 2)


def _safe_detail(message: str) -> str:
    """Keep report details useful without printing credentials or task content."""

    for secret in (settings.database_url, settings.redis_url, settings.model_api_key):
        if secret:
            message = message.replace(secret, "<redacted>")
    return message[:500]


def _request(
    client: httpx.Client,
    report: AcceptanceReport,
    method: str,
    path: str,
    **kwargs: Any,
) -> httpx.Response:
    started = time.perf_counter()
    response = client.request(method, path, **kwargs)
    elapsed = (time.perf_counter() - started) * 1000
    report.http_latency(elapsed)
    return response


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _run_module(module: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(BACKEND_ROOT)
    project_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    python_executable = str(project_python) if project_python.exists() else sys.executable
    return subprocess.run(
        [python_executable, "-m", module],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _database_checks(report: AcceptanceReport, *, require_vector: bool) -> None:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            dialect = connection.dialect.name
            report.check(
                "postgresql_dialect",
                dialect == "postgresql",
                f"SQLAlchemy dialect={dialect}",
            )
            if dialect != "postgresql":
                return

            version = connection.scalar(text("SELECT version_num FROM alembic_version"))
            report.check(
                "alembic_head",
                version == "0007_task_checkpoint_state",
                f"alembic_version={version}",
            )
            table_names = set(inspect(connection).get_table_names())
            required_tables = {
                "users",
                "family_members",
                "knowledge_documents",
                "knowledge_chunks",
                "business_tasks",
                "task_checkpoints",
                "task_confirmation_records",
            }
            missing = sorted(required_tables - table_names)
            report.check(
                "required_tables",
                not missing,
                "all required tables exist" if not missing else f"missing={missing}",
            )

            user_count = int(connection.scalar(text("SELECT count(*) FROM users")) or 0)
            member_count = int(
                connection.scalar(text("SELECT count(*) FROM family_members")) or 0
            )
            knowledge_count = int(
                connection.scalar(text("SELECT count(*) FROM knowledge_chunks")) or 0
            )
            report.check(
                "seed_data",
                user_count > 0 and member_count >= 2 and knowledge_count > 0,
                f"users={user_count}, members={member_count}, knowledge_chunks={knowledge_count}",
            )

            extension = connection.scalar(
                text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            )
            report.check("pgvector_extension", extension == 1, "vector extension is installed")

            vector_count = int(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM knowledge_chunks "
                        "WHERE embedding IS NOT NULL"
                    )
                )
                or 0
            )
            vector_dimension: int | None = None
            if vector_count:
                vector_dimension = int(
                    connection.scalar(
                        text(
                            "SELECT vector_dims(embedding) FROM knowledge_chunks "
                            "WHERE embedding IS NOT NULL LIMIT 1"
                        )
                    )
                )
            vector_ok = vector_count > 0 and vector_dimension == settings.rag_embedding_dimensions
            report.check(
                "rag_vector_index_data",
                vector_ok if require_vector else True,
                f"indexed_chunks={vector_count}, dimension={vector_dimension}, "
                f"configured_dimension={settings.rag_embedding_dimensions}",
                skipped=not require_vector,
            )
    except Exception as exc:
        report.check("postgresql_connectivity", False, _safe_detail(repr(exc)))
    finally:
        engine.dispose()


def _redis_check(report: AcceptanceReport, *, expect_down: bool) -> bool:
    client = from_url(settings.redis_url, decode_responses=True)
    key = "family-health:task12:acceptance-probe"
    try:
        client.ping()
        if expect_down:
            report.check("redis_failure_detection", False, "Redis is still reachable")
            return False
        client.set(key, "ok", ex=15)
        ttl = int(client.ttl(key))
        report.check("redis_ttl_cache", ttl > 0, f"probe TTL={ttl}s")
        client.delete(key)
        return True
    except Exception as exc:
        if expect_down:
            report.check("redis_failure_detection", True, "Redis connection failed as expected")
            return False
        report.check("redis_connectivity", False, _safe_detail(repr(exc)))
        return False


def _get_members(client: httpx.Client, report: AcceptanceReport) -> list[dict[str, Any]]:
    response = _request(client, report, "GET", "/api/family-members")
    payload = _json(response)
    items = payload.get("items", [])
    members = [item for item in items if isinstance(item, dict) and item.get("id")]
    report.check(
        "family_member_seed_api",
        response.status_code == 200 and len(members) >= 2,
        f"status={response.status_code}, member_count={len(members)}",
    )
    return members


def _create_task(
    client: httpx.Client,
    report: AcceptanceReport,
    *,
    domain: str,
    member_id: str,
    key: str,
    input_payload: dict[str, Any],
) -> dict[str, Any]:
    response = _request(
        client,
        report,
        "POST",
        "/api/business-tasks",
        json={
            "business_domain": domain,
            "member_id": member_id,
            "user_input": f"task12 acceptance for {domain}",
            "input_payload": input_payload,
            "idempotency_key": key,
            "provider_mode": "mock",
        },
    )
    payload = _json(response)
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    ok = (
        response.status_code == 201
        and task.get("business_domain") == domain
        and task.get("member_id") == member_id
        and bool(payload.get("run_id"))
    )
    report.check(
        f"business_api_{domain}",
        ok,
        f"status={response.status_code}, state={payload.get('status', 'unknown')}",
    )
    return payload


def _confirm_once(
    base_url: str,
    task_id: str,
    key: str,
    checkpoint_version: int,
    confirmation_version: int,
) -> tuple[int, dict[str, Any], float]:
    started = time.perf_counter()
    with httpx.Client(base_url=base_url, timeout=30, trust_env=False) as client:
        response = client.post(
            f"/api/business-tasks/{task_id}/confirm",
            json={
                "human_confirmation_granted": True,
                "idempotency_key": key,
                "checkpoint_version": checkpoint_version,
                "confirmation_version": confirmation_version,
            },
        )
    return response.status_code, _json(response), (time.perf_counter() - started) * 1000


def _concurrency_check(
    client: httpx.Client,
    report: AcceptanceReport,
    *,
    member_id: str,
    key: str,
) -> None:
    first = _create_task(
        client,
        report,
        domain="chronic_care",
        member_id=member_id,
        key=key,
        input_payload={
            "action_type": "refill_request",
            "medicine_name": "amlodipine",
        },
    )
    task = first.get("task", {})
    task_id = task.get("id")
    if not task_id or first.get("status") != "needs_confirmation":
        report.check("concurrent_confirmation", False, "task did not enter DRAFT state")
        return

    checkpoint_version = int(first.get("checkpoint_version") or 1)
    confirmation_version = int(first.get("confirmation_version") or 1)
    results: list[tuple[int, dict[str, Any], float]] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(
                _confirm_once,
                report.base_url,
                str(task_id),
                key,
                checkpoint_version,
                confirmation_version,
            )
            for _ in range(4)
        ]
        for future in as_completed(futures):
            results.append(future.result())
    report.latencies_ms.extend(item[2] for item in results)

    status_codes = [item[0] for item in results]
    replay_count = sum(
        code == 200 and bool(payload.get("idempotent_replay"))
        for code, payload, _ in results
    )
    first_execution_count = sum(
        code == 200 and not bool(payload.get("idempotent_replay"))
        for code, payload, _ in results
    )
    conflict_count = sum(code == 409 for code in status_codes)
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            execute_count = int(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM task_confirmation_records "
                        "WHERE task_id = :task_id AND action = 'execute'"
                    ),
                    {"task_id": str(task_id)},
                )
                or 0
            )
    finally:
        engine.dispose()

    report.check(
        "concurrent_confirmation",
        first_execution_count == 1
        and execute_count == 1
        and all(code in {200, 409} for code in status_codes),
        f"responses={status_codes}, first_execution={first_execution_count}, "
        f"idempotent_replays={replay_count}, conflicts={conflict_count}, "
        f"execute_records={execute_count}",
    )


def _api_checks(report: AcceptanceReport, *, frontend_url: str, check_frontend: bool) -> None:
    with httpx.Client(base_url=report.base_url, timeout=30, trust_env=False) as client:
        health = _request(client, report, "GET", "/health")
        report.check("backend_health", health.status_code == 200 and _json(health).get("status") == "ok", f"status={health.status_code}")

        members = _get_members(client, report)
        if len(members) < 2:
            return
        member_a = str(members[0]["id"])
        member_b = str(members[1]["id"])
        run_key = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")

        _create_task(
            client,
            report,
            domain="preconsultation",
            member_id=member_b,
            key=f"task12-preconsultation-{run_key}",
            input_payload={"department_keyword": "internal medicine", "symptoms": "follow-up materials"},
        )
        _create_task(
            client,
            report,
            domain="chronic_care",
            member_id=member_a,
            key=f"task12-chronic-care-{run_key}",
            input_payload={"action_type": "refill_request", "medicine_name": "amlodipine"},
        )
        _create_task(
            client,
            report,
            domain="health_record",
            member_id=member_b,
            key=f"task12-health-record-{run_key}",
            input_payload={"text": "follow-up report content for organization", "document_type": "medical_report"},
        )

        search = _request(
            client,
            report,
            "GET",
            "/api/knowledge/search",
            params={"q": "human confirmation", "category": "human_confirmation"},
        )
        search_payload = _json(search)
        items = search_payload.get("items", [])
        report.check(
            "knowledge_search_api",
            search.status_code == 200 and bool(items) and bool(items[0].get("source_id")),
            f"status={search.status_code}, source_count={len(items)}",
        )

        invalid = _request(client, report, "GET", "/api/knowledge/search")
        invalid_payload = _json(invalid)
        report.check(
            "api_validation_error_mapping",
            invalid.status_code == 422 and invalid_payload.get("error", {}).get("code") == "validation_error",
            f"status={invalid.status_code}, code={invalid_payload.get('error', {}).get('code')}",
        )

        if report.mode == "baseline":
            _concurrency_check(
                client,
                report,
                member_id=member_a,
                key=f"task12-concurrency-{run_key}",
            )
        else:
            failure_task = _create_task(
                client,
                report,
                domain="chronic_care",
                member_id=member_a,
                key=f"task12-redis-failure-{run_key}",
                input_payload={"action_type": "refill_request", "medicine_name": "amlodipine"},
            )
            task_id = failure_task.get("task", {}).get("id")
            if task_id:
                confirmed = _request(
                    client,
                    report,
                    "POST",
                    f"/api/business-tasks/{task_id}/confirm",
                    json={
                        "human_confirmation_granted": True,
                        "idempotency_key": f"task12-redis-failure-{run_key}",
                        "checkpoint_version": failure_task.get("checkpoint_version", 1),
                        "confirmation_version": failure_task.get("confirmation_version", 1),
                    },
                )
                confirmed_payload = _json(confirmed)
                report.check(
                    "redis_failure_postgresql_fallback",
                    confirmed.status_code == 200
                    and confirmed_payload.get("status") == "completed"
                    and confirmed_payload.get("checkpoint_source") == "postgresql",
                    f"status={confirmed.status_code}, checkpoint_source={confirmed_payload.get('checkpoint_source')}",
                )

        if check_frontend:
            try:
                started = time.perf_counter()
                frontend = httpx.get(frontend_url, timeout=15, trust_env=False)
                report.http_latency((time.perf_counter() - started) * 1000)
                report.check("frontend_health", frontend.status_code == 200, f"status={frontend.status_code}")
            except Exception as exc:
                report.check("frontend_health", False, _safe_detail(repr(exc)))


def _write_report(report: AcceptanceReport, json_path: Path | None, markdown_path: Path | None) -> None:
    payload = report.as_dict()
    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if markdown_path:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# 4B Task 12 Backend Acceptance",
            "",
            f"- Mode: `{report.mode}`",
            f"- Base URL: `{report.base_url}`",
            f"- Generated: `{payload['finished_at']}`",
            "",
            "| Check | Status | Detail |",
            "| --- | --- | --- |",
        ]
        for item in report.checks:
            lines.append(f"| `{item['name']}` | **{item['status']}** | {item['detail'].replace('|', '/') } |")
        summary = payload["summary"]
        lines.extend(
            [
                "",
                "## Wall-clock",
                "",
                f"- Samples: `{summary['sample_count']}`",
                f"- p95: `{summary['p95_wall_clock_ms']} ms`",
                "",
                "This report is local Docker acceptance evidence. It is not a production SLO, clinical safety claim, or model quality benchmark.",
                "",
            ]
        )
        markdown_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--frontend-url", default="http://localhost:3000")
    parser.add_argument("--mode", choices=("baseline", "redis-failure"), default="baseline")
    parser.add_argument("--skip-seed", action="store_true")
    parser.add_argument("--skip-index", action="store_true")
    parser.add_argument(
        "--require-vector",
        action="store_true",
        help="Fail unless PostgreSQL contains compatible indexed vectors.",
    )
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--json-report", type=Path, default=Path("var/demo/task12_backend_acceptance.json"))
    parser.add_argument("--markdown-report", type=Path, default=Path("var/demo/task12_backend_acceptance.md"))
    args = parser.parse_args()

    report = AcceptanceReport(mode=args.mode, base_url=args.base_url)
    if not args.skip_seed:
        seed = _run_module("scripts.seed")
        report.check(
            "seed_repeatability",
            seed.returncode == 0,
            "idempotent seed completed" if seed.returncode == 0 else _safe_detail(seed.stderr or seed.stdout),
        )

    require_vector = args.require_vector or settings.rag_vector_enabled
    if not args.skip_index and require_vector:
        index = _run_module("scripts.index_knowledge")
        report.check(
            "rag_index_command",
            index.returncode == 0,
            "knowledge index refresh completed" if index.returncode == 0 else _safe_detail(index.stderr or index.stdout),
        )
    elif not require_vector:
        report.check("rag_index_command", True, "RAG_VECTOR_ENABLED=false; keyword fallback mode", skipped=True)

    _database_checks(report, require_vector=require_vector)
    _redis_check(report, expect_down=args.mode == "redis-failure")
    _api_checks(report, frontend_url=args.frontend_url, check_frontend=not args.skip_frontend)
    _write_report(report, args.json_report, args.markdown_report)

    payload = report.as_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
