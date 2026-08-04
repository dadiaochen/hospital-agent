"""Prepare the local review queue and identity map for the final v2 gate.

This command only reads the frozen synthetic benchmark.  It does not start
Docker, call PostgreSQL, call a Provider or call an LLM.  The output is
machine-local and ignored by Git.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.agent.v2_final_gate import prepare_final_gate_artifacts  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Defaults to <project-root>/var/demo; keep this directory local.",
    )
    args = parser.parse_args()
    review_path, identity_path = prepare_final_gate_artifacts(
        project_root=args.project_root,
        output_dir=args.output_dir,
    )
    print(f"review_queue: {review_path}")
    print(f"identity_template: {identity_path}")
    print("status: pending_review; fill local mappings and review Gold before integration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
