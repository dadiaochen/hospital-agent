from __future__ import annotations

import pytest

from app.agent.legacy_role_adapter import (
    canonical_domain_role,
    is_canonical_domain_role,
    map_role,
)


@pytest.mark.parametrize("role", ["TriageAgent", "MedicationAgent", "ReportAgent"])
def test_canonical_roles_are_the_only_domain_execution_roles(role: str) -> None:
    mapping = map_role(role)

    assert mapping.layer == "domain"
    assert mapping.canonical_role == role
    assert mapping.skill is None
    assert is_canonical_domain_role(role) is True


@pytest.mark.parametrize(
    ("legacy_role", "skill"),
    [
        ("ProfileAgent", "profile_lookup"),
        ("RefillAgent", "refill_material_preparation"),
        ("PharmacyAgent", "pharmacy_lookup"),
        ("ReminderAgent", "reminder_draft_preparation"),
    ],
)
def test_legacy_roles_map_to_medication_skills(
    legacy_role: str,
    skill: str,
) -> None:
    mapping = map_role(legacy_role)

    assert mapping.layer == "legacy_skill"
    assert mapping.canonical_role == "MedicationAgent"
    assert mapping.skill == skill
    assert canonical_domain_role(legacy_role) == "MedicationAgent"


@pytest.mark.parametrize("role, layer", [("SafetyAgent", "governance"), ("Planner", "planning")])
def test_governance_and_planning_roles_cannot_become_domain_agents(
    role: str,
    layer: str,
) -> None:
    mapping = map_role(role)

    assert mapping.layer == layer
    assert mapping.canonical_role is None
    with pytest.raises(ValueError, match="not a domain"):
        canonical_domain_role(role)


def test_unknown_role_fails_closed() -> None:
    with pytest.raises(ValueError, match="unknown agent role"):
        map_role("UnknownAgent")

