"""Run the optional 4D-B3 real-LLM benchmark.

Without ``--live`` this command is a readiness check and sends no request.
Without a complete OpenAI-compatible configuration it writes a blocked report
with N/A metrics instead of failing the deterministic project path.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.agent.real_llm_benchmark import RealLLMBenchmarkRunner  # noqa: E402
from app.agent.unified_eval_dataset import load_unified_agent_benchmark  # noqa: E402
from app.agent.v2_eval_schemas import V2RunnerOptions  # noqa: E402
from app.agent.v2_integration import IntegrationIdentityMap  # noqa: E402


def _load_identity_map(path: Path | None) -> IntegrationIdentityMap | None:
    if path is None:
        return None
    return IntegrationIdentityMap.from_json(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually call the configured model; without it no network request is sent.",
    )
    parser.add_argument(
        "--require-live",
        action="store_true",
        help="Return exit code 2 when the real experiment cannot run.",
    )
    parser.add_argument("--identity-map", type=Path)
    parser.add_argument(
        "--max-cases",
        type=int,
        default=1,
        help="Keep the first live run small; increase only after reviewing results.",
    )
    parser.add_argument(
        "--query-offset",
        type=int,
        default=0,
        help="Skip this many queries within the selected split before max-cases.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        choices=(1, 2, 3),
        help="Repeat each fixed case at most three times for local variance observation.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        choices=range(1, 17),
        metavar="1-16",
        help=(
            "Bounded parallel Query groups. Each Query still uses an isolated "
            "PostgreSQL transaction; reports remain in dataset order."
        ),
    )
    parser.add_argument(
        "--split",
        choices=("all", "development", "validation", "holdout"),
        default="development",
    )
    parser.add_argument(
        "--allow-pending-review",
        action="store_true",
        help="Legacy v2 fixture compatibility only; the active fast-400 dataset uses automatic Gold scoring.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/benchmarks/4d-b3-real-llm"),
    )
    args = parser.parse_args()

    runner = RealLLMBenchmarkRunner(
        project_root=PROJECT_ROOT,
        identity_map=_load_identity_map(args.identity_map),
    )
    if args.query_offset < 0:
        parser.error("--query-offset must be non-negative")
    _, unified_queries, _ = load_unified_agent_benchmark(project_root=PROJECT_ROOT)
    split_queries = [
        query
        for query in unified_queries.queries
        if args.split == "all" or query.dataset_split == args.split
    ]
    selected_queries = split_queries[args.query_offset :]
    if args.max_cases is not None:
        selected_queries = selected_queries[: args.max_cases]
    if not selected_queries:
        parser.error("the selected split and query offset contain no queries")
    report = runner.run(
        V2RunnerOptions(
            runner_mode="integration",
            dataset_split=args.split,
            query_ids=tuple(query.query_id for query in selected_queries),
            repeat=args.repeat,
            concurrency=args.concurrency,
            allow_pending_review=args.allow_pending_review,
        ),
        live=args.live,
    )
    json_path, markdown_path = runner.write_report(
        report,
        output_dir=args.output_dir,
    )
    print(f"json: {json_path}")
    print(f"markdown: {markdown_path}")
    print(f"review_queue: {args.output_dir / 'badcase_review_queue.4d-b3.json'}")
    print(f"status: {report.status}; samples: {report.sample_count}")
    if args.require_live and report.status == "blocked":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
