from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.model_provider_diagnostic import (  # noqa: E402
    diagnostic_exit_code,
    run_model_provider_diagnostic,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check Model Gateway configuration. External HTTP is called only with --live."
        )
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Perform one structured provider request when openai_compatible is configured.",
    )
    args = parser.parse_args()

    report = run_model_provider_diagnostic(live=args.live)
    print(report.model_dump_json(indent=2))
    return diagnostic_exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
