from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ApiSchema


ReportStatus = Literal[
    "uploaded",
    "processing",
    "ready",
    "needs_review",
    "failed",
]


class ReportSummaryResponse(ApiSchema):
    id: str
    member_id: str
    title: str
    document_type: str
    status: ReportStatus
    reported_at: datetime | None
    updated_at: datetime
    document_version: str
    source_name: str
    metric_count: int


class ReportListResponse(ApiSchema):
    items: list[ReportSummaryResponse]


class ReportReferenceRangeResponse(ApiSchema):
    low: float | None
    high: float | None
    display_text: str


class ReportMetricResponse(ApiSchema):
    id: str
    name: str
    value: str | int | float | None
    unit: str | None
    reference_range: ReportReferenceRangeResponse | None
    interpretation_status: Literal[
        "within_range",
        "above_range",
        "below_range",
        "not_available",
    ]
    trend: Literal["up", "down", "stable", "unknown"]
    measured_at: datetime | None
    explanation: str
    source_ref: str


class ReportSectionResponse(ApiSchema):
    id: str
    title: str
    content: str
    source_ref: str


class ReportSourceResponse(ApiSchema):
    id: str
    source_type: Literal["medical_report", "doctor_note", "knowledge_base"]
    display_name: str
    document_version: str
    page_number: int | None
    excerpt: str | None
    verified: bool


class ReportSummaryTextResponse(ApiSchema):
    text: str
    disclaimer: str


class ReportSafetyResponse(ApiSchema):
    requires_professional_review: bool
    notice: str


class ReportDetailResponse(ApiSchema):
    report: ReportSummaryResponse
    summary: ReportSummaryTextResponse
    metrics: list[ReportMetricResponse]
    sections: list[ReportSectionResponse]
    sources: list[ReportSourceResponse]
    safety: ReportSafetyResponse


class ReportUploadRequest(ApiSchema):
    """Initial JSON upload contract; file content is kept in memory only."""

    title: str = Field(min_length=1, max_length=160)
    document_type: str = Field(min_length=1, max_length=80)
    input_type: Literal["text", "pdf", "image"]
    text: str = ""
    content_base64: str | None = None
    extracted_text: str = ""


class ReportUploadResponse(ApiSchema):
    report: ReportSummaryResponse
    metric_count: int
