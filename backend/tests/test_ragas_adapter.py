import math

import pytest
from pydantic import SecretStr

from app.agent.ragas_adapter import RagasEvaluationAdapter, _judge_extra_body
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
        "ragas_judge_thinking_mode": "disabled",
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


def test_target_and_judge_settings_are_loaded_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MODEL_API_BASE", "https://target.example/v1")
    monkeypatch.setenv("MODEL_API_KEY", "target-secret")
    monkeypatch.setenv("MODEL_NAME", "target-model")
    monkeypatch.setenv("RAGAS_JUDGE_API_BASE", "https://judge.example/v1")
    monkeypatch.setenv("RAGAS_JUDGE_API_KEY", "judge-secret")
    monkeypatch.setenv("RAGAS_JUDGE_MODEL", "judge-model")
    monkeypatch.setenv("RAGAS_JUDGE_THINKING_MODE", "disabled")

    configured = Settings()

    assert configured.model_api_base == "https://target.example/v1"
    assert configured.model_api_key is not None
    assert configured.model_api_key.get_secret_value() == "target-secret"
    assert configured.model_name == "target-model"
    assert configured.ragas_judge_api_base == "https://judge.example/v1"
    assert configured.ragas_judge_api_key is not None
    assert configured.ragas_judge_api_key.get_secret_value() == "judge-secret"
    assert configured.ragas_judge_model == "judge-model"
    assert configured.ragas_judge_thinking_mode == "disabled"
    assert "target-secret" not in repr(configured)
    assert "judge-secret" not in repr(configured)


def test_judge_thinking_mode_maps_to_qwen_compatible_body() -> None:
    assert _judge_extra_body(_settings(ragas_judge_thinking_mode="disabled")) == {
        "enable_thinking": False
    }
    assert _judge_extra_body(_settings(ragas_judge_thinking_mode="enabled")) == {
        "enable_thinking": True
    }
    assert _judge_extra_body(_settings(ragas_judge_thinking_mode="default")) is None
