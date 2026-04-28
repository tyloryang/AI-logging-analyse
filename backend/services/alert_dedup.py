"""Alert aggregation and deduplication for Alertmanager webhooks."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "alert_groups.json"
_SUPPRESS_TTL = 900
_WINDOW_SECS = 300


def _load() -> dict[str, Any]:
    if _DATA_FILE.exists():
        try:
            return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"groups": {}, "suppressed": {}}


def _save(state: dict[str, Any]) -> None:
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DATA_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _fingerprint(alert: dict) -> str:
    group_key = str(alert.get("__group_key") or "").strip()
    if group_key:
        return hashlib.md5(f"group:{group_key}".encode()).hexdigest()[:12]

    alert_fp = str(alert.get("fingerprint") or "").strip()
    if alert_fp:
        return hashlib.md5(f"alert:{alert_fp}".encode()).hexdigest()[:12]

    labels = alert.get("labels", {})
    alertname = labels.get("alertname", "unknown")
    service = labels.get("service") or labels.get("job") or labels.get("instance", "unknown")
    bucket = int(time.time() // _WINDOW_SECS)
    raw = f"{alertname}|{service}|{bucket}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _severity(alert: dict) -> str:
    labels = alert.get("labels", {})
    return labels.get("severity", labels.get("level", "warning")).lower()


def _service(alert: dict) -> str:
    labels = alert.get("labels", {})
    return labels.get("service") or labels.get("job") or labels.get("instance", "unknown")


def _is_parent_alert(alert: dict) -> bool:
    name = alert.get("labels", {}).get("alertname", "").lower()
    return any(k in name for k in ("nodedown", "hostdown", "instancedown", "networkdown"))


def ingest_alerts(raw_alerts: list[dict]) -> list[str]:
    """Ingest a batch of Alertmanager alerts and return affected group ids."""
    state = _load()
    groups: dict[str, dict] = state["groups"]
    suppressed: dict[str, float] = state["suppressed"]
    now = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    suppressed = {k: v for k, v in suppressed.items() if v > now}
    affected_groups: list[str] = []

    for alert in raw_alerts:
        if alert.get("status") == "resolved":
            _handle_resolved(groups, alert, now_iso)
            continue

        fp = _fingerprint(alert)
        labels = alert.get("labels", {})
        name = labels.get("alertname", "unknown")
        svc = _service(alert)
        sev = _severity(alert)

        if _is_parent_alert(alert):
            instance = labels.get("instance", "")
            for group in groups.values():
                if group["status"] in ("resolved", "suppressed"):
                    continue
                if any(a.get("labels", {}).get("instance") == instance for a in group.get("raw_alerts", [])):
                    group["status"] = "suppressed"
                    group["suppressed_at"] = now_iso
            suppressed[f"parent|{instance}"] = now + _SUPPRESS_TTL

        instance = labels.get("instance", "")
        if any(k.startswith("parent|") and k.split("|", 1)[1] == instance for k in suppressed):
            logger.debug("[alert_dedup] suppressed by parent alert: %s / %s", name, instance)
            continue

        if fp in groups and groups[fp]["status"] != "resolved":
            _merge_group(groups[fp], alert, sev, now_iso)
        else:
            groups[fp] = _new_group(fp, alert, svc, sev, name, now_iso)

        affected_groups.append(fp)

    state["groups"] = groups
    state["suppressed"] = suppressed
    _save(state)
    return list(dict.fromkeys(affected_groups))


def _merge_group(group: dict, alert: dict, severity: str, now_iso: str) -> None:
    group["count"] += 1
    group["last_at"] = now_iso
    group["raw_alerts"].append(_slim_alert(alert))

    if severity in ("critical", "error") and group["severity"] not in ("critical", "error"):
        group["severity"] = severity

    summary = alert.get("annotations", {}).get("summary", "")
    description = alert.get("annotations", {}).get("description", "")
    if summary:
        group["summary"] = summary
    if description:
        group["description"] = description

    group["source"] = alert.get("__source", group.get("source", "alertmanager"))
    group["receiver"] = alert.get("__receiver", group.get("receiver", ""))
    group["external_url"] = alert.get("__external_url", group.get("external_url", ""))
    group["group_key"] = alert.get("__group_key", group.get("group_key", ""))
    group["group_labels"] = alert.get("__group_labels", group.get("group_labels", {}))
    group["common_labels"] = alert.get("__common_labels", group.get("common_labels", {}))
    group["common_annotations"] = alert.get("__common_annotations", group.get("common_annotations", {}))
    group["alertmanager_status"] = alert.get("__payload_status", group.get("alertmanager_status", ""))
    group["truncated_alerts"] = alert.get("__truncated_alerts", group.get("truncated_alerts", 0))


def _extract_namespace(alert: dict) -> str:
    """从告警标签中提取 K8s namespace。"""
    labels = alert.get("labels", {})
    for k in ("namespace", "kubernetes_namespace", "k8s_namespace"):
        if labels.get(k):
            return labels[k]
    return ""


def _extract_env(alert: dict) -> str:
    """从告警标签中提取环境标识（env/environment/cluster）。"""
    labels = alert.get("labels", {})
    for k in ("env", "environment", "cluster", "datacenter"):
        if labels.get(k):
            return labels[k]
    return ""


def _new_group(fp: str, alert: dict, service: str, severity: str, name: str, now_iso: str) -> dict:
    return {
        "id": fp,
        "fingerprint": fp,
        "alertname": name,
        "service": service,
        "severity": severity,
        "status": "new",
        "count": 1,
        "first_at": now_iso,
        "last_at": now_iso,
        "raw_alerts": [_slim_alert(alert)],
        "rca_id": None,
        "suppressed_at": None,
        "resolved_at": None,
        "summary": alert.get("annotations", {}).get("summary", ""),
        "description": alert.get("annotations", {}).get("description", ""),
        "source": alert.get("__source", "alertmanager"),
        "receiver": alert.get("__receiver", ""),
        "external_url": alert.get("__external_url", ""),
        "group_key": alert.get("__group_key", ""),
        "group_labels": alert.get("__group_labels", {}),
        "common_labels": alert.get("__common_labels", {}),
        "common_annotations": alert.get("__common_annotations", {}),
        "alertmanager_status": alert.get("__payload_status", ""),
        "truncated_alerts": alert.get("__truncated_alerts", 0),
        "alertmanager_silence_id": None,
        "alertmanager_silence_url": "",
        "namespace": _extract_namespace(alert),
        "env": _extract_env(alert),
    }


def _slim_alert(alert: dict) -> dict:
    return {
        "labels": alert.get("labels", {}),
        "annotations": alert.get("annotations", {}),
        "status": alert.get("status", ""),
        "fingerprint": alert.get("fingerprint", ""),
        "startsAt": alert.get("startsAt", ""),
        "endsAt": alert.get("endsAt", ""),
        "generatorURL": alert.get("generatorURL", ""),
    }


def _handle_resolved(groups: dict[str, dict], alert: dict, now_iso: str) -> None:
    fp = _fingerprint(alert)
    if fp in groups and groups[fp]["status"] != "resolved":
        groups[fp]["status"] = "resolved"
        groups[fp]["resolved_at"] = now_iso
        groups[fp]["alertmanager_status"] = "resolved"


def list_groups(
    status: str | None = None,
    namespace: str | None = None,
    env: str | None = None,
    service: str | None = None,
    limit: int = 100,
) -> list[dict]:
    groups = _load()["groups"]
    result = list(groups.values())
    result.sort(key=lambda x: x["last_at"], reverse=True)
    if status:
        result = [g for g in result if g["status"] == status]
    if namespace:
        result = [g for g in result if g.get("namespace") == namespace]
    if env:
        result = [g for g in result if g.get("env") == env]
    if service:
        result = [g for g in result if service.lower() in g.get("service", "").lower()]
    return result[:limit]


def list_namespaces() -> list[str]:
    """返回所有告警中出现过的 namespace 列表。"""
    groups = _load()["groups"]
    return sorted({g.get("namespace", "") for g in groups.values() if g.get("namespace")})


def list_envs() -> list[str]:
    """返回所有告警中出现过的 env 列表。"""
    groups = _load()["groups"]
    return sorted({g.get("env", "") for g in groups.values() if g.get("env")})


def get_group(group_id: str) -> dict | None:
    return _load()["groups"].get(group_id)


def update_group_status(
    group_id: str,
    status: str,
    rca_id: str | None = None,
    extra_updates: dict | None = None,
) -> bool:
    state = _load()
    group = state["groups"].get(group_id)
    if not group:
        return False

    group["status"] = status
    if rca_id:
        group["rca_id"] = rca_id
    if extra_updates:
        group.update(extra_updates)

    if status == "resolved":
        group["resolved_at"] = datetime.now(timezone.utc).isoformat()
    if status == "suppressed":
        group["suppressed_at"] = datetime.now(timezone.utc).isoformat()
        state["suppressed"][f"rca|{group_id}"] = time.time() + _SUPPRESS_TTL

    _save(state)
    return True


def stats() -> dict:
    groups = list(_load()["groups"].values())
    active = [g for g in groups if g["status"] not in ("resolved", "suppressed")]
    return {
        "total": len(groups),
        "active": len(active),
        "p0": sum(1 for g in active if g["severity"] in ("critical", "error")),
        "p1": sum(1 for g in active if g["severity"] == "warning"),
        "resolved": sum(1 for g in groups if g["status"] == "resolved"),
        "suppressed": sum(1 for g in groups if g["status"] == "suppressed"),
    }
