from types import SimpleNamespace
from threading import Lock, get_ident
import time

from app.agent.model_gateway_schemas import ModelCallTrace, ModelProviderAttemptTrace
from app.rag.retrieval_schemas import RetrievedChunk
from app.rag.retriever import (
    Bm25CorpusIndex,
    _dedupe_sources,
    _filter_irrelevant_sources,
    _promote_document_head_sources,
    _rerank_sources,
    select_minimal_evidence_sources,
)
from scripts.rag_synthetic_eval import generate_corpus, generate_dataset
from scripts.run_synthetic_rag_full_eval import (
    FrozenKnowledgeSnapshot,
    LockedEmbeddingProvider,
    SyntheticAnswer,
    _ordered_parallel_map,
    _answer_row,
    _build_prompt,
    _retrieval_row,
    resolve_retrieval_profile,
)
from app.rag.embedding_provider import DeterministicHashEmbeddingProvider


def _successful_trace(query_id: str) -> ModelCallTrace:
    attempt = ModelProviderAttemptTrace(
        provider_name="openai_compatible",
        model_name="test-model",
        success=True,
        schema_valid=True,
        safety_passed=True,
        latency_ms=1,
    )
    return ModelCallTrace(
        run_id=f"test-{query_id}",
        task_id="test-task",
        member_id="synthetic-member-01",
        purpose="synthetic_rag_full_eval",
        requested_provider="openai_compatible",
        effective_provider="openai_compatible",
        success=True,
        schema_valid=True,
        safety_passed=True,
        latency_ms=1,
        attempts=(attempt,),
    )


def test_full_eval_answer_score_requires_gold_source_binding() -> None:
    corpus = generate_corpus(20260807)
    dataset = generate_dataset(corpus, 20260807)
    query = next(query for query in dataset.queries if query["case_type"] == "single_document")
    expected_chunk_id = query["answer_gold"]["supporting_chunk_ids"][0]
    result = SimpleNamespace(
        output=SyntheticAnswer(
            response_type="grounded_answer",
            answer="有来源的合成测试回答。",
            cited_chunk_ids=[expected_chunk_id],
            claim_texts=["synthetic claim"],
        ),
        trace=_successful_trace(query["query_id"]),
    )

    row = _answer_row(
        query,
        result=result,
        retrieved_ids=[expected_chunk_id],
        model_ms=1.0,
    )

    assert row["source_bound_answer_correct"] is True
    assert row["required_source_recall"] == 1.0
    assert row["supported_citation_precision"] == 1.0
    assert row["hallucination_detected"] is False


def test_full_eval_answer_score_flags_non_gold_citation() -> None:
    corpus = generate_corpus(20260807)
    dataset = generate_dataset(corpus, 20260807)
    query = next(query for query in dataset.queries if query["case_type"] == "single_document")
    expected_chunk_id = query["answer_gold"]["supporting_chunk_ids"][0]
    result = SimpleNamespace(
        output=SyntheticAnswer(
            response_type="grounded_answer",
            answer="有来源但混入非 gold 引用的测试回答。",
            cited_chunk_ids=[expected_chunk_id, "syn-rag-v1-chunk-999999"],
        ),
        trace=_successful_trace(query["query_id"]),
    )

    row = _answer_row(
        query,
        result=result,
        retrieved_ids=[expected_chunk_id, "syn-rag-v1-chunk-999999"],
        model_ms=1.0,
    )

    assert row["source_bound_answer_correct"] is False
    assert row["hallucination_detected"] is True
    assert row["unsupported_citation_ids"] == ["syn-rag-v1-chunk-999999"]


def test_faithfulness_prompt_allows_current_version_fact_after_filtering() -> None:
    corpus = generate_corpus(20260807)
    dataset = generate_dataset(corpus, 20260807)
    query = next(query for query in dataset.queries if query["case_type"] == "stale_version")

    system, _ = _build_prompt(
        query,
        [],
        minimal_citation=True,
        faithfulness_prompt_enabled=True,
    )

    assert "已经由检索层过滤为活动版本" in system
    assert "不要仅因正文没有逐字重复“现行要求”而选择 no_answer" in system


def _retrieved_chunk(
    chunk_id: str,
    *,
    chunk_index: int,
    content: str,
    rrf_score: float,
    matched_by: tuple[str, ...] = ("keyword", "vector"),
) -> RetrievedChunk:
    return RetrievedChunk(
        source_id=f"knowledge:doc-01:{chunk_id}",
        document_id="doc-01",
        chunk_id=chunk_id,
        document_version="1.0",
        chunk_version="1.0",
        title="测试规则",
        category="business_rule",
        source="synthetic:test",
        safety_level="test_only",
        chunk_index=chunk_index,
        content=content,
        keywords=["测试规则"],
        score=rrf_score,
        keyword_score=rrf_score if "keyword" in matched_by else None,
        vector_score=rrf_score if "vector" in matched_by else None,
        keyword_rank=1 if "keyword" in matched_by else None,
        vector_rank=1 if "vector" in matched_by else None,
        rrf_score=rrf_score,
        embedding_schema_version="rag-embedding-v1" if "vector" in matched_by else None,
        purpose="test",
        matched_by=matched_by,
    )


def test_m2_profile_filters_to_active_documents() -> None:
    corpus = generate_corpus(20260807)
    profile = resolve_retrieval_profile("m2-version-filter", corpus)

    assert profile.allowed_document_ids is not None
    assert len(profile.allowed_document_ids) == 100
    assert profile.candidate_limit is None
    assert profile.rerank_enabled is False
    assert profile.dedupe_enabled is False

    cost_profile = resolve_retrieval_profile("m4-cost", corpus)
    assert cost_profile.snapshot_cache_enabled is True
    assert cost_profile.max_output_tokens == 256

    dedupe_profile = resolve_retrieval_profile("m2-dedupe", corpus)
    assert dedupe_profile.candidate_limit is None
    assert dedupe_profile.dedupe_enabled is True

    hybrid_profile = resolve_retrieval_profile("m5-hybrid-rerank", corpus)
    assert hybrid_profile.keyword_scoring_strategy == "bm25"
    assert hybrid_profile.candidate_limit == 20
    assert hybrid_profile.rerank_enabled is True
    assert hybrid_profile.dedupe_enabled is True
    assert hybrid_profile.relevance_filter_enabled is True

    prompt_profile = resolve_retrieval_profile("m5-faithfulness-prompt", corpus)
    assert prompt_profile.rerank_enabled is False
    assert prompt_profile.evidence_gate_enabled is True


def test_m2_rerank_promotes_query_entity_without_gold() -> None:
    generic = _retrieved_chunk(
        "chunk-generic",
        chunk_index=0,
        content="这里是没有目标规则编号的相似说明。",
        rrf_score=0.04,
    )
    exact = _retrieved_chunk(
        "chunk-exact",
        chunk_index=1,
        content="测试规则 SYN-BUSINESS-01 的当前处理要求。",
        rrf_score=0.02,
    )

    ranked = _rerank_sources("请说明 SYN-BUSINESS-01 的处理要求", [generic, exact])

    assert [source.chunk_id for source in ranked] == ["chunk-exact", "chunk-generic"]


def test_bm25_snapshot_index_is_reused_for_filtered_records() -> None:
    corpus = generate_corpus(20260807)
    records = [
        SimpleNamespace(
            chunk_id=chunk["chunk_id"],
            document_id=chunk["document_id"],
            document_version="1.0",
            chunk_version=chunk["chunk_version"],
            title="测试规则",
            category="test",
            source="synthetic:test",
            safety_level="test_only",
            document_content="",
            chunk_index=chunk["chunk_index"],
            chunk_content=chunk["content"],
            keywords=tuple(chunk["keywords"]),
        )
        for chunk in corpus.chunks[:20]
    ]
    index = Bm25CorpusIndex.build(records)

    scored = index.score("SYN-BUSINESS-01", records)

    assert scored
    assert scored[0][0].chunk_id == records[0].chunk_id


def test_m2_dedupe_removes_exact_adjacent_duplicate_only() -> None:
    duplicate = _retrieved_chunk(
        "chunk-duplicate",
        chunk_index=1,
        content="测试规则 SYN-BUSINESS-01 的当前处理要求。",
        rrf_score=0.03,
    )
    original = _retrieved_chunk(
        "chunk-original",
        chunk_index=0,
        content="测试规则 SYN-BUSINESS-01 的当前处理要求。",
        rrf_score=0.04,
    )
    complementary = _retrieved_chunk(
        "chunk-complementary",
        chunk_index=2,
        content="测试规则 SYN-BUSINESS-01 的例外条件和补充步骤。",
        rrf_score=0.02,
    )

    deduped = _dedupe_sources(
        "请综合 SYN-BUSINESS-01 的处理要求",
        [original, duplicate, complementary],
    )

    assert [source.chunk_id for source in deduped] == [
        "chunk-original",
        "chunk-duplicate",
        "chunk-complementary",
    ]


def test_relevance_filter_removes_other_explicit_entity_without_gold() -> None:
    wrong = _retrieved_chunk(
        "chunk-wrong",
        chunk_index=0,
        content="测试规则 SYN-SAFETY-01 的当前要求。",
        rrf_score=0.05,
    )
    exact = _retrieved_chunk(
        "chunk-exact",
        chunk_index=1,
        content="测试规则 SYN-DRUG-01 的当前要求。",
        rrf_score=0.04,
    )

    filtered = _filter_irrelevant_sources(
        "请说明 SYN-DRUG-01 的处理要求",
        [wrong, exact],
    )

    assert [source.chunk_id for source in filtered] == ["chunk-exact"]


def test_document_head_promotion_prefers_requested_evidence_roles() -> None:
    tail = _retrieved_chunk(
        "chunk-tail",
        chunk_index=5,
        content="SYN-DRUG-01 的后续相似说明。",
        rrf_score=0.06,
    )
    head = _retrieved_chunk(
        "chunk-head",
        chunk_index=0,
        content="SYN-DRUG-01 的当前处理要求。",
        rrf_score=0.04,
    )
    step = _retrieved_chunk(
        "chunk-step",
        chunk_index=3,
        content="处理步骤：SYN-DRUG-01 先完成作用域检查，再读取必要证据。",
        rrf_score=0.03,
    )
    exception = _retrieved_chunk(
        "chunk-exception",
        chunk_index=7,
        content="例外路径：SYN-DRUG-01 在信息不足或来源冲突时请求补充信息。",
        rrf_score=0.03,
    )

    promoted = _promote_document_head_sources(
        "请综合 SYN-DRUG-01 的步骤和例外条件",
        [tail, head, exception, step],
    )

    assert [source.chunk_id for source in promoted] == [
        "chunk-step",
        "chunk-exception",
        "chunk-tail",
        "chunk-head",
    ]


def test_m3_evidence_gate_filters_wrong_entity_and_limits_context() -> None:
    wrong = _retrieved_chunk(
        "chunk-wrong",
        chunk_index=0,
        content="测试规则 SYN-SAFETY-01 的相似说明。",
        rrf_score=0.05,
    )
    first = _retrieved_chunk(
        "chunk-first",
        chunk_index=1,
        content="测试规则 SYN-DRUG-01 的处理结果。",
        rrf_score=0.04,
    )
    second = _retrieved_chunk(
        "chunk-second",
        chunk_index=2,
        content="测试规则 SYN-DRUG-01 的补充来源。",
        rrf_score=0.03,
    )
    third = _retrieved_chunk(
        "chunk-third",
        chunk_index=3,
        content="测试规则 SYN-DRUG-01 的无关相邻内容。",
        rrf_score=0.02,
    )

    single = select_minimal_evidence_sources(
        "请说明 SYN-DRUG-01 的处理要求",
        [wrong, first, second, third],
    )
    multiple = select_minimal_evidence_sources(
        "请综合 SYN-DRUG-01 的步骤和例外条件",
        [wrong, first, second, third],
    )
    missing = select_minimal_evidence_sources(
        "请说明 SYN-NOANSWER-999 的处理要求",
        [wrong, first, second, third],
    )

    assert [source.chunk_id for source in single] == ["chunk-first"]
    assert [source.chunk_id for source in multiple] == [
        "chunk-first",
        "chunk-second",
    ]
    assert missing == []


def test_evidence_gate_selects_one_source_per_requested_role() -> None:
    head = _retrieved_chunk(
        "chunk-head",
        chunk_index=0,
        content="SYN-DRUG-01 的当前处理要求。",
        rrf_score=0.05,
    )
    exception = _retrieved_chunk(
        "chunk-exception",
        chunk_index=7,
        content="SYN-DRUG-01 的例外条件是信息不足或来源冲突时请求补充信息。",
        rrf_score=0.03,
    )
    step = _retrieved_chunk(
        "chunk-step",
        chunk_index=3,
        content="SYN-DRUG-01 的处理步骤是先完成作用域检查，再读取必要证据。",
        rrf_score=0.02,
    )

    selected = select_minimal_evidence_sources(
        "请综合说明 SYN-DRUG-01 的处理步骤和例外条件",
        [head, exception, step],
    )

    assert [source.chunk_id for source in selected] == [
        "chunk-step",
        "chunk-exception",
    ]


def test_m4_profile_enables_only_run_scoped_snapshot_cache() -> None:
    corpus = generate_corpus(20260807)
    profile = resolve_retrieval_profile("m4-snapshot-cache", corpus)

    assert profile.snapshot_cache_enabled is True
    assert profile.evidence_gate_enabled is True
    assert profile.allowed_document_ids is not None
    assert profile.candidate_limit is None
    assert profile.rerank_enabled is False
    assert profile.dedupe_enabled is False


def test_retrieval_row_reports_binary_ndcg_for_frozen_chunk_gold() -> None:
    query = {
        "query_id": "query-ndcg",
        "base_case_id": "case-ndcg",
        "split": "validation",
        "variant_type": "canonical",
        "case_type": "single_document",
        "retrieval_gold": {
            "relevant_chunk_ids": ["relevant-1", "relevant-2"],
            "stale_chunk_ids": [],
        },
    }
    result = SimpleNamespace(
        sources=[
            _retrieved_chunk("irrelevant", chunk_index=0, content="无关", rrf_score=0.3),
            _retrieved_chunk("relevant-1", chunk_index=1, content="相关一", rrf_score=0.2),
            _retrieved_chunk("relevant-2", chunk_index=2, content="相关二", rrf_score=0.1),
        ],
        requested_mode="hybrid",
        effective_mode="hybrid",
        retrieval_provider="pgvector",
        embedding_model="test-embedding",
        embedding_dimension=384,
        embedding_schema_version="rag-embedding-v1",
        fallback_used=False,
        fallback_reason=None,
    )

    row = _retrieval_row(query, result, retrieval_ms=1.0)

    assert row["recall_at_3"] == 1.0
    assert row["precision_at_3"] == 0.6667
    assert row["mrr_at_10"] == 0.5
    assert row["ndcg_at_10"] == 0.6934


def test_parallel_rag_helpers_preserve_snapshot_and_embedding_contract() -> None:
    corpus = generate_corpus(20260807)
    records = [
        SimpleNamespace(chunk_id="chunk-a", document_id="doc-a"),
        SimpleNamespace(chunk_id="chunk-b", document_id="doc-b"),
    ]
    snapshot = FrozenKnowledgeSnapshot(records)
    assert [record.chunk_id for record in snapshot.list_records()] == [
        "chunk-a",
        "chunk-b",
    ]
    assert list(snapshot.records_by_chunk_ids(["chunk-b", "missing"])) == ["chunk-b"]

    provider = LockedEmbeddingProvider(
        DeterministicHashEmbeddingProvider(model_name="test", dimension=512)
    )
    assert len(provider.embed_query(corpus.documents[0]["title"])) == 512


def test_parallel_rag_mapper_runs_workers_concurrently_and_preserves_order() -> None:
    active = 0
    maximum = 0
    lock = Lock()
    thread_ids: set[int] = set()

    def worker(value: int) -> int:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            thread_ids.add(get_ident())
        time.sleep(0.02)
        with lock:
            active -= 1
        return value * 2

    assert _ordered_parallel_map([1, 2, 3, 4], worker, concurrency=4) == [2, 4, 6, 8]
    assert maximum > 1
    assert len(thread_ids) > 1
