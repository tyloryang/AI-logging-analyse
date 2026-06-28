"""工单系统路由 — /api/tickets/*

支持四类工单：deploy（应用发布）/ sql（SQL审计）/ incident（事务工单）/ approval（审批流）。
数据持久化到 data/tickets.json。
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from json_snapshot_store import read_json_file, write_json_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tickets", tags=["tickets"])

_DATA_FILE = Path(__file__).parent.parent / "data" / "tickets.json"

TicketType   = Literal["deploy", "sql", "incident", "approval"]
TicketStatus = Literal["pending", "approved", "rejected", "in_progress", "done", "cancelled"]


def _load() -> list[dict]:
    data = read_json_file(_DATA_FILE, default=[])
    return data if isinstance(data, list) else []


def _save(data: list[dict]) -> None:
    write_json_file(_DATA_FILE, data, ensure_parent=True)


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


class SqlPrecheckRequest(BaseModel):
    sql:        str = ""
    datasource: str = ""


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql or "", flags=re.S)
    sql = re.sub(r"--.*?$", " ", sql, flags=re.M)
    return sql.strip()


def _first_keyword(statement: str) -> str:
    match = re.match(r"^\s*([a-zA-Z]+)", statement or "")
    return match.group(1).upper() if match else ""


def analyze_sql_risk(sql: str) -> dict:
    """Lightweight SQL risk precheck inspired by sxdevops SQL audit workflow."""
    cleaned = _strip_sql_comments(sql)
    statements = [s.strip() for s in cleaned.split(";") if s.strip()]
    findings: list[dict] = []
    score = 0

    def add(level: str, rule: str, message: str, points: int) -> None:
        nonlocal score
        findings.append({"level": level, "rule": rule, "message": message})
        score += points

    if not cleaned:
        add("warning", "empty_sql", "未填写 SQL，建议补充执行语句后再提交审计。", 3)

    if len(statements) > 1:
        add("warning", "multi_statement", f"检测到 {len(statements)} 条语句，建议拆分为独立工单便于回滚和审计。", 2)

    for statement in statements:
        keyword = _first_keyword(statement)
        upper = statement.upper()
        if keyword in {"DROP", "TRUNCATE"}:
            add("critical", "destructive_ddl", f"{keyword} 属于高危破坏性 DDL，必须确认备份、回滚方案和执行窗口。", 8)
        elif keyword in {"ALTER", "RENAME"}:
            add("warning", "schema_change", f"{keyword} 会变更表结构，建议补充影响范围、锁表风险和回滚方案。", 4)
        elif keyword in {"DELETE", "UPDATE"}:
            if " WHERE " not in f" {upper} ":
                add("critical", "missing_where", f"{keyword} 未检测到 WHERE 条件，存在全表影响风险。", 8)
            else:
                add("warning", "write_dml", f"{keyword} 为写操作，建议先提供 SELECT 验证语句和影响行数预估。", 3)
        elif keyword in {"INSERT", "REPLACE"}:
            add("info", "write_insert", f"{keyword} 为写操作，建议确认唯一键冲突和幂等性。", 1)
        elif keyword in {"GRANT", "REVOKE"}:
            add("warning", "permission_change", f"{keyword} 会变更数据库权限，建议明确账号、权限范围和有效期。", 4)
        elif keyword == "SELECT" and re.search(r"\bSELECT\s+\*", upper):
            add("info", "select_star", "SELECT * 可能返回过多字段，建议改为显式字段列表。", 1)
        elif keyword and keyword not in {"SELECT", "SHOW", "DESC", "DESCRIBE", "EXPLAIN", "WITH"}:
            add("warning", "unknown_statement", f"检测到非常见语句 {keyword}，建议人工复核。", 3)

    if not findings:
        findings.append({"level": "ok", "rule": "readonly", "message": "未发现明显高危模式。"})

    if score >= 8:
        risk = "critical"
    elif score >= 4:
        risk = "high"
    elif score >= 2:
        risk = "medium"
    else:
        risk = "low"

    suggestions = [
        "生产执行前先在只读连接或备库验证影响范围。",
        "写操作请补充回滚 SQL、备份位置和执行窗口。",
    ]
    if risk in {"critical", "high"}:
        suggestions.insert(0, "建议走审批后执行，并在事件墙记录执行结果。")

    return {
        "risk_level": risk,
        "score": score,
        "statement_count": len(statements),
        "findings": findings,
        "suggestions": suggestions,
    }


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
    extra = dict(body.extra or {})
    priority = body.priority
    if body.type == "sql":
        sql_audit = analyze_sql_risk(str(extra.get("sql") or body.description or ""))
        extra["sql_audit"] = sql_audit
        if sql_audit["risk_level"] in {"critical", "high"} and priority in {"low", "normal"}:
            priority = "high"
    ticket = {
        "id":          str(uuid.uuid4()),
        "no":          f"{prefix}-{count + 1:04d}",
        "type":        body.type,
        "title":       body.title,
        "description": body.description,
        "priority":    priority,
        "assignee":    body.assignee,
        "status":      "pending",
        "extra":       extra,
        "created_at":  _now(),
        "updated_at":  _now(),
        "history":     [],
    }
    tickets.append(ticket)
    _save(tickets)
    return ticket


@router.post("/sql/precheck")
async def precheck_sql_ticket(body: SqlPrecheckRequest):
    return analyze_sql_risk(body.sql)


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
