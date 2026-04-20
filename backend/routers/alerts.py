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

from fastapi import APIRouter, Body, Query
from pydantic import BaseModel

from services.alert_dedup import (
    ingest_alerts,
    list_groups,
    get_group,
    update_group_status,
    stats,
)

logger = logging.getLogger(__name__)
router = APIRouter()


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

    affected = ingest_alerts(raw_alerts)
    logger.info("[alerts] webhook 接收 %d 条原始告警，影响 %d 个告警组", len(raw_alerts), len(affected))

    # 异步推送飞书（不阻塞响应）
    if affected:
        import asyncio
        asyncio.create_task(_notify_feishu(affected))

    return {"ok": True, "affected_groups": affected, "raw_count": len(raw_alerts)}


async def _notify_feishu(group_ids: list[str]) -> None:
    """将聚合后的告警组推送到飞书 Webhook（纯文本卡片）。"""
    import os
    import httpx

    webhook = os.getenv("FEISHU_WEBHOOK", "")
    if not webhook:
        return

    for gid in group_ids:
        try:
            g = get_group(gid)
            if not g or g["status"] in ("resolved", "suppressed"):
                continue
            sev_emoji = {"critical": "🔴", "error": "🔴", "warning": "🟡"}.get(g["severity"], "🔵")
            text = (
                f"{sev_emoji} 告警聚合通知\n"
                f"告警名：{g['alertname']}\n"
                f"服务：{g['service']}\n"
                f"共触发 {g['count']} 次（首次：{g['first_at'][:19].replace('T', ' ')}）\n"
                f"摘要：{g['summary'] or '（无摘要）'}"
            )
            payload = {"msg_type": "text", "content": {"text": text}}
            async with httpx.AsyncClient(timeout=8) as client:
                await client.post(webhook, json=payload)
        except Exception as exc:
            logger.warning("[alerts] 飞书推送失败 group=%s: %s", gid, exc)


# ── 告警组 CRUD ───────────────────────────────────────────────────────────────

@router.get("/api/alerts/groups")
async def get_alert_groups(
    status: str | None = Query(None, description="过滤状态: new/grouped/analyzing/resolved/suppressed"),
    limit: int = Query(100, ge=1, le=500),
):
    return {"groups": list_groups(status=status, limit=limit)}


@router.get("/api/alerts/groups/{group_id}")
async def get_alert_group(group_id: str):
    g = get_group(group_id)
    if not g:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="告警组不存在")
    return g


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
