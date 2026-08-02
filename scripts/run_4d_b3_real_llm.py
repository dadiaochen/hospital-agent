"""Run the optional 4D-B3 real-LLM benchmark.

Without ``--live`` this command is a readiness check and sends no request.
Without a complete OpenAI-compatible configuration it writes a blocked report
with N/A metrics instead of failing the deterministic project path.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.agent.real_llm_benchmark import RealLLMBenchmarkRunner  # noqa: E402
from app.agent.v2_eval_schemas import V2RunnerOptions  # noqa: E402
from app.agent.v2_integration import IntegrationIdentityMap  # noqa: E402


def _load_identity_map(path: Path | None) -> IntegrationIdentityMap | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return IntegrationIdentityMap(
        benchmark_user_id=str(payload["benchmark_user_id"]),
        actual_user_id=str(payload["actual_user_id"]),
        member_ids={
            str(key): str(value) for key, value in payload["member_ids"].items()
        },
        source_ids={
            str(key): str(value)
            for key, value in payload.get("source_ids", {}).items()
        },
    )


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
        "--repeat",
        type=int,
        default=1,
        choices=(1, 2, 3),
        help="Repeat each fixed case at most three times for local variance observation.",
    )
    parser.add_argument(
        "--split",
        choices=("all", "development", "validation", "holdout"),
        default="development",
    )
    parser.add_argument("--allow-pending-review", action="store_true")
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
    report = runner.run(
        V2RunnerOptions(
            runner_mode="integration",
            dataset_split=args.split,
            max_cases=args.max_cases,
            repeat=args.repeat,
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
