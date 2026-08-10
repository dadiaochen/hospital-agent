"""Deterministic product-scope guard executed before medical safety checks."""

from __future__ import annotations

from time import perf_counter

from app.schemas.request_scope import ScopeAction, ScopeDecision


_HEALTH_SIGNALS = (
    "健康",
    "症状",
    "胸痛",
    "胸闷",
    "呼吸",
    "发烧",
    "发热",
    "疼",
    "痛",
    "难受",
    "用药",
    "药品",
    "药物",
    "处方",
    "续方",
    "复诊",
    "医院",
    "医生",
    "检查",
    "报告",
    "化验",
    "指标",
    "过敏",
    "血压",
    "血糖",
    "血常规",
    "药箱",
    "reminder",
    "medicine",
    "medical",
    "symptom",
    "prescription",
)

_AMBIGUOUS_INPUTS = {
    "帮我看看",
    "看看",
    "怎么了",
    "怎么办",
    "有点难受",
    "这正常吗",
    "正常吗",
}

_OFF_TOPIC_SIGNALS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("weather_request", ("天气", "气温", "下雨", "降雨", "天气预报")),
    (
        "programming_request",
        ("python", "javascript", "编程", "代码", "算法", "调试", "bug", "sql"),
    ),
    (
        "finance_request",
        ("股票", "基金", "a股", "涨停", "买入", "卖出", "比特币"),
    ),
    (
        "travel_request",
        ("旅游", "旅行", "攻略", "景点", "酒店", "机票", "行程"),
    ),
    (
        "entertainment_request",
        ("电影", "电视剧", "明星", "游戏", "小说", "娱乐新闻"),
    ),
)

_NON_MEDICAL_WRITING_SIGNALS = ("写作文", "写文案", "写邮件", "写诗", "请假条")


class RequestScopeGuard:
    """Keep high-confidence non-health requests out of the business graph.

    This is deliberately independent from ``RequestSafetyGuard``: product
    scope answers whether the request belongs to this family-health product;
    medical safety answers whether an in-scope request can proceed safely.
    The guard defaults to ``ALLOW`` so a missed pattern cannot suppress a
    potentially relevant health request.
    """

    def evaluate(self, user_input: str) -> ScopeDecision:
        started = perf_counter()
        normalized = self._normalize(user_input)
        has_health_signal = any(signal in normalized for signal in _HEALTH_SIGNALS)

        if normalized in _AMBIGUOUS_INPUTS:
            action = ScopeAction.CLARIFY_SCOPE
            reason_code = "ambiguous_health_intent"
            confidence = 0.9
        elif not has_health_signal:
            reason_code = self._off_topic_reason(normalized)
            if reason_code is not None:
                action = ScopeAction.REJECT_OFF_TOPIC
                confidence = 0.98
            else:
                action = ScopeAction.ALLOW
                reason_code = "conservative_default_allow"
                confidence = None
        else:
            action = ScopeAction.ALLOW
            reason_code = "health_signal_present"
            confidence = 0.98

        return ScopeDecision(
            action=action,
            reason_code=reason_code,
            confidence=confidence,
            latency_ms=max(0, round((perf_counter() - started) * 1000)),
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join((value or "").casefold().split())

    @staticmethod
    def _off_topic_reason(normalized: str) -> str | None:
        for reason_code, signals in _OFF_TOPIC_SIGNALS:
            if any(signal in normalized for signal in signals):
                return reason_code
        if any(signal in normalized for signal in _NON_MEDICAL_WRITING_SIGNALS):
            return "non_medical_writing_request"
        return None


__all__ = ["RequestScopeGuard"]
