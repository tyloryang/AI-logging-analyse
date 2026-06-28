"""事件墙路由 — /api/events/*

从 Prometheus 告警 + Loki 错误日志聚合实时事件流。
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from cachetools import TTLCache
from fastapi import APIRouter, Body, Header, HTTPException, Query

from json_snapshot_store import read_json_file, write_json_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/events", tags=["events"])

_SEVERITY_ORDER = {"critical": 0, "error": 1, "warning": 2, "info": 3}
_stats_cache: TTLCache = TTLCache(maxsize=1, ttl=30)
_EXTERNAL_EVENTS_FILE = Path(__file__).parent.parent / "data" / "events_external.json"
_EXTERNAL_SOURCES = [
    {"code": "jenkins", "name": "Jenkins", "auth": "webhook", "description": "构建开始、成功、失败、回滚和部署流水线事件"},
    {"code": "gitlab", "name": "GitLab", "auth": "webhook", "description": "push、merge request、tag、pipeline 和 deployment 事件"},
    {"code": "argocd", "name": "ArgoCD", "auth": "webhook", "description": "应用同步、健康状态、回滚和 GitOps 发布事件"},
    {"code": "jira", "name": "Jira", "auth": "webhook", "description": "issue 创建、流转、发布关联和故障工单事件"},
    {"code": "custom", "name": "自定义事件源", "auth": "webhook", "description": "内部系统按统一事件规范写入事件墙"},
]


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_external_events() -> list[dict]:
    data = read_json_file(_EXTERNAL_EVENTS_FILE, default=[])
    return data if isinstance(data, list) else []


def _save_external_events(events: list[dict]) -> None:
    write_json_file(_EXTERNAL_EVENTS_FILE, events[:1000], ensure_parent=True)


def _safe_get(payload: dict[str, Any], path: str, default: Any = "") -> Any:
    cur: Any = payload
    for part in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
        if cur is None:
            return default
    return cur


def _normalize_severity(value: Any, *, result: Any = "") -> str:
    raw = str(value or result or "info").strip().lower()
    if raw in {"critical", "fatal", "blocker", "danger"}:
        return "critical"
    if raw in {"error", "failed", "failure", "aborted", "degraded", "missing"}:
        return "error"
    if raw in {"warning", "warn", "partial", "pending", "unknown"}:
        return "warning"
    return "info"


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.isdigit():
            stamp = int(text)
            if stamp > 10_000_000_000:
                stamp = stamp / 1000
            return datetime.fromtimestamp(stamp, timezone.utc)
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def _event_time(payload: dict[str, Any]) -> str:
    raw = (
        payload.get("time")
        or payload.get("occurred_at")
        or payload.get("timestamp")
        or payload.get("created_at")
        or payload.get("build_timestamp")
    )
    parsed = _parse_ts(raw)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") if parsed else _now_ts()


def _normalize_external_event(source_code: str, payload: dict[str, Any]) -> dict:
    source = (source_code or "custom").strip().lower() or "custom"
    result = payload.get("result") or payload.get("status") or payload.get("state")
    title = payload.get("title") or payload.get("summary") or payload.get("message")
    service = payload.get("service") or payload.get("application") or payload.get("app")
    actor = payload.get("actor") or payload.get("user") or payload.get("username")
    resource_type = payload.get("resource_type") or source
    resource_id = payload.get("resource_id") or payload.get("id") or payload.get("event_id")
    resource_name = payload.get("resource_name") or payload.get("name") or service or ""

    if source == "jenkins":
        job_name = payload.get("job_name") or payload.get("name") or _safe_get(payload, "job.name")
        build_number = payload.get("build_number") or payload.get("number") or _safe_get(payload, "build.number")
        result = result or payload.get("phase")
        title = title or f"Jenkins {job_name or '构建事件'}"
        service = service or payload.get("application") or job_name
        actor = actor or "jenkins"
        resource_type = "jenkins_build"
        resource_id = str(build_number or resource_id or "")
        resource_name = str(job_name or resource_name or "")
    elif source == "gitlab":
        project = _safe_get(payload, "project.name") or payload.get("project_name")
        title = title or payload.get("object_kind") or payload.get("event_name") or "GitLab 事件"
        service = service or project
        actor = actor or payload.get("user_username") or payload.get("user_name")
        resource_type = "gitlab_project"
        resource_id = str(_safe_get(payload, "project.id") or resource_id or "")
        resource_name = str(_safe_get(payload, "project.path_with_namespace") or project or resource_name or "")
    elif source == "argocd":
        app_name = _safe_get(payload, "app.metadata.name") or payload.get("app_name") or service
        health = _safe_get(payload, "app.status.health.status") or payload.get("health")
        result = result or health
        title = title or f"ArgoCD {app_name or '应用同步'}"
        service = service or app_name
        actor = actor or "argocd"
        resource_type = "argocd_application"
        resource_id = str(app_name or resource_id or "")
        resource_name = str(app_name or resource_name or "")
    elif source == "jira":
        issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else {}
        fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
        title = title or fields.get("summary") or f"Jira {issue.get('key', '')}".strip() or "Jira 事件"
        actor = actor or _safe_get(payload, "user.name") or _safe_get(payload, "user.displayName")
        resource_type = "jira_issue"
        resource_id = str(issue.get("key") or issue.get("id") or resource_id or "")
        resource_name = str(fields.get("summary") or issue.get("key") or resource_name or "")

    message = payload.get("message") or payload.get("summary") or payload.get("description") or title or ""
    event_id = str(payload.get("event_id") or resource_id or uuid.uuid4())
    labels = payload.get("labels") if isinstance(payload.get("labels"), dict) else {}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else payload

    return {
        "id": f"external-{source}-{event_id}",
        "source": source,
        "severity": _normalize_severity(payload.get("severity"), result=result),
        "title": title or f"{source} 事件",
        "message": str(message)[:1000],
        "service": service or "",
        "instance": payload.get("instance") or "",
        "labels": {
            **labels,
            "event_type": payload.get("event_type") or payload.get("object_kind") or source,
            "action": payload.get("action") or payload.get("event_name") or payload.get("phase") or "",
            "actor": actor or "",
            "resource_type": resource_type,
            "resource_id": resource_id or "",
            "resource_name": resource_name or "",
        },
        "time": _event_time(payload),
        "status": payload.get("status") or ("failed" if str(result).lower() in {"failed", "failure"} else "active"),
        "metadata": metadata,
    }


def _check_ingest_token(x_event_token: str | None, authorization: str | None) -> None:
    expected = os.getenv("EVENTS_INGEST_TOKEN", "").strip()
    if not expected:
        return
    auth = (authorization or "").strip()
    token = (x_event_token or "").strip()
    if token == expected or auth == f"Bearer {expected}":
        return
    raise HTTPException(status_code=401, detail="invalid event ingest token")


@router.get("/sources")
async def event_sources():
    """返回内置和外部事件源接入说明。"""
    token_required = bool(os.getenv("EVENTS_INGEST_TOKEN", "").strip())
    return {
        "builtin": [
            {"code": "prometheus", "name": "Prometheus", "description": "firing alerts"},
            {"code": "loki", "name": "Loki", "description": "error logs"},
        ],
        "external": _EXTERNAL_SOURCES,
        "ingest_endpoint": "/api/events/ingest/{source}",
        "auth": "X-Event-Token or Authorization: Bearer <token>" if token_required else "disabled in current environment",
    }


@router.post("/ingest/{source_code}")
async def ingest_external_event(
    source_code: str,
    payload: dict[str, Any] = Body(...),
    x_event_token: str | None = Header(default=None, alias="X-Event-Token"),
    authorization: str | None = Header(default=None, alias="Authorization"),
):
    """外部系统 webhook 接入事件墙，参考 sxdevops 的事件源归一化思路。"""
    _check_ingest_token(x_event_token, authorization)
    event = _normalize_external_event(source_code, payload)
    events = _load_external_events()
    old_idx = next((i for i, item in enumerate(events) if item.get("id") == event["id"]), None)
    if old_idx is None:
        events.insert(0, event)
        status = "created"
    else:
        events[old_idx] = {**events[old_idx], **event}
        status = "updated"
    _save_external_events(events)
    _stats_cache.clear()
    return {"ok": True, "status": status, "event": event}


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

    # ── External webhook events ───────────────────────────────────────────────
    if not source or source not in {"prometheus", "loki"}:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        for event in _load_external_events():
            if source and event.get("source") != source:
                continue
            occurred = _parse_ts(event.get("time"))
            if occurred and occurred < cutoff:
                continue
            events.append(event)

    # ── Filter & sort ─────────────────────────────────────────────────
    if severity:
        events = [e for e in events if e["severity"] == severity]

    events.sort(key=lambda e: (_SEVERITY_ORDER.get(e["severity"], 99), e.get("time", "")))
    return events[:limit]


@router.get("/stats")
async def event_stats():
    """各级别事件计数，用于仪表盘摘要（30s 缓存，避免每次实时扫 Loki）。"""
    from state import prom, loki

    if "stats" in _stats_cache:
        return _stats_cache["stats"]

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

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    for event in _load_external_events():
        occurred = _parse_ts(event.get("time"))
        if occurred and occurred < cutoff:
            continue
        sev = event.get("severity") or "info"
        if sev in stats:
            stats[sev] += 1
        stats["total"] += 1

    _stats_cache["stats"] = stats
    return stats
