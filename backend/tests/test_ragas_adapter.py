import math

from pydantic import SecretStr

from app.agent.ragas_adapter import RagasEvaluationAdapter
from app.agent.ragas_schemas import RagasGenerationEvalInput
from app.core.config import Settings


def _input() -> RagasGenerationEvalInput:
    return RagasGenerationEvalInput(
        user_input="测试问题",
        response="测试回答",
        retrieved_contexts=("测试来源",),
        reference="测试参考答案",
    )


def _settings(**overrides: object) -> Settings:
    defaults: dict[str, object] = {
        "model_name": "target-model",
        "ragas_enabled": True,
        "ragas_version": "0.2.9",
        "ragas_judge_api_base": "https://judge.example/v1",
        "ragas_judge_api_key": SecretStr("test-key"),
        "ragas_judge_model": "independent-judge-model",
    }
    return Settings(**(defaults | overrides))


def test_ragas_adapter_skips_when_disabled_without_running_judge() -> None:
    called = False

    def runner(inputs: object, configuration: Settings) -> list[dict[str, float]]:
        nonlocal called
        called = True
        return []

    result = RagasEvaluationAdapter(
        configuration=_settings(ragas_enabled=False), runner=runner
    ).evaluate_batch([_input()])

    assert called is False
    assert result[0].status == "skipped"
    assert result[0].error == "ragas_disabled"


def test_ragas_adapter_scores_with_injected_offline_runner() -> None:
    def runner(
        inputs: object, configuration: Settings
    ) -> list[dict[str, float]]:
        return [
            {
                "faithfulness": 0.8,
                "answer_relevancy": 0.7,
                "context_recall": 0.9,
            }
        ]

    result = RagasEvaluationAdapter(
        configuration=_settings(), runner=runner
    ).evaluate_batch([_input()])

    assert result[0].status == "scored"
    assert result[0].faithfulness == 0.8
    assert result[0].response_relevancy == 0.7
    assert result[0].context_recall == 0.9


def test_ragas_adapter_keeps_partial_scores_when_one_metric_is_nan() -> None:
    def runner(
        inputs: object, configuration: Settings
    ) -> list[dict[str, float]]:
        return [
            {
                "faithfulness": 0.8,
                "answer_relevancy": math.nan,
                "context_recall": 0.9,
            }
        ]

    result = RagasEvaluationAdapter(
        configuration=_settings(), runner=runner
    ).evaluate_batch([_input()])

    assert result[0].status == "scored"
    assert result[0].faithfulness == 0.8
    assert result[0].response_relevancy is None
    assert result[0].context_recall == 0.9
    assert result[0].error == "ragas_metrics_unavailable:response_relevancy"


def test_ragas_adapter_marks_row_failed_when_all_metrics_are_nan() -> None:
    def runner(
        inputs: object, configuration: Settings
    ) -> list[dict[str, float]]:
        return [
            {
                "faithfulness": math.nan,
                "answer_relevancy": math.nan,
                "context_recall": math.nan,
            }
        ]

    result = RagasEvaluationAdapter(
        configuration=_settings(), runner=runner
    ).evaluate_batch([_input()])

    assert result[0].status == "failed"
    assert result[0].faithfulness is None
    assert result[0].response_relevancy is None
    assert result[0].context_recall is None


def test_ragas_adapter_failure_is_returned_not_raised() -> None:
    def runner(inputs: object, configuration: Settings) -> list[dict[str, float]]:
        raise RuntimeError("offline judge unavailable")

    result = RagasEvaluationAdapter(
        configuration=_settings(), runner=runner
    ).evaluate_batch([_input()])

    assert result[0].status == "failed"
    assert result[0].error == "ragas_evaluation_failed:RuntimeError:offline judge unavailable"


def test_ragas_adapter_rejects_self_judging_configuration() -> None:
    result = RagasEvaluationAdapter(
        configuration=_settings(ragas_judge_model="target-model")
    ).evaluate_batch([_input()])

    assert result[0].status == "skipped"
    assert result[0].error == "ragas_judge_must_differ_from_target"
