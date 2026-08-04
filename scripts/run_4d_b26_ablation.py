"""Generate the A/B/C/D ablation report for 4D-B2.6.

The default mode is a deterministic preview. ``--mode integration`` runs the
same four conditions through PostgreSQL shadow transactions and the real
UnifiedHealthGraph, but requires an explicit local identity map.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.agent.v2_ablation import V2AblationRunner  # noqa: E402
from app.agent.v2_eval_runner import V2EvalRunner  # noqa: E402
from app.agent.v2_eval_schemas import V2RunnerOptions  # noqa: E402
from app.agent.v2_integration import (  # noqa: E402
    IntegrationIdentityMap,
    PostgresV2Materializer,
    UnifiedHealthGraphIntegrationExecutor,
)
from app.core.database import SessionLocal  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("synthetic_preview", "integration"),
        default="synthetic_preview",
        help="Use deterministic Gold projection or the real PostgreSQL graph adapter.",
    )
    parser.add_argument(
        "--identity-map",
        type=Path,
        help="Required by integration mode; never commit this machine-local file.",
    )
    parser.add_argument("--max-cases", type=int, default=16)
    parser.add_argument(
        "--split",
        choices=("all", "development", "validation", "holdout"),
        default="development",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/benchmarks/4d-b26-ablation"),
    )
    args = parser.parse_args()

    runner_options = V2RunnerOptions(
        dataset_split=args.split,
        max_cases=args.max_cases,
        allow_pending_review=True,
        runner_mode=(
            "integration" if args.mode == "integration" else "synthetic_projection"
        ),
    )
    if args.mode == "synthetic_preview":
        ablation_runner = V2AblationRunner(project_root=PROJECT_ROOT)
    else:
        if args.identity_map is None:
            parser.error("--identity-map is required when --mode=integration")
        identity = IntegrationIdentityMap.from_json(args.identity_map)

        def run_real_condition(condition, base_options):
            materializer = PostgresV2Materializer(SessionLocal)
            executor = UnifiedHealthGraphIntegrationExecutor(
                identity,
                runtime_options=condition.runtime_options,
            )
            runner = V2EvalRunner(
                project_root=PROJECT_ROOT,
                materializer=materializer,
                executor=executor,
            )
            return runner.run(
                base_options.model_copy(update={"runner_mode": "integration"})
            )

        ablation_runner = V2AblationRunner(
            project_root=PROJECT_ROOT,
            condition_runner=run_real_condition,
        )

    report = ablation_runner.run(runner_options=runner_options)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "integration" if args.mode == "integration" else "preview"
    json_path = args.output_dir / f"agent_eval_report.v2.ablation.{suffix}.json"
    markdown_path = args.output_dir / f"agent_eval_report.v2.ablation.{suffix}.md"
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        V2AblationRunner.render_markdown(report),
        encoding="utf-8",
    )
    print(f"json: {json_path}")
    print(f"markdown: {markdown_path}")
    print(f"status: {report.status}; conditions: {len(report.conditions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
