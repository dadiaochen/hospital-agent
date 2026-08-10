"""Derive entry, retrieval and answer views from one frozen synthetic query."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import Field

from app.agent.context_schemas import ContractModel, NonEmptyStr


class EntryHarnessView(ContractModel):
    query_id: NonEmptyStr
    base_case_id: NonEmptyStr
    split: NonEmptyStr
    user_input: NonEmptyStr
    expected_route: NonEmptyStr
    should_call_main_llm: bool


class RetrievalHarnessView(ContractModel):
    query_id: NonEmptyStr
    base_case_id: NonEmptyStr
    split: NonEmptyStr
    user_input: NonEmptyStr
    relevant_chunk_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    stale_chunk_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)
    answerable: bool


class AnswerHarnessView(ContractModel):
    query_id: NonEmptyStr
    base_case_id: NonEmptyStr
    split: NonEmptyStr
    user_input: NonEmptyStr
    expected_response_type: NonEmptyStr
    required_claims: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    supporting_chunk_ids: tuple[NonEmptyStr, ...] = Field(default_factory=tuple)


class SyntheticCaseHarnessAdapter:
    """Project frozen data without deriving Gold from a retriever result."""

    def build_views(
        self,
        queries: Iterable[Mapping[str, Any]],
    ) -> tuple[list[EntryHarnessView], list[RetrievalHarnessView], list[AnswerHarnessView]]:
        entry: list[EntryHarnessView] = []
        retrieval: list[RetrievalHarnessView] = []
        answer: list[AnswerHarnessView] = []
        for query in queries:
            flow = dict(query["expected_flow"])
            gold = dict(query["retrieval_gold"])
            answer_gold = dict(query["answer_gold"])
            common = {
                "query_id": str(query["query_id"]),
                "base_case_id": str(query["base_case_id"]),
                "split": str(query["split"]),
                "user_input": str(query["user_input"]),
            }
            entry.append(
                EntryHarnessView(
                    **common,
                    expected_route=str(flow["expected_route"]),
                    should_call_main_llm=bool(flow["should_call_main_llm"]),
                )
            )
            if bool(flow["should_call_rag"]):
                retrieval.append(
                    RetrievalHarnessView(
                        **common,
                        relevant_chunk_ids=tuple(gold["relevant_chunk_ids"]),
                        stale_chunk_ids=tuple(gold["stale_chunk_ids"]),
                        answerable=bool(gold["relevant_chunk_ids"]),
                    )
                )
            if bool(flow["should_call_main_llm"]):
                answer.append(
                    AnswerHarnessView(
                        **common,
                        expected_response_type=str(answer_gold["expected_response_type"]),
                        required_claims=tuple(answer_gold["required_claims"]),
                        supporting_chunk_ids=tuple(answer_gold["supporting_chunk_ids"]),
                    )
                )
        return entry, retrieval, answer


__all__ = [
    "AnswerHarnessView",
    "EntryHarnessView",
    "RetrievalHarnessView",
    "SyntheticCaseHarnessAdapter",
]
