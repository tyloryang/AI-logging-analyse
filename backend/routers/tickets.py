"""工单系统路由 — /api/tickets/*

支持四类工单：deploy（应用发布）/ sql（SQL审计）/ incident（事务工单）/ approval（审批流）。
数据持久化到 data/tickets.json。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tickets", tags=["tickets"])

_DATA_FILE = Path(__file__).parent.parent / "data" / "tickets.json"

TicketType   = Literal["deploy", "sql", "incident", "approval"]
TicketStatus = Literal["pending", "approved", "rejected", "in_progress", "done", "cancelled"]


def _load() -> list[dict]:
    if _DATA_FILE.exists():
        try:
            return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(data: list[dict]) -> None:
    _DATA_FILE.parent.mkdir(exist_ok=True)
    _DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Pydantic 模型 ─────────────────────────────────────────────────────────────

class TicketCreate(BaseModel):
    type:        TicketType
    title:       str
    description: str = ""
    priority:    str = "normal"    # low / normal / high / urgent
    assignee:    str = ""
    extra:       dict = {}         # 各类型扩展字段

class TicketUpdate(BaseModel):
    title:       str | None = None
    description: str | None = None
    status:      TicketStatus | None = None
    priority:    str | None = None
    assignee:    str | None = None
    extra:       dict | None = None
    comment:     str = ""          # 操作备注


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("")
async def list_tickets(
    type:   str = Query("", description="工单类型"),
    status: str = Query("", description="状态过滤"),
    limit:  int = Query(100),
):
    tickets = _load()
    if type:
        tickets = [t for t in tickets if t.get("type") == type]
    if status:
        tickets = [t for t in tickets if t.get("status") == status]
    return sorted(tickets, key=lambda t: t.get("created_at", ""), reverse=True)[:limit]


@router.post("")
async def create_ticket(body: TicketCreate):
    tickets = _load()
    # 按类型生成编号
    prefix = {"deploy": "DP", "sql": "SQL", "incident": "INC", "approval": "APR"}.get(body.type, "TK")
    count = sum(1 for t in tickets if t.get("type") == body.type)
    ticket = {
        "id":          str(uuid.uuid4()),
        "no":          f"{prefix}-{count + 1:04d}",
        "type":        body.type,
        "title":       body.title,
        "description": body.description,
        "priority":    body.priority,
        "assignee":    body.assignee,
        "status":      "pending",
        "extra":       body.extra,
        "created_at":  _now(),
        "updated_at":  _now(),
        "history":     [],
    }
    tickets.append(ticket)
    _save(tickets)
    return ticket


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: str):
    t = next((t for t in _load() if t["id"] == ticket_id), None)
    if not t:
        raise HTTPException(404, "工单不存在")
    return t


@router.put("/{ticket_id}")
async def update_ticket(ticket_id: str, body: TicketUpdate):
    tickets = _load()
    idx = next((i for i, t in enumerate(tickets) if t["id"] == ticket_id), None)
    if idx is None:
        raise HTTPException(404, "工单不存在")

    t = tickets[idx]
    old_status = t.get("status", "")

    if body.title       is not None: t["title"]       = body.title
    if body.description is not None: t["description"] = body.description
    if body.priority    is not None: t["priority"]    = body.priority
    if body.assignee    is not None: t["assignee"]    = body.assignee
    if body.extra       is not None: t["extra"]       = {**t.get("extra", {}), **body.extra}
    if body.status      is not None: t["status"]      = body.status

    t["updated_at"] = _now()

    if body.comment or (body.status and body.status != old_status):
        t.setdefault("history", []).append({
            "time":       _now(),
            "old_status": old_status,
            "new_status": t["status"],
            "comment":    body.comment,
        })

    _save(tickets)
    return t


@router.delete("/{ticket_id}")
async def delete_ticket(ticket_id: str):
    tickets = [t for t in _load() if t["id"] != ticket_id]
    _save(tickets)
    return {"ok": True}


@router.post("/{ticket_id}/approve")
async def approve_ticket(ticket_id: str, comment: str = ""):
    return await _set_status(ticket_id, "approved", comment or "已批准")


@router.post("/{ticket_id}/reject")
async def reject_ticket(ticket_id: str, comment: str = ""):
    return await _set_status(ticket_id, "rejected", comment or "已拒绝")


@router.post("/{ticket_id}/done")
async def done_ticket(ticket_id: str, comment: str = ""):
    return await _set_status(ticket_id, "done", comment or "已完成")


async def _set_status(ticket_id: str, status: str, comment: str) -> dict:
    tickets = _load()
    t = next((t for t in tickets if t["id"] == ticket_id), None)
    if not t:
        raise HTTPException(404, "工单不存在")
    old = t.get("status", "")
    t["status"] = status
    t["updated_at"] = _now()
    t.setdefault("history", []).append({"time": _now(), "old_status": old, "new_status": status, "comment": comment})
    _save(tickets)
    return t


# ── 统计 ──────────────────────────────────────────────────────────────────────

@router.get("/stats/summary")
async def ticket_stats():
    tickets = _load()
    result = {}
    for tp in ("deploy", "sql", "incident", "approval"):
        subset = [t for t in tickets if t.get("type") == tp]
        result[tp] = {
            "total":       len(subset),
            "pending":     sum(1 for t in subset if t["status"] == "pending"),
            "in_progress": sum(1 for t in subset if t["status"] == "in_progress"),
            "done":        sum(1 for t in subset if t["status"] == "done"),
        }
    return result
