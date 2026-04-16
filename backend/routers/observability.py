"""可观测性平台总览路由

端点：
  GET  /api/observability/overview   — 汇总统计（告警数/错误数/Trace量/Grafana看板数）
  GET  /api/observability/alerts     — 最近告警列表
  GET  /api/observability/traces     — 最近 Trace 列表
  GET  /api/observability/services   — 有异常的服务拓扑
  POST /api/observability/analyze    — 流式 AI 分析（SSE）
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from state import loki, prom, analyzer
from skywalking_client import sw_client, check_connectivity as sw_check

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/observability", tags=["observability"])

# Grafana 看板定义（uid 与 Grafana 官方 dashboard uid 对齐）
_GRAFANA_BOARD_DEFS = [
    {"id": "node-exporter",  "title": "Node Exporter Full",    "uid": "rYdddlPWk"},
    {"id": "jvm",            "title": "JVM Micrometer",        "uid": "4PSsg1MZz"},
    {"id": "mysql",          "title": "MySQL Overview",        "uid": "MQWgroiiz"},
    {"id": "redis",          "title": "Redis Dashboard",       "uid": "x7ozmSZMk"},
]

def _build_grafana_boards():
    # 每次调用时读取 env，支持 settings 页面热更新
    base = os.getenv("GRAFANA_URL", "http://localhost:3000").rstrip("/")
    return [
        {**b, "url": f"{base}/d/{b['uid']}/{b['id']}"}
        for b in _GRAFANA_BOARD_DEFS
    ]


# ── 辅助：从 Loki 获取各服务错误数 ─────────────────────────────────────────

async def _get_loki_error_count(hours: int = 1) -> tuple[int, list[dict]]:
    """返回 (total_error_count, [{service, count}]) """
    try:
        services_raw = await loki.get_services()
        total = 0
        breakdown = []
        for svc in services_raw:
            cnt = svc.get("error_count", 0) or 0
            total += cnt
            if cnt > 0:
                breakdown.append({"service": svc.get("name", ""), "count": cnt})
        breakdown.sort(key=lambda x: x["count"], reverse=True)
        return total, breakdown
    except Exception as e:
        logger.warning("[obs] Loki error count failed: %s", e)
        return 0, []


# ── 辅助：从 SkyWalking 获取 Trace 数 ──────────────────────────────────────

async def _get_sw_trace_count(hours: int = 1) -> tuple[int, list[dict]]:
    """返回 (trace_count, recent_traces)"""
    try:
        result = await sw_client.get_traces(hours=hours, page=1, page_size=20)
        traces = result.get("traces", [])
        total = result.get("total", len(traces))
        recent = []
        for t in traces[:10]:
            recent.append({
                "trace_id":   t.get("traceIds", [""])[0] if t.get("traceIds") else t.get("key", ""),
                "service":    t.get("endpointNames", [""])[0] if t.get("endpointNames") else "",
                "endpoint":   t.get("endpointNames", ["--"])[0] if t.get("endpointNames") else "--",
                "duration":   t.get("duration", 0),
                "start_time": t.get("start", ""),
                "error":      t.get("isError", False),
            })
        return total, recent
    except Exception as e:
        logger.warning("[obs] SkyWalking trace count failed: %s", e)
        return 0, []


# ── 辅助：从 Prometheus 获取告警数（alertmanager alerts） ──────────────────

async def _get_alert_count() -> tuple[int, list[dict]]:
    """返回 (alert_count, recent_alerts)"""
    try:
        # 尝试通过 Prometheus ALERTS 指标
        result = await prom.query('ALERTS{alertstate="firing"}', timeout=5)
        data = result.get("data", {}).get("result", [])
        alerts = []
        for item in data:
            metric = item.get("metric", {})
            alerts.append({
                "service":    metric.get("job", metric.get("instance", "unknown")),
                "name":       metric.get("alertname", "Unknown Alert"),
                "severity":   metric.get("severity", "warning"),
                "namespace":  metric.get("namespace", "production"),
                "time":       datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
            })
        return len(alerts), alerts[:10]
    except Exception as e:
        logger.warning("[obs] Alert count failed: %s", e)
        return 0, []


# ── 辅助：构造有问题的服务列表（根因中心数据） ─────────────────────────────

async def _get_problem_services(error_breakdown: list[dict], recent_alerts: list[dict]) -> list[dict]:
    """合并 Loki 错误服务 + 告警服务，生成根因中心卡片数据"""
    service_map: dict[str, dict] = {}

    for item in error_breakdown:
        svc = item["service"]
        if svc not in service_map:
            service_map[svc] = {
                "service":  svc,
                "errors":   0,
                "alerts":   0,
                "traces":   0,
                "severity": "warning",
                "summary":  "",
            }
        service_map[svc]["errors"] += item["count"]
        service_map[svc]["severity"] = "error" if item["count"] > 50 else "warning"
        service_map[svc]["summary"] = f"最近 1h 产生 {item['count']} 条错误日志"

    for alert in recent_alerts:
        svc = alert["service"]
        if svc not in service_map:
            service_map[svc] = {
                "service":  svc,
                "errors":   0,
                "alerts":   0,
                "traces":   0,
                "severity": alert.get("severity", "warning"),
                "summary":  alert.get("name", ""),
            }
        service_map[svc]["alerts"] += 1

    result = sorted(service_map.values(), key=lambda x: (x["alerts"] + x["errors"]), reverse=True)
    return result[:6]


# ══════════════════════════════════════════════════════════════════════════════
# 端点：GET /api/observability/overview
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/overview")
async def get_overview(hours: int = Query(1, ge=1, le=24)):
    """
    汇总返回：
      - alert_count      告警触发数
      - error_count      服务错误数
      - trace_count      Trace 量
      - grafana_count    Grafana 看板数
      - recent_alerts    最近告警列表
      - recent_traces    最近 Trace 列表
      - problem_services 有问题的服务（根因中心）
      - grafana_boards   看板列表
    """
    (alert_count, recent_alerts), \
    (error_count, error_breakdown), \
    (trace_count, recent_traces) = await asyncio.gather(
        _get_alert_count(),
        _get_loki_error_count(hours),
        _get_sw_trace_count(hours),
    )

    problem_services = await _get_problem_services(error_breakdown, recent_alerts)

    grafana_boards = _build_grafana_boards()
    return {
        "alert_count":      alert_count,
        "error_count":      error_count,
        "trace_count":      trace_count,
        "grafana_count":    len(grafana_boards),
        "hours":            hours,
        "recent_alerts":    recent_alerts,
        "recent_traces":    recent_traces,
        "problem_services": problem_services,
        "grafana_boards":   grafana_boards,
        "error_breakdown":  error_breakdown,
        "timestamp":        datetime.now(timezone.utc).isoformat(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# 端点：GET /api/observability/alerts
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/alerts")
async def get_alerts(limit: int = Query(20, ge=1, le=100)):
    _, alerts = await _get_alert_count()
    return {"data": alerts, "total": len(alerts)}


# ══════════════════════════════════════════════════════════════════════════════
# 端点：GET /api/observability/traces
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/traces")
async def get_traces(hours: int = Query(1), limit: int = Query(20)):
    _, traces = await _get_sw_trace_count(hours)
    return {"data": traces[:limit], "total": len(traces)}


# ══════════════════════════════════════════════════════════════════════════════
# 端点：GET /api/observability/services
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/services")
async def get_problem_services(hours: int = Query(1)):
    (_, recent_alerts), (_, error_breakdown) = await asyncio.gather(
        _get_alert_count(),
        _get_loki_error_count(hours),
    )
    services = await _get_problem_services(error_breakdown, recent_alerts)
    return {"data": services}


# ══════════════════════════════════════════════════════════════════════════════
# 端点：POST /api/observability/analyze  （SSE 流式 AI 分析）
# ══════════════════════════════════════════════════════════════════════════════

class AnalyzeRequest:
    pass

from pydantic import BaseModel

class AnalyzeReq(BaseModel):
    question: str = "分析当前系统健康状况"
    hours: int = 1

@router.post("/analyze")
async def analyze_observability(req: AnalyzeReq):
    """对可观测性数据做 AI 流式分析"""

    async def _stream():
        # 1. 收集上下文数据
        try:
            (alert_count, recent_alerts), \
            (error_count, error_breakdown), \
            (trace_count, recent_traces) = await asyncio.gather(
                _get_alert_count(),
                _get_loki_error_count(req.hours),
                _get_sw_trace_count(req.hours),
            )
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"
            return

        # 2. 构造 prompt
        context_lines = [
            f"当前时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"统计时间范围：最近 {req.hours} 小时",
            f"",
            f"## 告警概况",
            f"- 触发告警数：{alert_count}",
        ]
        for a in recent_alerts[:5]:
            context_lines.append(f"  - [{a.get('severity','?')}] {a.get('service','?')}: {a.get('name','?')}")

        context_lines += [
            f"",
            f"## 服务错误",
            f"- 错误总数：{error_count}",
        ]
        for e in error_breakdown[:5]:
            context_lines.append(f"  - {e['service']}: {e['count']} 条错误")

        context_lines += [
            f"",
            f"## APM Trace",
            f"- Trace 总量：{trace_count}",
        ]
        for t in recent_traces[:3]:
            status = "❌" if t.get("error") else "✅"
            context_lines.append(f"  - {status} {t.get('service','?')} {t.get('endpoint','?')} {t.get('duration',0)}ms")

        prompt = "\n".join(context_lines)
        prompt += f"\n\n---\n用户问题：{req.question}"

        system = (
            "你是一名资深 SRE 工程师，负责分析可观测性平台数据。"
            "请根据以下运维数据，给出简洁的根因分析和行动建议。"
            "输出格式：\n## 告警分析\n## 错误根因\n## 建议行动\n"
            "每节保持简短，建议行动使用编号列表，最多3条。"
        )

        # 3. 流式输出
        try:
            full_prompt = f"{system}\n\n{prompt}"
            async for chunk in analyzer.provider.stream(full_prompt, max_tokens=1500):
                yield f"data: {json.dumps({'type':'token','text':chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"
        finally:
            yield f"data: {json.dumps({'type':'done'})}\n\n"

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
