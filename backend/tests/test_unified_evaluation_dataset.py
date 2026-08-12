import json

from scripts.build_unified_evaluation_dataset import (
    DATASET_REVISION,
    DATASET_VERSION,
    DEFAULT_OUTPUT_DIR,
    build_unified_evaluation_dataset,
)

def test_unified_dataset_merges_agent_rag_and_parameter_gold() -> None:
    manifest = build_unified_evaluation_dataset()

    validation = json.loads(
        (DEFAULT_OUTPUT_DIR / "validation.json").read_text(encoding="utf-8")
    )
    agent_queries = (DEFAULT_OUTPUT_DIR / "agent/queries.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()

    assert manifest["dataset_version"] == DATASET_VERSION
    assert manifest["dataset_revision"] == DATASET_REVISION
    assert manifest["future_evaluation_source_of_truth"] is True
    assert manifest["base_state_count"] == 225
    assert manifest["query_count"] == 900
    assert manifest["active_agent_profile"] == "fast-400"
    assert manifest["agent"]["world_state_count"] == 100
    assert manifest["agent"]["query_count"] == 400
    assert manifest["agent"]["tool_parameter_seed_case_count"] == 32
    assert manifest["agent"]["tool_parameter_seed_invocation_count"] == 48
    assert validation["passed"] is True
    assert len(agent_queries) == 400
    assert "expected_tool_invocations" in json.loads(agent_queries[0])
    rows = [json.loads(row) for row in agent_queries]
    blocked = [row for row in rows if row["expected_blocked"]]
    assert len(blocked) == 96
    assert all(row["expected_required_tools"] == [] for row in blocked)
    assert all(
        any(
            signal in row["user_input"]
            for signal in ("胸痛", "呼吸困难", "家庭成员", "他人", "过期", "旧版")
        )
        for row in blocked
    )
    reminder = next(
        row
        for row in rows
        if row["expected_intent"] == "reminder" and not row["expected_blocked"]
    )
    assert "query_health_profile" in reminder["expected_required_tools"]
    assert "notification_prepare_reminder" in reminder["expected_required_tools"]
    no_source = next(
        row for row in rows if row["world_state_id"] == "world-v2-0019"
    )
    assert no_source["expected_required_tools"] == [
        "query_health_profile",
        "query_medicine_box",
        "query_prescriptions",
        "search_safety_knowledge",
    ]
    assert "consultation_prepare_draft" not in no_source["expected_required_tools"]
    assert not any(
        "v2" in path.name
        for path in DEFAULT_OUTPUT_DIR.rglob("*")
        if path.is_file()
    )
