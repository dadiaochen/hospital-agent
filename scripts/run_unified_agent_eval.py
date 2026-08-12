"""Run all unified Agent queries through the evaluation Harness."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.agent.unified_eval_dataset import load_unified_agent_benchmark  # noqa: E402
from app.agent.v2_eval_runner import (  # noqa: E402
    SyntheticProjectionExecutor,
    V2EvalRunner,
)
from app.agent.v2_eval_schemas import V2RunnerOptions  # noqa: E402
from app.agent.v2_integration import (  # noqa: E402
    IntegrationIdentityMap,
    PostgresV2Materializer,
    UnifiedHealthGraphIntegrationExecutor,
)
from app.core.config import Settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("integration", "projection"),
        default="integration",
    )
    parser.add_argument("--identity-map", type=Path)
    parser.add_argument("--max-cases", type=int, default=None)
    parser.add_argument(
        "--split",
        choices=("all", "development", "validation", "holdout"),
        default="all",
    )
    parser.add_argument(
        "--real-model",
        action="store_true",
        help="Use configured paid model; default integration mode uses deterministic provider.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        choices=range(1, 17),
        metavar="1-16",
        help=(
            "Bounded parallel Query groups; every integration Query keeps its "
            "own PostgreSQL transaction and deterministic report order."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(
            "output/benchmarks/evaluation_runs/unified-agent-400-20260812"
        ),
    )
    args = parser.parse_args()

    runner_mode = "synthetic_projection"
    if args.mode == "projection":
        runner = V2EvalRunner(
            project_root=PROJECT_ROOT,
            executor=SyntheticProjectionExecutor(),
            dataset_loader=load_unified_agent_benchmark,
        )
    else:
        if args.identity_map is None:
            parser.error("--identity-map is required in integration mode")
        identity = IntegrationIdentityMap.from_json(args.identity_map)
        configuration = None
        if not args.real_model:
            configuration = Settings(
                model_provider="deterministic",
                model_name="deterministic-local",
                model_api_base=None,
                model_api_key=None,
            )
        runner = V2EvalRunner(
            project_root=PROJECT_ROOT,
            materializer=PostgresV2Materializer(SessionLocal),
            executor=UnifiedHealthGraphIntegrationExecutor(
                identity,
                model_configuration=configuration,
            ),
            dataset_loader=load_unified_agent_benchmark,
        )
        runner_mode = "integration"

    report = runner.run(
        V2RunnerOptions(
            runner_mode=runner_mode,
            dataset_split=args.split,
            max_cases=args.max_cases,
            concurrency=args.concurrency,
            allow_pending_review=True,
        )
    )
    json_path, markdown_path = runner.write_report(
        report,
        output_dir=args.output_dir,
    )
    print(f"json: {json_path}")
    print(f"markdown: {markdown_path}")
    print(f"status: {report.status}; samples: {report.sample_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
