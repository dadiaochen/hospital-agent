"""Deterministic runner for the frozen 4D benchmark datasets.

The runner validates benchmark data and evaluates deterministic policy
consistency. It deliberately does not call an LLM, database, API, Provider,
or LangGraph. Runtime quality, latency, token, and cost metrics stay N/A until
an actual observation source is supplied by a later run mode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from pydantic import TypeAdapter

from app.agent.benchmark_schemas import (
    AnswerQualityCase,
    BenchmarkDataset,
    BenchmarkDatasetReport,
    BenchmarkManifest,
    BenchmarkMetric,
    BenchmarkMode,
    BenchmarkReport,
    MemoryContextCase,
    ProviderFaultCase,
    RAGGoldCase,
    SafetyGoldCase,
)


MANIFEST_FILENAME = "benchmark_manifest.v1.json"
DATASET_SPECS: tuple[tuple[str, str, type[Any]], ...] = (
    ("answer_quality.v1.json", "answer_quality", AnswerQualityCase),
    ("rag_gold.v1.json", "rag_gold", RAGGoldCase),
    ("safety_gold.v1.json", "safety_gold", SafetyGoldCase),
    ("memory_context.v1.json", "memory_context", MemoryContextCase),
    ("provider_faults.v1.json", "provider_faults", ProviderFaultCase),
)
KNOWN_RAG_SOURCE_KEYS = {
    "knowledge_category:refill_sop",
    "knowledge_category:reminder_template",
    "knowledge_category:human_confirmation",
    "knowledge_category:medical_safety",
}
RETRYABLE_FAULTS = {"timeout", "rate_limit", "transient_5xx", "connection_reset"}
RUN_NAMESPACE = UUID("bce4d0a0-1f93-4dcb-9d72-4d1bc1d7b1f4")


class BenchmarkDataError(ValueError):
    """Raised when a frozen benchmark cannot be trusted."""


def canonical_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class BenchmarkRunner:
    """Load a frozen manifest and produce a reproducible deterministic report."""

    def __init__(
        self,
        *,
        fixture_dir: Path,
        output_dir: Path | None = None,
    ) -> None:
        self.fixture_dir = fixture_dir
        self.output_dir = output_dir or fixture_dir.parents[3] / "output" / "benchmarks"

    @classmethod
    def from_project_root(cls, project_root: Path | None = None) -> "BenchmarkRunner":
        root = project_root or Path(__file__).resolve().parents[3]
        return cls(
            fixture_dir=root / "backend" / "tests" / "fixtures" / "benchmarks",
            output_dir=root / "output" / "benchmarks",
        )

    def load_manifest(self) -> tuple[BenchmarkManifest, dict[str, Any], str]:
        raw = self._read_json(MANIFEST_FILENAME)
        manifest = BenchmarkManifest.model_validate(raw)
        if manifest.dataset_version != "4d-a-gold-v1":
            raise BenchmarkDataError("manifest must use the frozen 4d-a-gold-v1 version")
        if set(manifest.datasets) != {filename for filename, _, _ in DATASET_SPECS}:
            raise BenchmarkDataError("manifest dataset inventory does not match runner")
        return manifest, raw, canonical_hash(raw)

    def load_datasets(self, manifest: BenchmarkManifest) -> dict[str, Any]:
        loaded: dict[str, Any] = {}
        for filename, dataset_id, case_type in DATASET_SPECS:
            raw = self._read_json(filename)
            dataset = TypeAdapter(BenchmarkDataset[case_type]).validate_python(raw)
            if dataset.dataset_id != dataset_id:
                raise BenchmarkDataError(f"dataset id mismatch: {filename}")
            entry = manifest.datasets.get(filename)
            if entry is None or entry.dataset_id != dataset_id:
                raise BenchmarkDataError(f"manifest entry missing: {filename}")
            if entry.case_count != len(dataset.cases):
                raise BenchmarkDataError(f"manifest count mismatch: {filename}")
            if entry.sha256 != canonical_hash(raw):
                raise BenchmarkDataError(f"dataset hash mismatch: {filename}")
            loaded[dataset_id] = dataset
        return loaded

    def run(self, mode: BenchmarkMode = "deterministic") -> BenchmarkReport:
        manifest, raw_manifest, manifest_hash = self.load_manifest()
        run_id = str(uuid5(RUN_NAMESPACE, f"{manifest_hash}:{mode}"))
        generated_at = datetime.now(timezone.utc).replace(microsecond=0)
        if mode != "deterministic":
            return BenchmarkReport(
                report_version="4d-benchmark-report-v1",
                manifest_id=manifest.manifest_id,
                manifest_sha256=manifest_hash,
                run_id=run_id,
                generated_at=generated_at,
                mode=mode,
                status="not_available",
                datasets=[],
                metrics=[],
                environment=self._environment(mode),
                notes=[
                    f"{mode} mode is declared but not enabled in this offline runner.",
                    "No LLM, database, API, Provider, or Docker process was called.",
                ],
            )

        datasets = self.load_datasets(manifest)
        dataset_reports: list[BenchmarkDatasetReport] = []
        metrics: list[BenchmarkMetric] = []
        bad_cases: list[str] = []

        answer_report, answer_metrics, answer_bad = self._answer_quality_report(datasets["answer_quality"])
        rag_report, rag_metrics, rag_bad = self._rag_report(datasets["rag_gold"])
        safety_report, safety_metrics, safety_bad = self._safety_report(datasets["safety_gold"])
        memory_report, memory_metrics, memory_bad = self._memory_report(datasets["memory_context"])
        provider_report, provider_metrics, provider_bad = self._provider_report(datasets["provider_faults"])
        for report, report_metrics, report_bad in (
            (answer_report, answer_metrics, answer_bad),
            (rag_report, rag_metrics, rag_bad),
            (safety_report, safety_metrics, safety_bad),
            (memory_report, memory_metrics, memory_bad),
            (provider_report, provider_metrics, provider_bad),
        ):
            dataset_reports.append(report)
            metrics.extend(report_metrics)
            bad_cases.extend(report_bad)

        metrics.extend(self._runtime_metrics())
        return BenchmarkReport(
            report_version="4d-benchmark-report-v1",
            manifest_id=manifest.manifest_id,
            manifest_sha256=manifest_hash,
            run_id=run_id,
            generated_at=generated_at,
            mode=mode,
            status="completed",
            datasets=dataset_reports,
            metrics=metrics,
            bad_cases=list(dict.fromkeys(bad_cases)),
            environment=self._environment(mode),
            notes=[
                "This is a deterministic benchmark-data and policy-contract report.",
                "It does not measure model answer quality, clinical accuracy, production latency, token usage, or cost.",
                "Runtime metrics remain N/A until real observations are supplied.",
            ],
        )

    def write_reports(self, report: BenchmarkReport, *, project_root: Path | None = None) -> tuple[Path, Path, Path]:
        root = project_root or self.fixture_dir.parents[3]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        json_path = self.output_dir / "benchmark_report.4d.json"
        markdown_path = root / "docs" / "benchmark_report.4d.md"
        badcases_path = root / "docs" / "benchmark_badcases.4d.md"
        json_path.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        markdown_path.write_text(self.render_markdown(report), encoding="utf-8")
        badcases_path.write_text(self.render_badcases(report), encoding="utf-8")
        return json_path, markdown_path, badcases_path

    @staticmethod
    def render_markdown(report: BenchmarkReport) -> str:
        lines = [
            "# 4D Benchmark Report",
            "",
            "> This report is deterministic evidence for frozen benchmark data and policy contracts. It is not a clinical or production performance claim.",
            "",
            f"- Status: `{report.status}`",
            f"- Mode: `{report.mode}`",
            f"- Manifest: `{report.manifest_id}`",
            f"- Manifest SHA-256: `{report.manifest_sha256}`",
            f"- Run ID: `{report.run_id}`",
            "",
            "## Metrics",
            "",
            "| Metric | Value | Status | Type | Samples | Notes |",
            "| --- | ---: | --- | --- | ---: | --- |",
        ]
        for metric in report.metrics:
            value = "N/A" if metric.value is None else f"{metric.value:.4f}"
            lines.append(
                f"| {metric.name} | {value} {metric.unit} | {metric.status} | {metric.metric_type} | {metric.sample_count} | {metric.notes} |"
            )
        lines.extend([
            "",
            "## Dataset Contract",
            "",
            "| Dataset | Cases | Contract valid | Bad cases | Category counts |",
            "| --- | ---: | --- | ---: | --- |",
        ])
        for dataset in report.datasets:
            counts = ", ".join(f"{key}={value}" for key, value in sorted(dataset.category_counts.items()))
            lines.append(
                f"| {dataset.dataset_id} | {dataset.case_count} | {str(dataset.contract_valid).lower()} | {len(dataset.bad_case_ids)} | {counts} |"
            )
        lines.extend(["", "## Notes", ""])
        lines.extend(f"- {note}" for note in report.notes)
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def render_badcases(report: BenchmarkReport) -> str:
        lines = [
            "# 4D Benchmark Bad Cases",
            "",
            "> Only deterministic data-contract and policy-consistency failures are listed here. Runtime model bad cases require actual RunTrace observations.",
            "",
        ]
        if not report.bad_cases:
            lines.append("No deterministic benchmark bad cases were found.")
        else:
            lines.extend(f"- `{case_id}`" for case_id in report.bad_cases)
        lines.append("")
        return "\n".join(lines)

    def _answer_quality_report(self, dataset: BenchmarkDataset[AnswerQualityCase]) -> tuple[BenchmarkDatasetReport, list[BenchmarkMetric], list[str]]:
        bad: list[str] = []
        for case in dataset.cases:
            if case.category == "high_risk_medical" and not case.expected_safety_flags:
                bad.append(f"answer_quality:{case.case_id}:missing_safety_flags")
            if case.category == "no_source_or_tool_failure" and case.expected_source_keys:
                bad.append(f"answer_quality:{case.case_id}:unexpected_source")
            if case.category in {"refill", "reminder"} and not case.expected_human_confirmation_required:
                bad.append(f"answer_quality:{case.case_id}:confirmation_not_required")
        report = self._dataset_report(dataset.dataset_id, dataset.cases, bad)
        metrics = [
            self._ratio_metric("answer_quality_contract_pass_rate", len(dataset.cases) - len(bad), len(dataset.cases), "ratio", "All answer-quality labels satisfy deterministic contract checks."),
        ]
        return report, metrics, bad

    def _rag_report(self, dataset: BenchmarkDataset[RAGGoldCase]) -> tuple[BenchmarkDatasetReport, list[BenchmarkMetric], list[str]]:
        bad: list[str] = []
        for case in dataset.cases:
            if any(key not in KNOWN_RAG_SOURCE_KEYS for key in case.expected_source_keys):
                bad.append(f"rag_gold:{case.case_id}:unknown_source_key")
            if not case.expected_citation_required:
                bad.append(f"rag_gold:{case.case_id}:citation_not_required")
        report = self._dataset_report(dataset.dataset_id, dataset.cases, bad)
        metrics = [
            self._ratio_metric("rag_source_mapping_contract_rate", len(dataset.cases) - len(bad), len(dataset.cases), "ratio", "Stable candidate keys map to the reviewed seed categories."),
        ]
        return report, metrics, bad

    def _safety_report(self, dataset: BenchmarkDataset[SafetyGoldCase]) -> tuple[BenchmarkDatasetReport, list[BenchmarkMetric], list[str]]:
        bad: list[str] = []
        for case in dataset.cases:
            if case.category == "high_risk" and (not case.expected_safety_flags or case.expected_decision != "block_or_escalate"):
                bad.append(f"safety_gold:{case.case_id}:high_risk_policy_mismatch")
            if case.category == "normal_or_confirmable" and case.expected_safety_flags:
                bad.append(f"safety_gold:{case.case_id}:normal_case_flagged")
        report = self._dataset_report(dataset.dataset_id, dataset.cases, bad)
        metrics = [
            self._ratio_metric("safety_label_contract_rate", len(dataset.cases) - len(bad), len(dataset.cases), "ratio", "Reviewed safety decisions and flags are internally consistent."),
        ]
        return report, metrics, bad

    def _memory_report(self, dataset: BenchmarkDataset[MemoryContextCase]) -> tuple[BenchmarkDatasetReport, list[BenchmarkMetric], list[str]]:
        bad: list[str] = []
        protected_facts = 0
        for case in dataset.cases:
            if not case.member_id or not case.task_id:
                bad.append(f"memory_context:{case.case_id}:missing_scope")
            unconfirmed = {turn.fact_id for turn in case.turns if turn.fact_id and not turn.confirmed}
            if unconfirmed & set(case.expected_memory_write_ids):
                bad.append(f"memory_context:{case.case_id}:unconfirmed_write")
            protected_facts += len(unconfirmed - set(case.expected_memory_write_ids))
            if case.category == "member_switch_isolation" and (not case.previous_member_id or case.previous_member_id == case.member_id):
                bad.append(f"memory_context:{case.case_id}:invalid_member_switch")
        report = self._dataset_report(dataset.dataset_id, dataset.cases, bad)
        metrics = [
            self._ratio_metric("memory_label_contract_rate", len(dataset.cases) - len(bad), len(dataset.cases), "ratio", "Retention and write labels pass deterministic member/confirmation checks."),
            self._ratio_metric("expected_unconfirmed_write_protection_rate", protected_facts, protected_facts, "ratio", "This is an expected-policy ratio, not an observed runtime write rate."),
        ]
        return report, metrics, bad

    def _provider_report(self, dataset: BenchmarkDataset[ProviderFaultCase]) -> tuple[BenchmarkDatasetReport, list[BenchmarkMetric], list[str]]:
        bad: list[str] = []
        for case in dataset.cases:
            expected_retry = case.read_only and case.injected_fault in RETRYABLE_FAULTS
            if case.expected_retryable != expected_retry:
                bad.append(f"provider_faults:{case.case_id}:retry_policy_mismatch")
            if not case.expected_retryable and case.expected_max_attempts != 1:
                bad.append(f"provider_faults:{case.case_id}:unexpected_retry")
            if not case.read_only and case.expected_write_retry_count != 0:
                bad.append(f"provider_faults:{case.case_id}:write_retry_not_zero")
            if case.expected_source_present:
                bad.append(f"provider_faults:{case.case_id}:failure_source_present")
        report = self._dataset_report(dataset.dataset_id, dataset.cases, bad)
        metrics = [
            self._ratio_metric("provider_fault_policy_contract_rate", len(dataset.cases) - len(bad), len(dataset.cases), "ratio", "Fault expectations are checked without invoking external Providers."),
            self._ratio_metric("expected_write_operation_retry_zero_rate", sum(case.expected_write_retry_count == 0 for case in dataset.cases), len(dataset.cases), "ratio", "This verifies gold labels, not observed Provider behavior."),
        ]
        return report, metrics, bad

    @staticmethod
    def _runtime_metrics() -> list[BenchmarkMetric]:
        names = [
            ("answer_quality_pass_rate", "ratio"),
            ("rag_recall_at_3", "ratio"),
            ("rag_recall_at_5", "ratio"),
            ("rag_mrr", "ratio"),
            ("rag_citation_correctness", "ratio"),
            ("safety_recall", "ratio"),
            ("normal_request_false_positive_rate", "ratio"),
            ("memory_key_retention_rate", "ratio"),
            ("cross_member_leakage_rate", "ratio"),
            ("checkpoint_recovery_success_rate", "ratio"),
            ("provider_recovery_rate", "ratio"),
            ("write_operation_retry_error_rate", "ratio"),
            ("latency_p50_ms", "ms"),
            ("latency_p95_ms", "ms"),
            ("average_input_tokens", "tokens"),
            ("average_output_tokens", "tokens"),
            ("average_cost_usd", "usd"),
        ]
        return [
            BenchmarkMetric(
                name=name,
                value=None,
                status="not_available",
                metric_type="runtime_observation",
                sample_count=0,
                unit=unit,
                notes="No runtime observation source was supplied.",
            )
            for name, unit in names
        ]

    @staticmethod
    def _dataset_report(dataset_id: str, cases: list[Any], bad: list[str]) -> BenchmarkDatasetReport:
        return BenchmarkDatasetReport(
            dataset_id=dataset_id,
            case_count=len(cases),
            contract_valid=not bad,
            category_counts=dict(Counter(case.category for case in cases)),
            bad_case_ids=list(dict.fromkeys(bad)),
        )

    @staticmethod
    def _ratio_metric(name: str, numerator: int, denominator: int, unit: str, notes: str) -> BenchmarkMetric:
        return BenchmarkMetric(
            name=name,
            value=(numerator / denominator if denominator else 0.0),
            status="measured",
            metric_type="dataset_contract",
            sample_count=denominator,
            unit=unit,
            notes=notes,
        )

    @staticmethod
    def _environment(mode: BenchmarkMode) -> dict[str, str]:
        return {
            "mode": mode,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "database": "not_used",
            "llm": "not_used",
            "provider": "not_used",
        }

    def _read_json(self, filename: str) -> dict[str, Any]:
        path = self.fixture_dir / filename
        if not path.exists():
            raise BenchmarkDataError(f"missing benchmark file: {path}")
        return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic 4D benchmark.")
    parser.add_argument("--mode", choices=("deterministic", "real_model", "docker_integration"), default="deterministic")
    parser.add_argument("--project-root", type=Path, default=None)
    args = parser.parse_args()
    runner = BenchmarkRunner.from_project_root(args.project_root)
    report = runner.run(args.mode)
    paths = runner.write_reports(report, project_root=args.project_root)
    print(f"4D-B status={report.status} mode={report.mode} bad_cases={len(report.bad_cases)}")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()


__all__ = ["BenchmarkDataError", "BenchmarkRunner", "canonical_hash"]
