"""Run reviewed v2 cases through PostgreSQL and UnifiedHealthGraph.

This command intentionally requires a local identity map.  The map points the
synthetic benchmark user/member/source IDs to the disposable demo rows used by
the local Docker database; it is machine-local and must not be committed.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

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
    parser.add_argument("--identity-map", type=Path, required=True)
    parser.add_argument("--max-cases", type=int, default=1)
    parser.add_argument("--split", choices=("all", "development", "validation", "holdout"), default="development")
    parser.add_argument("--allow-pending-review", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=Path("output/benchmarks/v2"))
    args = parser.parse_args()

    identity = IntegrationIdentityMap.from_json(args.identity_map)
    materializer = PostgresV2Materializer(SessionLocal)
    executor = UnifiedHealthGraphIntegrationExecutor(identity)
    runner = V2EvalRunner(
        project_root=PROJECT_ROOT,
        materializer=materializer,
        executor=executor,
    )
    report = runner.run(
        V2RunnerOptions(
            runner_mode="integration",
            dataset_split=args.split,
            max_cases=args.max_cases,
            allow_pending_review=args.allow_pending_review,
        )
    )
    json_path, markdown_path = runner.write_report(report, output_dir=args.output_dir)
    print(f"json: {json_path}")
    print(f"markdown: {markdown_path}")
    print(f"status: {report.status}; samples: {report.sample_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
