"""Alert center routes."""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, Body, Query
from pydantic import BaseModel

from notifier import send_feishu_alert_group
from services.alert_dedup import (
    get_group,
    ingest_alerts,
    list_envs,
    list_groups,
    list_namespaces,
    stats,
    update_group_status,
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
    for source in (alert_group.get("group_labels", {}), alert_group.get("common_labels", {})):
        if isinstance(source, dict):
            labels.update({str(k): str(v) for k, v in source.items() if v is not None})
    for raw in alert_group.get("raw_alerts", []) or []:
        raw_labels = raw.get("labels", {}) if isinstance(raw, dict) else {}
        if isinstance(raw_labels, dict):
            labels.update({str(k): str(v) for k, v in raw_labels.items() if v is not None})
    for key in ("alertname", "service", "severity", "namespace", "env"):
        value = alert_group.get(key)
        if value:
            labels.setdefault(key, str(value))
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
        targets.append(
            {
                "group_id": group.get("id", ""),
                "group_name": group.get("name", ""),
                "webhook_url": webhook,
                "keyword": group.get("feishu_keyword", ""),
                "matches": matches,
            }
        )
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


@router.post("/api/alerts/webhook")
async def alertmanager_webhook(payload: dict = Body(...)):
    raw_alerts = payload.get("alerts", [])
    if not raw_alerts:
        return {"ok": True, "message": "no alerts"}

    enriched_alerts = [_decorate_alert(alert, payload) for alert in raw_alerts]
    affected = ingest_alerts(enriched_alerts)
    logger.info("[alerts] webhook received raw=%d affected=%d", len(raw_alerts), len(affected))

    if affected:
        asyncio.create_task(_notify_feishu(affected))

    # AIOps Router：告警自动派单给 aiops_router Agent 出根因/建议/趋势
    # 用 ALERTS_TO_AIOPS_ROUTER 环境变量控制（默认关闭，避免线上首次开就爆炸）
    if os.getenv("ALERTS_TO_AIOPS_ROUTER", "false").lower() in ("1", "true", "yes"):
        asyncio.create_task(_dispatch_to_aiops_router(enriched_alerts))

    return {"ok": True, "affected_groups": affected, "raw_count": len(raw_alerts)}


def _extract_report_section(report: str, keyword: str) -> str:
    """从 AI 报告里抠出【keyword】段落正文（到下一个【 或 ## 为止）。"""
    import re

    m = re.search(rf"【{keyword}[^】]*】\s*\n?(.*?)(?=\n\s*(?:#+\s*)?【|\n#{{2,}}\s|\Z)", report, re.S)
    return m.group(1).strip() if m else ""


async def _dispatch_to_aiops_router(alerts: list[dict]) -> None:
    """把告警派单给 aiops_router Agent 跑 SKILL 剧本，结果三路分发：
      ① 挂到告警组 ai_report 字段（告警中心前端可见）
      ② 写入 Milvus 事件记忆（供 recall_similar_incidents 召回历史案例）
      ③ 可选推飞书（ALERTS_AI_REPORT_FEISHU=true 且配置了 FEISHU_WEBHOOK）
    """
    from datetime import datetime, timezone

    from agent.graph import build_graph
    from langchain_core.messages import HumanMessage
    from services.alert_dedup import _fingerprint, get_group, update_group_status

    for alert in alerts[:5]:  # 一次最多派 5 条，避免 LLM 长上下文
        labels = alert.get("labels", {}) or {}
        annotations = alert.get("annotations", {}) or {}
        alertname = labels.get("alertname", "UnknownAlert")
        severity = labels.get("severity", "warning")
        service = labels.get("service", "") or labels.get("job", "")
        summary = annotations.get("summary", "")
        desc = annotations.get("description", "")

        body = (
            f"[Alertmanager 告警派单]\n"
            f"- alertname: {alertname}\n"
            f"- severity: {severity}\n"
            f"- labels: {labels}\n"
            f"- summary: {summary}\n"
            f"- description: {desc}\n\n"
            f"请按 aiops-router SKILL 流程处理：L1 抽实体 → L2 打域标签 → "
            f"L3 派单 domain skill → L4 交叉验证 → L5 输出【根因/影响/建议/趋势】。"
        )

        try:
            graph = build_graph(mode="aiops_router")
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=body)]},
                config={"configurable": {"thread_id": f"alert-{alertname}"}},
            )
            report = ""
            for msg in reversed(result.get("messages", [])):
                if getattr(msg, "type", "") == "ai" and str(msg.content).strip():
                    report = str(msg.content).strip()
                    break
            if not report:
                logger.warning("[aiops_router] alert=%s 无 AI 报告输出", alertname)
                continue
            logger.info("[aiops_router] alert=%s report_len=%d head=%s",
                        alertname, len(report), report[:200])
        except Exception:
            logger.exception("[aiops_router] alert=%s 分析失败", alertname)
            continue

        # ① 挂到告警组（告警中心前端直接展示）
        try:
            fp = _fingerprint(alert)
            group = get_group(fp)
            if group:
                update_group_status(
                    fp,
                    group.get("status", "firing"),
                    extra_updates={
                        "ai_report": report[:6000],
                        "ai_report_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
        except Exception as exc:
            logger.warning("[aiops_router] 报告挂载告警组失败 alert=%s err=%s", alertname, exc)

        # ② 写事件记忆（Milvus 不可用时 save 内部自动跳过）
        try:
            from agent.milvus_memory import get_memory

            await get_memory().save(
                mode="rca",
                user_query=f"[告警] {alertname} service={service} severity={severity} {summary}"[:500],
                full_summary=report[:4000],
                affected_services=service,
                root_cause=_extract_report_section(report, "根因")[:500],
                resolution=_extract_report_section(report, "建议")[:500],
            )
        except Exception as exc:
            logger.warning("[aiops_router] 写事件记忆失败 alert=%s err=%s", alertname, exc)

        # ③ 推飞书（默认关）
        if os.getenv("ALERTS_AI_REPORT_FEISHU", "false").lower() in ("1", "true", "yes"):
            webhook = os.getenv("FEISHU_WEBHOOK", "").strip()
            if webhook:
                try:
                    import httpx

                    keyword = os.getenv("FEISHU_KEYWORD", "").strip()
                    prefix = f"{keyword} " if keyword else ""
                    text = f"{prefix}🤖 AI 根因分析 | {alertname} ({severity})\n\n{report[:1500]}"
                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.post(webhook, json={"msg_type": "text", "content": {"text": text}})
                except Exception as exc:
                    logger.warning("[aiops_router] 飞书推送失败 alert=%s err=%s", alertname, exc)


async def _notify_feishu(group_ids: list[str]) -> None:
    fallback_webhook = os.getenv("FEISHU_WEBHOOK", "").strip()
    fallback_keyword = os.getenv("FEISHU_KEYWORD", "").strip()

    for gid in group_ids:
        try:
            group = get_group(gid)
            if not group or group["status"] in ("resolved", "suppressed"):
                continue

            targets = _resolve_alert_targets(group)
            if targets:
                for target in targets:
                    result = await send_feishu_alert_group(
                        group,
                        target["webhook_url"],
                        keyword=target["keyword"],
                        target_name=target["group_name"],
                        matches=target["matches"],
                    )
                    if not result.get("ok"):
                        logger.warning(
                            "[alerts] feishu group push failed alert=%s group=%s msg=%s",
                            gid,
                            target["group_name"],
                            result.get("msg", "unknown error"),
                        )
                continue

            if fallback_webhook:
                result = await send_feishu_alert_group(
                    group,
                    fallback_webhook,
                    keyword=fallback_keyword,
                    target_name="default-feishu-group",
                )
                if not result.get("ok"):
                    logger.warning(
                        "[alerts] feishu fallback push failed alert=%s msg=%s",
                        gid,
                        result.get("msg", "unknown error"),
                    )
        except Exception as exc:
            logger.warning("[alerts] feishu push failed group=%s err=%s", gid, exc)


@router.get("/api/alerts/groups")
async def get_alert_groups(
    status: str | None = Query(None, description="new/grouped/analyzing/resolved/suppressed"),
    namespace: str | None = Query(None, description="k8s namespace"),
    env: str | None = Query(None, description="environment"),
    service: str | None = Query(None, description="service fuzzy match"),
    limit: int = Query(100, ge=1, le=500),
):
    groups = list_groups(status=status, namespace=namespace, env=env, service=service, limit=limit)
    return {"groups": [_decorate_alert_group(group) for group in groups]}


@router.get("/api/alerts/filters")
async def get_alert_filters():
    return {"namespaces": list_namespaces(), "envs": list_envs()}


@router.get("/api/alerts/groups/{group_id}")
async def get_alert_group(group_id: str):
    group = get_group(group_id)
    if not group:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="alert group not found")
    return _decorate_alert_group(group)


class StatusUpdate(BaseModel):
    status: str
    rca_id: str | None = None


class AlertRCATriggerRequest(BaseModel):
    hours: float = 0.5
    extra_context: str = ""


@router.put("/api/alerts/groups/{group_id}/status")
async def update_alert_status(group_id: str, body: StatusUpdate):
    ok = update_group_status(group_id, body.status, body.rca_id)
    if not ok:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="alert group not found")
    return {"ok": True}


@router.post("/api/alerts/groups/{group_id}/rca")
async def trigger_alert_group_rca(group_id: str, body: AlertRCATriggerRequest | None = Body(default=None)):
    group = get_group(group_id)
    if not group:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="alert group not found")

    payload = body or AlertRCATriggerRequest()
    labels = _collect_alert_labels(group)
    extra_context = "\n".join(
        item
        for item in (
            str(group.get("summary") or "").strip(),
            str(group.get("description") or "").strip(),
            str(payload.extra_context or "").strip(),
        )
        if item
    )

    from services.rca_engine import create_pending_rca, run_rca

    pending = create_pending_rca(
        service=group.get("service"),
        alert_name=group.get("alertname", ""),
        alert_group_id=group_id,
        hours=payload.hours,
        extra_context=extra_context,
        source_type="alert",
        source_id=group_id,
        source_name=group.get("alertname", ""),
        source_labels=labels,
    )
    update_group_status(group_id, "analyzing", rca_id=pending["id"])

    async def _run():
        try:
            await run_rca(
                service=group.get("service"),
                alert_name=group.get("alertname", ""),
                alert_group_id=group_id,
                hours=payload.hours,
                extra_context=extra_context,
                source_type="alert",
                source_id=group_id,
                source_name=group.get("alertname", ""),
                source_labels=labels,
                existing_id=pending["id"],
            )
        except Exception as exc:
            logger.error("[alerts] RCA trigger failed group=%s err=%s", group_id, exc)

    asyncio.create_task(_run())
    return {"ok": True, "rca_id": pending["id"], "record": pending}


@router.get("/api/alerts/stats")
async def get_alert_stats():
    return stats()
