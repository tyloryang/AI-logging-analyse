"""AIOps 待确认动作（Pending Action）

SxDevOps 风格的动作闭环：
  AI 想执行高风险动作 → 不直接执行 → 先生成 PendingAction 草稿
  用户在任务中心看到 → 点「确认执行」→ 才真正调用底层工具
  执行结果回写 + 写审计日志
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from auth.deps import current_user
from auth.models import User
from json_snapshot_store import read_json_file, write_json_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/aiops", tags=["aiops-pending"])

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "pending_actions.json"

ActionStatus = Literal["pending", "approved", "rejected", "executed", "failed", "expired"]
RiskLevel = Literal["low", "medium", "high"]


class PendingActionCreate(BaseModel):
    title: str
    action: str                  # 工具调用 / 命令 / 操作描述
    target: str = ""             # 主机 IP / 服务名 / 资源
    risk: RiskLevel = "medium"
    rationale: str = ""          # AI 提交时的理由（结论 / 依据）
    expected: str = ""           # 预期效果
    requested_by: str = "AIOps"
    payload: dict = {}           # 真正执行时需要的参数


def _load() -> list[dict]:
    data = read_json_file(_DATA_FILE, default=[])
    return data if isinstance(data, list) else []


def _save(items: list[dict]) -> None:
    write_json_file(_DATA_FILE, items, ensure_parent=True)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/pending-actions")
async def list_pending_actions(
    status: str = "",
    limit: int = 100,
    user: User = Depends(current_user),
):
    """返回当前用户可见的待确认动作。"""
    items = _load()
    if status:
        items = [i for i in items if i.get("status") == status]
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"data": items[:limit], "total": len(items)}


@router.post("/pending-actions")
async def create_pending_action(body: PendingActionCreate, user: User = Depends(current_user)):
    """AI Agent 生成动作草稿（不立即执行）。"""
    items = _load()
    item = {
        "id": "pa_" + uuid.uuid4().hex[:10],
        "title": body.title,
        "action": body.action,
        "target": body.target,
        "risk": body.risk,
        "rationale": body.rationale,
        "expected": body.expected,
        "requested_by": body.requested_by,
        "payload": body.payload,
        "status": "pending",
        "created_at": _now(),
        "updated_at": _now(),
        "approved_by": "",
        "approved_at": "",
        "result": "",
        "history": [{"at": _now(), "by": body.requested_by, "action": "create", "detail": "AI 提交"}],
    }
    items.append(item)
    _save(items)
    return item


@router.post("/pending-actions/{action_id}/approve")
async def approve_pending_action(action_id: str, user: User = Depends(current_user)):
    """用户确认 → 标记 approved。真正的执行由调用方触发对应工具/工单接口。"""
    items = _load()
    idx = next((i for i, x in enumerate(items) if x.get("id") == action_id), None)
    if idx is None:
        raise HTTPException(404, "动作不存在")
    item = items[idx]
    if item["status"] != "pending":
        raise HTTPException(400, f"状态不可批准：{item['status']}")
    item["status"] = "approved"
    item["approved_by"] = user.username
    item["approved_at"] = _now()
    item["updated_at"] = _now()
    item["history"].append({"at": _now(), "by": user.username, "action": "approve",
                            "detail": "用户确认"})
    items[idx] = item
    _save(items)
    return {"ok": True, "action": item}


@router.post("/pending-actions/{action_id}/reject")
async def reject_pending_action(action_id: str, user: User = Depends(current_user)):
    items = _load()
    idx = next((i for i, x in enumerate(items) if x.get("id") == action_id), None)
    if idx is None:
        raise HTTPException(404, "动作不存在")
    item = items[idx]
    if item["status"] != "pending":
        raise HTTPException(400, f"状态不可拒绝：{item['status']}")
    item["status"] = "rejected"
    item["approved_by"] = user.username
    item["approved_at"] = _now()
    item["updated_at"] = _now()
    item["history"].append({"at": _now(), "by": user.username, "action": "reject", "detail": "用户拒绝"})
    items[idx] = item
    _save(items)
    return {"ok": True, "action": item}


class ExecuteResult(BaseModel):
    success: bool
    output: str = ""
    error: str = ""


@router.post("/pending-actions/{action_id}/result")
async def write_execute_result(action_id: str, body: ExecuteResult, user: User = Depends(current_user)):
    """记录执行结果（由执行方在真正调用工具后回写）。"""
    items = _load()
    idx = next((i for i, x in enumerate(items) if x.get("id") == action_id), None)
    if idx is None:
        raise HTTPException(404, "动作不存在")
    item = items[idx]
    item["status"] = "executed" if body.success else "failed"
    item["result"] = body.output if body.success else body.error
    item["updated_at"] = _now()
    item["history"].append({"at": _now(), "by": user.username,
                            "action": "result", "detail": f"{'success' if body.success else 'failed'}"})
    items[idx] = item
    _save(items)
    return {"ok": True, "action": item}
