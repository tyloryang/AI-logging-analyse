"""LLM 维度的 Prometheus 计量。

无 prometheus_client 时降级为 no-op，主进程仍可正常启动。
统一暴露 metrics_response() 给 FastAPI 路由用，避免每个 router 自己拼装。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        Counter,
        Histogram,
        generate_latest,
    )

    _ENABLED = True

    LLM_TOKEN_TOTAL = Counter(
        "aiops_llm_tokens_total",
        "LLM tokens used by provider/model/kind",
        ["provider", "model", "kind"],
    )
    LLM_LATENCY = Histogram(
        "aiops_llm_latency_seconds",
        "LLM call latency seconds",
        ["provider", "model", "op"],
        buckets=(0.5, 1, 2, 5, 10, 30, 60, 120, 300),
    )
    LLM_ERROR = Counter(
        "aiops_llm_errors_total",
        "LLM errors by provider/model/type",
        ["provider", "model", "type"],
    )

except ImportError:
    logger.info("[llm_metrics] prometheus_client 未安装，metrics 走 no-op 模式")
    _ENABLED = False
    CONTENT_TYPE_LATEST = "text/plain"  # type: ignore[assignment]
    REGISTRY = None  # type: ignore[assignment]

    class _NoopMetric:
        def labels(self, *_args: Any, **_kw: Any) -> "_NoopMetric":
            return self

        def inc(self, *_args: Any, **_kw: Any) -> None:  # noqa: D401
            return None

        def observe(self, *_args: Any, **_kw: Any) -> None:  # noqa: D401
            return None

    LLM_TOKEN_TOTAL = _NoopMetric()  # type: ignore[assignment]
    LLM_LATENCY = _NoopMetric()  # type: ignore[assignment]
    LLM_ERROR = _NoopMetric()  # type: ignore[assignment]

    def generate_latest(*_args: Any, **_kw: Any) -> bytes:  # type: ignore[no-redef]
        return b"# prometheus_client not installed\n"


def record_tokens(provider: str, model: str, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
    if prompt_tokens > 0:
        LLM_TOKEN_TOTAL.labels(provider=provider, model=model, kind="prompt").inc(prompt_tokens)
    if completion_tokens > 0:
        LLM_TOKEN_TOTAL.labels(provider=provider, model=model, kind="completion").inc(completion_tokens)


def observe_latency(provider: str, model: str, op: str, seconds: float) -> None:
    LLM_LATENCY.labels(provider=provider, model=model, op=op).observe(max(0.0, seconds))


def record_error(provider: str, model: str, error_type: str) -> None:
    LLM_ERROR.labels(provider=provider, model=model, type=error_type or "unknown").inc()


def metrics_response() -> tuple[bytes, str]:
    """返回 (body, content_type)，供 FastAPI 直接构造 Response。"""
    body = generate_latest(REGISTRY) if _ENABLED else generate_latest()
    return body, CONTENT_TYPE_LATEST


__all__ = [
    "LLM_TOKEN_TOTAL",
    "LLM_LATENCY",
    "LLM_ERROR",
    "record_tokens",
    "observe_latency",
    "record_error",
    "metrics_response",
]
