"""统一 cron 调度 tick（每分钟由 APScheduler 触发一次）。

驱动两类计划任务的真实执行：
  1. Ansible 计划任务（data/ansible_crons.json，routers.ansible_tasks.execute_scheduled_cron）
  2. 工作流定时任务（data/workflows.json scheduled_tasks → services.workflow_engine）

内置轻量 5 段 cron 匹配器（分 时 日 月 周），支持 * , - / 组合，
避免引入 croniter 依赖。day_of_week 支持 0-7（0 和 7 都是周日）。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _field_matches(field: str, value: int, min_v: int, max_v: int) -> bool:
    for part in str(field).split(","):
        part = part.strip()
        if not part:
            continue
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            try:
                step = max(1, int(step_text))
            except ValueError:
                step = 1
        if part in ("*", ""):
            start, end = min_v, max_v
        elif "-" in part:
            try:
                a, b = part.split("-", 1)
                start, end = int(a), int(b)
            except ValueError:
                continue
        else:
            try:
                start = int(part)
            except ValueError:
                continue
            # "5/10" 形式：从 5 开始每 step；无 step 则精确匹配
            end = max_v if step > 1 else start
        if start <= value <= end and (value - start) % step == 0:
            return True
    return False


def cron_matches(expr: str, dt: datetime) -> bool:
    """判断 5 段 cron 表达式是否命中给定时间（分钟粒度）。非法表达式返回 False。"""
    parts = str(expr or "").split()
    if len(parts) != 5:
        return False
    minute, hour, day, month, dow = parts
    # cron 周日=0 或 7；Python weekday() 周一=0 → 转 cron 习惯并对周日双值匹配
    dt_dow = (dt.weekday() + 1) % 7
    dow_ok = _field_matches(dow, dt_dow, 0, 7) or (dt_dow == 0 and _field_matches(dow, 7, 0, 7))
    return (
        _field_matches(minute, dt.minute, 0, 59)
        and _field_matches(hour, dt.hour, 0, 23)
        and _field_matches(day, dt.day, 1, 31)
        and _field_matches(month, dt.month, 1, 12)
        and dow_ok
    )


async def _tick_ansible_crons(now: datetime) -> None:
    from routers.ansible_tasks import _load_crons, execute_scheduled_cron

    for cron in _load_crons():
        if not cron.get("enabled"):
            continue
        if not cron_matches(cron.get("cron", ""), now):
            continue
        logger.info("[cron_tick] 触发 Ansible 计划任务: %s (%s)", cron.get("name"), cron.get("cron"))
        asyncio.create_task(execute_scheduled_cron(cron["id"]))


async def _tick_workflow_schedules(now: datetime) -> None:
    from routers.workflows import _load_store, _save_store, _short_id, _now
    from services.workflow_engine import execute_workflow_task

    data = _load_store()
    workflows = {wf.get("id"): wf for wf in data["workflows"]}
    changed = False

    for schedule in data["scheduled_tasks"]:
        if not schedule.get("enabled"):
            continue
        if not cron_matches(schedule.get("cron_expression", ""), now):
            continue
        workflow = workflows.get(schedule.get("workflow_id"))
        if not workflow or workflow.get("status") != "enabled":
            continue

        now_iso = _now()
        nodes = workflow.get("nodes") or []
        task = {
            "id": _short_id("task"),
            "workflow_id": workflow.get("id"),
            "workflow_name": workflow.get("name", ""),
            "name": f"[定时] {schedule.get('name') or workflow.get('name', '工作流')}",
            "status": "running",
            "start_time": now_iso,
            "end_time": None,
            "current_node_id": nodes[0].get("id") if nodes else "",
            "node_results": {},
            "logs": [{"level": "info", "message": f"由定时计划「{schedule.get('name')}」触发", "time": now_iso}],
            "context": {"source": "scheduled", "schedule_id": schedule.get("id")},
            "input": "",
            "execution_order": [node.get("id") for node in nodes],
            "created_at": now_iso,
        }
        data["tasks"].insert(0, task)
        data["tasks"] = data["tasks"][:200]
        schedule["last_run_at"] = now_iso
        changed = True

        logger.info("[cron_tick] 触发工作流定时任务: %s → %s", schedule.get("name"), workflow.get("name"))
        asyncio.create_task(execute_workflow_task(task["id"], dict(workflow)))

    if changed:
        _save_store(data)


async def run_cron_tick() -> None:
    """每分钟一次：检查两类计划任务并触发到点项（互不阻塞）。"""
    now = datetime.now()
    try:
        await _tick_ansible_crons(now)
    except Exception as exc:
        logger.warning("[cron_tick] Ansible 计划检查失败: %s", exc)
    try:
        await _tick_workflow_schedules(now)
    except Exception as exc:
        logger.warning("[cron_tick] 工作流定时检查失败: %s", exc)
