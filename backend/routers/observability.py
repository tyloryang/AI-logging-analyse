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
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

from cachetools import TTLCache
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from json_snapshot_store import read_json_file, write_json_file
from state import loki, prom, analyzer, load_hosts_list
from skywalking_client import sw_client, check_connectivity as sw_check

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/observability", tags=["observability"])
_overview_cache: TTLCache = TTLCache(maxsize=8, ttl=15)
# 最近一次构建结果长期保留：TTL 过期后先秒回旧数据 + 后台刷新（stale-while-revalidate）
_overview_stale: dict[str, dict] = {}
_overview_refresh_tasks: dict[str, asyncio.Task] = {}
_overview_locks: dict[int, asyncio.Lock] = {}
_DEFAULT_OVERVIEW_MINUTES = 1
_MAX_WINDOW_MINUTES = 24 * 60
_RCA_SUMMARY_MAX_AGE_HOURS = 24
_OVERVIEW_PART_TIMEOUT_SECONDS = 3.0
_OVERVIEW_RESOURCE_TIMEOUT_SECONDS = 4.0
_OVERVIEW_PROBLEM_TIMEOUT_SECONDS = 2.0


def _normalize_problem_severity(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"critical", "error", "fatal", "high"}:
        return "error"
    return "warning"


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clean_markdown_line(line: str) -> str:
    value = str(line or "")
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = value.replace("**", "").replace("__", "")
    value = re.sub(r"^\s*[-*]\s*", "", value)
    value = re.sub(r"^\s*\d+\.\s*", "", value)
    return " ".join(value.split()).strip()


def _extract_rca_summary(result: str) -> str:
    text = str(result or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    summary_match = re.search(
        r"^##\s*根因摘要\s*$\n+([\s\S]*?)(?=^##\s+|\Z)",
        text,
        flags=re.MULTILINE,
    )
    if summary_match:
        lines = [
            _clean_markdown_line(line)
            for line in summary_match.group(1).splitlines()
        ]
        lines = [line for line in lines if line]
        if lines:
            return " ".join(lines[:2])[:240].rstrip()

    plain_lines: list[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("## "):
            continue
        cleaned = _clean_markdown_line(stripped)
        if not cleaned:
            continue
        plain_lines.append(cleaned)
        if len(plain_lines) >= 2:
            break
    return " ".join(plain_lines)[:240].rstrip()


def _load_recent_rca_records(max_age_hours: int = _RCA_SUMMARY_MAX_AGE_HOURS) -> list[dict]:
    try:
        from services.rca_engine import list_rca
    except Exception as exc:
        logger.warning("[obs] RCA history load failed: %s", exc)
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    records: list[dict] = []
    for record in list_rca(200):
        created_at = _parse_iso_datetime(record.get("created_at"))
        if not created_at or created_at < cutoff:
            continue

        result_text = str(record.get("result") or "")
        if "AI 分析失败" in result_text:
            continue

        summary = _extract_rca_summary(result_text)
        if not summary:
            continue

        item = dict(record)
        item["_created_at_dt"] = created_at
        item["_summary"] = summary
        records.append(item)

    return records


def _pick_latest_service_rca(service_item: dict, recent_rca: list[dict]) -> dict | None:
    service_name = str(service_item.get("service") or "").strip()
    alert_names = {
        str(name).strip()
        for name in service_item.get("_alert_names", [])
        if str(name).strip()
    }
    linked_rca_ids = {
        str(rca_id).strip()
        for rca_id in service_item.get("_rca_ids", [])
        if str(rca_id).strip()
    }

    best_record: dict | None = None
    best_key: tuple[int, datetime] | None = None
    for record in recent_rca:
        record_id = str(record.get("id") or "").strip()
        record_service = str(record.get("service") or "").strip()
        record_alert_name = str(record.get("alert_name") or "").strip()
        created_at = record["_created_at_dt"]

        priority: int | None = None
        if record_id and record_id in linked_rca_ids:
            priority = 3
        elif service_name and record_service == service_name:
            priority = 2
        elif (
            alert_names
            and record_alert_name in alert_names
            and record_service in {service_name, "global"}
        ):
            priority = 1

        if priority is None:
            continue

        candidate_key = (priority, created_at)
        if best_key is None or candidate_key > best_key:
            best_key = candidate_key
            best_record = record

    return best_record

# Grafana 看板定义（uid 与 Grafana 官方 dashboard uid 对齐）
_GRAFANA_BOARD_DEFS = [
    {"id": "node-exporter",  "title": "Node Exporter Full",    "uid": "rYdddlPWk"},
    {"id": "jvm",            "title": "JVM Micrometer",        "uid": "4PSsg1MZz"},
    {"id": "mysql",          "title": "MySQL Overview",        "uid": "MQWgroiiz"},
    {"id": "redis",          "title": "Redis Dashboard",       "uid": "x7ozmSZMk"},
]

def _build_grafana_boards():
    """每次调用时读取 env + settings.json，支持热更新和自定义看板"""
    base = os.getenv("GRAFANA_URL", "").strip().rstrip("/")
    # 合并默认 + 自定义
    try:
        settings_file = Path(__file__).resolve().parent.parent / "data" / "settings.json"
        custom_boards: list[dict] = []
        d = read_json_file(settings_file, default={})
        if isinstance(d, dict):
            custom_boards = d.get("grafana_boards", [])
    except Exception:
        custom_boards = []

    combined = list(_GRAFANA_BOARD_DEFS)
    existing_ids = {b["id"] for b in combined}
    for b in custom_boards:
        if b.get("id") not in existing_ids:
            combined.append(b)

    result = []
    for b in combined:
        if b.get("url"):
            result.append({**b})
        elif base and b.get("uid"):
            result.append({**b, "url": f"{base}/d/{b['uid']}/{b['id']}"})
        else:
            result.append({**b, "url": ""})
    return result


def _normalize_window(
    hours: Optional[int] = None,
    minutes: Optional[int] = None,
) -> tuple[float, int]:
    if minutes is not None:
        window_minutes = minutes
    elif hours is not None:
        window_minutes = hours * 60
    else:
        window_minutes = _DEFAULT_OVERVIEW_MINUTES
    window_minutes = max(1, min(window_minutes, _MAX_WINDOW_MINUTES))
    return window_minutes / 60, window_minutes


def _format_window_label(window_minutes: int) -> str:
    if window_minutes < 60:
        return f"{window_minutes}m"
    hours, minutes = divmod(window_minutes, 60)
    if minutes == 0:
        return f"{hours}h"
    return f"{hours}h{minutes}m"


def _format_window_text(window_minutes: int) -> str:
    if window_minutes < 60:
        return f"{window_minutes} 分钟"
    hours, minutes = divmod(window_minutes, 60)
    if minutes == 0:
        return f"{hours} 小时"
    return f"{hours} 小时 {minutes} 分钟"


# ── 辅助：从 Loki 获取各服务错误数 ─────────────────────────────────────────

async def _get_loki_error_count(hours: float = 1, *, raise_on_error: bool = False) -> tuple[int, list[dict]]:
    """返回 (total_error_count, [{service, count}]) """
    try:
        counts = await loki.count_errors_by_service_fast(hours=hours)
        breakdown = [
            {"service": service, "count": count}
            for service, count in counts.items()
            if count > 0
        ]
        total = sum(item["count"] for item in breakdown)
        return total, breakdown
    except Exception as e:
        logger.warning("[obs] Loki error count failed: %s", e)
        if raise_on_error:
            raise
        return 0, []


# ── 辅助：从 SkyWalking 获取 Trace 数 ──────────────────────────────────────

async def _get_sw_trace_count(hours: float = 1, *, raise_on_error: bool = False) -> tuple[int, list[dict]]:
    """返回 (trace_count, recent_traces)"""
    try:
        result = await sw_client.get_traces(hours=hours, page=1, page_size=10)
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
        if raise_on_error:
            raise
        return 0, []


# ── 辅助：从 Prometheus 获取告警数（alertmanager alerts） ──────────────────

_HOST_ALERT_KEYWORDS = (
    "host",
    "node",
    "instancedown",
    "machine",
    "filesystem",
    "disk",
    "load",
    "主机",
    "节点",
    "磁盘",
)


def _load_active_alert_groups(limit: int = 500) -> list[dict]:
    try:
        from services.alert_dedup import list_groups as _list_groups
        groups = _list_groups(status=None, limit=limit)
        return [g for g in groups if g.get("status") not in ("resolved", "suppressed")]
    except Exception as e:
        logger.warning("[obs] Alert groups load failed: %s", e)
        return []


def _collect_alert_labels(group: dict) -> dict[str, str]:
    labels: dict[str, str] = {}
    for source in (group.get("group_labels"), group.get("common_labels"), group.get("labels")):
        if isinstance(source, dict):
            labels.update({str(k): str(v) for k, v in source.items() if v is not None})

    for raw in group.get("raw_alerts", []) or []:
        if not isinstance(raw, dict):
            continue
        raw_labels = raw.get("labels", {})
        if isinstance(raw_labels, dict):
            labels.update({str(k): str(v) for k, v in raw_labels.items() if v is not None})

    for key in ("alertname", "service", "severity", "namespace", "env"):
        value = group.get(key)
        if value not in (None, ""):
            labels.setdefault(key, str(value))
    return labels


def _host_identity_values(hosts: list[dict]) -> set[str]:
    values: set[str] = set()
    for host in hosts:
        for key in ("ip", "hostname", "name", "instance"):
            raw = str(host.get(key) or "").strip().lower()
            if not raw:
                continue
            values.add(raw)
            values.add(raw.split(":", 1)[0])
            if key == "ip":
                values.add(f"{raw}:9100")
    values.discard("")
    return values


def _is_host_related_alert(group: dict, host_values: set[str]) -> bool:
    labels = _collect_alert_labels(group)
    alertname = str(labels.get("alertname") or group.get("alertname") or "").lower()
    service = str(labels.get("service") or group.get("service") or "").lower()
    job = str(labels.get("job") or "").lower()
    summary = " ".join(
        str(group.get(key) or "")
        for key in ("summary", "description")
    ).lower()
    infra_text = " ".join([alertname, service, job, summary])

    if any(keyword in infra_text for keyword in _HOST_ALERT_KEYWORDS):
        return True

    identity_keys = ("instance", "node", "host", "hostname", "exported_instance", "nodename")
    for key in identity_keys:
        value = str(labels.get(key) or "").strip().lower()
        if not value:
            continue
        if value in host_values or value.split(":", 1)[0] in host_values:
            return True

    return False


def _host_status_is_abnormal(host: dict) -> bool:
    status = str(host.get("status") or "").strip().lower()
    if not status:
        return False
    return status not in {"active", "online", "running", "normal", "ok", "healthy"}


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _count_not_ready(summary: dict, key: str, ready_key: str) -> int:
    item = summary.get(key) or {}
    return max(0, _to_int(item.get("total")) - _to_int(item.get(ready_key)))


def _resource_total_from_k8s_summary(summary: dict) -> int:
    return sum(
        _to_int((summary.get(key) or {}).get("total"))
        for key in (
            "pods",
            "nodes",
            "deployments",
            "daemonSets",
            "statefulSets",
            "jobs",
            "cronJobs",
        )
    )


def _container_abnormal_from_k8s_summary(summary: dict) -> dict:
    pods = _count_not_ready(summary, "pods", "running")
    nodes = _count_not_ready(summary, "nodes", "ready")
    deployments = _count_not_ready(summary, "deployments", "ready")
    daemonsets = _count_not_ready(summary, "daemonSets", "ready")
    statefulsets = _count_not_ready(summary, "statefulSets", "ready")
    workloads = deployments + daemonsets + statefulsets
    return {
        "total": pods + nodes + workloads,
        "pods": pods,
        "nodes": nodes,
        "workloads": workloads,
        "deployments": deployments,
        "daemonSets": daemonsets,
        "statefulSets": statefulsets,
    }


_k8s_summary_tasks: dict[str, asyncio.Task] = {}


async def _fetch_and_cache_k8s_summary(cluster: dict) -> dict:
    """拉取 K8s 摘要并写入 _SUMMARY_CACHE。作为独立 task 运行，
    即使调用方超时取消，本任务仍继续完成，为下次请求填充缓存。"""
    from routers import kubernetes as k8s

    core_task = asyncio.to_thread(k8s._fetch_core_summary_resources, cluster["id"])
    apps_task = asyncio.to_thread(k8s._fetch_apps_summary_resources, cluster["id"])
    batch_task = asyncio.to_thread(k8s._fetch_batch_summary_resources, cluster["id"])
    (pods, nodes), \
    (deps, daemonsets, statefulsets), \
    (jobs, cronjobs) = await asyncio.gather(core_task, apps_task, batch_task)
    summary = k8s._build_cluster_summary_payload(
        cluster,
        pods,
        deps,
        daemonsets,
        statefulsets,
        jobs,
        cronjobs,
        nodes,
    )
    k8s._SUMMARY_CACHE[cluster["id"]] = summary
    return summary


async def _get_k8s_resource_health_summary() -> dict:
    empty = {
        "available": False,
        "cluster": {},
        "resource_count": 0,
        "abnormal_count": 0,
        "abnormal": {
            "total": 0,
            "pods": 0,
            "nodes": 0,
            "workloads": 0,
            "deployments": 0,
            "daemonSets": 0,
            "statefulSets": 0,
        },
        "summary": {},
    }
    try:
        from routers import kubernetes as k8s

        cluster = k8s._get_cluster()
        cache_key = cluster["id"]
        summary = k8s._SUMMARY_CACHE.get(cache_key)
        if summary is None:
            task = _k8s_summary_tasks.get(cache_key)
            if task is None or task.done():
                task = asyncio.create_task(_fetch_and_cache_k8s_summary(cluster))
                _k8s_summary_tasks[cache_key] = task
            # shield：外层超时不取消拉取任务，跑完自动进缓存供下次秒回
            summary = await asyncio.wait_for(asyncio.shield(task), timeout=8)

        abnormal = _container_abnormal_from_k8s_summary(summary)
        return {
            "available": True,
            "cluster": summary.get("cluster", {}),
            "resource_count": _resource_total_from_k8s_summary(summary),
            "abnormal_count": abnormal["total"],
            "abnormal": abnormal,
            "summary": summary,
        }
    except asyncio.TimeoutError:
        logger.warning("[obs] K8s resource summary timed out")
        return {**empty, "error": "timeout"}
    except HTTPException as e:
        logger.debug("[obs] K8s resource summary skipped: %s", e.detail)
        return {**empty, "error": str(e.detail)}
    except Exception as e:
        logger.warning("[obs] K8s resource summary failed: %s", e)
        return {**empty, "error": str(e)}


async def _get_resource_health_summary() -> dict:
    # 文件读取走线程池避免阻塞事件循环；与 K8s 摘要三路并行
    hosts, active_alerts, k8s_summary = await asyncio.gather(
        asyncio.to_thread(load_hosts_list),
        asyncio.to_thread(_load_active_alert_groups, 500),
        _get_k8s_resource_health_summary(),
    )
    host_values = _host_identity_values(hosts)
    host_alerts = [
        group for group in active_alerts
        if _is_host_related_alert(group, host_values)
    ]
    host_count = len(hosts)
    host_status_abnormal = sum(1 for host in hosts if _host_status_is_abnormal(host))
    k8s_available = bool(k8s_summary.get("available"))
    container_resource_count = _to_int(k8s_summary.get("resource_count")) if k8s_available else None
    container_abnormal_count = _to_int(k8s_summary.get("abnormal_count")) if k8s_available else None
    resource_count = host_count + container_resource_count if container_resource_count is not None else None
    return {
        "resource_count": resource_count,
        "resource_summary": {
            "total": resource_count,
            "hosts": host_count,
            "containers": container_resource_count,
            "k8s_available": k8s_available,
        },
        "host_abnormal_alert_count": len(host_alerts),
        "host_resource_summary": {
            "total": host_count,
            "abnormal_alerts": len(host_alerts),
            "abnormal_status": host_status_abnormal,
        },
        "container_resource_count": container_resource_count,
        "container_resource_abnormal_count": container_abnormal_count,
        "container_resource_summary": k8s_summary,
    }


async def _get_alert_count(*, raise_on_error: bool = False) -> tuple[int, list[dict]]:
    """返回 (active_alert_count, recent_alerts)，直接读 AIOps 告警存储。"""
    try:
        active = await asyncio.to_thread(_load_active_alert_groups, 200)
        recent = []
        for g in active[:10]:
            recent.append({
                "group_id":   g.get("id"),
                "rca_id":     g.get("rca_id"),
                "service":   g.get("service", "unknown"),
                "name":      g.get("alertname", "Unknown Alert"),
                "alertname": g.get("alertname", ""),
                "severity":  g.get("severity", "warning"),
                "namespace": g.get("namespace", ""),
                "status":    g.get("status", "new"),
                "time":      (g.get("last_at") or "")[:16].replace("T", " "),
                "summary":   g.get("summary", ""),
            })
        return len(active), recent
    except Exception as e:
        logger.warning("[obs] Alert count failed: %s", e)
        if raise_on_error:
            raise
        return 0, []


# ── 辅助：构造有问题的服务列表（根因中心数据） ─────────────────────────────

async def _safe_overview_part(name: str, coro, *, timeout: float = _OVERVIEW_PART_TIMEOUT_SECONDS):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("[obs] overview %s timed out after %.1fs", name, timeout)
    except Exception as e:
        logger.warning("[obs] overview %s failed: %s", name, e)
    return None


def _missing_resource_health() -> dict:
    return {
        "resource_count": None,
        "resource_summary": {
            "total": None,
            "hosts": None,
            "containers": None,
            "k8s_available": False,
            "unavailable": True,
        },
        "host_abnormal_alert_count": None,
        "host_resource_summary": {
            "total": None,
            "abnormal_alerts": None,
            "abnormal_status": None,
        },
        "container_resource_count": None,
        "container_resource_abnormal_count": None,
        "container_resource_summary": {
            "available": False,
            "error": "not_fetched",
        },
    }


async def _get_problem_services_legacy(
    error_breakdown: list[dict],
    recent_alerts: list[dict],
    window_label: str = "1h",
) -> list[dict]:
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
        service_map[svc]["summary"] = f"最近 {window_label} 产生 {item['count']} 条错误日志"

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


async def _get_problem_services(
    error_breakdown: list[dict],
    recent_alerts: list[dict],
    window_label: str = "1h",
    recent_rca: list[dict] | None = None,
) -> list[dict]:
    service_map: dict[str, dict] = {}

    for item in error_breakdown:
        svc = item["service"]
        if svc not in service_map:
            service_map[svc] = {
                "service": svc,
                "errors": 0,
                "alerts": 0,
                "traces": 0,
                "severity": "warning",
                "summary": "",
                "_alert_names": [],
                "_rca_ids": [],
            }
        service_map[svc]["errors"] += item["count"]
        service_map[svc]["severity"] = "error" if item["count"] > 50 else "warning"
        service_map[svc]["summary"] = f"最近{window_label} 产生 {item['count']} 条错误日志"

    for alert in recent_alerts:
        svc = alert["service"]
        if svc not in service_map:
            service_map[svc] = {
                "service": svc,
                "errors": 0,
                "alerts": 0,
                "traces": 0,
                "severity": _normalize_problem_severity(alert.get("severity", "warning")),
                "summary": alert.get("name", ""),
                "_alert_names": [],
                "_rca_ids": [],
            }

        service_map[svc]["alerts"] += 1
        service_map[svc]["severity"] = _normalize_problem_severity(
            "error" if service_map[svc]["severity"] == "error" else alert.get("severity", "warning")
        )

        alert_name = alert.get("alertname") or alert.get("name")
        if alert_name:
            service_map[svc]["_alert_names"].append(alert_name)
        if alert.get("rca_id"):
            service_map[svc]["_rca_ids"].append(alert["rca_id"])

    if recent_rca is None:
        recent_rca = await asyncio.to_thread(_load_recent_rca_records)
    for item in service_map.values():
        matched_rca = _pick_latest_service_rca(item, recent_rca)
        if matched_rca:
            item["summary"] = matched_rca["_summary"]
            item["summary_source"] = "rca"
            item["rca_id"] = matched_rca.get("id")
            item["rca_created_at"] = matched_rca.get("created_at")
            item["rca_alert_name"] = matched_rca.get("alert_name", "")
        else:
            item["summary_source"] = "signals"
            item["rca_id"] = None
            item["rca_created_at"] = None
            item["rca_alert_name"] = ""

        item.pop("_alert_names", None)
        item.pop("_rca_ids", None)

    result = sorted(service_map.values(), key=lambda x: (x["alerts"] + x["errors"]), reverse=True)
    return result[:6]


# ══════════════════════════════════════════════════════════════════════════════
# 端点：GET /api/observability/overview
# ══════════════════════════════════════════════════════════════════════════════

async def _build_overview(window_hours: float, window_minutes: int) -> dict:
    """实际拉取各数据源并组装 payload（不含缓存逻辑）。"""
    window_label = _format_window_label(window_minutes)
    window_text = _format_window_text(window_minutes)

    alert_part, error_part, trace_part, resource_health_part, rca_part = await asyncio.gather(
        _safe_overview_part("alerts", _get_alert_count(raise_on_error=True)),
        _safe_overview_part("loki", _get_loki_error_count(window_hours, raise_on_error=True)),
        _safe_overview_part("skywalking", _get_sw_trace_count(window_hours, raise_on_error=True)),
        _safe_overview_part(
            "resources",
            _get_resource_health_summary(),
            timeout=_OVERVIEW_RESOURCE_TIMEOUT_SECONDS,
        ),
        # RCA 历史提前并行读，problem_services 阶段免二次等待
        _safe_overview_part("rca_history", asyncio.to_thread(_load_recent_rca_records)),
    )

    alert_count, recent_alerts = alert_part if alert_part is not None else (None, [])
    error_count, error_breakdown = error_part if error_part is not None else (None, [])
    trace_count, recent_traces = trace_part if trace_part is not None else (None, [])
    resource_health = resource_health_part if resource_health_part is not None else _missing_resource_health()

    problem_services = []
    if alert_part is not None or error_part is not None:
        problem_services = await _safe_overview_part(
            "problem_services",
            _get_problem_services(
                error_breakdown,
                recent_alerts,
                window_label=window_label,
                recent_rca=rca_part if rca_part is not None else [],
            ),
            timeout=_OVERVIEW_PROBLEM_TIMEOUT_SECONDS,
        ) or []
    grafana_boards = _build_grafana_boards()
    fetch_status = {
        "alerts": alert_part is not None,
        "loki": error_part is not None,
        "skywalking": trace_part is not None,
        "resources": resource_health_part is not None,
        "k8s": bool(resource_health.get("resource_summary", {}).get("k8s_available")),
    }

    return {
        "alert_count": alert_count,
        **resource_health,
        "error_count": error_count,
        "trace_count": trace_count,
        "grafana_count": len(grafana_boards),
        "hours": round(window_hours, 4),
        "minutes": window_minutes,
        "window_label": window_label,
        "window_text": window_text,
        "recent_alerts": recent_alerts,
        "recent_traces": recent_traces,
        "problem_services": problem_services,
        "grafana_boards": grafana_boards,
        "grafana_url": os.getenv("GRAFANA_URL", "").strip().rstrip("/"),
        "error_breakdown": error_breakdown,
        "fetch_status": fetch_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _rebuild_overview(cache_key: str, window_hours: float, window_minutes: int, *, force: bool = False) -> dict:
    """加锁重建总览并写缓存。部分数据源失败也缓存（15s TTL），避免每次请求重复吃满超时。"""
    lock = _overview_locks.setdefault(window_minutes, asyncio.Lock())
    async with lock:
        if not force:
            cached = _overview_cache.get(cache_key)
            if cached is not None:
                return cached
        payload = await _build_overview(window_hours, window_minutes)
        _overview_cache[cache_key] = payload
        _overview_stale[cache_key] = payload
        return payload


def _schedule_overview_refresh(cache_key: str, window_hours: float, window_minutes: int) -> None:
    """后台刷新（stale-while-revalidate 的 revalidate 半边），同 key 只保留一个在跑。"""
    task = _overview_refresh_tasks.get(cache_key)
    if task is not None and not task.done():
        return

    async def _run():
        try:
            await _rebuild_overview(cache_key, window_hours, window_minutes)
        except Exception as exc:
            logger.warning("[obs] overview 后台刷新失败: %s", exc)

    _overview_refresh_tasks[cache_key] = asyncio.create_task(_run())


@router.get("/overview")
async def get_overview(
    hours: Optional[int] = Query(None, ge=1, le=24),
    minutes: Optional[int] = Query(None, ge=1, le=_MAX_WINDOW_MINUTES),
    refresh: bool = Query(False, description="跳过缓存强制重建（手动刷新按钮）"),
):
    """
    汇总返回：
      - alert_count      告警触发数
      - resource_count   CMDB + K8s 资源数量
      - host_abnormal_alert_count 主机运行异常告警数
      - container_resource_abnormal_count 容器资源异常数量
      - error_count      服务错误数
      - trace_count      Trace 量
      - grafana_count    Grafana 看板数
      - recent_alerts    最近告警列表
      - recent_traces    最近 Trace 列表
      - problem_services 有问题的服务（根因中心）
      - grafana_boards   看板列表

    加载策略：TTL 缓存命中秒回 → 过期但有旧数据则秒回旧数据并后台刷新 → 首次同步构建。
    """
    window_hours, window_minutes = _normalize_window(hours=hours, minutes=minutes)
    cache_key = f"overview:{window_minutes}"

    if not refresh:
        cached = _overview_cache.get(cache_key)
        if cached is not None:
            return cached
        stale = _overview_stale.get(cache_key)
        if stale is not None:
            _schedule_overview_refresh(cache_key, window_hours, window_minutes)
            return {**stale, "stale": True}

    return await _rebuild_overview(cache_key, window_hours, window_minutes, force=refresh)


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

class AnalyzeReq(BaseModel):
    question: str = "分析当前系统健康状况"
    hours: Optional[int] = None
    minutes: Optional[int] = None

async def _get_host_metrics() -> list[dict]:
    """获取 CMDB 所有主机的 Prometheus 实时指标。"""
    try:
        cmdb_hosts = load_hosts_list()
        if not cmdb_hosts:
            return []
        all_metrics    = await prom.get_all_host_metrics()
        all_partitions = await prom.get_all_partitions()
        # 建立 ip → instance 映射
        discovered = await prom.discover_hosts()
        ip_to_inst = {h["ip"]: h["instance"] for h in discovered if h.get("ip")}

        result = []
        for h in cmdb_hosts:
            ip   = h.get("ip", "")
            inst = ip_to_inst.get(ip, f"{ip}:9100")
            m    = all_metrics.get(inst, {})
            parts = all_partitions.get(inst, [])
            # 取根分区使用率
            root_disk = next((p["usage_pct"] for p in parts if p.get("mountpoint") == "/"), None)
            result.append({
                "hostname":  h.get("hostname") or ip,
                "ip":        ip,
                "group":     h.get("group", ""),
                "env":       h.get("env", ""),
                "cpu":       m.get("cpu_usage"),
                "mem":       m.get("mem_usage"),
                "disk_root": root_disk,
                "load5":     m.get("load5"),
                "has_data":  bool(m),
            })
        return result
    except Exception as e:
        logger.warning("[analyze] 获取主机指标失败: %s", e)
        return []


async def _get_k8s_summary() -> dict:
    """获取 K8s 集群摘要（Pod 状态）。"""
    try:
        from services.k8s_store import load_k8s_clusters
        clusters = load_k8s_clusters()
        if not clusters:
            return {}
        from kubernetes import client as k8s_client, config as k8s_config
        default_cluster = next((c for c in clusters if c.get("default")), clusters[0])
        kubeconfig = default_cluster.get("kubeconfig_content") or default_cluster.get("kubeconfig_path")
        if not kubeconfig:
            return {}
        # 简化：直接返回已知信息
        return {"cluster_name": default_cluster.get("name", "default")}
    except Exception:
        return {}


@router.post("/analyze")
async def analyze_observability(req: AnalyzeReq):
    """对可观测性数据做全面 AI 流式分析（含服务器状态）"""
    window_hours, window_minutes = _normalize_window(hours=req.hours, minutes=req.minutes)
    window_text = _format_window_text(window_minutes)

    async def _stream():
        # 1. 并发收集所有上下文数据
        try:
            results = await asyncio.gather(
                _get_alert_count(),
                _get_loki_error_count(window_hours),
                _get_sw_trace_count(window_hours),
                _get_host_metrics(),
                return_exceptions=True,
            )
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"
            return

        (alert_count, recent_alerts) = results[0] if not isinstance(results[0], Exception) else (0, [])
        (error_count, error_breakdown) = results[1] if not isinstance(results[1], Exception) else (0, [])
        (trace_count, recent_traces)  = results[2] if not isinstance(results[2], Exception) else (0, [])
        host_metrics = results[3] if not isinstance(results[3], Exception) else []

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 2. 构造全面 prompt
        context_lines = [
            f"当前时间：{now_str}",
            f"统计范围：最近 {window_text}",
            "",
        ]

        # ── 服务器状态 ──────────────────────────────────────────
        context_lines.append("## 服务器实时状态")
        if host_metrics:
            has_data_hosts = [h for h in host_metrics if h["has_data"]]
            no_data_hosts  = [h for h in host_metrics if not h["has_data"]]

            if has_data_hosts:
                # 危险指标（CPU>80 / 内存>85 / 磁盘>85）
                danger = []
                warn   = []
                normal = []
                for h in has_data_hosts:
                    issues = []
                    if h["cpu"] is not None and h["cpu"] > 80:
                        issues.append(f"CPU {h['cpu']:.0f}%")
                    if h["mem"] is not None and h["mem"] > 85:
                        issues.append(f"内存 {h['mem']:.0f}%")
                    if h["disk_root"] is not None and h["disk_root"] > 85:
                        issues.append(f"磁盘 {h['disk_root']:.0f}%")
                    if issues:
                        if any(">90" in i or int(''.join(filter(str.isdigit, i.split()[1].rstrip('%'))))>=90 for i in issues if '%' in i):
                            danger.append((h, issues))
                        else:
                            warn.append((h, issues))
                    else:
                        normal.append(h)

                context_lines.append(f"- 在线主机：{len(has_data_hosts)} 台，离线/无数据：{len(no_data_hosts)} 台")
                if danger:
                    context_lines.append(f"- 🔴 严重异常主机（{len(danger)} 台）：")
                    for h, issues in danger[:5]:
                        context_lines.append(f"    {h['hostname']}({h['ip']}) {' / '.join(issues)}")
                if warn:
                    context_lines.append(f"- 🟡 警告主机（{len(warn)} 台）：")
                    for h, issues in warn[:5]:
                        context_lines.append(f"    {h['hostname']}({h['ip']}) {' / '.join(issues)}")
                if normal:
                    context_lines.append(f"- ✅ 正常主机：{len(normal)} 台")

                # 最高资源占用
                by_cpu  = sorted([h for h in has_data_hosts if h["cpu"] is not None],  key=lambda x: -x["cpu"])
                by_mem  = sorted([h for h in has_data_hosts if h["mem"] is not None],  key=lambda x: -x["mem"])
                by_disk = sorted([h for h in has_data_hosts if h["disk_root"] is not None], key=lambda x: -x["disk_root"])
                if by_cpu:
                    context_lines.append(f"- CPU 最高：{by_cpu[0]['hostname']} {by_cpu[0]['cpu']:.1f}%")
                if by_mem:
                    context_lines.append(f"- 内存最高：{by_mem[0]['hostname']} {by_mem[0]['mem']:.1f}%")
                if by_disk:
                    context_lines.append(f"- 磁盘最高：{by_disk[0]['hostname']} {by_disk[0]['disk_root']:.1f}%（根分区）")

            if no_data_hosts:
                names = ", ".join(h["hostname"] for h in no_data_hosts[:5])
                context_lines.append(f"- 无 Prometheus 数据（未安装 node_exporter 或离线）：{names}")
        else:
            context_lines.append("- 暂无主机数据（Prometheus 未配置或无 CMDB 主机）")

        # ── 告警 ────────────────────────────────────────────────
        context_lines += ["", "## 告警状态"]
        context_lines.append(f"- 活跃告警：{alert_count} 条")
        if recent_alerts:
            # 按严重度统计
            by_sev: dict[str, int] = {}
            for a in recent_alerts:
                s = a.get("severity", "unknown")
                by_sev[s] = by_sev.get(s, 0) + 1
            for sev, cnt in sorted(by_sev.items(), key=lambda x: {"critical":0,"error":1,"warning":2}.get(x[0],9)):
                context_lines.append(f"  - {sev}: {cnt} 条")
            context_lines.append("- 最近告警：")
            for a in recent_alerts[:5]:
                context_lines.append(f"  [{a.get('severity','?')}] {a.get('service','?')}: {a.get('alertname') or a.get('name','?')}")

        # ── 日志错误 ────────────────────────────────────────────
        context_lines += ["", "## 日志错误（Loki）"]
        context_lines.append(f"- 错误日志总数：{error_count} 条（最近 {window_text}）")
        if error_breakdown:
            context_lines.append("- 错误最多的服务：")
            for e in error_breakdown[:8]:
                context_lines.append(f"  - {e['service']}: {e['count']} 条")

        # ── APM Trace ───────────────────────────────────────────
        context_lines += ["", "## APM 链路追踪（SkyWalking）"]
        context_lines.append(f"- Trace 总量：{trace_count}")
        if recent_traces:
            errors = [t for t in recent_traces if t.get("error")]
            slow   = [t for t in recent_traces if t.get("duration", 0) > 1000]
            if errors:
                context_lines.append(f"- 错误 Trace：{len(errors)} 条")
                for t in errors[:3]:
                    context_lines.append(f"  ❌ {t.get('service','?')} {t.get('endpoint','?')} {t.get('duration',0)}ms")
            if slow:
                context_lines.append(f"- 慢请求（>1s）：{len(slow)} 条")

        prompt = "\n".join(context_lines)
        prompt += f"\n\n---\n用户问题：{req.question}"

        system = (
            "你是一名资深 SRE 工程师，负责全栈运维分析。"
            "请根据以下全面的运维数据（服务器状态 + 告警 + 日志 + 链路追踪），"
            "给出系统当前健康状况的综合评估和优先处理建议。\n"
            "输出格式：\n"
            "## 🖥️ 服务器状况\n（分析 CPU/内存/磁盘异常，点出需关注的主机）\n"
            "## 🚨 告警与错误\n（归纳告警模式和日志错误根因）\n"
            "## 🔗 链路追踪\n（是否有慢接口或错误接口）\n"
            "## ✅ 优先处理建议\n（编号列表，最多5条，按紧急程度排序）\n"
            "语言简洁专业，每节不超过5行。"
        )

        # 3. 流式输出
        try:
            full_prompt = f"{system}\n\n{prompt}"
            async for chunk in analyzer.provider.stream(full_prompt, max_tokens=2000):
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


# ══════════════════════════════════════════════════════════════════════════════
# Grafana 看板管理（自定义看板增删改查）
# 自定义看板存储在 data/settings.json["grafana_boards"]
# ══════════════════════════════════════════════════════════════════════════════

from pathlib import Path as _Path

_SETTINGS_FILE = _Path(__file__).resolve().parent.parent / "data" / "settings.json"


def _load_settings() -> dict:
    data = read_json_file(_SETTINGS_FILE, default={})
    return data if isinstance(data, dict) else {}


def _save_settings(data: dict) -> None:
    write_json_file(_SETTINGS_FILE, data, ensure_parent=True)


def _all_boards_raw() -> list[dict]:
    """合并默认看板 + 自定义看板"""
    custom: list[dict] = _load_settings().get("grafana_boards", [])
    combined = list(_GRAFANA_BOARD_DEFS)
    existing_ids = {b["id"] for b in combined}
    for b in custom:
        if b.get("id") not in existing_ids:
            combined.append(b)
    return combined


class GrafanaBoardIn(BaseModel):
    title: str
    uid: str = ""
    url: str = ""   # 完整 URL（直接填写时优先；uid 用于拼接）


class PrometheusInstantQueryIn(BaseModel):
    query: str
    time: Optional[float] = None


class PrometheusRangeQueryIn(BaseModel):
    query: str
    start: float
    end: float
    step: int = 60


class PrometheusLabelFilter(BaseModel):
    label: str
    op: str = "="
    value: str = ""


class HttpServerMetricsRequest(BaseModel):
    metric: str = "http_server_requests_seconds_count"
    filters: list[PrometheusLabelFilter] = []
    group_by: list[str] = ["application", "uri", "method"]
    range_minutes: int = 30
    step: int = 60
    rate_window: str = "5m"
    top_n: int = 20


_PROM_LABEL_RE = re.compile(r"^[a-zA-Z_:][a-zA-Z0-9_:]*$")
_PROM_DURATION_RE = re.compile(r"^[1-9][0-9]*(s|m|h|d|w|y)$")
_HTTP_SERVER_DEFAULT_LABELS = [
    "application",
    "app",
    "service",
    "job",
    "uri",
    "method",
    "status",
    "outcome",
    "exception",
    "instance",
    "namespace",
    "pod",
]


def _validate_metric_name(metric: str) -> str:
    value = str(metric or "").strip()
    if not _PROM_LABEL_RE.match(value):
        raise HTTPException(status_code=400, detail="invalid metric name")
    return value


def _validate_label_name(label: str) -> str:
    value = str(label or "").strip()
    if not _PROM_LABEL_RE.match(value) or value == "le":
        raise HTTPException(status_code=400, detail=f"invalid label name: {label}")
    return value


def _escape_prom_value(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _sanitize_rate_window(value: str) -> str:
    raw = str(value or "5m").strip()
    return raw if _PROM_DURATION_RE.match(raw) else "5m"


def _label_selector(filters: list[PrometheusLabelFilter] | None, *, extra: str = "") -> str:
    parts: list[str] = []
    for item in filters or []:
        label = _validate_label_name(item.label)
        op = str(item.op or "=").strip()
        if op not in {"=", "!=", "=~", "!~"}:
            raise HTTPException(status_code=400, detail=f"invalid matcher operator: {op}")
        value = str(item.value or "").strip()
        if not value:
            continue
        parts.append(f'{label}{op}"{_escape_prom_value(value)}"')
    if extra:
        parts.append(extra)
    return "{" + ",".join(parts) + "}" if parts else ""


def _sanitize_group_by(labels: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    for label in labels or []:
        value = _validate_label_name(label)
        if value not in cleaned:
            cleaned.append(value)
        if len(cleaned) >= 8:
            break
    return cleaned or ["application", "uri", "method"]


def _group_clause(labels: list[str]) -> str:
    return "(" + ",".join(labels) + ")" if labels else ""


def _series_key(metric: dict, group_by: list[str]) -> str:
    return "|".join(f"{label}={metric.get(label, '')}" for label in group_by)


def _series_label(metric: dict, group_by: list[str]) -> str:
    parts = [str(metric.get(label) or "-") for label in group_by if label != "status"]
    return " / ".join(parts) if parts else "total"


def _last_matrix_value(series: dict) -> float | None:
    values = series.get("values") or []
    if not values:
        return None
    try:
        v = float(values[-1][1])
    except Exception:
        return None
    # Prometheus 对 histogram_quantile/除零返回 "NaN"/"+Inf"，float() 会得到
    # nan/inf，JSON 序列化会 500。这里统一清成 None（真实 http_server 数据同样受保护）。
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


async def _safe_prom_range(query: str, start: float, end: float, step: int) -> list[dict]:
    try:
        return await prom.query_range(query, start=start, end=end, step=step, timeout=30)
    except Exception as exc:
        logger.warning("[http-server-metrics] query failed: %s query=%s", exc, query[:240])
        return []


async def _safe_prom_instant(query: str) -> list[dict]:
    try:
        return await prom.query_instant(query, timeout=20)
    except Exception as exc:
        logger.warning("[http-server-metrics] instant query failed: %s query=%s", exc, query[:240])
        return []


@router.post("/metrics/query")
async def query_prometheus_instant(body: PrometheusInstantQueryIn):
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    try:
        result = await prom.query_instant(query, timeout=20, time_ts=body.time)
        return {
            "status": "success",
            "result_type": "vector",
            "data": result,
            "query": query,
            "series_count": len(result),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/metrics/query-range")
async def query_prometheus_range(body: PrometheusRangeQueryIn):
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    if body.end <= body.start:
        raise HTTPException(status_code=400, detail="end must be greater than start")
    step = max(1, min(int(body.step or 60), 3600))
    try:
        result = await prom.query_range(
            query,
            start=body.start,
            end=body.end,
            step=step,
            timeout=30,
        )
        return {
            "status": "success",
            "result_type": "matrix",
            "data": result,
            "query": query,
            "start": body.start,
            "end": body.end,
            "step": step,
            "series_count": len(result),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/metrics/label-values/{label}")
async def prometheus_label_values(
    label: str,
    limit: int = Query(200, ge=1, le=5000),
):
    try:
        values = await prom.label_values(label, timeout=15)
        values = sorted(values)
        return {"label": label, "data": values[:limit], "total": len(values)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/metrics/http-server/label-values/{label}")
async def http_server_label_values(
    label: str,
    metric: str = Query("http_server_requests_seconds_count"),
    limit: int = Query(200, ge=1, le=5000),
):
    metric_name = _validate_metric_name(metric)
    label_name = _validate_label_name(label)
    query = f"count by ({label_name}) ({metric_name})"
    try:
        result = await prom.query_instant(query, timeout=20)
        values = sorted({
            str(item.get("metric", {}).get(label_name) or "")
            for item in result
            if item.get("metric", {}).get(label_name)
        })
        return {"label": label_name, "metric": metric_name, "data": values[:limit], "total": len(values)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/metrics/http-server/labels")
async def http_server_label_inventory(
    metric: str = Query("http_server_requests_seconds_count"),
    limit: int = Query(60, ge=1, le=500),
):
    metric_name = _validate_metric_name(metric)
    labels = []
    for label in _HTTP_SERVER_DEFAULT_LABELS:
        query = f"count by ({label}) ({metric_name})"
        result = await _safe_prom_instant(query)
        values = sorted({
            str(item.get("metric", {}).get(label) or "")
            for item in result
            if item.get("metric", {}).get(label)
        })
        if values:
            labels.append({"label": label, "values": values[:limit], "total": len(values)})
    return {"metric": metric_name, "labels": labels}


@router.post("/metrics/http-server")
async def http_server_metrics(body: HttpServerMetricsRequest):
    metric = _validate_metric_name(body.metric)
    if not metric.endswith("_count"):
        raise HTTPException(status_code=400, detail="metric must be a *_count metric")

    group_by = _sanitize_group_by(body.group_by)
    group = _group_clause(group_by)
    range_minutes = max(1, min(int(body.range_minutes or 30), 24 * 60))
    step = max(5, min(int(body.step or 60), 3600))
    rate_window = _sanitize_rate_window(body.rate_window)
    top_n = max(1, min(int(body.top_n or 20), 200))
    end = datetime.now(timezone.utc).timestamp()
    start = end - range_minutes * 60

    selector = _label_selector(body.filters)
    error_selector = _label_selector(body.filters, extra='status=~"5.."')
    sum_metric = metric[:-6] + "_sum"
    bucket_metric = metric[:-6] + "_bucket"
    group_without_status = [label for label in group_by if label != "status"]
    ratio_group = _group_clause(group_without_status or group_by)

    queries = {
        "request_rate": f"sum by {group} (rate({metric}{selector}[{rate_window}]))",
        "request_count": f"sum by {group} (increase({metric}{selector}[{range_minutes}m]))",
        "error_rate": f"sum by {group} (rate({metric}{error_selector}[{rate_window}]))",
        "error_ratio": (
            f"sum by {ratio_group} (rate({metric}{error_selector}[{rate_window}])) "
            f"/ clamp_min(sum by {ratio_group} (rate({metric}{selector}[{rate_window}])), 0.000001) * 100"
        ),
        "success_rate": (
            f"(1 - (sum by {ratio_group} (rate({metric}{error_selector}[{rate_window}])) "
            f"/ clamp_min(sum by {ratio_group} (rate({metric}{selector}[{rate_window}])), 0.000001))) * 100"
        ),
        "avg_latency": (
            f"sum by {ratio_group} (rate({sum_metric}{selector}[{rate_window}])) "
            f"/ clamp_min(sum by {ratio_group} (rate({metric}{selector}[{rate_window}])), 0.000001) * 1000"
        ),
        "p95_latency": (
            f"histogram_quantile(0.95, sum by (le,{','.join(group_without_status or group_by)}) "
            f"(rate({bucket_metric}{selector}[{rate_window}]))) * 1000"
        ),
        "p99_latency": (
            f"histogram_quantile(0.99, sum by (le,{','.join(group_without_status or group_by)}) "
            f"(rate({bucket_metric}{selector}[{rate_window}]))) * 1000"
        ),
    }

    chart_meta = {
        "request_rate": {"label": "请求速率", "unit": "rps", "precision": 3},
        "request_count": {"label": "窗口请求量", "unit": "次", "precision": 0},
        "error_rate": {"label": "错误速率", "unit": "rps", "precision": 3},
        "error_ratio": {"label": "错误率", "unit": "%", "precision": 2},
        "success_rate": {"label": "成功率", "unit": "%", "precision": 2},
        "avg_latency": {"label": "平均耗时", "unit": "ms", "precision": 1},
        "p95_latency": {"label": "P95", "unit": "ms", "precision": 1},
        "p99_latency": {"label": "P99", "unit": "ms", "precision": 1},
    }

    result_lists = await asyncio.gather(*[
        _safe_prom_range(query, start, end, step)
        for query in queries.values()
    ])
    raw_results = dict(zip(queries.keys(), result_lists))

    charts: list[dict] = []
    rows_by_key: dict[str, dict] = {}
    for key, series_list in raw_results.items():
        meta = chart_meta[key]
        chart_series = []
        for index, series in enumerate(series_list):
            metric_labels = {
                label: str(series.get("metric", {}).get(label) or "")
                for label in group_by
                if series.get("metric", {}).get(label) is not None
            }
            row_key = _series_key(metric_labels, group_by)
            if row_key not in rows_by_key:
                rows_by_key[row_key] = {
                    "id": row_key or f"series-{index}",
                    "name": _series_label(metric_labels, group_by),
                    "labels": metric_labels,
                }
            last_value = _last_matrix_value(series)
            if last_value is not None:
                rows_by_key[row_key][key] = last_value
            chart_series.append({
                "id": row_key or f"{key}-{index}",
                "name": _series_label(metric_labels, group_by),
                "labels": metric_labels,
                "values": series.get("values") or [],
                "last": last_value,
            })
        chart_series.sort(key=lambda item: item["last"] if item["last"] is not None else -1, reverse=True)
        charts.append({
            "key": key,
            **meta,
            "query": queries[key],
            "series": chart_series[:top_n],
            "series_count": len(chart_series),
        })

    rows = list(rows_by_key.values())
    rows.sort(key=lambda item: float(item.get("request_rate") or item.get("request_count") or 0), reverse=True)
    for item in rows:
        item["error_ratio"] = float(item.get("error_ratio") or 0)
        item["success_rate"] = float(item.get("success_rate") or (100 - item["error_ratio"]))

    return {
        "metric": metric,
        "sum_metric": sum_metric,
        "bucket_metric": bucket_metric,
        "filters": [item.model_dump() for item in body.filters if str(item.value or "").strip()],
        "group_by": group_by,
        "range_minutes": range_minutes,
        "step": step,
        "rate_window": rate_window,
        "start": start,
        "end": end,
        "charts": charts,
        "rows": rows[:top_n],
        "row_count": len(rows),
        "queries": queries,
    }


@router.get("/grafana/boards")
async def list_grafana_boards():
    """返回全部看板（默认 + 自定义），附带完整 URL"""
    base = os.getenv("GRAFANA_URL", "").strip().rstrip("/")
    boards = []
    for b in _all_boards_raw():
        full_url = b.get("url") or (f"{base}/d/{b['uid']}/{b['id']}" if b.get("uid") else "")
        boards.append({**b, "url": full_url, "custom": b.get("custom", False)})
    return {"boards": boards, "grafana_url": base}


@router.post("/grafana/boards")
async def add_grafana_board(board: GrafanaBoardIn):
    """添加自定义 Grafana 看板"""
    import uuid as _uuid
    settings = _load_settings()
    customs: list[dict] = settings.get("grafana_boards", [])
    new_board = {
        "id": f"custom-{_uuid.uuid4().hex[:8]}",
        "title": board.title.strip(),
        "uid": board.uid.strip(),
        "url": board.url.strip(),
        "custom": True,
    }
    customs.append(new_board)
    settings["grafana_boards"] = customs
    _save_settings(settings)
    return {"ok": True, "board": new_board}


@router.delete("/grafana/boards/{board_id}")
async def delete_grafana_board(board_id: str):
    """删除自定义 Grafana 看板（默认看板不可删）"""
    settings = _load_settings()
    customs: list[dict] = settings.get("grafana_boards", [])
    before = len(customs)
    customs = [b for b in customs if b.get("id") != board_id]
    if len(customs) == before:
        # 尝试删除默认看板 → 拒绝
        if any(b["id"] == board_id for b in _GRAFANA_BOARD_DEFS):
            from fastapi import HTTPException as _HTTPException
            raise _HTTPException(status_code=400, detail="默认看板不可删除")
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(status_code=404, detail="看板不存在")
    settings["grafana_boards"] = customs
    _save_settings(settings)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# 自定义 PromQL 图表面板（指标图表页配置持久化）
# 数据查询走已有 POST /metrics/query-range；这里只存图表定义。
# ══════════════════════════════════════════════════════════════════════════════

_METRIC_PANELS_FILE = _Path(__file__).resolve().parent.parent / "data" / "metric_panels.json"

_METRIC_PANEL_SEEDS = [
    {
        "id": "cpu-usage",
        "title": "主机 CPU 使用率",
        "query": '100 - avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100',
        "unit": "%",
        "width": "half",
    },
    {
        "id": "mem-usage",
        "title": "主机内存使用率",
        "query": "(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100",
        "unit": "%",
        "width": "half",
    },
    {
        "id": "disk-usage",
        "title": "根分区磁盘使用率",
        "query": '100 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} * 100',
        "unit": "%",
        "width": "half",
    },
    {
        "id": "load5",
        "title": "系统负载 load5",
        "query": "node_load5",
        "unit": "",
        "width": "half",
    },
]


class MetricPanelsPayload(BaseModel):
    charts: list[dict] = []
    range_minutes: int = 60
    step: int = 60
    refresh_seconds: int = 0


@router.get("/metric-panels")
async def get_metric_panels():
    data = read_json_file(_METRIC_PANELS_FILE, default=None)
    if not isinstance(data, dict) or not isinstance(data.get("charts"), list):
        data = {"charts": _METRIC_PANEL_SEEDS, "range_minutes": 60, "step": 60, "refresh_seconds": 0}
        write_json_file(_METRIC_PANELS_FILE, data, ensure_parent=True)
    return data


@router.put("/metric-panels")
async def save_metric_panels(body: MetricPanelsPayload):
    charts = []
    for item in body.charts[:60]:
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()
        if not query:
            continue
        charts.append({
            "id": str(item.get("id") or f"chart-{len(charts)}"),
            "title": str(item.get("title") or "未命名图表")[:80],
            "query": query[:2000],
            "unit": str(item.get("unit") or "")[:20],
            "width": item.get("width") if item.get("width") in ("half", "full") else "half",
        })
    data = {
        "charts": charts,
        "range_minutes": max(5, min(int(body.range_minutes or 60), 7 * 24 * 60)),
        "step": max(10, min(int(body.step or 60), 3600)),
        "refresh_seconds": max(0, min(int(body.refresh_seconds or 0), 3600)),
    }
    write_json_file(_METRIC_PANELS_FILE, data, ensure_parent=True)
    return data


# ══════════════════════════════════════════════════════════════════════════════
# Grafana 自动发现：调用 Grafana HTTP API 获取全部看板
# ══════════════════════════════════════════════════════════════════════════════

def _read_grafana_settings() -> tuple[str, str]:
    """直接从 settings.json 读取 grafana_url 和 grafana_api_key，比 env 更实时。"""
    settings_file = Path(__file__).resolve().parent.parent / "data" / "settings.json"
    try:
        d = read_json_file(settings_file, default={})
        if not isinstance(d, dict):
            raise ValueError("invalid settings snapshot")
        base    = d.get("grafana_url", "").strip().rstrip("/")
        api_key = d.get("grafana_api_key", "").strip()
        return base, api_key
    except Exception:
        return (os.getenv("GRAFANA_URL", "") or "").strip().rstrip("/"), \
               (os.getenv("GRAFANA_API_KEY", "") or "").strip()


@router.get("/grafana/discover")
async def discover_grafana_boards():
    """
    调用 Grafana /api/search 自动发现所有已安装看板。
    需要在系统配置中填写 Grafana URL 和 API Key（或开启匿名访问）。
    """
    import httpx

    base, api_key = _read_grafana_settings()

    if not base:
        return {"boards": [], "error": "未配置 GRAFANA_URL，请先在系统配置中填写 Grafana 地址", "grafana_url": ""}

    headers: dict[str, str] = {}
    if api_key:
        # 兼容用户直接粘贴带 "Bearer " 前缀的 token
        token = api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}"
        headers["Authorization"] = token

    search_url = f"{base}/api/search"
    logger.info("[grafana-discover] GET %s  api_key_set=%s", search_url, bool(api_key))

    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False, headers=headers) as client:
            resp = await client.get(search_url, params={"type": "dash-db", "limit": 500})
            logger.info("[grafana-discover] status=%s", resp.status_code)
            resp.raise_for_status()
            raw: list[dict] = resp.json()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        body_text = e.response.text[:200]
        if status == 401:
            msg = "API Key 无效或已过期（401 Unauthorized）"
        elif status == 403:
            msg = "API Key 权限不足，需要 Viewer 以上角色（403 Forbidden）"
        else:
            msg = f"Grafana 返回 {status}：{body_text}"
        logger.warning("[grafana-discover] error: %s", msg)
        return {"boards": [], "error": msg, "grafana_url": base}
    except httpx.ConnectError as e:
        msg = f"无法连接 Grafana（{base}）：{e}"
        logger.warning("[grafana-discover] connect error: %s", msg)
        return {"boards": [], "error": msg, "grafana_url": base}
    except httpx.TimeoutException:
        msg = f"连接 Grafana 超时（{base}），请检查地址和网络"
        logger.warning("[grafana-discover] timeout: %s", base)
        return {"boards": [], "error": msg, "grafana_url": base}
    except Exception as e:
        logger.exception("[grafana-discover] unexpected error")
        return {"boards": [], "error": str(e), "grafana_url": base}

    boards = []
    for item in raw:
        uid      = item.get("uid", "")
        url_path = item.get("url", "")
        full_url = f"{base}{url_path}" if url_path.startswith("/") else url_path
        boards.append({
            "id":     uid or str(item.get("id", "")),
            "uid":    uid,
            "title":  item.get("title", ""),
            "url":    full_url,
            "tags":   item.get("tags", []),
            "folder": item.get("folderTitle", "General"),
            "custom": False,
        })

    boards.sort(key=lambda b: (b["folder"], b["title"]))
    logger.info("[grafana-discover] found %d boards", len(boards))
    return {"boards": boards, "total": len(boards), "grafana_url": base}


@router.get("/grafana/test")
async def test_grafana_connection():
    """诊断 Grafana 连通性，返回详细状态（供排查自动发现失败时使用）"""
    import httpx

    base, api_key = _read_grafana_settings()

    result = {
        "grafana_url":   base,
        "api_key_set":   bool(api_key),
        "version":       "",
        "health_ok":     False,
        "search_ok":     False,
        "search_count":  0,
        "health_error":  "",
        "search_error":  "",
    }

    if not base:
        result["health_error"] = "GRAFANA_URL 未配置"
        return result

    headers: dict[str, str] = {}
    if api_key:
        token = api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}"
        headers["Authorization"] = token

    async with httpx.AsyncClient(timeout=8.0, trust_env=False, headers=headers) as client:
        # 1. 健康检查（无需认证），同时读取版本号
        try:
            r = await client.get(f"{base}/api/health")
            result["health_ok"] = r.status_code == 200
            if result["health_ok"]:
                try:
                    result["version"] = r.json().get("version", "")
                except Exception:
                    pass
            else:
                result["health_error"] = f"HTTP {r.status_code}"
        except Exception as e:
            result["health_error"] = str(e)

        # 2. 搜索接口（需要认证或匿名）— 拉取全量以获得准确数量
        try:
            r = await client.get(f"{base}/api/search", params={"type": "dash-db", "limit": 500})
            if r.status_code == 200:
                result["search_ok"] = True
                result["search_count"] = len(r.json())
            elif r.status_code == 401:
                result["search_error"] = "401 Unauthorized：需要 API Key 或开启匿名访问"
            elif r.status_code == 403:
                result["search_error"] = "403 Forbidden：API Key 权限不足"
            else:
                result["search_error"] = f"HTTP {r.status_code}: {r.text[:100]}"
        except Exception as e:
            result["search_error"] = str(e)

    return result


# ── Grafana 反向代理 ──────────────────────────────────────────────────────────
# 前端 iframe 指向 /api/grafana-proxy/<path>，后端透明转发并注入 API Key。
# 这样浏览器不需要登录 Grafana，认证完全由后端承担。

from fastapi import Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response as _Response
import re as _re


@router.websocket("/grafana-proxy/{gpath:path}")
async def grafana_ws_proxy(websocket: WebSocket, gpath: str):
    """WebSocket 代理：转发 Grafana Live (/api/live/ws) 连接"""
    import websockets as _ws

    base, api_key = _read_grafana_settings()
    if not base:
        await websocket.close(code=1011, reason="GRAFANA_URL 未配置")
        return

    qs = websocket.url.query
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    target = f"{ws_base}/{gpath}" + (f"?{qs}" if qs else "")

    extra_headers = {}
    if api_key:
        token = api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}"
        extra_headers["Authorization"] = token

    await websocket.accept()
    try:
        async with _ws.connect(target, additional_headers=extra_headers, ssl=None) as upstream:
            async def _up():
                try:
                    async for msg in upstream:
                        if isinstance(msg, bytes):
                            await websocket.send_bytes(msg)
                        else:
                            await websocket.send_text(msg)
                except Exception:
                    pass

            async def _down():
                try:
                    async for msg in websocket.iter_bytes():
                        await upstream.send(msg)
                except WebSocketDisconnect:
                    pass
                except Exception:
                    pass

            await asyncio.gather(_up(), _down())
    except Exception as e:
        logger.debug("[grafana-ws] upstream error: %s", e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@router.api_route(
    "/grafana-proxy/{gpath:path}",
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def grafana_proxy(gpath: str, request: Request):
    base, api_key = _read_grafana_settings()

    if not base:
        return _Response(content="GRAFANA_URL 未配置", status_code=503)

    qs = request.url.query
    target_url = f"{base}/{gpath}" + (f"?{qs}" if qs else "")

    forward_headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "origin", "referer", "authorization", "cookie")
    }
    if api_key:
        token = api_key if api_key.startswith("Bearer ") else f"Bearer {api_key}"
        forward_headers["Authorization"] = token

    body = await request.body()

    import httpx
    try:
        async with httpx.AsyncClient(timeout=30, verify=False, follow_redirects=True) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=forward_headers,
                content=body or None,
            )
    except Exception as e:
        return _Response(content=str(e), status_code=502)

    skip_headers = {"transfer-encoding", "content-encoding", "content-length",
                    "x-frame-options", "content-security-policy"}
    resp_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in skip_headers
    }

    content = resp.content
    content_type = resp.headers.get("content-type", "")
    proxy_base = "/api/observability/grafana-proxy"

    if "text/html" in content_type:
        text = content.decode("utf-8", errors="replace")

        # ① 重写 Grafana boot data 中的 appSubUrl / appUrl
        #    appSubUrl 告诉 Grafana SPA 它的客户端路由根路径，必须与代理前缀一致
        #    否则 SPA 会把 /api/observability/grafana-proxy/d/xxx 当成未知路由报 404
        grafana_origin_esc = _re.escape(base)
        text = _re.sub(
            r'"appSubUrl"\s*:\s*"[^"]*"',
            f'"appSubUrl":"{proxy_base}"',
            text,
        )
        text = _re.sub(
            rf'"appUrl"\s*:\s*"[^"]*"',
            f'"appUrl":"{proxy_base}/"',
            text,
        )

        # ② 注入 <base href> + fetch/XHR 拦截脚本，放在 <head> 最前面
        #    <base href> 让 HTML 中的相对路径资源走代理
        #    fetch/XHR 拦截让 SPA 运行时的数据 API 请求也走代理
        head_inject = f"""<base href="{proxy_base}/">
<script>
(function(){{
  var _pb={json.dumps(proxy_base)};
  function _rw(u){{
    if(typeof u==='string'&&u.startsWith('/')&&!u.startsWith(_pb))
      return _pb+u;
    return u;
  }}
  var _f=window.fetch;
  window.fetch=function(u,o){{return _f.call(this,_rw(u),o);}};
  var _xo=XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open=function(m,u){{
    arguments[1]=_rw(u);return _xo.apply(this,arguments);
  }};
}})();
</script>"""
        if "<head>" in text:
            text = text.replace("<head>", "<head>" + head_inject, 1)
        elif "<Head>" in text:
            text = text.replace("<Head>", "<Head>" + head_inject, 1)
        else:
            text = head_inject + text

        content = text.encode("utf-8")
        resp_headers["content-type"] = "text/html; charset=utf-8"

    return _Response(
        content=content,
        status_code=resp.status_code,
        headers=resp_headers,
        media_type=content_type or None,
    )
