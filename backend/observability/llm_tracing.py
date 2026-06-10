"""OpenTelemetry-style 的 LLM span 上下文管理器。

按 2026 半标准 gen_ai.* attribute 命名（system/request.model/operation.name/
prompt/completion.length/latency_ms/error.type），Jaeger / Tempo / SkyWalking 都能识别。

无 opentelemetry-api 时降级为简单计时器 + 结构化日志，不阻塞主流程。
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncIterator, Iterator

from .redact import redact

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace  # type: ignore[import-not-found]

    _tracer = trace.get_tracer("aiops.llm")
    _OTEL_ENABLED = True
except ImportError:
    logger.info("[llm_tracing] opentelemetry 未安装，span 走结构化日志模式")
    _tracer = None
    _OTEL_ENABLED = False


_MAX_PROMPT_ATTR_CHARS = 8000  # span attribute 上限，超出截断


class _LogSpan:
    """OTEL 不可用时的兜底 span，攒一个 dict 在 __exit__ 时一次性 INFO 日志输出。"""

    def __init__(self) -> None:
        self._attrs: dict[str, Any] = {}
        self._error: Exception | None = None

    def set_attribute(self, key: str, value: Any) -> None:
        self._attrs[key] = value

    def record_exception(self, exc: Exception) -> None:
        self._error = exc

    def emit(self) -> None:
        if self._error is not None:
            logger.warning("[gen_ai] span error=%s attrs=%s", self._error, self._attrs)
        else:
            logger.info("[gen_ai] %s", self._attrs)


@asynccontextmanager
async def llm_span(
    provider: str,
    model: str,
    op: str = "stream",
) -> AsyncIterator[dict[str, Any]]:
    """async 版本 LLM span 上下文。

    yield 一个 ctx dict：
      - ctx["set"](key, value): 设置 attribute（自动脱敏字符串）
      - ctx["record_prompt"](text): 写 gen_ai.prompt（脱敏+截断）
      - ctx["record_completion_chars"](n): 增量累计 completion 字符数

    退出时自动写 gen_ai.latency_ms 与 gen_ai.completion.length。
    """
    started_at = time.perf_counter()
    completion_chars = {"count": 0}

    if _OTEL_ENABLED and _tracer is not None:
        cm = _tracer.start_as_current_span(f"llm.{op}")  # type: ignore[union-attr]
        span = cm.__enter__()
    else:
        cm = None
        span = _LogSpan()

    span.set_attribute("gen_ai.system", provider)
    span.set_attribute("gen_ai.request.model", model)
    span.set_attribute("gen_ai.operation.name", op)

    def _set(key: str, value: Any) -> None:
        if isinstance(value, str):
            value = redact(value)
        span.set_attribute(key, value)

    def _record_prompt(text: str) -> None:
        redacted = redact(text)
        if len(redacted) > _MAX_PROMPT_ATTR_CHARS:
            redacted = redacted[:_MAX_PROMPT_ATTR_CHARS] + "...<truncated>"
        span.set_attribute("gen_ai.prompt", redacted)
        span.set_attribute("gen_ai.prompt.length", len(text))

    def _record_completion_chars(n: int) -> None:
        completion_chars["count"] += max(0, int(n))

    ctx: dict[str, Any] = {
        "span": span,
        "set": _set,
        "record_prompt": _record_prompt,
        "record_completion_chars": _record_completion_chars,
        "provider": provider,
        "model": model,
        "op": op,
        "started_at": started_at,
    }

    try:
        yield ctx
    except Exception as exc:
        span.set_attribute("error.type", type(exc).__name__)
        if hasattr(span, "record_exception"):
            span.record_exception(exc)
        raise
    finally:
        elapsed = time.perf_counter() - started_at
        span.set_attribute("gen_ai.latency_ms", round(elapsed * 1000, 2))
        span.set_attribute("gen_ai.completion.length", completion_chars["count"])
        ctx["latency_seconds"] = elapsed
        ctx["completion_chars"] = completion_chars["count"]
        if cm is not None:
            cm.__exit__(None, None, None)
        elif isinstance(span, _LogSpan):
            span.emit()


@contextmanager
def llm_span_sync(provider: str, model: str, op: str = "call") -> Iterator[dict[str, Any]]:
    """同步版本（给非 async 调用点用）。功能与 llm_span 相同。"""
    started_at = time.perf_counter()
    completion_chars = {"count": 0}

    if _OTEL_ENABLED and _tracer is not None:
        cm = _tracer.start_as_current_span(f"llm.{op}")  # type: ignore[union-attr]
        span = cm.__enter__()
    else:
        cm = None
        span = _LogSpan()

    span.set_attribute("gen_ai.system", provider)
    span.set_attribute("gen_ai.request.model", model)
    span.set_attribute("gen_ai.operation.name", op)

    ctx: dict[str, Any] = {
        "span": span,
        "set": lambda k, v: span.set_attribute(k, redact(v) if isinstance(v, str) else v),
        "record_completion_chars": lambda n: completion_chars.__setitem__(
            "count", completion_chars["count"] + max(0, int(n))
        ),
        "provider": provider,
        "model": model,
        "op": op,
        "started_at": started_at,
    }

    try:
        yield ctx
    except Exception as exc:
        span.set_attribute("error.type", type(exc).__name__)
        if hasattr(span, "record_exception"):
            span.record_exception(exc)
        raise
    finally:
        elapsed = time.perf_counter() - started_at
        span.set_attribute("gen_ai.latency_ms", round(elapsed * 1000, 2))
        span.set_attribute("gen_ai.completion.length", completion_chars["count"])
        ctx["latency_seconds"] = elapsed
        if cm is not None:
            cm.__exit__(None, None, None)
        elif isinstance(span, _LogSpan):
            span.emit()


__all__ = ["llm_span", "llm_span_sync"]
