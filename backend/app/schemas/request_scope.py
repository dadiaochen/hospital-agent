"""Contracts for the pre-routing product-scope guard."""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from app.schemas.common import ApiSchema


class ScopeAction(str, Enum):
    """The only outcomes allowed before business workflow execution."""

    ALLOW = "allow"
    REJECT_OFF_TOPIC = "reject_off_topic"
    CLARIFY_SCOPE = "clarify_scope"


class ScopeDecision(ApiSchema):
    """A privacy-safe, deterministic decision from :class:`RequestScopeGuard`."""

    action: ScopeAction
    reason_code: str = Field(min_length=1, max_length=80)
    confidence: float | None = Field(default=None, ge=0, le=1)
    latency_ms: int = Field(default=0, ge=0)


__all__ = ["ScopeAction", "ScopeDecision"]
