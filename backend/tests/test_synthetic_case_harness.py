from app.agent.synthetic_case_harness import SyntheticCaseHarnessAdapter
from scripts.rag_synthetic_eval import generate_corpus, generate_dataset


def test_frozen_synthetic_dataset_projects_three_independent_views() -> None:
    corpus = generate_corpus(20260807)
    dataset = generate_dataset(corpus, 20260807)

    entry, retrieval, answer = SyntheticCaseHarnessAdapter().build_views(
        dataset.queries
    )

    assert len(dataset.cases) == 125
    assert len(dataset.queries) == 500
    assert len(entry) == 500
    assert len(retrieval) == sum(
        query["expected_flow"]["should_call_rag"] for query in dataset.queries
    )
    assert len(answer) == sum(
        query["expected_flow"]["should_call_main_llm"] for query in dataset.queries
    )
    assert {item.query_id for item in entry} == {
        query["query_id"] for query in dataset.queries
    }
    assert {item.base_case_id for item in entry if item.split == "holdout"} == {
        query["base_case_id"]
        for query in dataset.queries
        if query["split"] == "holdout"
    }
