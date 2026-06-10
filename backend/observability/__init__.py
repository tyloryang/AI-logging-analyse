"""可观测性子系统：脱敏 / Prometheus 计量 / OTEL trace。

三个模块都设计为"无依赖时优雅降级 no-op"，避免引入硬部署门槛。
"""
from .redact import redact, redact_dict  # noqa: F401
from .llm_metrics import (  # noqa: F401
    LLM_TOKEN_TOTAL,
    LLM_LATENCY,
    LLM_ERROR,
    metrics_response,
    record_tokens,
    observe_latency,
    record_error,
)
from .llm_tracing import llm_span  # noqa: F401
