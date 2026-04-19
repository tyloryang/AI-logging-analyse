"""事件墙路由 — /api/events/*

从 Prometheus 告警 + Loki 错误日志聚合实时事件流。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/events", tags=["events"])

_SEVERITY_ORDER = {"critical": 0, "error": 1, "warning": 2, "info": 3}


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("")
async def list_events(
    hours: int = Query(24, ge=1, le=168),
    severity: str = Query("", description="critical/error/warning/info，空=全部"),
    source: str = Query("", description="prometheus/loki，空=全部"),
    limit: int = Query(200, ge=1, le=500),
):
    """聚合 Prometheus 告警 + Loki 错误日志，返回统一事件列表。"""
    from state import prom, loki

    events: list[dict] = []

    # ── Prometheus firing alerts ──────────────────────────────────────
    if not source or source == "prometheus":
        try:
            result = await prom.query_instant('ALERTS{alertstate="firing"}')
            for item in (result or []):
                metric = item.get("metric", {})
                sev = (metric.get("severity") or "warning").lower()
                events.append({
                    "id":       f"prom-{metric.get('alertname','?')}-{metric.get('instance','')}",
                    "source":   "prometheus",
                    "severity": sev,
                    "title":    metric.get("alertname", "告警"),
                    "message":  metric.get("summary") or metric.get("description") or "",
                    "service":  metric.get("job") or metric.get("instance") or "",
                    "instance": metric.get("instance", ""),
                    "labels":   metric,
                    "time":     _now_ts(),
                    "status":   "firing",
                })
        except Exception as exc:
            logger.debug("[events] Prometheus alerts failed: %s", exc)

    # ── Loki error logs ───────────────────────────────────────────────
    if not source or source == "loki":
        try:
            logs = await loki.query_logs(service="", hours=hours, limit=limit, level="error")
            for log in logs:
                ts = log.get("timestamp", _now_ts())
                if isinstance(ts, datetime):
                    ts = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
                events.append({
                    "id":       f"loki-{ts}-{log.get('service','')}",
                    "source":   "loki",
                    "severity": "error",
                    "title":    f"[错误] {log.get('service', '未知服务')}",
                    "message":  str(log.get("message", ""))[:300],
                    "service":  log.get("service", ""),
                    "instance": "",
                    "labels":   {"level": "error", "service": log.get("service", "")},
                    "time":     ts if isinstance(ts, str) else _now_ts(),
                    "status":   "active",
                })
        except Exception as exc:
            logger.debug("[events] Loki errors failed: %s", exc)

    # ── Filter & sort ─────────────────────────────────────────────────
    if severity:
        events = [e for e in events if e["severity"] == severity]

    events.sort(key=lambda e: (_SEVERITY_ORDER.get(e["severity"], 99), e.get("time", "")))
    return events[:limit]


@router.get("/stats")
async def event_stats():
    """各级别事件计数，用于仪表盘摘要。"""
    from state import prom, loki

    stats = {"critical": 0, "error": 0, "warning": 0, "info": 0, "total": 0}

    try:
        result = await prom.query_instant('ALERTS{alertstate="firing"}')
        for item in (result or []):
            sev = (item.get("metric", {}).get("severity") or "warning").lower()
            if sev in stats:
                stats[sev] += 1
            stats["total"] += 1
    except Exception:
        pass

    try:
        logs = await loki.query_logs(service="", hours=1, limit=500, level="error")
        stats["error"] += len(logs)
        stats["total"] += len(logs)
    except Exception:
        pass

    return stats
