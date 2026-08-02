"""Run the Docker evidence checks required by 4D-B2.6.

The script never uploads data and never starts an LLM.  ``--start`` and
``--stop`` are explicit because Docker lifecycle is an operator choice.  The
actual API/database/Redis/pgvector assertions remain in task12_acceptance.py
so there is one canonical Docker smoke test.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(command: list[str], *, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _compose(*args: str, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return _run(["docker", "compose", *args], timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", action="store_true", help="build and start the Docker stack")
    parser.add_argument("--stop", action="store_true", help="stop the Docker stack after checks")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("var/demo/4d-b26-docker"),
    )
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    if args.start:
        started = _compose("up", "-d", "--build")
        checks.append(
            {
                "name": "docker_compose_up",
                "status": "PASS" if started.returncode == 0 else "FAIL",
                "detail": (started.stdout or started.stderr)[-1000:],
            }
        )
        if started.returncode != 0:
            return _write_report(args.output_dir, checks)

    acceptance_command = [
        sys.executable,
        "-m",
        "scripts.task12_acceptance",
        "--require-vector",
        "--json-report",
        str(args.output_dir / "task12_backend_acceptance.json"),
        "--markdown-report",
        str(args.output_dir / "task12_backend_acceptance.md"),
    ]
    if args.skip_frontend:
        acceptance_command.append("--skip-frontend")
    acceptance = _run(acceptance_command, timeout=900)
    checks.append(
        {
            "name": "task12_backend_acceptance",
            "status": "PASS" if acceptance.returncode == 0 else "FAIL",
            "detail": (acceptance.stdout or acceptance.stderr)[-2000:],
        }
    )

    if args.stop:
        stopped = _compose("stop")
        checks.append(
            {
                "name": "docker_compose_stop",
                "status": "PASS" if stopped.returncode == 0 else "FAIL",
                "detail": (stopped.stdout or stopped.stderr)[-1000:],
            }
        )
    return _write_report(args.output_dir, checks)


def _write_report(output_dir: Path, checks: list[dict[str, Any]]) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "task": "4D-B2.6 Docker full-chain regression",
        "checks": checks,
        "passed": sum(item["status"] == "PASS" for item in checks),
        "failed": sum(item["status"] == "FAIL" for item in checks),
        "notes": [
            "This report is local Docker evidence, not a production SLO.",
            "The v2 formal benchmark remains blocked until WorldState human review and integration identity/source mapping are complete.",
        ],
    }
    json_path = output_dir / "4d_b26_docker_regression.json"
    markdown_path = output_dir / "4d_b26_docker_regression.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# 4D-B2.6 Docker Full-Chain Regression",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| `{item['name']}` | **{item['status']}** | {str(item['detail']).replace('|', '/') } |"
        for item in checks
    )
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in payload["notes"])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if payload["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
