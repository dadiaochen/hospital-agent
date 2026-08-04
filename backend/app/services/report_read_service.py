from __future__ import annotations

from datetime import datetime
from numbers import Real
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ResourceNotFoundError
from app.models import FamilyMember, MedicalDocument
from app.schemas.reports import (
    ReportDetailResponse,
    ReportListResponse,
    ReportMetricResponse,
    ReportReferenceRangeResponse,
    ReportSafetyResponse,
    ReportSectionResponse,
    ReportSourceResponse,
    ReportStatus,
    ReportSummaryResponse,
    ReportSummaryTextResponse,
)

_REPORT_STATUSES = {"uploaded", "processing", "ready", "needs_review", "failed"}
_INTERPRETATION_STATUSES = {
    "within_range",
    "above_range",
    "below_range",
    "not_available",
}
_TRENDS = {"up", "down", "stable", "unknown"}
_SOURCE_TYPES = {"medical_report", "doctor_note", "knowledge_base"}


class ReportReadService:
    """Read and normalize report data into the frozen report-detail.v1 contract."""

    def __init__(self, db: Session, user_id: str) -> None:
        self.db = db
        self.user_id = user_id

    def list_reports(self, member_id: str) -> ReportListResponse:
        self._get_scoped_member(member_id)
        documents = list(
            self.db.scalars(
                select(MedicalDocument)
                .where(
                    MedicalDocument.user_id == self.user_id,
                    MedicalDocument.member_id == member_id,
                )
                .order_by(MedicalDocument.updated_at.desc())
            )
        )
        return ReportListResponse(
            items=[self._summary(document) for document in documents]
        )

    def get_report(self, member_id: str, report_id: str) -> ReportDetailResponse:
        self._get_scoped_member(member_id)
        document = self.db.scalar(
            select(MedicalDocument).where(
                MedicalDocument.id == report_id,
                MedicalDocument.user_id == self.user_id,
                MedicalDocument.member_id == member_id,
            )
        )
        if document is None:
            raise ResourceNotFoundError("medical report was not found")

        source_id = self._source_id(document)
        extracted = document.extracted_content if isinstance(document.extracted_content, dict) else {}
        sources = self._sources(document, extracted, source_id)
        known_source_ids = {source.id for source in sources}

        metrics = [
            metric
            for raw_metric in _list_of_dicts(extracted.get("metrics"))
            if (metric := self._metric(raw_metric, source_id, known_source_ids)) is not None
        ]
        sections = [
            section
            for raw_section in _list_of_dicts(extracted.get("sections"))
            if (section := self._section(raw_section, source_id, known_source_ids)) is not None
        ]

        return ReportDetailResponse(
            report=self._summary(document, metric_count=len(metrics)),
            summary=self._summary_text(extracted, len(metrics)),
            metrics=metrics,
            sections=sections,
            sources=sources,
            safety=ReportSafetyResponse(
                requires_professional_review=bool(
                    document.need_human_confirmation
                    or extracted.get("requires_professional_review", False)
                ),
                notice=_string(
                    extracted.get("safety_notice")
                    or extracted.get("disclaimer")
                    or "如有明显不适、结果异常或对报告有疑问，请咨询医生或药师。"
                ),
            ),
        )

    def _summary(
        self,
        document: MedicalDocument,
        *,
        metric_count: int | None = None,
    ) -> ReportSummaryResponse:
        extracted = document.extracted_content if isinstance(document.extracted_content, dict) else {}
        if metric_count is None:
            metric_count = len(_list_of_dicts(extracted.get("metrics")))
        return ReportSummaryResponse(
            id=document.id,
            member_id=document.member_id,
            title=document.title,
            document_type=document.document_type,
            status=_status(document.status),
            reported_at=document.created_at,
            updated_at=document.updated_at,
            document_version=document.document_version,
            source_name=document.title,
            metric_count=metric_count,
        )

    def _summary_text(
        self,
        extracted: dict[str, Any],
        metric_count: int,
    ) -> ReportSummaryTextResponse:
        raw_summary = extracted.get("summary")
        if isinstance(raw_summary, dict):
            text = _string(raw_summary.get("text"))
            disclaimer = _string(raw_summary.get("disclaimer"))
        else:
            text = _string(raw_summary)
            disclaimer = ""

        if not text:
            text = (
                f"报告中已整理出 {metric_count} 项可展示指标。"
                if metric_count
                else "报告已读取，但暂时没有可展示的指标。"
            )
        if not disclaimer:
            disclaimer = "这是信息整理和通俗解释，不是诊断或治疗建议。"
        return ReportSummaryTextResponse(text=text, disclaimer=disclaimer)

    def _metric(
        self,
        raw: dict[str, Any],
        source_id: str,
        known_source_ids: set[str],
    ) -> ReportMetricResponse | None:
        name = _string(raw.get("name"))
        if not name:
            return None
        value = raw.get("value")
        if not isinstance(value, (str, Real)) or isinstance(value, bool):
            value = None
        raw_range = raw.get("reference_range")
        reference_range = None
        if isinstance(raw_range, dict):
            reference_range = ReportReferenceRangeResponse(
                low=_number_or_none(raw_range.get("low")),
                high=_number_or_none(raw_range.get("high")),
                display_text=_string(raw_range.get("display_text")) or "未提供参考范围",
            )
        raw_status = _string(raw.get("interpretation_status"))
        status = raw_status if raw_status in _INTERPRETATION_STATUSES else "not_available"
        raw_trend = _string(raw.get("trend"))
        trend = raw_trend if raw_trend in _TRENDS else "unknown"
        raw_source_ref = _string(raw.get("source_ref"))
        source_ref = raw_source_ref if raw_source_ref in known_source_ids else source_id
        return ReportMetricResponse(
            id=_string(raw.get("id")) or f"{source_id}:metric:{name}",
            name=name,
            value=value,
            unit=_optional_string(raw.get("unit")),
            reference_range=reference_range,
            interpretation_status=status,
            trend=trend,
            measured_at=_datetime_or_none(raw.get("measured_at")),
            explanation=_string(raw.get("explanation")) or "当前没有足够信息提供更多解释。",
            source_ref=source_ref,
        )

    def _section(
        self,
        raw: dict[str, Any],
        source_id: str,
        known_source_ids: set[str],
    ) -> ReportSectionResponse | None:
        title = _string(raw.get("title"))
        content = _string(raw.get("content"))
        if not title or not content:
            return None
        raw_source_ref = _string(raw.get("source_ref"))
        return ReportSectionResponse(
            id=_string(raw.get("id")) or f"{source_id}:section:{title}",
            title=title,
            content=content,
            source_ref=raw_source_ref if raw_source_ref in known_source_ids else source_id,
        )

    def _sources(
        self,
        document: MedicalDocument,
        extracted: dict[str, Any],
        source_id: str,
    ) -> list[ReportSourceResponse]:
        sources: list[ReportSourceResponse] = [
            ReportSourceResponse(
                id=source_id,
                source_type="medical_report",
                display_name=document.title,
                document_version=document.document_version,
                page_number=None,
                excerpt=None,
                verified=_status(document.status) == "ready",
            )
        ]
        for raw in _list_of_dicts(extracted.get("sources")):
            raw_id = _string(raw.get("id"))
            if not raw_id or raw_id == source_id:
                continue
            raw_type = _string(raw.get("source_type"))
            source_type = raw_type if raw_type in _SOURCE_TYPES else "medical_report"
            page_number = raw.get("page_number")
            sources.append(
                ReportSourceResponse(
                    id=raw_id,
                    source_type=source_type,
                    display_name=_string(raw.get("display_name")) or document.title,
                    document_version=_string(raw.get("document_version"))
                    or document.document_version,
                    page_number=page_number if isinstance(page_number, int) else None,
                    excerpt=_optional_string(raw.get("excerpt")),
                    verified=bool(raw.get("verified", False)),
                )
            )
        return sources

    def _source_id(self, document: MedicalDocument) -> str:
        return f"medical-document:{document.id}:{document.document_version}"

    def _get_scoped_member(self, member_id: str) -> FamilyMember:
        member = self.db.scalar(
            select(FamilyMember).where(
                FamilyMember.id == member_id,
                FamilyMember.user_id == self.user_id,
            )
        )
        if member is None:
            raise ResourceNotFoundError("family member was not found")
        return member


def _status(value: str) -> ReportStatus:
    if value == "parsed":
        return "ready"
    if value in _REPORT_STATUSES:
        return value  # type: ignore[return-value]
    return "processing"


def _list_of_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_string(value: Any) -> str | None:
    value = _string(value)
    return value or None


def _number_or_none(value: Any) -> float | None:
    if isinstance(value, Real) and not isinstance(value, bool):
        return float(value)
    return None


def _datetime_or_none(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
