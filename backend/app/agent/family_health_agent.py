from pydantic import BaseModel, Field


class FamilyHealthState(BaseModel):
    user_id: str | None = None
    member_id: str | None = None
    user_message: str
    intent: str | None = None
    need_human_confirmation: bool = False
    safety_result: dict[str, str] = Field(default_factory=dict)
    final_answer: str | None = None


class FamilyHealthAgent:
    name = "FamilyHealthAgent"
    workflow_nodes = [
        "intent_recognition",
        "load_profile",
        "load_medication_context",
        "estimate_remaining_days",
        "check_prescription_validity",
        "generate_refill_plan",
        "check_pharmacy_inventory",
        "human_confirmation",
        "create_tasks",
        "persist_agent_run",
    ]

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "phase": "phase-1-skeleton",
            "workflow_nodes": self.workflow_nodes,
            "medical_boundary": "no diagnosis, no automatic prescription, no prescription modification",
        }

