"""AI 分析器 - 支持 Anthropic Claude 和 OpenAI 兼容接口（Qwen3 等本地模型）

每一次发起 LLM 调用都通过 _observed_stream 包装：
  - 入参 prompt 经脱敏后写入 OTEL gen_ai.prompt attribute
  - 出参累计字符数 → Prometheus aiops_llm_tokens_total{kind=completion}（近似）
  - 整体耗时 → aiops_llm_latency_seconds
  - 异常 → aiops_llm_errors_total
"""
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import AsyncIterator

from observability.llm_metrics import observe_latency, record_error, record_tokens
from observability.llm_tracing import llm_span
from observability.redact import redact


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
        import anthropic, httpx
        self.client = anthropic.AsyncAnthropic(
            api_key=api_key,
            http_client=httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(120.0)),
        )
        self.model = model

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
        import httpx
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "EMPTY",   # 本地模型通常不需要 key，传占位符
            http_client=httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(120.0)),
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
      AI_MODEL=<your-model-id>

    AI_PROVIDER=openai     →  使用 OpenAI 兼容接口（本地模型等）
      AI_BASE_URL=http://192.168.x.x:8000/v1
      AI_API_KEY=                      （本地模型可留空）
      AI_MODEL=<your-model-id>
    """
    provider = os.getenv("AI_PROVIDER", "").strip().lower()

    import logging
    _log = logging.getLogger(__name__)
    _log.info("[AI] AI_PROVIDER=%s", provider)

    if not provider:
        raise ValueError("AI_PROVIDER 未配置")

    if provider == "openai":
        base_url = os.getenv("AI_BASE_URL", "")
        api_key  = os.getenv("AI_API_KEY", "EMPTY")
        model    = os.getenv("AI_MODEL", "").strip()
        wire_api = os.getenv("AI_WIRE_API", "chat")  # "chat" 或 "responses"
        _log.info("[AI] base_url=%s, model=%s, wire_api=%s", base_url, model, wire_api)
        if not base_url:
            raise ValueError("AI_PROVIDER=openai 时必须设置 AI_BASE_URL")
        if not model:
            raise ValueError("AI_MODEL 未配置")
        return OpenAICompatProvider(base_url, api_key, model, wire_api)

    if provider != "anthropic":
        raise ValueError(f"暂不支持的 AI_PROVIDER: {provider}")

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    model   = os.getenv("AI_MODEL", "").strip()
    if not api_key:
        raise ValueError("AI_PROVIDER=anthropic 时必须设置 ANTHROPIC_API_KEY")
    if not model:
        raise ValueError("AI_MODEL 未配置")
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

    def _provider_kind(self) -> str:
        return "anthropic" if isinstance(self.provider, AnthropicProvider) else "openai"

    async def _observed_stream(
        self,
        prompt: str,
        max_tokens: int,
        op: str,
    ) -> AsyncIterator[str]:
        """所有对 self.provider.stream 的调用都应走这里。"""
        import time as _time

        provider_kind = self._provider_kind()
        model = getattr(self.provider, "model", "")
        started = _time.perf_counter()
        completion_chars = 0
        try:
            async with llm_span(provider_kind, model, op) as ctx:
                ctx["record_prompt"](prompt)
                async for chunk in self.provider.stream(prompt, max_tokens=max_tokens):
                    if chunk:
                        completion_chars += len(chunk)
                        ctx["record_completion_chars"](len(chunk))
                    yield chunk
        except Exception as exc:
            record_error(provider_kind, model, type(exc).__name__)
            raise
        finally:
            elapsed = _time.perf_counter() - started
            observe_latency(provider_kind, model, op, elapsed)
            # 字符→token 粗略换算（4:1），主流模型足够监控用
            record_tokens(
                provider_kind, model,
                prompt_tokens=max(1, len(prompt) // 4),
                completion_tokens=max(0, completion_chars // 4),
            )

    async def analyze_logs_stream(
        self,
        logs: list[dict],
        service: str = "",
        extra_context: str = "",
    ) -> AsyncIterator[str]:
        """流式分析日志。

        调用前 logs 已由 router 完成去重+采样，此处直接构建 prompt。
        每行截断到 300 字符，防止单条超长日志撑爆上下文。
        """
        log_text = "\n".join(
            f"[{l['timestamp']}] {l['line'][:300]}" for l in logs
        )

        svc_hint = f"服务 {service} 的" if service else ""
        ctx_hint = f"\n\n{extra_context}" if extra_context else ""

        prompt = f"""你是一名资深 SRE（网站可靠性工程师），请对以下 {svc_hint}日志进行深度分析。{ctx_hint}

日志内容（共 {len(logs)} 条，已按严重级别优先采样，时间升序）：
```
{log_text}
```

请提供：
1. **错误模式识别** - 识别主要错误类型和出现规律，列出具体示例
2. **根因分析** - 推断可能的根本原因（区分直接原因和深层原因）
3. **影响评估** - 判断对系统稳定性的影响程度（高/中/低）
4. **优化建议** - 具体的修复和预防措施（按优先级排列）
5. **需立即处理的问题** - 用 🔴 标出需要立即响应的项目

请用简洁专业的中文回答，重点突出关键问题，避免泛泛而谈。"""

        async for chunk in self._observed_stream(prompt, max_tokens=2048, op="analyze_logs"):
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
                f"- 分组={r.get('group_name') or '未分组'}；"
                f"{r.get('hostname') or r.get('instance')} ({r.get('ip', '-')})；"
                f"负责人={r.get('owner') or '未配置'}；机房={r.get('datacenter') or '未配置'} "
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
1. 开头直接用 2-3 句话给出本次巡检结论，明确是否需要立即处置
2. 按主机分组输出异常，先列含严重告警的组，再列警告组；同组内严重优先于警告
3. 逐台列出异常主机的 IP、主机名、负责人、机房和具体问题
4. 列出 3-5 条最值得关注的问题（每条以"⚠️"开头，注明受影响分组和 IP）
5. 给出 2-4 条最优先的处置建议（每条以"✅"开头，注明负责人和需操作的 IP）
6. 最后补充"未来24小时风险预测"

要求：
- 使用中文
- 异常清单必须明确列出每台异常主机的 IP，不能只写主机名
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
        async for chunk in self._observed_stream(prompt, max_tokens=1400, op="inspect_summary"):
            yield chunk

    async def generate_daily_report(
        self,
        error_counts: dict[str, int],
        total_logs: int,
        service_count: int,
        node_status: dict,
        active_alerts: int,
        sample_errors: list[dict],
        service_error_summaries: list[dict] | None = None,
        error_keywords: list[dict] | None = None,
        interface_status: dict | None = None,
    ) -> AsyncIterator[str]:
        """流式生成运维日报"""
        total_errors = sum(error_counts.values())
        health_score = max(0, min(100, 100 - int(total_errors / max(total_logs, 1) * 200)))

        summary_text = "\n".join(
            f"- {item.get('summary', '')}"
            for item in (service_error_summaries or [])
        ) or "- 未发现需要概括的微服务错误。"
        keyword_text = "\n".join(
            f"- {item.get('keyword', '未知')}：高频出现，涉及 {', '.join(item.get('services') or []) or '未标记服务'}"
            for item in (error_keywords or [])[:10]
        ) or "- 暂无可统计的高频错误关键字。"

        interface_status = interface_status or {}
        interface_rows = interface_status.get("rows") or []
        interface_text = "\n".join(
            (
                f"- [{row.get('status', 'unknown')}] "
                f"{row.get('application', '-')} {row.get('method', '-')} {row.get('uri', '-')}："
                f"5xx率 {row.get('error_ratio', 0)}%，P95 {row.get('p95_ms', 0)}ms"
            )
            for row in interface_rows[:10]
        ) or "- 未采集到 http_server 接口指标，无法完成接口健康评估。"

        sample_text = "\n".join(
            f"[{l.get('timestamp', '')}][{(l.get('labels') or {}).get('app', '?')}] {_log_line[:160]}"
            for l in sample_errors[:20]
            for _log_line in [str(l.get("line") or l.get("message") or "")]
        )

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        prompt = f"""你是一名资深运维工程师，请根据以下数据生成今日运维日报分析。

=== 运行概况 ===
报告时间: {now}
涉及服务数: {service_count} 个
节点状态: {node_status.get('normal', 0)} 正常 / {node_status.get('abnormal', 0)} 异常
活跃告警: {active_alerts} 个
整体健康评分: {health_score}/100

=== 微服务错误一句话摘要（禁止改写为条数排名）===
{summary_text}

=== 高频错误关键字 ===
{keyword_text}

=== 接口监控评估数据 ===
总体状态: {interface_status.get('status', 'unknown')}
监控接口数: {interface_status.get('monitored_interfaces', 0)}
异常接口数: {interface_status.get('abnormal_interfaces', 0)}
{interface_text}

=== 代表性错误样本（仅用于判断，不在结论中逐条复述）===
{sample_text}

请直接生成「AI 运维结论」，要求：
1. 第一段用 2-3 句话给出整体结论，先说是否需要立即处置
2. 每个有错误的微服务只用一句话概括错误模式与影响，不写错误日志条数
3. 汇总高频错误关键字，并说明它们指向的共同风险
4. 单独给出接口监控状况评估，明确异常接口、5xx 风险和延迟风险；无指标时明确说明
5. 给出 2-4 条按优先级排序的处置建议（每条用 ✅ 开头）

语言简洁、专业，使用中文。禁止输出“某服务有 N 条错误”这类条数陈述。"""

        async for chunk in self._observed_stream(prompt, max_tokens=1800, op="daily_report"):
            yield chunk

    async def generate_host_inspect_report(
        self,
        inspect_results: list[dict],
        summary: dict,
    ) -> AsyncIterator[str]:
        """流式生成主机巡检日报 AI 分析（用于报告存储）"""
        prompt = self._build_inspect_prompt(inspect_results, summary, max_abnormal_hosts=15)
        async for chunk in self._observed_stream(prompt, max_tokens=1500, op="host_inspect_report"):
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

        async for chunk in self._observed_stream(prompt, max_tokens=2048, op="analyze_templates"):
            yield chunk

    async def analyze_rca_candidates_stream(
        self,
        candidates: list[dict],
        sample_logs_by_service: dict[str, list[dict]] | None = None,
        extra_context: str = "",
    ) -> AsyncIterator[str]:
        """阶段 B：拿阶段 A 输出的嫌疑组件清单，让 LLM 给结构化 RCA。

        prompt 要求 LLM 返回 JSON-like 结构（root_cause/blast_radius/remediation），
        UI 端可二次解析；不要求严格 JSON 输出避免被截断卡死。
        """
        sample_logs_by_service = sample_logs_by_service or {}
        lines: list[str] = []
        for idx, c in enumerate(candidates[:3], 1):
            ev = c.get("evidence", {}) or {}
            svc = c.get("service", "?")
            lines.append(
                f"[{idx}] service={svc}  score={c.get('score', 0)}\n"
                f"     burst_z={ev.get('burst_z', 0)}  "
                f"current_errors={ev.get('current_errors', 0)}  "
                f"baseline_mean={ev.get('baseline_mean_per_window', 0)}\n"
                f"     new_templates={ev.get('new_template_count', 0)}  "
                f"rate_delta={ev.get('error_rate_delta_pct', 0)}%"
            )
            examples = ev.get("new_template_examples") or []
            if examples:
                lines.append("     新模板样例：")
                for ex in examples[:3]:
                    lines.append(f"       - {str(ex)[:160]}")
            samples = sample_logs_by_service.get(svc) or []
            if samples:
                lines.append("     日志样本（最多 6 条）：")
                for log in samples[:6]:
                    ts = str(log.get("timestamp", ""))[:19]
                    msg = str(log.get("line") or log.get("message", ""))[:200]
                    lines.append(f"       [{ts}] {msg}")

        body = "\n".join(lines) if lines else "（阶段 A 未返回候选）"
        ctx_hint = f"\n\n附加上下文：\n{extra_context}" if extra_context else ""

        prompt = f"""你是资深 SRE。下面是 Failure Localization 阶段（纯算子）输出的嫌疑组件清单与证据。
请基于这些证据做根因分析，**不要凭空猜测，只能引用证据里出现的服务/数值**。

嫌疑清单（按嫌疑分降序）：
{body}{ctx_hint}

请按以下结构输出（用易读的 markdown，不需要严格 JSON）：

## 根因判定
- 责任服务: <服务名>
- 故障类别: <GC/OOM/DependencyTimeout/ConfigDrift/NetworkPartition/Saturation/Bug/Other>
- 直接原因: <1-2 句>
- 深层原因: <1-2 句>

## 影响范围（blast radius）
- 直接受影响: <服务/接口列表>
- 潜在传播路径: <若可推断>

## 修复方案（按优先级）
对每条给出 risk 与 auto_safe 字段：
- risk:  low / medium / high
- auto_safe:  true / false（true 表示在 behaviors.auto=on + 高置信度下可自动执行）

例如：
1. [risk=low, auto_safe=true] 重启 order-service 副本 1（pod 已 OOM）
2. [risk=medium, auto_safe=false] 把 max_heap_size 从 2G 调到 4G，需要走 ConfigMap 变更审批
3. [risk=high, auto_safe=false] 回滚 v1.4.2 到 v1.4.1（涉及流量切换）

## 置信度
0-1 之间一个数字 + 理由（证据是否足够、是否单源、历史相似度等）"""

        async for chunk in self._observed_stream(prompt, max_tokens=2000, op="rca_stage_b"):
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
