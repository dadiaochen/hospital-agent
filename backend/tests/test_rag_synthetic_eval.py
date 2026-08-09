from collections import Counter

from scripts.rag_synthetic_eval import (
    SCENARIO_COUNTS,
    SPLIT_COUNTS,
    VARIANTS,
    generate_corpus,
    generate_dataset,
    validate_bundle,
)


def test_synthetic_rag_fast_bundle_has_frozen_shape_and_isolation() -> None:
    corpus = generate_corpus(20260807)
    dataset = generate_dataset(corpus, 20260807)
    validation = validate_bundle(corpus, dataset)

    assert validation["passed"] is True
    assert len(corpus.documents) == 120
    assert len(corpus.chunks) >= 1800
    assert len(dataset.cases) == 125
    assert len(dataset.queries) == 500
    assert Counter(case["case_type"] for case in dataset.cases) == Counter(SCENARIO_COUNTS)
    assert Counter(case["split"] for case in dataset.cases) == Counter(SPLIT_COUNTS)
    assert all(not case["human_reviewed"] and case["clinical_gold"] is False for case in dataset.cases)
    assert all(
        {query["variant_type"] for query in dataset.queries if query["base_case_id"] == case["base_case_id"]}
        == set(VARIANTS)
        for case in dataset.cases
    )


def test_synthetic_rag_gold_is_source_first_and_no_answer_anchor_is_absent() -> None:
    corpus = generate_corpus(20260807)
    dataset = generate_dataset(corpus, 20260807)
    chunk_ids = {chunk["chunk_id"] for chunk in corpus.chunks}
    active_document_ids = {doc["document_id"] for doc in corpus.documents if doc["status"] == "active"}
    active_chunk_ids = {
        chunk["chunk_id"]
        for chunk in corpus.chunks
        if chunk["document_id"] in active_document_ids
    }

    for case in dataset.cases:
        retrieval = case["retrieval_gold"]
        assert set(retrieval["relevant_chunk_ids"]).issubset(chunk_ids)
        if case["case_type"] in {"single_document", "multi_chunk_hard_negative", "stale_version"}:
            assert set(retrieval["relevant_chunk_ids"]).issubset(active_chunk_ids)
        if case["case_type"] == "rag_no_answer":
            assert retrieval["relevant_chunk_ids"] == []
            assert case["protected_slots"]["anchor"] not in " ".join(doc["content"] for doc in corpus.documents)
