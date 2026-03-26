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
        """流式分析日志（智能采样：error优先 + 去重 + 近期优先）"""
        # ── 分层采样 ──────────────────────────────────────────────────
        # logs 已按时间倒序（最新在前）
        BUDGET = 300

        def _level(line: str) -> int:
            l = line.lower()
            if any(k in l for k in ("panic", "fatal", "critical")): return 4
            if "error" in l or "exception" in l or "traceback" in l:  return 3
            if "warn" in l:                                            return 2
            return 1

        # 去除完全重复的行（保留最新一条）
        seen: set[str] = set()
        deduped: list[dict] = []
        for log in logs:
            key = log["line"][:120]   # 用前120字符做去重键
            if key not in seen:
                seen.add(key)
                deduped.append(log)

        # 按严重级别分组
        by_level: dict[int, list] = {4: [], 3: [], 2: [], 1: []}
        for log in deduped:
            by_level[_level(log["line"])].append(log)

        # 按预算比例采样：严重(4)>error(3)>warn(2)>info(1)
        weights = {4: 0.30, 3: 0.50, 2: 0.15, 1: 0.05}
        sample: list[dict] = []
        for lv in (4, 3, 2, 1):
            quota = max(1, int(BUDGET * weights[lv]))
            sample.extend(by_level[lv][:quota])
        sample = sample[:BUDGET]

        # 按时间升序展示（更符合阅读习惯）
        sample.sort(key=lambda x: x.get("timestamp_ns", 0))

        log_text = "\n".join(
            f"[{l['timestamp']}] {l['line'][:200]}" for l in sample
        )

        prompt = f"""你是一名资深 SRE（网站可靠性工程师），请对以下{'服务 ' + service + ' 的' if service else ''}日志进行深度分析。

采样说明：原始日志 {len(logs)} 条，去重后 {len(deduped)} 条，按严重级别优先采样展示 {len(sample)} 条（最新优先）：
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

    @staticmethod
    def _build_inspect_prompt(
        inspect_results: list[dict],
        summary: dict,
        max_abnormal_hosts: int = 15,
    ) -> str:
        """构建主机巡检 AI 分析 prompt，供两个巡检方法共用"""
        total    = summary.get("total", len(inspect_results))
        normal   = summary.get("normal", 0)
        warning  = summary.get("warning", 0)
        critical = summary.get("critical", 0)

        abnormal = [r for r in inspect_results if r.get("overall") != "normal"]
        abnormal.sort(
            key=lambda r: (
                {"critical": 2, "warning": 1, "normal": 0}.get(r.get("overall", "normal"), 0),
                sum(1 for c in r.get("checks", []) if c.get("status") != "normal"),
            ),
            reverse=True,
        )
        host_lines = []
        for r in abnormal[:max_abnormal_hosts]:
            bad_checks = [c for c in r.get("checks", []) if c.get("status") != "normal"][:5]
            detail = "；".join(
                f"{c.get('item', '未知项')}={c.get('value', '-')}" for c in bad_checks
            ) or "未发现明显异常"
            host_lines.append(
                f"- {r.get('hostname') or r.get('instance')} ({r.get('ip', '-')}) "
                f"[{r.get('overall', 'normal')}]：{detail}"
            )
        if not host_lines:
            host_lines.append("- 所有主机巡检项均为正常，未发现告警主机。")

        issue_cnt: dict[str, int] = {}
        for r in inspect_results:
            for c in r.get("checks", []):
                if c.get("status") != "normal":
                    key = c.get("item", "未知项")
                    issue_cnt[key] = issue_cnt.get(key, 0) + 1
        top_issues = sorted(issue_cnt.items(), key=lambda x: x[1], reverse=True)[:10]
        issue_lines = [f"- {k}：影响 {v} 台主机" for k, v in top_issues] or ["- 当前没有统计到告警项。"]

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return f"""你是一名资深运维/SRE 工程师，请根据以下主机巡检结果生成 AI 分析总结。

=== 巡检概况 ===
报告时间: {now}
巡检主机总数: {total}
正常: {normal} 台  警告: {warning} 台  严重: {critical} 台

=== 高频异常项 ===
{chr(10).join(issue_lines)}

=== 异常主机详情（最多 {max_abnormal_hosts} 台）===
{chr(10).join(host_lines)}

请输出：
1. 用 2-3 句话概括本次巡检整体健康状态
2. 逐台列出每个异常主机的 IP 地址和具体问题，格式为：
   - IP x.x.x.x（主机名）：[严重/警告] 问题描述（如：CPU 使用率 95%、磁盘 /data 使用率 92%）
3. 列出 3-5 条最值得关注的问题（每条以"⚠️"开头，注明受影响的 IP 列表）
4. 给出 2-4 条最优先的处置建议（每条以"✅"开头，注明需操作的 IP）
5. 最后补充"未来24小时风险预测"

要求：
- 使用中文
- 第2点必须明确列出每台异常主机的 IP，不能只写主机名
- 结论具体，避免空话
- 不要复述原始数据表格，直接给结论和动作建议
"""

    async def generate_inspection_summary(
        self,
        inspect_results: list[dict],
        summary: dict,
    ) -> AsyncIterator[str]:
        """基于巡检结果生成 AI 总结（用于实时巡检流）"""
        prompt = self._build_inspect_prompt(inspect_results, summary, max_abnormal_hosts=12)
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
        """流式生成主机巡检日报 AI 分析（用于报告存储）"""
        prompt = self._build_inspect_prompt(inspect_results, summary, max_abnormal_hosts=15)
        async for chunk in self.provider.stream(prompt, max_tokens=1500):
            yield chunk

    async def analyze_templates_stream(
        self,
        templates: list[dict],
        service: str = "",
        extra_hint: str = "",
    ) -> AsyncIterator[str]:
        """流式分析日志模板聚类结果"""
        total_logs = sum(t.get("count", 0) for t in templates)
        tpl_lines = []
        for i, t in enumerate(templates[:30], 1):
            cnt = t.get("count", 0)
            pct = f"{cnt / total_logs * 100:.1f}%" if total_logs else "0%"
            svcs = ", ".join(s["name"] for s in t.get("top_services", [])[:3])
            tpl_lines.append(f"{i}. [{cnt}条/{pct}] 模板: {t.get('template', '')[:200]}"
                             + (f"\n   来源服务: {svcs}" if svcs else ""))

        prompt = f"""你是一名资深 SRE，请分析以下{'服务 ' + service + ' 的' if service else ''}日志模板聚类结果。{(' ' + extra_hint) if extra_hint else ''}

聚类统计（共 {total_logs} 条日志，{len(templates)} 个模板，展示前 {len(tpl_lines)} 个）：
{chr(10).join(tpl_lines)}

请提供：
1. **高频模式解读** - 出现最多的日志类型及其含义，重点关注错误/异常模板
2. **异常模式识别** - 哪些模板反映了系统异常，严重程度如何
3. **根因推断** - 基于日志模式，可能的问题根因是什么
4. **优化建议** - 针对异常模板的具体处置建议（按优先级排序）
5. **日志质量评估** - 日志是否完整、是否有冗余、是否需要优化日志级别

请用简洁专业的中文回答，重点突出高频异常模板。"""

        async for chunk in self.provider.stream(prompt, max_tokens=2048):
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
