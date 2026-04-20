"""告警聚合 / 降噪服务。

职责：
- 接收 AlertManager Webhook 原始告警
- 按指纹（alertname + service + 5min 时间桶）合并
- 维护告警组状态机：new → grouped → analyzing → resolved / suppressed
- 持久化到 data/alert_groups.json
"""

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
_SUPPRESS_TTL = 900   # 15 分钟：同一 RCA 推送后抑制重复
_WINDOW_SECS  = 300   # 5 分钟合并时间窗口


# ── 持久化 ────────────────────────────────────────────────────────────────────

def _load() -> dict[str, Any]:
    if _DATA_FILE.exists():
        try:
            return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"groups": {}, "suppressed": {}}


def _save(state: dict) -> None:
    _DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DATA_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── 指纹计算 ──────────────────────────────────────────────────────────────────

def _fingerprint(alert: dict) -> str:
    labels = alert.get("labels", {})
    alertname = labels.get("alertname", "unknown")
    service   = labels.get("service") or labels.get("job") or labels.get("instance", "unknown")
    # 5 分钟时间桶
    bucket = int(time.time() // _WINDOW_SECS)
    raw = f"{alertname}|{service}|{bucket}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _severity(alert: dict) -> str:
    labels = alert.get("labels", {})
    return labels.get("severity", labels.get("level", "warning")).lower()


def _service(alert: dict) -> str:
    labels = alert.get("labels", {})
    return labels.get("service") or labels.get("job") or labels.get("instance", "unknown")


# ── 父告警抑制判断 ─────────────────────────────────────────────────────────────

def _is_parent_alert(alert: dict) -> bool:
    """主机宕机 / 网络中断等父级告警，触发后抑制同主机其他告警。"""
    name = alert.get("labels", {}).get("alertname", "").lower()
    return any(k in name for k in ("nodedown", "hostdown", "instancedown", "networkdown"))


# ── 核心：处理一批原始告警 ────────────────────────────────────────────────────

def ingest_alerts(raw_alerts: list[dict]) -> list[str]:
    """
    处理来自 AlertManager 的一批原始告警，返回新建/更新的 group_id 列表。
    """
    state = _load()
    groups: dict = state["groups"]
    suppressed: dict = state["suppressed"]
    now = time.time()
    now_iso = datetime.now(timezone.utc).isoformat()

    # 清理过期抑制记录
    suppressed = {k: v for k, v in suppressed.items() if v > now}

    affected_groups: list[str] = []

    for alert in raw_alerts:
        if alert.get("status") == "resolved":
            _handle_resolved(groups, alert, now_iso)
            continue

        fp = _fingerprint(alert)
        name = alert.get("labels", {}).get("alertname", "unknown")
        svc  = _service(alert)
        sev  = _severity(alert)

        # 父告警抑制：将同主机 / 同服务的其他组标记为 suppressed
        if _is_parent_alert(alert):
            instance = alert.get("labels", {}).get("instance", "")
            for gid, g in groups.items():
                if g["status"] not in ("resolved", "suppressed"):
                    if any(
                        a.get("labels", {}).get("instance") == instance
                        for a in g.get("raw_alerts", [])
                    ):
                        g["status"] = "suppressed"
                        g["suppressed_at"] = now_iso
            # 记录全局抑制 key
            suppressed[f"parent|{instance}"] = now + _SUPPRESS_TTL

        # 检查是否被父告警抑制
        instance = alert.get("labels", {}).get("instance", "")
        if any(
            k.startswith("parent|") and k.split("|", 1)[1] == instance
            for k in suppressed
        ):
            logger.debug("[alert_dedup] 告警被父级抑制: %s / %s", name, instance)
            continue

        if fp in groups:
            g = groups[fp]
            if g["status"] == "resolved":
                # 相同指纹但已 resolved → 新建
                groups[fp] = _new_group(fp, alert, svc, sev, name, now_iso)
            else:
                # 合并
                g["count"] += 1
                g["last_at"] = now_iso
                g["raw_alerts"].append(_slim_alert(alert))
                if sev in ("critical", "error") and g["severity"] not in ("critical", "error"):
                    g["severity"] = sev
        else:
            groups[fp] = _new_group(fp, alert, svc, sev, name, now_iso)

        affected_groups.append(fp)

    state["groups"] = groups
    state["suppressed"] = suppressed
    _save(state)
    return list(set(affected_groups))


def _new_group(fp, alert, svc, sev, name, now_iso) -> dict:
    return {
        "id": fp,
        "fingerprint": fp,
        "alertname": name,
        "service": svc,
        "severity": sev,
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
    }


def _slim_alert(alert: dict) -> dict:
    return {
        "labels": alert.get("labels", {}),
        "annotations": alert.get("annotations", {}),
        "startsAt": alert.get("startsAt", ""),
        "generatorURL": alert.get("generatorURL", ""),
    }


def _handle_resolved(groups: dict, alert: dict, now_iso: str) -> None:
    fp = _fingerprint(alert)
    if fp in groups and groups[fp]["status"] not in ("resolved",):
        groups[fp]["status"] = "resolved"
        groups[fp]["resolved_at"] = now_iso


# ── 查询接口 ──────────────────────────────────────────────────────────────────

def list_groups(status: str | None = None, limit: int = 100) -> list[dict]:
    groups = _load()["groups"]
    result = list(groups.values())
    result.sort(key=lambda x: x["last_at"], reverse=True)
    if status:
        result = [g for g in result if g["status"] == status]
    return result[:limit]


def get_group(group_id: str) -> dict | None:
    return _load()["groups"].get(group_id)


def update_group_status(group_id: str, status: str, rca_id: str | None = None) -> bool:
    state = _load()
    g = state["groups"].get(group_id)
    if not g:
        return False
    g["status"] = status
    if rca_id:
        g["rca_id"] = rca_id
    if status == "resolved":
        g["resolved_at"] = datetime.now(timezone.utc).isoformat()
    if status == "suppressed":
        g["suppressed_at"] = datetime.now(timezone.utc).isoformat()
        # 15 分钟内抑制同指纹
        state["suppressed"][f"rca|{group_id}"] = time.time() + _SUPPRESS_TTL
    _save(state)
    return True


def stats() -> dict:
    groups = list(_load()["groups"].values())
    active = [g for g in groups if g["status"] not in ("resolved", "suppressed")]
    return {
        "total":      len(groups),
        "active":     len(active),
        "p0":         sum(1 for g in active if g["severity"] in ("critical", "error")),
        "p1":         sum(1 for g in active if g["severity"] == "warning"),
        "resolved":   sum(1 for g in groups if g["status"] == "resolved"),
        "suppressed": sum(1 for g in groups if g["status"] == "suppressed"),
    }
