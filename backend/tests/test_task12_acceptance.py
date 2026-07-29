from __future__ import annotations

from pathlib import Path

from scripts.task12_acceptance import AcceptanceReport, _p95, _write_report


def test_task12_p95_uses_real_wall_clock_samples() -> None:
    assert _p95([3.0, 5.0, 8.0, 13.0, 21.0]) == 21.0
    assert _p95([]) is None


def test_task12_report_contains_pass_fail_and_skip_statuses(tmp_path: Path) -> None:
    report = AcceptanceReport(mode="baseline", base_url="http://localhost:8000")
    report.check("migration", True, "head=0007")
    report.check("redis", True, "outage test deferred", skipped=True)
    report.check("api", False, "status=503")
    report.http_latency(4.0)
    report.http_latency(7.0)

    json_path = tmp_path / "task12.json"
    markdown_path = tmp_path / "task12.md"
    _write_report(report, json_path, markdown_path)

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "`migration`" in markdown
    assert "**SKIP**" in markdown
    assert "**FAIL**" in markdown
    assert "p95" in markdown
    assert '"failed": 1' in json_path.read_text(encoding="utf-8")
