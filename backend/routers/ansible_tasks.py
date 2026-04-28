"""Ansible 任务中心路由 — /api/ansible/*

通过 ansible-runner 或 subprocess 执行 playbook，
持久化任务记录到 data/ansible_tasks.json。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ansible", tags=["ansible"])

_DATA_DIR   = Path(__file__).parent.parent / "data"
_TASKS_FILE = _DATA_DIR / "ansible_tasks.json"

TaskStatus = Literal["pending", "running", "success", "failed", "cancelled"]


# ── 持久化 ──────────────────────────────────────────────────────────────────

def _load_tasks() -> list[dict]:
    if _TASKS_FILE.exists():
        try:
            return json.loads(_TASKS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_tasks(tasks: list[dict]) -> None:
    _DATA_DIR.mkdir(exist_ok=True)
    _TASKS_FILE.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Ansible 执行 ─────────────────────────────────────────────────────────────

def _ansible_base_dir() -> str:
    try:
        import json as _json
        p = Path(__file__).parent.parent / "data" / "settings.json"
        if p.exists():
            d = _json.loads(p.read_text()).get("ansible_base_dir", "")
            if d:
                return d
    except Exception:
        pass
    return os.getenv("ANSIBLE_BASE_DIR", str(Path.home()))


def _ansible_binary() -> str:
    for path in [
        os.getenv("ANSIBLE_PLAYBOOK_BIN", ""),
        "/usr/bin/ansible-playbook",
        "/usr/local/bin/ansible-playbook",
    ]:
        if path and Path(path).exists():
            return path
    return "ansible-playbook"


async def _run_playbook(task_id: str, playbook: str, inventory: str, extra_vars: dict) -> None:
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return

    task["status"] = "running"
    task["started_at"] = _now()
    _save_tasks(tasks)

    cmd = [_ansible_binary(), playbook, "-i", inventory]
    if extra_vars:
        cmd += ["--extra-vars", json.dumps(extra_vars)]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=_ansible_base_dir(),
        )
        stdout_lines = []
        assert proc.stdout
        async for line in proc.stdout:
            stdout_lines.append(line.decode("utf-8", errors="replace").rstrip())
        await proc.wait()

        tasks = _load_tasks()
        task = next((t for t in tasks if t["id"] == task_id), None)
        if task:
            task["status"] = "success" if proc.returncode == 0 else "failed"
            task["finished_at"] = _now()
            task["output"] = "\n".join(stdout_lines[-500:])  # 保留最后 500 行
            task["return_code"] = proc.returncode
            _save_tasks(tasks)
    except Exception as exc:
        tasks = _load_tasks()
        task = next((t for t in tasks if t["id"] == task_id), None)
        if task:
            task["status"] = "failed"
            task["finished_at"] = _now()
            task["output"] = str(exc)
            _save_tasks(tasks)


# ── API ──────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    name: str
    playbook: str
    inventory: str = "localhost,"
    extra_vars: dict = {}
    description: str = ""


class CronJobCreate(BaseModel):
    name: str
    cron: str           # e.g. "0 9 * * *"
    playbook: str
    inventory: str = "localhost,"
    extra_vars: dict = {}
    enabled: bool = True
    description: str = ""


@router.get("/tasks")
async def list_tasks():
    tasks = _load_tasks()
    return sorted(tasks, key=lambda t: t.get("created_at", ""), reverse=True)


@router.post("/tasks")
async def create_task(body: TaskCreate):
    task = {
        "id":          str(uuid.uuid4()),
        "name":        body.name,
        "playbook":    body.playbook,
        "inventory":   body.inventory,
        "extra_vars":  body.extra_vars,
        "description": body.description,
        "status":      "pending",
        "created_at":  _now(),
        "started_at":  None,
        "finished_at": None,
        "output":      "",
        "return_code": None,
        "type":        "adhoc",
    }
    tasks = _load_tasks()
    tasks.append(task)
    _save_tasks(tasks)

    asyncio.create_task(_run_playbook(task["id"], body.playbook, body.inventory, body.extra_vars))
    return task


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    task = next((t for t in _load_tasks() if t["id"] == task_id), None)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    tasks = [t for t in _load_tasks() if t["id"] != task_id]
    _save_tasks(tasks)
    return {"ok": True}


# ── Cron Jobs ────────────────────────────────────────────────────────────────

_CRON_FILE = _DATA_DIR / "ansible_crons.json"


def _load_crons() -> list[dict]:
    if _CRON_FILE.exists():
        try:
            return json.loads(_CRON_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_crons(crons: list[dict]) -> None:
    _DATA_DIR.mkdir(exist_ok=True)
    _CRON_FILE.write_text(json.dumps(crons, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/crons")
async def list_crons():
    return _load_crons()


@router.post("/crons")
async def create_cron(body: CronJobCreate):
    cron = {
        "id":          str(uuid.uuid4()),
        "name":        body.name,
        "cron":        body.cron,
        "playbook":    body.playbook,
        "inventory":   body.inventory,
        "extra_vars":  body.extra_vars,
        "enabled":     body.enabled,
        "description": body.description,
        "created_at":  _now(),
        "last_run":    None,
        "last_status": None,
    }
    crons = _load_crons()
    crons.append(cron)
    _save_crons(crons)
    return cron


@router.put("/crons/{cron_id}")
async def update_cron(cron_id: str, body: CronJobCreate):
    crons = _load_crons()
    idx = next((i for i, c in enumerate(crons) if c["id"] == cron_id), None)
    if idx is None:
        raise HTTPException(404, "定时任务不存在")
    crons[idx].update({
        "name":        body.name,
        "cron":        body.cron,
        "playbook":    body.playbook,
        "inventory":   body.inventory,
        "extra_vars":  body.extra_vars,
        "enabled":     body.enabled,
        "description": body.description,
    })
    _save_crons(crons)
    return crons[idx]


@router.delete("/crons/{cron_id}")
async def delete_cron(cron_id: str):
    crons = [c for c in _load_crons() if c["id"] != cron_id]
    _save_crons(crons)
    return {"ok": True}


@router.post("/crons/{cron_id}/run")
async def run_cron_now(cron_id: str):
    cron = next((c for c in _load_crons() if c["id"] == cron_id), None)
    if not cron:
        raise HTTPException(404, "定时任务不存在")

    task = {
        "id":          str(uuid.uuid4()),
        "name":        f"[手动触发] {cron['name']}",
        "playbook":    cron["playbook"],
        "inventory":   cron["inventory"],
        "extra_vars":  cron.get("extra_vars", {}),
        "description": f"手动触发定时任务 {cron_id}",
        "status":      "pending",
        "created_at":  _now(),
        "started_at":  None,
        "finished_at": None,
        "output":      "",
        "return_code": None,
        "type":        "cron_manual",
    }
    tasks = _load_tasks()
    tasks.append(task)
    _save_tasks(tasks)

    asyncio.create_task(_run_playbook(task["id"], cron["playbook"], cron["inventory"], cron.get("extra_vars", {})))
    return task


# ── Playbook 列表 ──────────────────────────────────────────────────────────

@router.get("/playbooks")
async def list_playbooks():
    """扫描 ANSIBLE_BASE_DIR 下的 *.yml / *.yaml 文件。
    未配置时返回空列表，避免扫描 home 目录导致超长等待。
    """
    base_str = os.getenv("ANSIBLE_BASE_DIR", "")
    try:
        import json as _json
        p = Path(__file__).parent.parent / "data" / "settings.json"
        if p.exists():
            d = _json.loads(p.read_text()).get("ansible_base_dir", "")
            if d:
                base_str = d
    except Exception:
        pass

    if not base_str:
        return []   # 未配置则直接返回，不扫描 home 目录

    base = Path(base_str)
    if not base.exists() or not base.is_dir():
        return []

    try:
        loop = asyncio.get_event_loop()
        def _scan():
            files = []
            for ext in ("*.yml", "*.yaml"):
                files.extend(base.rglob(ext))
            return [str(f.relative_to(base)) for f in sorted(files)[:200]]
        # 在线程池中执行，避免阻塞事件循环
        return await loop.run_in_executor(None, _scan)
    except Exception:
        return []
