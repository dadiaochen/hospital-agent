from typing import Literal


ErrorCategory = Literal[
    "validation",
    "permission",
    "not_found",
    "timeout",
    "rate_limit",
    "provider_unavailable",
    "business_conflict",
    "schema",
    "internal",
]


_ERROR_CATEGORY_BY_TYPE: dict[str, ErrorCategory] = {
    "validation": "validation",
    "validation_error": "validation",
    "input_schema_error": "validation",
    "input_scope_error": "validation",
    "tool_not_allowed": "permission",
    "permission_denied": "permission",
    "scope_violation": "permission",
    "context_isolation_violation": "permission",
    "not_found": "not_found",
    "tool_not_found": "not_found",
    "related_record_not_found": "not_found",
    "timeout": "timeout",
    "rate_limit": "rate_limit",
    "provider_unavailable": "provider_unavailable",
    "business_conflict": "business_conflict",
    "idempotency_conflict": "business_conflict",
    "output_schema_error": "schema",
    "schema_error": "schema",
    "schema_validation_failed": "schema",
}


RETRYABLE_ERROR_CATEGORIES: frozenset[ErrorCategory] = frozenset(
    {"timeout", "rate_limit", "provider_unavailable"}
)


def classify_error(error_type: str | None) -> ErrorCategory:
    """Map legacy error names to the stable reliability taxonomy."""

    if not error_type:
        return "internal"
    return _ERROR_CATEGORY_BY_TYPE.get(error_type, "internal")


__all__ = [
    "ErrorCategory",
    "RETRYABLE_ERROR_CATEGORIES",
    "classify_error",
]
