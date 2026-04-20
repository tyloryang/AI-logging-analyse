"""根因分析引擎（RCA Engine）。

流程：
1. 并行采集 Loki 错误日志、Prometheus 指标、SkyWalking Trace、CMDB 主机信息
2. 压缩上下文（去重日志、只取指标峰值摘要），避免超出 Token 限制
3. 调用 AI 流式分析，输出结构化结论
4. 落库 + 推送飞书
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)

_RCA_FILE = Path(__file__).resolve().parent.parent / "data" / "rca_results.json"
_MAX_LOGS  = 500   # 最多采集日志行数
_CTX_TIMEOUT = 10  # 上下文采集超时（秒）


# ── 持久化 ────────────────────────────────────────────────────────────────────

def _load_results() -> list[dict]:
    if _RCA_FILE.exists():
        try:
            return json.loads(_RCA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_results(results: list[dict]) -> None:
    _RCA_FILE.parent.mkdir(parents=True, exist_ok=True)
    # 保留最近 200 条
    _RCA_FILE.write_text(
        json.dumps(results[-200:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_rca(record: dict) -> str:
    """持久化一条 RCA 记录，返回其 id。"""
    results = _load_results()
    rca_id = record.get("id") or f"rca_{int(time.time())}"
    record["id"] = rca_id
    results.append(record)
    _save_results(results)
    return rca_id


def list_rca(limit: int = 50) -> list[dict]:
    return list(reversed(_load_results()))[:limit]


def get_rca(rca_id: str) -> dict | None:
    for r in reversed(_load_results()):
        if r.get("id") == rca_id:
            return r
    return None


# ── 上下文采集 ────────────────────────────────────────────────────────────────

async def _collect_loki(service: str | None, hours: float = 1.0) -> str:
    try:
        import state
        logs = await asyncio.wait_for(
            state.loki.query_error_logs(service=service, hours=hours, limit=_MAX_LOGS),
            timeout=_CTX_TIMEOUT,
        )
        if not logs:
            return "（无 ERROR 日志）"
        # 去重：相同消息只保留计数
        freq: dict[str, int] = {}
        for entry in logs:
            msg = entry.get("line", "")[:200]
            freq[msg] = freq.get(msg, 0) + 1
        top = sorted(freq.items(), key=lambda x: -x[1])[:30]
        lines = [f"[×{cnt}] {msg}" for msg, cnt in top]
        return f"错误日志（去重后 Top {len(lines)} 条，共 {len(logs)} 条原始）：\n" + "\n".join(lines)
    except asyncio.TimeoutError:
        return "（Loki 查询超时）"
    except Exception as exc:
        return f"（Loki 查询失败: {exc}）"


async def _collect_prometheus(service: str | None) -> str:
    try:
        import state
        svc_filter = f'{{service="{service}"}}' if service else ""
        queries = {
            "CPU 使用率 (%)":      f'100 - avg(rate(node_cpu_seconds_total{{mode="idle"}}[5m])) * 100',
            "内存使用率 (%)":      f'100 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100',
            "HTTP 错误率 (%)":     f'sum(rate(http_requests_total{{status=~"5.."}}[5m])) / sum(rate(http_requests_total[5m])) * 100',
            "P99 响应时间 (ms)":   f'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) * 1000',
        }
        parts: list[str] = []
        for label, promql in queries.items():
            try:
                result = await asyncio.wait_for(
                    state.prom.query(promql),
                    timeout=_CTX_TIMEOUT,
                )
                if result:
                    val = float(result[0].get("value", [0, 0])[1] or 0)
                    parts.append(f"{label}: {val:.2f}")
            except Exception:
                pass
        return "当前指标：\n" + ("\n".join(parts) if parts else "（无法获取指标）")
    except Exception as exc:
        return f"（Prometheus 查询失败: {exc}）"


async def _collect_skywalking(service: str | None) -> str:
    try:
        sw_url = os.getenv("SKYWALKING_OAP_URL", "").rstrip("/")
        if not sw_url:
            return "（SkyWalking 未配置）"
        end_ms   = int(time.time() * 1000)
        start_ms = end_ms - 3600 * 1000
        query = """
        query { getAllServices(duration: {start: "%s", end: "%s", step: MINUTE}) { name } }
        """ % (
            datetime.utcfromtimestamp(start_ms / 1000).strftime("%Y-%m-%d %H%M"),
            datetime.utcfromtimestamp(end_ms / 1000).strftime("%Y-%m-%d %H%M"),
        )
        async with httpx.AsyncClient(timeout=_CTX_TIMEOUT) as client:
            r = await client.post(f"{sw_url}/graphql", json={"query": query})
            services = r.json().get("data", {}).get("getAllServices", [])
        names = [s["name"] for s in services[:10]]
        return f"SkyWalking 服务（最近1小时）：{', '.join(names) or '无'}"
    except Exception as exc:
        return f"（SkyWalking 查询失败: {exc}）"


async def _collect_cmdb(service: str | None) -> str:
    try:
        import state
        hosts = await asyncio.wait_for(state.prom.discover_hosts(), timeout=_CTX_TIMEOUT)
        if not hosts:
            return "（CMDB：无主机数据）"
        relevant = hosts[:10]
        lines = [f"- {h.get('instance')} ({h.get('state','?')})" for h in relevant]
        return f"相关主机（共 {len(hosts)} 台，展示前10）：\n" + "\n".join(lines)
    except Exception as exc:
        return f"（CMDB 查询失败: {exc}）"


async def collect_context(service: str | None, hours: float = 1.0) -> dict[str, str]:
    """并行采集所有数据源，超时后返回部分结果。"""
    loki_task, prom_task, sw_task, cmdb_task = await asyncio.gather(
        _collect_loki(service, hours),
        _collect_prometheus(service),
        _collect_skywalking(service),
        _collect_cmdb(service),
        return_exceptions=True,
    )
    def _safe(r):
        return r if isinstance(r, str) else f"（采集异常: {r}）"
    return {
        "loki":        _safe(loki_task),
        "prometheus":  _safe(prom_task),
        "skywalking":  _safe(sw_task),
        "cmdb":        _safe(cmdb_task),
    }


# ── AI 分析 ───────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """你是一名资深 SRE 工程师，负责根因分析。
请根据以下运维数据，用中文输出结构化的根因分析报告。

输出格式（严格遵守）：
## 根因摘要
一句话描述根本原因。

## 影响范围
受影响的服务、主机或用户群体。

## 证据
- 关键日志/指标证据（每条一行）

## 处置建议
1. 第一步行动
2. 第二步行动
3. 第三步行动

## 置信度
0-100 的整数，后跟简要说明。
"""


async def analyze_stream(
    service: str | None,
    alert_name: str = "",
    hours: float = 1.0,
    extra_context: str = "",
) -> AsyncIterator[str]:
    """流式输出 RCA 分析结果。"""
    import state

    ctx = await collect_context(service, hours)

    prompt = f"""告警名称：{alert_name or '手动触发'}
分析时间窗口：最近 {hours} 小时
目标服务：{service or '全局'}

--- Loki 错误日志 ---
{ctx['loki']}

--- Prometheus 指标 ---
{ctx['prometheus']}

--- SkyWalking APM ---
{ctx['skywalking']}

--- CMDB 主机 ---
{ctx['cmdb']}
"""
    if extra_context:
        prompt += f"\n--- 额外上下文 ---\n{extra_context}"

    full_prompt = _SYSTEM_PROMPT + "\n\n" + prompt

    try:
        async for chunk in state.analyzer._provider.stream(full_prompt, max_tokens=1500):
            yield chunk
    except Exception as exc:
        yield f"\n\n（AI 分析失败: {exc}）"


async def run_rca(
    service: str | None,
    alert_name: str = "",
    alert_group_id: str | None = None,
    hours: float = 1.0,
    extra_context: str = "",
) -> str:
    """执行完整 RCA，落库并返回 rca_id。"""
    now_iso = datetime.now(timezone.utc).isoformat()
    parts: list[str] = []

    async for chunk in analyze_stream(service, alert_name, hours, extra_context):
        parts.append(chunk)

    full_text = "".join(parts)

    record = {
        "id": f"rca_{int(time.time())}",
        "created_at": now_iso,
        "service": service or "global",
        "alert_name": alert_name,
        "alert_group_id": alert_group_id,
        "result": full_text,
        "context_hours": hours,
    }
    rca_id = save_rca(record)

    # 关联告警组
    if alert_group_id:
        try:
            from services.alert_dedup import update_group_status
            update_group_status(alert_group_id, "resolved", rca_id=rca_id)
        except Exception:
            pass

    # 推送飞书
    asyncio.create_task(_notify_feishu(record))

    return rca_id


async def _notify_feishu(record: dict) -> None:
    webhook = os.getenv("FEISHU_WEBHOOK", "")
    if not webhook:
        return
    try:
        result = record.get("result", "")
        # 截取前 500 字符，避免消息过长
        summary = result[:500] + ("..." if len(result) > 500 else "")
        text = (
            f"🧠 RCA 根因分析完成\n"
            f"服务：{record.get('service', '—')}\n"
            f"告警：{record.get('alert_name', '—')}\n\n"
            f"{summary}"
        )
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(webhook, json={"msg_type": "text", "content": {"text": text}})
    except Exception as exc:
        logger.warning("[rca] 飞书推送失败: %s", exc)
