"""Member-scoped upload, draft confirmation and report-history lifecycle."""

from __future__ import annotations

import base64
import binascii

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import InvalidRequestError, ResourceNotFoundError
from app.models import FamilyMember, MedicalDocument
from app.schemas.reports import (
    ReportUploadRequest,
    ReportUploadResponse,
)
from app.services.document_parser_service import DocumentParserService
from app.services.report_read_service import ReportReadService


class ReportLifecycleService:
    """Persist member-scoped parsed reports without creating medical conclusions."""

    def __init__(self, db: Session, user_id: str, *, parser: DocumentParserService | None = None) -> None:
        self.db = db
        self.user_id = user_id
        self.parser = parser or DocumentParserService()
        self.reader = ReportReadService(db, user_id)

    def upload(self, member_id: str, request: ReportUploadRequest) -> ReportUploadResponse:
        self._scoped_member(member_id)
        content = self._decode_content(request.content_base64)
        if request.input_type == "text" and not request.text.strip():
            raise InvalidRequestError("文本报告内容不能为空")
        parsed = self.parser.parse(
            input_type=request.input_type,
            document_type=request.document_type,
            text=request.text,
            content=content,
            extracted_text=request.extracted_text,
        )
        document = MedicalDocument(
            user_id=self.user_id,
            member_id=member_id,
            document_type=request.document_type,
            title=request.title,
            source_text=parsed.raw_text or None,
            parser_provider=parsed.parser_version,
            status="ready",
            extracted_content=self._extracted_content(parsed),
            document_version="1.0",
            need_human_confirmation=False,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return ReportUploadResponse(
            report=self.reader._summary(document),
            metric_count=len(parsed.metrics),
        )

    def _scoped_member(self, member_id: str) -> FamilyMember:
        member = self.db.scalar(select(FamilyMember).where(
            FamilyMember.id == member_id, FamilyMember.user_id == self.user_id,
        ))
        if member is None:
            raise ResourceNotFoundError("family member was not found")
        return member

    @staticmethod
    def _decode_content(content_base64: str | None) -> bytes | None:
        if not content_base64:
            return None
        try:
            return base64.b64decode(content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise InvalidRequestError("文件内容不是有效的 Base64") from exc

    @staticmethod
    def _extracted_content(parsed) -> dict:
        sections = [
            {"id": item.id, "title": item.title, "content": item.content}
            for item in parsed.sections
        ]
        metrics = [
            {"id": item.id, "name": item.name, "value": item.value,
             "unit": item.unit, "interpretation_status": "not_available",
             "trend": "unknown", "explanation": "指标来自上传报告的结构化整理，需结合原始报告和专业人员意见。"}
            for item in parsed.metrics
        ]
        return {
            "summary": {"text": "报告已解析为可查看的结构化指标。", "disclaimer": "这是信息整理，不是诊断或治疗建议。"},
            "sections": sections, "metrics": metrics,
            "tables": [item.model_dump(mode="json") for item in parsed.tables],
            "requires_professional_review": True, "safety_notice": parsed.safety_notice,
            "parser_version": parsed.parser_version, "input_type": parsed.input_type,
        }


__all__ = ["ReportLifecycleService"]
