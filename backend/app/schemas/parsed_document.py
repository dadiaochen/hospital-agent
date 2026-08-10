"""Safe, unified parsing contract for member-scoped medical documents.

The parser only preserves document evidence and structured metrics.  It deliberately
does not infer a diagnosis or a treatment plan.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.common import ApiSchema


DocumentInputType = Literal["text", "pdf", "image"]


class ParsedSection(ApiSchema):
    id: str
    title: str
    content: str
    page_number: int | None = None


class ParsedTable(ApiSchema):
    id: str
    headers: list[str]
    rows: list[list[str]]
    page_number: int | None = None


class ParsedMetric(ApiSchema):
    id: str
    name: str
    value: str | None = None
    unit: str | None = None
    reference_display: str | None = None
    source_section_id: str


class ParsedDocument(ApiSchema):
    input_type: DocumentInputType
    document_type: str
    raw_text: str = ""
    sections: list[ParsedSection] = Field(default_factory=list)
    tables: list[ParsedTable] = Field(default_factory=list)
    metrics: list[ParsedMetric] = Field(default_factory=list)
    parser_version: str
    requires_professional_review: Literal[True] = True
    diagnosis_provided: Literal[False] = False
    safety_notice: str = "仅整理原始报告内容和结构化指标，不构成诊断或治疗建议。"


__all__ = [
    "DocumentInputType",
    "ParsedDocument",
    "ParsedMetric",
    "ParsedSection",
    "ParsedTable",
]
