from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.reliability import classify_error
from app.providers.registry import ProviderInvocationError
from app.providers.schemas import ProviderRequest, ProviderResponse
from app.schemas.business import SourceRef


ProviderTransport = Callable[[ProviderRequest, int], dict[str, Any]]


class _ProviderData(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MedicalDocumentSection(_ProviderData):
    section_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    text: str
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)


class MedicalDocumentParseData(_ProviderData):
    document_type: str = Field(min_length=1)
    sections: list[MedicalDocumentSection]
    raw_text: str
    parser_version: str = Field(min_length=1)
    medical_review_required: Literal[True] = True
    diagnosis_provided: Literal[False] = False


class PharmacyCandidate(_ProviderData):
    pharmacy: str = Field(min_length=1)
    availability: str = Field(min_length=1)
    fulfillment: list[Literal["delivery", "pickup"]]


class PharmacyInventoryData(_ProviderData):
    candidates: list[PharmacyCandidate]
    realtime: bool
    order_created: Literal[False] = False


class HospitalDepartmentCandidate(_ProviderData):
    department: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class HospitalDepartmentData(_ProviderData):
    candidates: list[HospitalDepartmentCandidate]
    diagnosis_provided: Literal[False] = False


class HospitalSlot(_ProviderData):
    date: str = Field(min_length=1)
    period: str = Field(min_length=1)
    mode: Literal["online", "offline"]


class HospitalSlotData(_ProviderData):
    slots: list[HospitalSlot]
    realtime: bool
    appointment_created: Literal[False] = False


class ConsultationDraft(_ProviderData):
    chief_complaint: str
    materials: list[Any]


class ConsultationDraftData(_ProviderData):
    draft: ConsultationDraft
    submitted: Literal[False] = False
    doctor_confirmation_required: Literal[True] = True


class _ReliableProvider:
    provider_name: str
    output_schemas: dict[str, type[_ProviderData]]

    def __init__(
        self,
        *,
        transport: ProviderTransport | None = None,
        timeout_ms: int = 3000,
    ) -> None:
        if timeout_ms < 1:
            raise ValueError("timeout_ms must be positive")
        self.transport = transport
        self.timeout_ms = timeout_ms

    def __call__(self, request: ProviderRequest) -> ProviderResponse:
        output_schema = self.output_schemas.get(request.operation)
        if output_schema is None:
            return self._failure(
                request,
                error_type="validation_error",
                fallback_reason="unsupported_operation",
                message="provider operation is not supported",
            )

        if request.provider_mode == "mock":
            raw_data = self._mock_data(request)
        elif self.transport is None:
            return self._failure(
                request,
                error_type="provider_unavailable",
                fallback_reason=f"{request.provider_mode}_adapter_not_configured",
                message="external provider adapter is not configured",
            )
        else:
            try:
                raw_data = self.transport(request, self.timeout_ms)
            except ProviderInvocationError:
                raise
            except TimeoutError as exc:
                raise ProviderInvocationError(
                    "provider request timed out",
                    error_type="timeout",
                    retryable=True,
                ) from exc
            except ConnectionError as exc:
                raise ProviderInvocationError(
                    "provider is temporarily unavailable",
                    error_type="provider_unavailable",
                    retryable=True,
                ) from exc

        try:
            data = output_schema.model_validate(raw_data)
        except ValidationError as exc:
            raise ProviderInvocationError(
                "provider returned data that violates its schema",
                error_type="schema_error",
                retryable=False,
                fallback_reason="provider_schema_invalid",
            ) from exc

        return ProviderResponse(
            provider_name=self.provider_name,
            provider_mode=request.provider_mode,
            operation=request.operation,
            success=True,
            data=data.model_dump(mode="json"),
            source_refs=[self._source(request, data)],
        )

    def _failure(
        self,
        request: ProviderRequest,
        *,
        error_type: str,
        fallback_reason: str,
        message: str,
    ) -> ProviderResponse:
        return ProviderResponse(
            provider_name=self.provider_name,
            provider_mode=request.provider_mode,
            operation=request.operation,
            success=False,
            error_type=error_type,
            error_category=classify_error(error_type),
            error_message=message,
            retryable=False,
            degraded=True,
            fallback_reason=fallback_reason,
        )

    def _mock_data(self, request: ProviderRequest) -> dict[str, Any]:
        raise NotImplementedError

    def _source(
        self,
        request: ProviderRequest,
        data: _ProviderData,
    ) -> SourceRef:
        return SourceRef(
            source_id=(
                f"provider:{self.provider_name}:{request.operation}:"
                f"{request.member_id}"
            ),
            source_type="structured_database",
            provider=self.provider_name,
            member_id=request.member_id,
            verified=False,
            source_metadata={
                "provider_mode": request.provider_mode,
                "simulation": request.provider_mode == "mock",
            },
        )


class MedicalDocumentParserProvider(_ReliableProvider):
    provider_name = "medical_document_parser"
    output_schemas = {"parse": MedicalDocumentParseData}

    def _mock_data(self, request: ProviderRequest) -> dict[str, Any]:
        raw_text = str(request.payload.get("text", ""))
        raw_sections = request.payload.get("sections")
        sections: list[dict[str, Any]] = []
        if isinstance(raw_sections, list):
            for index, item in enumerate(raw_sections):
                text = item.get("text", "") if isinstance(item, dict) else str(item)
                start = item.get("start_char", 0) if isinstance(item, dict) else 0
                end = item.get("end_char", len(text)) if isinstance(item, dict) else len(text)
                sections.append(
                    {
                        "section_id": (
                            str(item.get("section_id", f"section-{index + 1}"))
                            if isinstance(item, dict)
                            else f"section-{index + 1}"
                        ),
                        "label": (
                            str(item.get("label", "report_content"))
                            if isinstance(item, dict)
                            else "report_content"
                        ),
                        "text": str(text),
                        "start_char": int(start),
                        "end_char": int(end),
                    }
                )
        if not sections and raw_text:
            sections.append(
                {
                    "section_id": "section-1",
                    "label": "report_content",
                    "text": raw_text,
                    "start_char": 0,
                    "end_char": len(raw_text),
                }
            )
        return {
            "document_type": request.payload.get("document_type", "medical_report"),
            "sections": sections,
            "raw_text": raw_text,
            "parser_version": "mock-parser-v1",
            "medical_review_required": True,
            "diagnosis_provided": False,
        }

    def _source(
        self,
        request: ProviderRequest,
        data: _ProviderData,
    ) -> SourceRef:
        parsed = MedicalDocumentParseData.model_validate(data)
        document_id = str(
            request.payload.get(
                "document_id",
                f"document:{request.member_id}:{request.operation}",
            )
        )
        document_version = str(request.payload.get("document_version", "1.0"))
        return SourceRef(
            source_id=f"provider:{self.provider_name}:{document_id}:{document_version}",
            source_type="medical_document",
            document_id=document_id,
            document_version=document_version,
            retrieval_mode="provider_parse",
            provider=self.provider_name,
            member_id=request.member_id,
            verified=False,
            source_metadata={
                "provider_mode": request.provider_mode,
                "simulation": request.provider_mode == "mock",
                "parser_version": parsed.parser_version,
                "section_count": len(parsed.sections),
                "source_locations": [
                    {
                        "section_id": section.section_id,
                        "start_char": section.start_char,
                        "end_char": section.end_char,
                    }
                    for section in parsed.sections
                ],
            },
        )


class PharmacyProvider(_ReliableProvider):
    provider_name = "pharmacy"
    output_schemas = {"search_inventory": PharmacyInventoryData}

    def _mock_data(self, request: ProviderRequest) -> dict[str, Any]:
        return {
            "candidates": [
                {
                    "pharmacy": "demo_pharmacy",
                    "availability": "recheck_before_order",
                    "fulfillment": ["delivery", "pickup"],
                }
            ],
            "realtime": False,
            "order_created": False,
        }


class HospitalOrConsultationProvider(_ReliableProvider):
    def __init__(
        self,
        provider_name: Literal["hospital", "online_consultation"],
        *,
        transport: ProviderTransport | None = None,
        timeout_ms: int = 3000,
    ) -> None:
        self.provider_name = provider_name
        self.output_schemas = (
            {
                "list_departments": HospitalDepartmentData,
                "list_slots": HospitalSlotData,
            }
            if provider_name == "hospital"
            else {"prepare_draft": ConsultationDraftData}
        )
        super().__init__(transport=transport, timeout_ms=timeout_ms)

    def _mock_data(self, request: ProviderRequest) -> dict[str, Any]:
        if request.operation == "list_departments":
            return {
                "candidates": [
                    {
                        "department": "general_medicine",
                        "reason": "general_review_first",
                    },
                    {
                        "department": "specialist_review",
                        "reason": "doctor_reviews_submitted_materials",
                    },
                ],
                "diagnosis_provided": False,
            }
        if request.operation == "list_slots":
            return {
                "slots": [
                    {
                        "date": "demo-next-day",
                        "period": "morning",
                        "mode": "online",
                    }
                ],
                "realtime": False,
                "appointment_created": False,
            }
        return {
            "draft": {
                "chief_complaint": request.payload.get("chief_complaint", ""),
                "materials": request.payload.get("materials", []),
            },
            "submitted": False,
            "doctor_confirmation_required": True,
        }


__all__ = [
    "ConsultationDraftData",
    "HospitalDepartmentData",
    "HospitalOrConsultationProvider",
    "HospitalSlotData",
    "MedicalDocumentParseData",
    "MedicalDocumentParserProvider",
    "MedicalDocumentSection",
    "PharmacyInventoryData",
    "PharmacyProvider",
    "ProviderTransport",
]
