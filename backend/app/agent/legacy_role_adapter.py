"""Explicit boundary between canonical domain roles and legacy roles.

The current product path uses three domain Agents: TriageAgent,
MedicationAgent and ReportAgent.  The older ``/api/agent-runs`` compatibility
workflow still emits ProfileAgent/RefillAgent/PharmacyAgent/ReminderAgent
names.  This module makes that compatibility vocabulary explicit instead of
letting it leak into the new Supervisor registry or business plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.agent.orchestration_schemas import DomainAgentRole


CompatibilityLayer = Literal["domain", "legacy_skill", "governance", "planning"]


@dataclass(frozen=True)
class RoleMapping:
    """One immutable role translation at a compatibility boundary."""

    input_role: str
    canonical_role: DomainAgentRole | None
    skill: str | None
    layer: CompatibilityLayer


_CANONICAL_ROLES: frozenset[str] = frozenset(
    {"TriageAgent", "MedicationAgent", "ReportAgent"}
)
_LEGACY_SKILLS: dict[str, str] = {
    "ProfileAgent": "profile_lookup",
    "RefillAgent": "refill_material_preparation",
    "PharmacyAgent": "pharmacy_lookup",
    "ReminderAgent": "reminder_draft_preparation",
}


def map_role(role: str) -> RoleMapping:
    """Translate one role or fail closed for an unknown vocabulary value."""

    if role in _CANONICAL_ROLES:
        return RoleMapping(
            input_role=role,
            canonical_role=role,  # type: ignore[arg-type]
            skill=None,
            layer="domain",
        )
    if role in _LEGACY_SKILLS:
        return RoleMapping(
            input_role=role,
            canonical_role="MedicationAgent",
            skill=_LEGACY_SKILLS[role],
            layer="legacy_skill",
        )
    if role == "SafetyAgent":
        return RoleMapping(
            input_role=role,
            canonical_role=None,
            skill=None,
            layer="governance",
        )
    if role == "Planner":
        return RoleMapping(
            input_role=role,
            canonical_role=None,
            skill=None,
            layer="planning",
        )
    raise ValueError(f"unknown agent role: {role}")


def canonical_domain_role(role: str) -> DomainAgentRole:
    """Return a domain role for business execution, rejecting governance."""

    mapping = map_role(role)
    if mapping.canonical_role is None:
        raise ValueError(f"role is not a domain execution role: {role}")
    return mapping.canonical_role


def is_canonical_domain_role(role: str) -> bool:
    """Return whether ``role`` is one of the three product domain roles."""

    return role in _CANONICAL_ROLES


__all__ = [
    "RoleMapping",
    "canonical_domain_role",
    "is_canonical_domain_role",
    "map_role",
]
