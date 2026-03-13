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

    async def generate_inspection_summary(
        self,
        inspect_results: list[dict],
        summary: dict,
    ) -> AsyncIterator[str]:
        """基于巡检结果生成 AI 总结"""
        total = summary.get("total", len(inspect_results))
        normal = summary.get("normal", 0)
        warning = summary.get("warning", 0)
        critical = summary.get("critical", 0)

        abnormal_hosts = [r for r in inspect_results if r.get("overall") != "normal"]
        abnormal_hosts.sort(
            key=lambda r: (
                {"critical": 2, "warning": 1, "normal": 0}.get(r.get("overall", "normal"), 0),
                sum(1 for c in r.get("checks", []) if c.get("status") != "normal"),
            ),
            reverse=True,
        )

        host_lines = []
        for r in abnormal_hosts[:12]:
            abnormal_checks = [c for c in r.get("checks", []) if c.get("status") != "normal"][:5]
            check_text = "；".join(
                f"{c.get('item', '未知项')}={c.get('value', '-')}"
                for c in abnormal_checks
            ) or "未发现明显异常"
            host_lines.append(
                f"- {r.get('hostname') or r.get('instance')} ({r.get('ip', '-')}) "
                f"[{r.get('overall', 'normal')}]：{check_text}"
            )
        if not host_lines:
            host_lines.append("- 所有主机巡检项均为正常，未发现告警主机。")

        issue_counter: dict[str, int] = {}
        for r in inspect_results:
            for check in r.get("checks", []):
                if check.get("status") == "normal":
                    continue
                issue = check.get("item", "未知项")
                issue_counter[issue] = issue_counter.get(issue, 0) + 1

        top_issues = sorted(issue_counter.items(), key=lambda item: item[1], reverse=True)[:10]
        issue_lines = [
            f"- {issue}: 影响 {count} 台主机"
            for issue, count in top_issues
        ] or ["- 当前没有统计到告警项。"]

        prompt = f"""你是一名资深运维/SRE 工程师，请根据以下主机巡检结果输出“AI 分析总结”。

=== 巡检汇总 ===
巡检主机总数: {total}
正常: {normal}
警告: {warning}
严重: {critical}

=== 高频问题 ===
{chr(10).join(issue_lines)}

=== 异常主机样本 ===
{chr(10).join(host_lines)}

请输出：
1. 用 2-3 句话概括本次巡检整体健康状态
2. 列出 3-5 条最值得关注的问题（每条以“⚠️”开头）
3. 给出 2-4 条最优先的处置建议（每条以“✅”开头）
4. 最后补充“未来24小时风险预测”

要求：
- 使用中文
- 结论具体，避免空话
- 优先强调严重主机、重复性问题和可能的容量/稳定性风险
- 不要复述原始数据表格，直接给结论和动作建议
"""

        async for chunk in self.provider.stream(prompt, max_tokens=1400):
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

    async def generate_host_inspect_report(
        self,
        inspect_results: list[dict],
        summary: dict,
    ) -> AsyncIterator[str]:
        """流式生成主机巡检日报 AI 分析"""
        total    = summary.get("total", len(inspect_results))
        normal   = summary.get("normal", 0)
        warning  = summary.get("warning", 0)
        critical = summary.get("critical", 0)

        # 异常主机详情
        abnormal = [r for r in inspect_results if r.get("overall") != "normal"]
        abnormal.sort(key=lambda r: {"critical": 2, "warning": 1}.get(r.get("overall", "normal"), 0), reverse=True)
        host_lines = []
        for r in abnormal[:15]:
            bad_checks = [c for c in r.get("checks", []) if c.get("status") != "normal"][:4]
            detail = "；".join(f"{c['item']}={c['value']}" for c in bad_checks) or "未发现明显异常"
            host_lines.append(f"- {r.get('hostname') or r.get('instance')} ({r.get('ip','-')}) [{r.get('overall')}]：{detail}")
        if not host_lines:
            host_lines.append("- 所有主机均正常，未发现告警。")

        # 高频问题
        issue_cnt: dict[str, int] = {}
        for r in inspect_results:
            for c in r.get("checks", []):
                if c.get("status") != "normal":
                    issue_cnt[c.get("item", "未知")] = issue_cnt.get(c.get("item", "未知"), 0) + 1
        top_issues = sorted(issue_cnt.items(), key=lambda x: x[1], reverse=True)[:8]
        issue_lines = [f"- {k}：影响 {v} 台" for k, v in top_issues] or ["- 当前无高频异常项。"]

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        prompt = f"""你是一名资深运维/SRE工程师，请根据以下主机巡检数据生成「主机巡检日报」。

=== 巡检概况 ===
报告时间: {now}
巡检主机总数: {total}
正常: {normal} 台  警告: {warning} 台  严重: {critical} 台

=== 高频异常项 ===
{chr(10).join(issue_lines)}

=== 异常主机详情（最多15台）===
{chr(10).join(host_lines)}

请生成「AI 分析」部分，要求：
1. 用 2-3 句话总结当前主机集群整体健康状态
2. 列出 3-5 个最值得关注的问题（每条用 ⚠️ 开头，注明影响范围）
3. 给出 2-3 条具体运维建议（每条用 ✅ 开头）
4. 若不处理，预测未来 24 小时可能出现的风险

语言简洁专业，使用中文。"""

        async for chunk in self.provider.stream(prompt, max_tokens=1500):
            yield chunk

    async def calculate_host_health_score(self, summary: dict) -> int:
        """根据巡检结果计算主机集群健康评分"""
        total    = summary.get("total", 1)
        warning  = summary.get("warning", 0)
        critical = summary.get("critical", 0)
        if total == 0:
            return 100
        score = 100
        score -= min(40, int(critical / total * 200))
        score -= min(30, int(warning  / total * 100))
        return max(0, score)

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
