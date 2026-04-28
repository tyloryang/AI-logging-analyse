"""告警中心路由。

端点：
  POST /api/alerts/webhook        — AlertManager Webhook 接入
  GET  /api/alerts/groups         — 告警组列表
  GET  /api/alerts/groups/{id}    — 告警组详情
  PUT  /api/alerts/groups/{id}/status — 更新状态（resolve / suppress）
  GET  /api/alerts/stats          — 统计（故障大盘用）
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Body, Query
from pydantic import BaseModel

from notifier import send_feishu_alert_group
from services.alert_dedup import (
    ingest_alerts,
    list_groups,
    get_group,
    update_group_status,
    stats,
    list_namespaces,
    list_envs,
)
from state import load_groups

logger = logging.getLogger(__name__)
router = APIRouter()


def _decorate_alert(alert: dict, payload: dict) -> dict:
    item = dict(alert or {})
    item["__source"] = "alertmanager"
    item["__receiver"] = payload.get("receiver", "")
    item["__external_url"] = payload.get("externalURL", "")
    item["__group_key"] = payload.get("groupKey", "")
    item["__group_labels"] = payload.get("groupLabels", {}) or {}
    item["__common_labels"] = payload.get("commonLabels", {}) or {}
    item["__common_annotations"] = payload.get("commonAnnotations", {}) or {}
    item["__payload_status"] = payload.get("status", "")
    item["__truncated_alerts"] = payload.get("truncatedAlerts", 0)
    return item


def _collect_alert_labels(alert_group: dict) -> dict[str, str]:
    labels: dict[str, str] = {}
    for source in (
        alert_group.get("group_labels", {}),
        alert_group.get("common_labels", {}),
    ):
        if isinstance(source, dict):
            labels.update({str(k): str(v) for k, v in source.items() if v is not None})
    for raw in alert_group.get("raw_alerts", []) or []:
        raw_labels = raw.get("labels", {}) if isinstance(raw, dict) else {}
        if isinstance(raw_labels, dict):
            labels.update({str(k): str(v) for k, v in raw_labels.items() if v is not None})
    if alert_group.get("alertname"):
        labels.setdefault("alertname", str(alert_group["alertname"]))
    if alert_group.get("service"):
        labels.setdefault("service", str(alert_group["service"]))
    if alert_group.get("severity"):
        labels.setdefault("severity", str(alert_group["severity"]))
    if alert_group.get("namespace"):
        labels.setdefault("namespace", str(alert_group["namespace"]))
    if alert_group.get("env"):
        labels.setdefault("env", str(alert_group["env"]))
    return labels


def _match_alert_matchers(labels: dict[str, str], matchers: list[dict]) -> list[dict]:
    matched: list[dict] = []
    for item in matchers or []:
        label = str(item.get("label") or "").strip()
        expected = str(item.get("value") or "").strip()
        if not label:
            continue
        actual = labels.get(label)
        if actual is None or actual == "":
            continue
        if expected not in {"", "*"} and actual != expected:
            continue
        matched.append({"label": label, "value": expected, "actual": actual})
    return matched


def _resolve_alert_targets(alert_group: dict) -> list[dict]:
    labels = _collect_alert_labels(alert_group)
    targets: list[dict] = []
    for group in load_groups():
        webhook = str(group.get("feishu_webhook", "") or "").strip()
        if not webhook:
            continue
        matches = _match_alert_matchers(labels, group.get("alert_matchers", []) or [])
        if not matches:
            continue
        targets.append({
            "group_id": group.get("id", ""),
            "group_name": group.get("name", ""),
            "webhook_url": webhook,
            "keyword": group.get("feishu_keyword", ""),
            "matches": matches,
        })
    return targets


def _decorate_alert_group(alert_group: dict) -> dict:
    item = dict(alert_group or {})
    targets = _resolve_alert_targets(item)
    item["notify_targets"] = [
        {
            "group_id": target["group_id"],
            "group_name": target["group_name"],
            "matches": target["matches"],
        }
        for target in targets
    ]
    item["notify_target_count"] = len(item["notify_targets"])
    item["notify_via_global_feishu"] = not item["notify_targets"] and bool(os.getenv("FEISHU_WEBHOOK", "").strip())
    return item


# ── AlertManager Webhook ──────────────────────────────────────────────────────

@router.post("/api/alerts/webhook")
async def alertmanager_webhook(payload: dict = Body(...)):
    """
    接收 AlertManager Webhook 推送（Prometheus Alerting 标准格式）。
    自动完成告警指纹计算、聚合、状态维护，并触发飞书聚合通知。
    """
    raw_alerts = payload.get("alerts", [])
    if not raw_alerts:
        return {"ok": True, "message": "no alerts"}

    enriched_alerts = [_decorate_alert(alert, payload) for alert in raw_alerts]
    affected = ingest_alerts(enriched_alerts)
    logger.info("[alerts] webhook 接收 %d 条原始告警，影响 %d 个告警组", len(raw_alerts), len(affected))

    # 异步推送飞书（不阻塞响应）
    if affected:
        import asyncio
        asyncio.create_task(_notify_feishu(affected))

    return {"ok": True, "affected_groups": affected, "raw_count": len(raw_alerts)}


async def _notify_feishu(group_ids: list[str]) -> None:
    """将聚合后的告警按标签路由推送到对应飞书群。"""
    fallback_webhook = os.getenv("FEISHU_WEBHOOK", "").strip()
    fallback_keyword = os.getenv("FEISHU_KEYWORD", "").strip()

    for gid in group_ids:
        try:
            g = get_group(gid)
            if not g or g["status"] in ("resolved", "suppressed"):
                continue
            targets = _resolve_alert_targets(g)
            if targets:
                for target in targets:
                    result = await send_feishu_alert_group(
                        g,
                        target["webhook_url"],
                        keyword=target["keyword"],
                        target_name=target["group_name"],
                        matches=target["matches"],
                    )
                    if not result.get("ok"):
                        logger.warning(
                            "[alerts] 飞书分组推送失败 alert=%s group=%s: %s",
                            gid,
                            target["group_name"],
                            result.get("msg", "unknown error"),
                        )
                continue

            if fallback_webhook:
                result = await send_feishu_alert_group(
                    g,
                    fallback_webhook,
                    keyword=fallback_keyword,
                    target_name="默认飞书群",
                )
                if not result.get("ok"):
                    logger.warning(
                        "[alerts] 默认飞书推送失败 alert=%s: %s",
                        gid,
                        result.get("msg", "unknown error"),
                    )
        except Exception as exc:
            logger.warning("[alerts] 飞书推送失败 group=%s: %s", gid, exc)


# ── 告警组 CRUD ───────────────────────────────────────────────────────────────

@router.get("/api/alerts/groups")
async def get_alert_groups(
    status:    str | None = Query(None, description="过滤状态: new/grouped/resolved/suppressed"),
    namespace: str | None = Query(None, description="K8s namespace 过滤"),
    env:       str | None = Query(None, description="环境过滤: production/staging/development/testing"),
    service:   str | None = Query(None, description="服务名模糊过滤"),
    limit:     int = Query(100, ge=1, le=500),
):
    groups = list_groups(status=status, namespace=namespace, env=env, service=service, limit=limit)
    return {"groups": [_decorate_alert_group(group) for group in groups]}


@router.get("/api/alerts/filters")
async def get_alert_filters():
    """返回告警中出现过的 namespace 和 env 枚举值（供前端下拉框使用）。"""
    return {
        "namespaces": list_namespaces(),
        "envs":       list_envs(),
    }


@router.get("/api/alerts/groups/{group_id}")
async def get_alert_group(group_id: str):
    g = get_group(group_id)
    if not g:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="告警组不存在")
    return _decorate_alert_group(g)


class StatusUpdate(BaseModel):
    status: str   # resolved | suppressed | new
    rca_id: str | None = None


@router.put("/api/alerts/groups/{group_id}/status")
async def update_alert_status(group_id: str, body: StatusUpdate):
    ok = update_group_status(group_id, body.status, body.rca_id)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="告警组不存在")
    return {"ok": True}


# ── 统计（故障大盘） ────────────────────────────────────────────────────────────

@router.get("/api/alerts/stats")
async def get_alert_stats():
    return stats()
