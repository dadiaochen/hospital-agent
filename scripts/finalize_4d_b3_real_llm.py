"""Finalize a human-reviewed 4D-B3 report without calling external systems."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.agent.real_llm_benchmark import (  # noqa: E402
    RealLLMFinalizationError,
    RealLLMBenchmarkRunner,
)


DEFAULT_PREVIEW_DIR = Path(
    "output/benchmarks/4d-b3-real-llm-development-world1-2"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_PREVIEW_DIR / "agent_eval_report.4d-b3.real-llm.json",
    )
    parser.add_argument(
        "--review-queue",
        type=Path,
        default=DEFAULT_PREVIEW_DIR / "badcase_review_queue.4d-b3.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/benchmarks/4d-b3-real-llm-final"),
    )
    args = parser.parse_args()

    runner = RealLLMBenchmarkRunner(project_root=PROJECT_ROOT)
    try:
        report = runner.finalize_reviewed_report(
            report_path=args.report,
            review_queue_path=args.review_queue,
        )
        json_path, markdown_path, manifest_path = runner.write_finalized_report(
            report,
            output_dir=args.output_dir,
        )
    except (OSError, ValueError, RealLLMFinalizationError) as exc:
        print(f"finalization blocked: {exc}", file=sys.stderr)
        return 2

    print(f"json: {json_path}")
    print(f"markdown: {markdown_path}")
    print(f"manifest: {manifest_path}")
    print(
        "status: completed; "
        f"reviewed: {report.reviewed_sample_count}; "
        f"pass: {report.reviewed_pass_count}; "
        f"fail: {report.reviewed_fail_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
