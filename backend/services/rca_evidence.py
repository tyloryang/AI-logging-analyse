"""Deadline-aware evidence helpers for structured RCA."""

from __future__ import annotations

import asyncio
import inspect
import re
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable


Collector = Callable[[], Awaitable[dict[str, Any]]]


def _parse_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def build_match_window(
    *,
    alert_started_at: str = "",
    trace_started_at: str = "",
    trace_ended_at: str = "",
) -> dict[str, Any]:
    trace_start = _parse_datetime(trace_started_at)
    trace_end = _parse_datetime(trace_ended_at)
    if trace_start and trace_end and trace_end >= trace_start:
        return {
            "source": "trace",
            "started_at": trace_start.isoformat(),
            "ended_at": trace_end.isoformat(),
            "confidence_capped": False,
        }

    alert_start = _parse_datetime(alert_started_at) or datetime.now(timezone.utc)
    return {
        "source": "alert",
        "started_at": (alert_start - timedelta(seconds=90)).isoformat(),
        "ended_at": (alert_start + timedelta(seconds=30)).isoformat(),
        "confidence_capped": True,
    }


def _sql_fingerprint(sql: str) -> str:
    value = str(sql or "").lower()
    value = re.sub(r"'(?:''|[^'])*'", "?", value)
    value = re.sub(r"\b\d+(?:\.\d+)?\b", "?", value)
    return re.sub(r"\s+", " ", value).strip()[:500]


def _confidence(score: int, *, dependency_match: bool, time_overlap: bool, capped: bool) -> str:
    if score >= 80 and dependency_match and time_overlap:
        value = "high"
    elif score >= 55:
        value = "medium"
    else:
        value = "low"
    if capped and value == "high":
        return "medium"
    return value


def rank_slowlog_candidates(
    entries: list[dict[str, Any]],
    *,
    dependency: dict[str, Any],
    match_window: dict[str, Any],
    response_duration_sec: float = 0.0,
) -> list[dict[str, Any]]:
    window_start = _parse_datetime(match_window.get("started_at"))
    window_end = _parse_datetime(match_window.get("ended_at"))
    dependency_match = bool(dependency.get("target") or dependency.get("host"))
    expected_host = str(dependency.get("source_host") or dependency.get("host") or "").strip()
    expected_user = str(dependency.get("db_user") or "").strip()
    keywords = [str(value).lower() for value in dependency.get("sql_keywords", []) if str(value).strip()]
    penalty = int(dependency.get("confidence_penalty") or 0)
    ranked: list[dict[str, Any]] = []

    for entry in entries:
        evidence: list[dict[str, Any]] = []
        score = 0
        if dependency_match:
            score += 30
            evidence.append({"rule": "dependency_match", "score": 30, "detail": "服务与 MySQL 依赖匹配"})

        query_time = max(0.0, float(entry.get("query_time") or 0.0))
        query_end = _parse_datetime(entry.get("time_dt") or entry.get("time_str") or entry.get("time_raw"))
        query_start = query_end - timedelta(seconds=query_time) if query_end else None
        time_overlap = bool(
            query_start and query_end and window_start and window_end
            and query_start <= window_end and query_end >= window_start
        )
        if time_overlap:
            score += 25
            evidence.append({"rule": "time_overlap", "score": 25, "detail": "SQL 执行区间与接口请求区间重叠"})

        entry_host = str(entry.get("host") or "").strip()
        if expected_host and entry_host == expected_host:
            score += 15
            evidence.append({"rule": "source_host", "score": 15, "detail": f"来源主机匹配 {entry_host}"})

        entry_user = str(entry.get("user") or "").strip()
        if expected_user and entry_user == expected_user:
            score += 10
            evidence.append({"rule": "db_user", "score": 10, "detail": f"数据库用户匹配 {entry_user}"})

        duration_floor = max(2.0, float(response_duration_sec or 0.0) * 0.5)
        if query_time >= duration_floor:
            score += 10
            evidence.append({"rule": "duration", "score": 10, "detail": f"SQL 耗时 {query_time:g}s 可解释接口超时"})

        sql = str(entry.get("sql") or "")
        matched_keywords = [keyword for keyword in keywords if keyword in sql.lower()]
        if matched_keywords:
            score += 10
            evidence.append({"rule": "sql_features", "score": 10, "detail": "SQL 特征匹配: " + ", ".join(matched_keywords[:4])})

        if penalty:
            score -= penalty
            evidence.append({"rule": "dependency_conflict", "score": -penalty, "detail": "依赖来源存在冲突"})
        score = max(0, min(100, score))
        ranked.append({
            "entry_id": entry.get("id"),
            "score": score,
            "confidence": _confidence(
                score,
                dependency_match=dependency_match,
                time_overlap=time_overlap,
                capped=bool(match_window.get("confidence_capped")),
            ),
            "query_time": query_time,
            "time": entry.get("time_dt") or entry.get("time_str") or entry.get("time_raw") or "",
            "user": entry_user,
            "host": entry_host,
            "sql": sql,
            "sql_fingerprint": _sql_fingerprint(sql),
            "evidence": evidence,
        })

    ranked.sort(key=lambda item: (-item["score"], -item["query_time"], str(item.get("entry_id") or "")))
    top = ranked[:3]
    for index, item in enumerate(top, start=1):
        item["rank"] = index
    return top


def _iso(value: Any) -> str:
    if value is None:
        return ""
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _label(labels: dict[str, Any], *names: str) -> str:
    lowered = {str(key).lower(): value for key, value in (labels or {}).items()}
    for name in names:
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return str(value)
    return ""


def _pod_payload(pod: Any, metric: dict[str, Any]) -> dict[str, Any]:
    metadata = getattr(pod, "metadata", None)
    spec = getattr(pod, "spec", None)
    status = getattr(pod, "status", None)
    container_statuses = getattr(status, "container_statuses", None) or []
    restarts = sum(int(getattr(item, "restart_count", 0) or 0) for item in container_statuses)
    last_restart: dict[str, Any] = {}
    for item in container_statuses:
        terminated = getattr(getattr(item, "last_state", None), "terminated", None)
        if not terminated:
            continue
        finished = _iso(getattr(terminated, "finished_at", None))
        if not last_restart or finished > str(last_restart.get("time") or ""):
            last_restart = {
                "reason": str(getattr(terminated, "reason", None) or ""),
                "time": finished,
                "exit_code": getattr(terminated, "exit_code", None),
                "container": str(getattr(item, "name", None) or ""),
            }
    return {
        "name": str(getattr(metadata, "name", None) or ""),
        "namespace": str(getattr(metadata, "namespace", None) or ""),
        "phase": str(getattr(status, "phase", None) or "Unknown"),
        "node": str(getattr(spec, "node_name", None) or ""),
        "pod_ip": str(getattr(status, "pod_ip", None) or ""),
        "host_ip": str(getattr(status, "host_ip", None) or ""),
        "restarts": restarts,
        "last_restart_reason": last_restart.get("reason", ""),
        "last_restart_time": last_restart.get("time", ""),
        "last_exit_code": last_restart.get("exit_code"),
        "last_restart_container": last_restart.get("container", ""),
        "cpu_usage_cores": metric.get("cpu_usage_cores"),
        "memory_usage_bytes": metric.get("memory_usage_bytes"),
        "containers": metric.get("containers", []),
        "labels": dict(getattr(metadata, "labels", None) or {}),
    }


def _event_payload(event: Any) -> dict[str, Any]:
    series = getattr(event, "series", None)
    involved = getattr(event, "involved_object", None)
    source = getattr(event, "source", None)
    metadata = getattr(event, "metadata", None)
    last_time = (
        getattr(series, "last_observed_time", None)
        or getattr(event, "last_timestamp", None)
        or getattr(event, "event_time", None)
        or getattr(event, "first_timestamp", None)
        or getattr(metadata, "creation_timestamp", None)
    )
    return {
        "type": str(getattr(event, "type", None) or "Normal"),
        "reason": str(getattr(event, "reason", None) or ""),
        "message": str(getattr(event, "message", None) or ""),
        "count": int(getattr(series, "count", None) or getattr(event, "count", None) or 1),
        "source": str(getattr(event, "reporting_component", None) or getattr(source, "component", None) or ""),
        "source_host": str(getattr(event, "reporting_instance", None) or getattr(source, "host", None) or ""),
        "namespace": str(getattr(metadata, "namespace", None) or ""),
        "object_kind": str(getattr(involved, "kind", None) or ""),
        "object_name": str(getattr(involved, "name", None) or ""),
        "last_ts": _iso(last_time),
    }


async def collect_kubernetes_evidence(
    *,
    service: str | None,
    labels: dict[str, Any],
    load_clusters: Callable[[], list[dict[str, Any]]] | None = None,
    get_client: Callable[[str | None], tuple[Any, Any]] | None = None,
    metrics_loader: Callable[[str | None, str], dict[tuple[str, str], dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Collect target pod state, restart details, resource usage, and related Events."""
    if load_clusters is None or get_client is None or metrics_loader is None:
        from routers.kubernetes import _fetch_pod_metrics_index, _get_client, _load_clusters

        load_clusters = load_clusters or _load_clusters
        get_client = get_client or _get_client
        metrics_loader = metrics_loader or _fetch_pod_metrics_index

    cluster_name = _label(labels, "cluster", "cluster_name", "env")
    namespace = _label(labels, "namespace", "kubernetes_namespace")
    pod_name = _label(labels, "pod", "pod_name", "kubernetes_pod_name")
    if not namespace:
        return {
            "title": "Kubernetes 证据",
            "summary": "告警未提供 namespace，无法定位目标 Pod。",
            "items": [],
            "pods": [],
            "events": [],
            "status": "unconfigured",
        }

    def collect() -> dict[str, Any]:
        clusters = load_clusters() or []
        cluster = next(
            (
                item for item in clusters
                if cluster_name and cluster_name in {str(item.get("id") or ""), str(item.get("name") or "")}
            ),
            None,
        )
        if cluster_name and cluster is None:
            return {
                "title": "Kubernetes 证据",
                "summary": f"未找到告警集群 {cluster_name} 的配置。",
                "items": [],
                "pods": [],
                "events": [],
                "status": "unconfigured",
            }
        cluster = cluster or next((item for item in clusters if item.get("is_default")), clusters[0] if clusters else None)
        if not cluster:
            return {
                "title": "Kubernetes 证据",
                "summary": "尚未配置 Kubernetes 集群。",
                "items": [],
                "pods": [],
                "events": [],
                "status": "unconfigured",
            }

        cluster_id = str(cluster.get("id") or "") or None
        core, _apps = get_client(cluster_id)
        pod_kwargs: dict[str, Any] = {"_request_timeout": 3}
        if pod_name:
            pod_kwargs["field_selector"] = f"metadata.name={pod_name}"
        response = core.list_namespaced_pod(namespace, **pod_kwargs)
        pods = list(getattr(response, "items", None) or [])
        if not pod_name and service:
            matching = []
            for pod in pods:
                pod_labels = dict(getattr(getattr(pod, "metadata", None), "labels", None) or {})
                values = {str(pod_labels.get(key) or "") for key in ("app", "application", "k8s-app", "service")}
                if service in values or str(getattr(getattr(pod, "metadata", None), "name", "")).startswith(f"{service}-"):
                    matching.append(pod)
            pods = matching

        metrics = metrics_loader(cluster_id, namespace)
        pod_payloads = []
        for pod in pods:
            metadata = getattr(pod, "metadata", None)
            key = (str(getattr(metadata, "namespace", None) or namespace), str(getattr(metadata, "name", None) or ""))
            pod_payloads.append(_pod_payload(pod, metrics.get(key, {})))

        event_kwargs: dict[str, Any] = {"_request_timeout": 3}
        if pod_name:
            event_kwargs["field_selector"] = f"involvedObject.kind=Pod,involvedObject.name={pod_name}"
        event_response = core.list_namespaced_event(namespace, **event_kwargs)
        events = [_event_payload(item) for item in (getattr(event_response, "items", None) or [])]
        target_names = {item["name"] for item in pod_payloads}
        if target_names and not pod_name:
            events = [item for item in events if not item["object_name"] or item["object_name"] in target_names]
        events.sort(key=lambda item: item.get("last_ts", ""), reverse=True)
        abnormal = sum(1 for item in events if item.get("type", "").lower() == "warning")
        restarts = sum(int(item.get("restarts") or 0) for item in pod_payloads)
        return {
            "title": "Kubernetes 证据",
            "summary": f"定位 {len(pod_payloads)} 个 Pod，累计重启 {restarts} 次，相关 Warning Event {abnormal} 条。",
            "items": [
                f"{item['name']} phase={item['phase']} restarts={item['restarts']} cpu={item['cpu_usage_cores']} memory={item['memory_usage_bytes']}"
                for item in pod_payloads[:8]
            ],
            "cluster": str(cluster.get("name") or cluster.get("id") or ""),
            "namespace": namespace,
            "pods": pod_payloads,
            "events": events[:20],
            "status": "completed",
        }

    try:
        return await asyncio.to_thread(collect)
    except Exception as exc:
        return {
            "title": "Kubernetes 证据",
            "summary": f"Kubernetes 采集不可用: {exc}",
            "items": [],
            "pods": [],
            "events": [],
            "status": "unavailable",
        }


async def _read_slowlog_entries(config: dict[str, Any], date_from: str, date_to: str) -> list[dict[str, Any]]:
    from routers.slowlog import _read_remote_file, _resolve_credential
    from slow_log_parser import parse_slow_log

    username, password, host, port = _resolve_credential(
        str(config.get("host_ip") or ""),
        credential_id=str(config.get("credential_id") or ""),
        username=str(config.get("ssh_user") or ""),
        password=str(config.get("ssh_password") or ""),
        port=int(config.get("ssh_port") or 22),
    )
    text = await _read_remote_file(
        host,
        port,
        username,
        password,
        str(config.get("log_path") or "/mysqldata/mysql/data/3306/mysql-slow.log"),
        tail_mb=float(config.get("tail_mb") or 20),
        date_from=date_from[:10],
    )
    return parse_slow_log(
        text,
        date_from=date_from,
        date_to=date_to,
        threshold_sec=float(config.get("threshold_sec") or 1.0),
        alert_sec=float(config.get("alert_sec") or 10.0),
    )


def _request_duration(labels: dict[str, Any]) -> float:
    seconds = _label(labels, "request_duration_seconds", "duration_seconds", "latency_seconds")
    if seconds:
        try:
            return max(0.0, float(seconds))
        except ValueError:
            pass
    milliseconds = _label(labels, "request_duration_ms", "duration_ms", "latency_ms")
    try:
        return max(0.0, float(milliseconds) / 1000.0) if milliseconds else 0.0
    except ValueError:
        return 0.0


async def collect_slowlog_evidence(
    *,
    service: str | None,
    labels: dict[str, Any],
    dependency_records: list[dict[str, Any]] | None = None,
    slowlog_configs: list[dict[str, Any]] | None = None,
    read_entries: Callable[[dict[str, Any], str, str], Awaitable[list[dict[str, Any]]]] | None = None,
    trace_loader: Callable[[str], Awaitable[list[dict[str, Any]]]] | None = None,
) -> dict[str, Any]:
    """Resolve the service's MySQL target and return probabilistically ranked slow SQL candidates."""
    from services.service_dependencies import load_dependencies, resolve_dependency

    if dependency_records is None:
        dependency_records = load_dependencies()
    if slowlog_configs is None:
        from routers.slowlog import _load_slowlog_configs

        slowlog_configs = _load_slowlog_configs()
    read_entries = read_entries or _read_slowlog_entries

    cluster = _label(labels, "cluster", "cluster_name", "env")
    namespace = _label(labels, "namespace", "kubernetes_namespace")
    resolution = resolve_dependency(
        dependency_records,
        cluster=cluster,
        namespace=namespace,
        service=str(service or ""),
        dependency_type="mysql",
    )
    selected = resolution.get("selected")
    if not selected:
        return {
            "title": "MySQL 慢日志候选",
            "summary": "未配置服务到 MySQL 的依赖关系，禁止推断慢 SQL 根因。",
            "items": [],
            "candidates": [],
            "status": "unconfigured",
        }

    config_id = str(selected.get("slowlog_config_id") or "")
    config = next((item for item in slowlog_configs if str(item.get("id") or "") == config_id), None)
    if not config:
        return {
            "title": "MySQL 慢日志候选",
            "summary": f"依赖 {selected.get('target') or selected.get('id')} 未关联有效的慢日志配置。",
            "items": [],
            "candidates": [],
            "dependency": selected,
            "status": "unconfigured",
        }

    trace_started_at = _label(labels, "trace_started_at", "trace_start_time")
    trace_ended_at = _label(labels, "trace_ended_at", "trace_end_time")
    trace_id = _label(labels, "trace_id", "traceid")
    if trace_id and not (trace_started_at and trace_ended_at):
        if trace_loader is None:
            from skywalking_client import sw_client

            trace_loader = sw_client.get_trace_detail
        try:
            spans = await asyncio.wait_for(trace_loader(trace_id), timeout=2.0)
            starts = [int(item.get("startTime") or 0) for item in spans if int(item.get("startTime") or 0) > 0]
            ends = [int(item.get("endTime") or 0) for item in spans if int(item.get("endTime") or 0) > 0]
            if starts and ends:
                trace_started_at = datetime.fromtimestamp(min(starts) / 1000.0, timezone.utc).isoformat()
                trace_ended_at = datetime.fromtimestamp(max(ends) / 1000.0, timezone.utc).isoformat()
        except Exception:
            trace_started_at = ""
            trace_ended_at = ""

    window = build_match_window(
        alert_started_at=_label(labels, "startsAt", "alert_started_at", "alert_start"),
        trace_started_at=trace_started_at,
        trace_ended_at=trace_ended_at,
    )
    try:
        entries = await read_entries(config, window["started_at"], window["ended_at"])
    except Exception as exc:
        return {
            "title": "MySQL 慢日志候选",
            "summary": f"慢日志采集不可用: {exc}",
            "items": [],
            "candidates": [],
            "dependency": selected,
            "match_window": window,
            "status": "unavailable",
        }

    scoring_dependency = dict(selected)
    scoring_dependency["confidence_penalty"] = int(resolution.get("confidence_penalty") or 0)
    response_duration = _request_duration(labels)
    if response_duration <= 0 and window.get("source") == "trace":
        window_start = _parse_datetime(window.get("started_at"))
        window_end = _parse_datetime(window.get("ended_at"))
        if window_start and window_end:
            response_duration = max(0.0, (window_end - window_start).total_seconds())
    candidates = rank_slowlog_candidates(
        entries,
        dependency=scoring_dependency,
        match_window=window,
        response_duration_sec=response_duration,
    )
    return {
        "title": "MySQL 慢日志候选",
        "summary": (
            f"按{window['source']}时间窗口匹配到 {len(candidates)} 个候选；"
            + (f"首选为 {candidates[0]['confidence']} 置信度。" if candidates else "当前没有可归因候选。")
        ),
        "items": [
            f"#{item['rank']} {item['confidence']} {item['score']}分 / {item['query_time']}s / {item['sql_fingerprint']}"
            for item in candidates
        ],
        "candidates": candidates,
        "dependency": selected,
        "dependency_conflicts": resolution.get("conflicts", []),
        "match_window": window,
        "status": "completed",
    }


async def _publish(callback: Callable[[dict[str, Any]], Any] | None, snapshot: dict[str, Any]) -> None:
    if not callback:
        return
    result = callback(deepcopy(snapshot))
    if inspect.isawaitable(result):
        await result


async def collect_two_stage(
    collectors: dict[str, Collector],
    *,
    facts_deadline_sec: float = 5.0,
    final_deadline_sec: float = 12.0,
    on_facts: Callable[[dict[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Publish completed facts at the first deadline while allowing late collectors to continue."""
    started = time.monotonic()
    tasks = {name: asyncio.create_task(factory()) for name, factory in collectors.items()}
    states = {name: {"status": "collecting", "latency_ms": None, "error": ""} for name in collectors}
    sections: dict[str, dict[str, Any]] = {}

    async def harvest(done: set[asyncio.Task]) -> None:
        for name, task in tasks.items():
            if task not in done or states[name]["status"] != "collecting":
                continue
            states[name]["latency_ms"] = round((time.monotonic() - started) * 1000)
            try:
                section = task.result()
                sections[name] = section if isinstance(section, dict) else {"summary": str(section)}
                states[name]["status"] = str(sections[name].get("status") or "completed")
            except Exception as exc:
                states[name]["status"] = "unavailable"
                states[name]["error"] = str(exc)
                sections[name] = {"title": name, "summary": f"采集不可用: {exc}", "items": [], "status": "unavailable"}

    done, pending = await asyncio.wait(set(tasks.values()), timeout=max(0.0, facts_deadline_sec))
    await harvest(done)
    facts_snapshot = {
        "phase": "facts_ready",
        "facts_ready_ms": round((time.monotonic() - started) * 1000),
        "sections": deepcopy(sections),
        "collector_states": deepcopy(states),
    }
    await _publish(on_facts, facts_snapshot)

    remaining = max(0.0, final_deadline_sec - (time.monotonic() - started))
    if pending:
        late_done, pending = await asyncio.wait(pending, timeout=remaining)
        await harvest(late_done)
    for name, task in tasks.items():
        if states[name]["status"] == "collecting":
            states[name]["status"] = "timeout"
            states[name]["latency_ms"] = round((time.monotonic() - started) * 1000)
            task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    return {
        "phase": "evidence_ready",
        "facts_ready_ms": facts_snapshot["facts_ready_ms"],
        "evidence_ready_ms": round((time.monotonic() - started) * 1000),
        "sections": sections,
        "collector_states": states,
    }
