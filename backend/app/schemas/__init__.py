"""Pydantic schemas."""

from app.schemas.business import (
    BusinessDomain,
    BusinessRequestContext,
    ProviderMode,
    SourceRef,
    SourceType,
)

_BUSINESS_TASK_EXPORTS = {
    "BusinessTaskConfirmRequest",
    "BusinessTaskCreateRequest",
    "BusinessTaskExecutionResponse",
    "BusinessTaskListResponse",
    "BusinessTaskSummaryResponse",
    "SourceReferenceResponse",
}


def __getattr__(name: str):
    """Load task DTOs lazily to keep tool/schema imports acyclic."""

    if name not in _BUSINESS_TASK_EXPORTS:
        raise AttributeError(name)
    from app.schemas import business_task

    value = getattr(business_task, name)
    globals()[name] = value
    return value

__all__ = [
    "BusinessDomain",
    "BusinessRequestContext",
    "ProviderMode",
    "SourceRef",
    "SourceType",
    "BusinessTaskConfirmRequest",
    "BusinessTaskCreateRequest",
    "BusinessTaskExecutionResponse",
    "BusinessTaskListResponse",
    "BusinessTaskSummaryResponse",
    "SourceReferenceResponse",
]
