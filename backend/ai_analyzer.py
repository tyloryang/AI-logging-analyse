"""AI 分析器 - 支持 Anthropic Claude 和 OpenAI 兼容接口（Qwen3 等本地模型）"""
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import AsyncIterator


# ─────────────────────────────────────────
# Provider 抽象基类
# ─────────────────────────────────────────

class BaseAIProvider(ABC):
    @abstractmethod
    async def stream(self, prompt: str, max_tokens: int = 2048) -> AsyncIterator[str]:
        """流式输出文本"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称"""


# ─────────────────────────────────────────
# Anthropic Provider
# ─────────────────────────────────────────

class AnthropicProvider(BaseAIProvider):
    def __init__(self, api_key: str, model: str):
        import anthropic
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model or "claude-opus-4-6"

    @property
    def name(self) -> str:
        return f"Anthropic ({self.model})"

    async def stream(self, prompt: str, max_tokens: int = 2048) -> AsyncIterator[str]:
        async with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        ) as s:
            async for text in s.text_stream:
                yield text


# ─────────────────────────────────────────
# OpenAI 兼容 Provider（Qwen3/vLLM/Ollama/LM Studio 等）
# ─────────────────────────────────────────

class OpenAICompatProvider(BaseAIProvider):
    def __init__(self, base_url: str, api_key: str, model: str, wire_api: str = "chat"):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "EMPTY",   # 本地模型通常不需要 key，传占位符
        )
        self.model = model
        self.wire_api = wire_api  # "chat" = /chat/completions, "responses" = /responses

    @property
    def name(self) -> str:
        return f"OpenAI-compatible ({self.model}, {self.wire_api})"

    async def stream(self, prompt: str, max_tokens: int = 2048) -> AsyncIterator[str]:
        if self.wire_api == "responses":
            # OpenAI Responses API (/v1/responses)
            response = await self.client.responses.create(
                model=self.model,
                input=[{"role": "user", "content": prompt}],
                stream=True,
            )
            async for event in response:
                if event.type == "response.output_text.delta":
                    yield event.delta
        else:
            # Chat Completions API (/v1/chat/completions)
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                stream=True,
                messages=[{"role": "user", "content": prompt}],
            )
            async for chunk in response:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta


# ─────────────────────────────────────────
# Provider 工厂
# ─────────────────────────────────────────

def create_provider() -> BaseAIProvider:
    """
    根据环境变量自动选择 Provider：

    AI_PROVIDER=anthropic  →  使用 Anthropic Claude
      ANTHROPIC_API_KEY=sk-ant-xxx
      AI_MODEL=claude-opus-4-6         （可选，默认 claude-opus-4-6）

    AI_PROVIDER=openai     →  使用 OpenAI 兼容接口（本地模型等）
      AI_BASE_URL=http://192.168.x.x:8000/v1
      AI_API_KEY=                      （本地模型可留空）
      AI_MODEL=gpt-5
    """
    provider = os.getenv("AI_PROVIDER", "anthropic").lower()

    import logging
    _log = logging.getLogger(__name__)
    _log.info("[AI] AI_PROVIDER=%s", provider)

    if provider == "openai":
        base_url = os.getenv("AI_BASE_URL", "")
        api_key  = os.getenv("AI_API_KEY", "EMPTY")
        model    = os.getenv("AI_MODEL", "gpt-5")
        wire_api = os.getenv("AI_WIRE_API", "chat")  # "chat" 或 "responses"
        _log.info("[AI] base_url=%s, model=%s, wire_api=%s", base_url, model, wire_api)
        if not base_url:
            raise ValueError("AI_PROVIDER=openai 时必须设置 AI_BASE_URL")
        return OpenAICompatProvider(base_url, api_key, model, wire_api)

    # 默认 Anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    model   = os.getenv("AI_MODEL", "claude-opus-4-6")
    if not api_key:
        raise ValueError("AI_PROVIDER=anthropic 时必须设置 ANTHROPIC_API_KEY")
    return AnthropicProvider(api_key, model)


# ─────────────────────────────────────────
# 主分析器
# ─────────────────────────────────────────

class AIAnalyzer:
    def __init__(self):
        self._provider: BaseAIProvider | None = None

    @property
    def provider(self) -> BaseAIProvider:
        if self._provider is None:
            self._provider = create_provider()
        return self._provider

    @property
    def provider_name(self) -> str:
        try:
            return self.provider.name
        except Exception as e:
            return f"未配置 ({e})"

    async def analyze_logs_stream(
        self,
        logs: list[dict],
        service: str = "",
        extra_context: str = "",
    ) -> AsyncIterator[str]:
        """流式分析日志"""
        sample = logs[:200]
        log_text = "\n".join(f"[{l['timestamp']}] {l['line'][:200]}" for l in sample)

        prompt = f"""你是一名资深 SRE（网站可靠性工程师），请对以下{'服务 ' + service + ' 的' if service else ''}日志进行深度分析。

日志样本（共 {len(logs)} 条，展示前 {len(sample)} 条）：
```
{log_text}
```
{('额外上下文：' + extra_context) if extra_context else ''}

请提供：
1. **错误模式识别** - 识别主要错误类型和出现规律
2. **根因分析** - 推断可能的根本原因
3. **影响评估** - 判断对系统稳定性的影响程度
4. **优化建议** - 具体的修复和预防措施
5. **优先级排序** - 哪些问题需要立即处理

请用简洁专业的中文回答，重点突出关键问题。"""

        async for chunk in self.provider.stream(prompt, max_tokens=2048):
            yield chunk

    async def generate_daily_report(
        self,
        error_counts: dict[str, int],
        total_logs: int,
        service_count: int,
        node_status: dict,
        active_alerts: int,
        sample_errors: list[dict],
    ) -> AsyncIterator[str]:
        """流式生成运维日报"""
        top10 = list(error_counts.items())[:10]
        top10_text = "\n".join(
            f"  {i+1}. {svc}: {cnt} 条错误" for i, (svc, cnt) in enumerate(top10)
        )
        total_errors = sum(error_counts.values())
        health_score = max(0, min(100, 100 - int(total_errors / max(total_logs, 1) * 200)))

        sample_text = "\n".join(
            f"[{l['timestamp']}][{l['labels'].get('app', '?')}] {l['line'][:120]}"
            for l in sample_errors[:30]
        )

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        prompt = f"""你是一名资深运维工程师，请根据以下数据生成今日运维日报分析。

=== 基础指标 ===
报告时间: {now}
总日志条数: {total_logs} 条
涉及服务数: {service_count} 个
节点状态: {node_status.get('normal', 0)} 正常 / {node_status.get('abnormal', 0)} 异常
活跃告警: {active_alerts} 个
错误日志总计: {total_errors} 条
整体健康评分: {health_score}/100

=== 错误 Top10 服务 ===
{top10_text}

=== 错误样本 ===
{sample_text}

请生成「AI 分析」部分，要求：
1. 用 2-3 句话总结当前系统整体状态
2. 列出 3-5 个最值得关注的问题（每条用 ⚠️ 开头）
3. 给出今日最重要的 2-3 条运维建议（每条用 ✅ 开头）
4. 预测若不处理，可能在未来 24 小时出现的风险

语言简洁、专业，使用中文。"""

        async for chunk in self.provider.stream(prompt, max_tokens=1500):
            yield chunk

    async def calculate_health_score(
        self,
        total_logs: int,
        error_count: int,
        active_alerts: int,
        abnormal_nodes: int,
    ) -> int:
        """计算健康评分（0-100）"""
        if total_logs == 0:
            return 100
        error_rate = error_count / total_logs
        score = 100
        score -= min(40, int(error_rate * 200))
        score -= min(30, active_alerts * 10)
        score -= min(20, abnormal_nodes * 10)
        return max(0, score)
