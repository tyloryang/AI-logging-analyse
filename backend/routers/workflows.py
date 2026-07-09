"""工作流编排路由（参考 qinshihu/itops-agent-platform workflow 模块）。

提供工作流定义、执行任务和定时任务三类对象。当前版本先落地本平台可用的
轻量编排台账与模拟执行记录，保留 nodes / edges / agent_configs 结构，后续可接
真实 SSH、K8s、审批或 AIOps 自动处置执行器。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth.deps import current_user
from auth.models import User
from json_snapshot_store import read_json_file, write_json_file

router = APIRouter()

_WORKFLOW_FILE = Path(__file__).resolve().parent.parent / "data" / "workflows.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _workflow_seed() -> dict[str, list[dict[str, Any]]]:
    now = _now()
    workflows = [
        {
            "id": "wf_alert_response",
            "name": "告警响应闭环",
            "description": "告警进入后执行诊断、审批、处置、验证和报告沉淀。",
            "tags": ["alert", "aiops", "remediation"],
            "trigger_type": "alert",
            "status": "enabled",
            "is_template": 1,
            "nodes": [
                {"id": "trigger", "type": "trigger", "label": "告警触发"},
                {"id": "diagnose", "type": "agent", "label": "AIOps 诊断"},
                {"id": "approve", "type": "approval", "label": "人工审批"},
                {"id": "execute", "type": "action", "label": "执行处置"},
                {"id": "verify", "type": "check", "label": "结果验证"},
                {"id": "report", "type": "report", "label": "报告沉淀"},
            ],
            "edges": [
                {"source": "trigger", "target": "diagnose"},
                {"source": "diagnose", "target": "approve"},
                {"source": "approve", "target": "execute"},
                {"source": "execute", "target": "verify"},
                {"source": "verify", "target": "report"},
            ],
            "agent_configs": {"mode": "hybrid", "risk": "approval"},
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "wf_host_inspection",
            "name": "主机巡检流程",
            "description": "按主机或分组采集指标、分析异常并生成巡检建议。",
            "tags": ["host", "inspection"],
            "trigger_type": "manual",
            "status": "enabled",
            "is_template": 1,
            "nodes": [
                {"id": "select", "type": "input", "label": "选择目标"},
                {"id": "metrics", "type": "metrics", "label": "采集指标"},
                {"id": "analyze", "type": "agent", "label": "异常分析"},
                {"id": "notify", "type": "notify", "label": "通知值班"},
            ],
            "edges": [
                {"source": "select", "target": "metrics"},
                {"source": "metrics", "target": "analyze"},
                {"source": "analyze", "target": "notify"},
            ],
            "agent_configs": {"mode": "inspect"},
            "created_at": now,
            "updated_at": now,
        },
        {
            "id": "wf_release_guard",
            "name": "发布前检查流程",
            "description": "发布前串联变更检查、服务健康、错误日志和回滚预案确认。",
            "tags": ["release", "change"],
            "trigger_type": "manual",
            "status": "enabled",
            "is_template": 1,
            "nodes": [
                {"id": "change", "type": "input", "label": "变更信息"},
                {"id": "health", "type": "check", "label": "健康检查"},
                {"id": "logs", "type": "log", "label": "错误日志扫描"},
                {"id": "rollback", "type": "approval", "label": "回滚预案确认"},
            ],
            "edges": [
                {"source": "change", "target": "health"},
                {"source": "health", "target": "logs"},
                {"source": "logs", "target": "rollback"},
            ],
            "agent_configs": {"mode": "release_guard"},
            "created_at": now,
            "updated_at": now,
        },
    ]
    return {"workflows": workflows, "tasks": [], "scheduled_tasks": []}


def _load_store() -> dict[str, list[dict[str, Any]]]:
    data = read_json_file(_WORKFLOW_FILE, default=None)
    if data is None:
        seeded = _workflow_seed()
        write_json_file(_WORKFLOW_FILE, seeded, ensure_parent=True)
        return seeded
    if not isinstance(data, dict):
        return _workflow_seed()
    data.setdefault("workflows", [])
    data.setdefault("tasks", [])
    data.setdefault("scheduled_tasks", [])
    return data


def _save_store(data: dict[str, list[dict[str, Any]]]) -> None:
    write_json_file(_WORKFLOW_FILE, data, ensure_parent=True)


def _find_workflow(data: dict[str, list[dict[str, Any]]], workflow_id: str) -> dict[str, Any]:
    for workflow in data["workflows"]:
        if workflow.get("id") == workflow_id:
            return workflow
    raise HTTPException(status_code=404, detail=f"工作流 {workflow_id} 不存在")


class WorkflowPayload(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    agent_configs: dict[str, Any] = Field(default_factory=dict)
    is_template: int | bool = 0
    status: str = "enabled"
    tags: list[str] = Field(default_factory=list)
    trigger_type: str = "manual"


class WorkflowRunPayload(BaseModel):
    name: str = ""
    input: str = ""
    context: dict[str, Any] = Field(default_factory=dict)


class ScheduledTaskPayload(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    workflow_id: str
    cron_expression: str = "0 9 * * *"
    enabled: bool = True


@router.get("/api/workflows/summary")
async def workflow_summary(_: User = Depends(current_user)):
    data = _load_store()
    tasks = data["tasks"]
    schedules = data["scheduled_tasks"]
    by_status: dict[str, int] = {}
    for task in tasks:
        status = str(task.get("status") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "workflows": len(data["workflows"]),
        "templates": sum(1 for item in data["workflows"] if int(item.get("is_template") or 0) == 1),
        "tasks": len(tasks),
        "scheduled_tasks": len(schedules),
        "enabled_schedules": sum(1 for item in schedules if item.get("enabled")),
        "task_status": by_status,
    }


@router.get("/api/workflows")
async def list_workflows(
    search: Optional[str] = Query(None),
    template: Optional[str] = Query(None, description="all/template/custom"),
    _: User = Depends(current_user),
):
    workflows = list(_load_store()["workflows"])
    if search:
        keyword = search.strip().lower()
        workflows = [
            item for item in workflows
            if keyword in str(item.get("name", "")).lower()
            or keyword in str(item.get("description", "")).lower()
            or keyword in " ".join(item.get("tags", []) or []).lower()
        ]
    if template == "template":
        workflows = [item for item in workflows if int(item.get("is_template") or 0) == 1]
    elif template == "custom":
        workflows = [item for item in workflows if int(item.get("is_template") or 0) == 0]
    workflows.sort(key=lambda item: (0 if int(item.get("is_template") or 0) else 1, item.get("updated_at", "")), reverse=False)
    return {"success": True, "data": workflows, "total": len(workflows)}


@router.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: str, _: User = Depends(current_user)):
    data = _load_store()
    return {"success": True, "data": _find_workflow(data, workflow_id)}


@router.post("/api/workflows")
async def create_workflow(payload: WorkflowPayload, _: User = Depends(current_user)):
    data = _load_store()
    now = _now()
    workflow = {
        "id": _short_id("wf"),
        "created_at": now,
        "updated_at": now,
        **payload.model_dump(),
        "name": payload.name.strip(),
        "is_template": 1 if payload.is_template else 0,
        "tags": [tag.strip() for tag in payload.tags if tag.strip()],
    }
    data["workflows"].append(workflow)
    _save_store(data)
    return {"success": True, "data": workflow}


@router.put("/api/workflows/{workflow_id}")
async def update_workflow(workflow_id: str, payload: WorkflowPayload, _: User = Depends(current_user)):
    data = _load_store()
    workflow = _find_workflow(data, workflow_id)
    workflow.update(payload.model_dump())
    workflow["name"] = payload.name.strip()
    workflow["is_template"] = 1 if payload.is_template else 0
    workflow["tags"] = [tag.strip() for tag in payload.tags if tag.strip()]
    workflow["updated_at"] = _now()
    _save_store(data)
    return {"success": True, "data": workflow}


@router.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str, _: User = Depends(current_user)):
    data = _load_store()
    before = len(data["workflows"])
    data["workflows"] = [item for item in data["workflows"] if item.get("id") != workflow_id]
    if len(data["workflows"]) == before:
        raise HTTPException(status_code=404, detail=f"工作流 {workflow_id} 不存在")
    _save_store(data)
    return {"success": True}


@router.post("/api/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str, payload: WorkflowRunPayload, _: User = Depends(current_user)):
    """真实执行工作流：创建 running 任务并后台逐节点执行（services.workflow_engine）。"""
    import asyncio

    from services.workflow_engine import execute_workflow_task

    data = _load_store()
    workflow = _find_workflow(data, workflow_id)
    now = _now()
    nodes = workflow.get("nodes") or []
    task = {
        "id": _short_id("task"),
        "workflow_id": workflow_id,
        "workflow_name": workflow.get("name", ""),
        "name": payload.name.strip() or f"执行 {workflow.get('name', '工作流')}",
        "status": "running",
        "start_time": now,
        "end_time": None,
        "current_node_id": nodes[0].get("id") if nodes else "",
        "node_results": {},
        "logs": [{"level": "info", "message": "任务已创建，开始执行", "time": now}],
        "context": payload.context,
        "input": payload.input,
        "execution_order": [node.get("id") for node in nodes],
        "created_at": now,
    }
    data["tasks"].insert(0, task)
    data["tasks"] = data["tasks"][:200]
    _save_store(data)

    asyncio.create_task(execute_workflow_task(
        task["id"], dict(workflow), input_text=payload.input, context=payload.context,
    ))
    return {"success": True, "data": task}


@router.get("/api/tasks")
async def list_tasks(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _: User = Depends(current_user),
):
    tasks = list(_load_store()["tasks"])
    if status:
        tasks = [item for item in tasks if item.get("status") == status]
    tasks.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return {"success": True, "data": tasks[:limit], "total": len(tasks)}


@router.get("/api/tasks/{task_id}")
async def get_task(task_id: str, _: User = Depends(current_user)):
    for task in _load_store()["tasks"]:
        if task.get("id") == task_id:
            return {"success": True, "data": task}
    raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")


@router.put("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str, _: User = Depends(current_user)):
    data = _load_store()
    for task in data["tasks"]:
        if task.get("id") == task_id:
            task["status"] = "cancelled"
            task["end_time"] = _now()
            task.setdefault("logs", []).append({"level": "warn", "message": "任务已手动取消"})
            _save_store(data)
            return {"success": True, "data": task}
    raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")


@router.get("/api/scheduled-tasks")
async def list_scheduled_tasks(_: User = Depends(current_user)):
    data = _load_store()
    schedules = list(data["scheduled_tasks"])
    workflow_names = {item["id"]: item.get("name", "") for item in data["workflows"]}
    for item in schedules:
        item["workflow_name"] = workflow_names.get(item.get("workflow_id"), "")
    schedules.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return {"success": True, "data": schedules, "total": len(schedules)}


@router.post("/api/scheduled-tasks")
async def create_scheduled_task(payload: ScheduledTaskPayload, _: User = Depends(current_user)):
    data = _load_store()
    _find_workflow(data, payload.workflow_id)
    now = _now()
    item = {
        "id": _short_id("sched"),
        "created_at": now,
        "updated_at": now,
        "last_run_at": None,
        "next_run_at": "按 cron 计算",
        **payload.model_dump(),
    }
    data["scheduled_tasks"].append(item)
    _save_store(data)
    return {"success": True, "data": item}


@router.put("/api/scheduled-tasks/{schedule_id}")
async def update_scheduled_task(schedule_id: str, payload: ScheduledTaskPayload, _: User = Depends(current_user)):
    data = _load_store()
    _find_workflow(data, payload.workflow_id)
    for item in data["scheduled_tasks"]:
        if item.get("id") == schedule_id:
            item.update(payload.model_dump())
            item["updated_at"] = _now()
            _save_store(data)
            return {"success": True, "data": item}
    raise HTTPException(status_code=404, detail=f"定时任务 {schedule_id} 不存在")


@router.post("/api/scheduled-tasks/{schedule_id}/toggle")
async def toggle_scheduled_task(schedule_id: str, _: User = Depends(current_user)):
    data = _load_store()
    for item in data["scheduled_tasks"]:
        if item.get("id") == schedule_id:
            item["enabled"] = not bool(item.get("enabled"))
            item["updated_at"] = _now()
            _save_store(data)
            return {"success": True, "data": item}
    raise HTTPException(status_code=404, detail=f"定时任务 {schedule_id} 不存在")


@router.delete("/api/scheduled-tasks/{schedule_id}")
async def delete_scheduled_task(schedule_id: str, _: User = Depends(current_user)):
    data = _load_store()
    before = len(data["scheduled_tasks"])
    data["scheduled_tasks"] = [item for item in data["scheduled_tasks"] if item.get("id") != schedule_id]
    if len(data["scheduled_tasks"]) == before:
        raise HTTPException(status_code=404, detail=f"定时任务 {schedule_id} 不存在")
    _save_store(data)
    return {"success": True}
