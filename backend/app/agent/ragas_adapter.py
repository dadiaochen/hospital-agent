"""Optional, post-run-only adapter for pinned RAGAS generation metrics.

The module intentionally has no top-level ``ragas`` import.  Online business
paths can import this module safely even when the optional package or its judge
configuration is unavailable.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import math
from time import perf_counter
from typing import Any

from app.agent.ragas_schemas import (
    RagasGenerationEvalInput,
    RagasGenerationEvalResult,
)
from app.core.config import Settings, settings


RagasRunner = Callable[[Sequence[RagasGenerationEvalInput], Settings], list[dict[str, Any]]]


class RagasEvaluationAdapter:
    """Run semantic RAG checks without letting evaluator failures affect runs."""

    def __init__(
        self,
        *,
        configuration: Settings = settings,
        runner: RagasRunner | None = None,
    ) -> None:
        self._settings = configuration
        self._runner = runner or _run_ragas_v029

    def evaluate_batch(
        self,
        inputs: Sequence[RagasGenerationEvalInput],
    ) -> list[RagasGenerationEvalResult]:
        if not inputs:
            return []
        if not self._settings.ragas_enabled:
            return self._same_result(inputs, status="skipped", error="ragas_disabled")
        if not self._settings.ragas_judge_api_base or self._settings.ragas_judge_api_key is None:
            return self._same_result(inputs, status="skipped", error="ragas_not_configured")
        if not self._settings.ragas_judge_model:
            return self._same_result(inputs, status="skipped", error="ragas_judge_model_missing")
        if self._settings.ragas_judge_model == self._settings.model_name:
            return self._same_result(inputs, status="skipped", error="ragas_judge_must_differ_from_target")

        started = perf_counter()
        try:
            raw_results = self._runner(inputs, self._settings)
            if len(raw_results) != len(inputs):
                raise ValueError("ragas_result_count_mismatch")
            latency_ms = max(0, round((perf_counter() - started) * 1000))
            results: list[RagasGenerationEvalResult] = []
            for row in raw_results:
                faithfulness = _score(row, "faithfulness")
                response_relevancy = _score(
                    row, "response_relevancy", "answer_relevancy"
                )
                context_recall = _score(row, "context_recall")
                available = {
                    "faithfulness": faithfulness,
                    "response_relevancy": response_relevancy,
                    "context_recall": context_recall,
                }
                missing = [name for name, value in available.items() if value is None]
                has_score = len(missing) < len(available)
                results.append(
                    RagasGenerationEvalResult(
                        faithfulness=faithfulness,
                        response_relevancy=response_relevancy,
                        context_recall=context_recall,
                        evaluator_model=self._settings.ragas_judge_model,
                        ragas_version=self._settings.ragas_version,
                        status="scored" if has_score else "failed",
                        latency_ms=latency_ms,
                        error=(
                            f"ragas_metrics_unavailable:{','.join(missing)}"
                            if missing
                            else None
                        ),
                    )
                )
            return results
        except Exception as exc:  # Offline evaluator failure must be non-blocking.
            detail = str(exc).replace("\n", " ").strip()[:240]
            return self._same_result(
                inputs,
                status="failed",
                error=(
                    f"ragas_evaluation_failed:{exc.__class__.__name__}"
                    + (f":{detail}" if detail else "")
                ),
                latency_ms=max(0, round((perf_counter() - started) * 1000)),
            )

    def _same_result(
        self,
        inputs: Sequence[RagasGenerationEvalInput],
        *,
        status: str,
        error: str,
        latency_ms: int = 0,
    ) -> list[RagasGenerationEvalResult]:
        model_name = self._settings.ragas_judge_model or "not_configured"
        return [
            RagasGenerationEvalResult(
                evaluator_model=model_name,
                ragas_version=self._settings.ragas_version,
                status=status,  # type: ignore[arg-type]
                latency_ms=latency_ms,
                error=error,
            )
            for _ in inputs
        ]


def _score(row: dict[str, Any], *names: str) -> float | None:
    for name in names:
        value = row.get(name)
        if value is not None:
            score = float(value)
            return score if math.isfinite(score) else None
    return None


def _run_ragas_v029(
    inputs: Sequence[RagasGenerationEvalInput],
    configuration: Settings,
) -> list[dict[str, Any]]:
    """Adapt the pinned RAGAS 0.2.9 surface only inside the offline adapter."""

    from ragas import EvaluationDataset, SingleTurnSample, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import Faithfulness, LLMContextRecall, ResponseRelevancy
    from ragas.run_config import RunConfig
    from langchain_openai import ChatOpenAI

    api_key = configuration.ragas_judge_api_key.get_secret_value()
    evaluator_llm = LangchainLLMWrapper(
        ChatOpenAI(
            model=configuration.ragas_judge_model,
            api_key=api_key,
            base_url=configuration.ragas_judge_api_base,
            temperature=0.0,
            timeout=configuration.ragas_timeout_seconds,
        )
    )
    if configuration.ragas_embedding_provider == "fastembed":
        from langchain_community.embeddings import FastEmbedEmbeddings

        raw_embeddings = FastEmbedEmbeddings(
            model_name=(
                configuration.ragas_embedding_model
                or configuration.rag_embedding_model
            ),
            cache_dir=configuration.rag_embedding_cache_dir,
        )
    else:
        from langchain_openai import OpenAIEmbeddings

        raw_embeddings = OpenAIEmbeddings(
            api_key=api_key,
            base_url=configuration.ragas_judge_api_base,
            model=configuration.ragas_embedding_model or "text-embedding-3-small",
            timeout=configuration.model_timeout_ms / 1000,
        )
    evaluator_embeddings = LangchainEmbeddingsWrapper(raw_embeddings)
    dataset = EvaluationDataset(
        samples=[
            SingleTurnSample(
                user_input=item.user_input,
                response=item.response,
                retrieved_contexts=list(item.retrieved_contexts),
                reference=item.reference,
            )
            for item in inputs
        ]
    )
    evaluated = evaluate(
        dataset=dataset,
        metrics=[Faithfulness(), ResponseRelevancy(), LLMContextRecall()],
        llm=evaluator_llm,
        embeddings=evaluator_embeddings,
        run_config=RunConfig(
            timeout=configuration.ragas_timeout_seconds,
            max_retries=2,
            max_workers=configuration.ragas_max_workers,
        ),
        raise_exceptions=False,
        show_progress=False,
        batch_size=configuration.ragas_batch_size,
    )
    return [dict(item) for item in evaluated.scores]


__all__ = ["RagasEvaluationAdapter", "RagasRunner"]
