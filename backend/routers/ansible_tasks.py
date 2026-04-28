"""内置计划任务中心 — 通过 asyncssh 在 CMDB 主机上执行命令/脚本。

不依赖 Ansible，完全内置：
  asyncssh  — SSH 执行
  APScheduler（main.py lifespan）— cron 调度
  CMDB      — 主机清单

端点：
  GET  /api/ansible/tasks           — 任务执行历史列表
  POST /api/ansible/tasks           — 手动触发即时任务
  GET  /api/ansible/tasks/{id}      — 任务详情+输出
  DELETE /api/ansible/tasks/{id}    — 删除历史记录
  GET  /api/ansible/crons           — 计划任务列表
  POST /api/ansible/crons           — 创建计划任务
  PUT  /api/ansible/crons/{id}      — 更新计划任务
  DELETE /api/ansible/crons/{id}    — 删除计划任务
  POST /api/ansible/crons/{id}/run  — 立即触发计划任务
  GET  /api/ansible/playbooks       — 兼容旧接口，返回 []
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ansible", tags=["ansible"])

_DATA_DIR   = Path(__file__).parent.parent / "data"
_TASKS_FILE = _DATA_DIR / "ansible_tasks.json"
_CRONS_FILE = _DATA_DIR / "ansible_crons.json"

TaskStatus = Literal["pending", "running", "success", "failed", "cancelled"]

_NOW = lambda: datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

# ── 持久化 ─────────────────────────────────────────────────────────────────────

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

def _load_crons() -> list[dict]:
    if _CRONS_FILE.exists():
        try:
            return json.loads(_CRONS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []

def _save_crons(crons: list[dict]) -> None:
    _DATA_DIR.mkdir(exist_ok=True)
    _CRONS_FILE.write_text(json.dumps(crons, ensure_ascii=False, indent=2), encoding="utf-8")

# ── SSH 执行核心 ───────────────────────────────────────────────────────────────

async def _ssh_exec_host(host: dict, command: str, timeout: int = 60) -> dict:
    """在单台主机上执行命令，返回 {ip, hostname, rc, stdout, stderr, error}。"""
    import asyncssh
    from state import decrypt_password, load_credentials

    ip       = host.get("ip", "")
    port     = int(host.get("ssh_port") or 22)
    username = host.get("ssh_user") or "root"
    password = None

    cred_id = host.get("credential_id", "")
    if cred_id:
        creds = load_credentials()
        cred = next((c for c in creds if c.get("id") == cred_id), None)
        if cred:
            username = cred.get("username", username)
            raw = cred.get("password", "")
            if raw:
                try:
                    password = decrypt_password(raw)
                except Exception:
                    password = raw

    if not password:
        enc = host.get("ssh_password", "")
        if enc:
            try:
                password = decrypt_password(enc)
            except Exception:
                pass

    base = {"ip": ip, "hostname": host.get("hostname", ip)}

    if not password:
        return {**base, "rc": -1, "stdout": "", "stderr": "", "error": "未配置 SSH 密码"}

    try:
        async with asyncssh.connect(
            host=ip, port=port, username=username, password=password,
            known_hosts=None, connect_timeout=10,
        ) as conn:
            result = await conn.run(command, timeout=timeout)
            return {
                **base,
                "rc":     result.exit_status,
                "stdout": (result.stdout or "").strip(),
                "stderr": (result.stderr or "").strip(),
                "error":  "",
            }
    except Exception as e:
        return {**base, "rc": -1, "stdout": "", "stderr": "", "error": str(e)}


async def _execute_task(task_id: str, hosts: list[dict], command: str,
                        timeout: int = 60, cron_id: str = "") -> None:
    """并发执行命令到所有目标主机，写入任务历史。"""
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return

    task["status"] = "running"
    task["started_at"] = _NOW()
    _save_tasks(tasks)

    try:
        results = await asyncio.gather(
            *[_ssh_exec_host(h, command, timeout) for h in hosts],
            return_exceptions=True,
        )

        host_results = []
        success_count = fail_count = 0
        for r in results:
            if isinstance(r, Exception):
                host_results.append({"error": str(r), "rc": -1})
                fail_count += 1
            else:
                host_results.append(r)
                if r.get("rc") == 0:
                    success_count += 1
                else:
                    fail_count += 1

        task["status"] = "success" if fail_count == 0 else ("failed" if success_count == 0 else "partial")
        task["finished_at"] = _NOW()
        task["host_results"] = host_results
        task["summary"] = f"成功 {success_count} 台，失败 {fail_count} 台"

    except Exception as e:
        task["status"] = "failed"
        task["finished_at"] = _NOW()
        task["summary"] = str(e)

    _save_tasks(tasks)

    # 更新 cron 的最后执行状态
    if cron_id:
        crons = _load_crons()
        cron = next((c for c in crons if c["id"] == cron_id), None)
        if cron:
            cron["last_run"]    = task["finished_at"]
            cron["last_status"] = task["status"]
            _save_crons(crons)


# ── 任务历史 ───────────────────────────────────────────────────────────────────

class RunTaskRequest(BaseModel):
    name:       str
    command:    str
    host_ids:   list[str] = []     # CMDB 主机 ID 列表
    host_group: str = ""           # 分组 ID（和 host_ids 二选一）
    timeout:    int = 60


@router.get("/tasks")
async def list_tasks(limit: int = 100):
    tasks = _load_tasks()
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    # 不返回 host_results 大字段
    lite = []
    for t in tasks[:limit]:
        item = {k: v for k, v in t.items() if k != "host_results"}
        lite.append(item)
    return lite


@router.post("/tasks")
async def run_task(body: RunTaskRequest):
    """立即执行一次任务（手动触发）。"""
    from state import load_hosts_list
    all_hosts = load_hosts_list()

    if body.host_group:
        hosts = [h for h in all_hosts if h.get("group") == body.host_group]
    elif body.host_ids:
        hosts = [h for h in all_hosts if h.get("id") in body.host_ids]
    else:
        raise HTTPException(status_code=400, detail="请指定 host_ids 或 host_group")

    if not hosts:
        raise HTTPException(status_code=400, detail="目标主机列表为空，请检查 host_ids/host_group 配置及 SSH 凭证")

    task_id = str(uuid.uuid4())[:8]
    task = {
        "id":          task_id,
        "name":        body.name,
        "command":     body.command,
        "status":      "pending",
        "created_at":  _NOW(),
        "started_at":  None,
        "finished_at": None,
        "summary":     "",
        "target_count": len(hosts),
        "host_results": [],
    }
    tasks = _load_tasks()
    tasks.insert(0, task)
    _save_tasks(tasks)

    asyncio.create_task(_execute_task(task_id, hosts, body.command, body.timeout))
    return task


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    tasks = _load_tasks()
    new_tasks = [t for t in tasks if t["id"] != task_id]
    if len(new_tasks) == len(tasks):
        raise HTTPException(status_code=404, detail="任务不存在")
    _save_tasks(new_tasks)
    return {"ok": True}


# ── 计划任务 (Cron) ────────────────────────────────────────────────────────────

class CronJobCreate(BaseModel):
    name:        str
    command:     str
    cron:        str = "0 9 * * *"
    host_ids:    list[str] = []
    host_group:  str = ""
    timeout:     int = 60
    enabled:     bool = True
    description: str = ""


@router.get("/crons")
async def list_crons():
    return _load_crons()


@router.post("/crons")
async def create_cron(body: CronJobCreate):
    crons = _load_crons()
    now = _NOW()
    cron = {
        "id":          str(uuid.uuid4())[:8],
        "name":        body.name,
        "command":     body.command,
        "cron":        body.cron,
        "host_ids":    body.host_ids,
        "host_group":  body.host_group,
        "timeout":     body.timeout,
        "enabled":     body.enabled,
        "description": body.description,
        "created_at":  now,
        "last_run":    None,
        "last_status": None,
    }
    crons.append(cron)
    _save_crons(crons)
    return cron


@router.put("/crons/{cron_id}")
async def update_cron(cron_id: str, body: CronJobCreate):
    crons = _load_crons()
    idx = next((i for i, c in enumerate(crons) if c["id"] == cron_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="计划任务不存在")
    crons[idx].update({
        "name":        body.name,
        "command":     body.command,
        "cron":        body.cron,
        "host_ids":    body.host_ids,
        "host_group":  body.host_group,
        "timeout":     body.timeout,
        "enabled":     body.enabled,
        "description": body.description,
    })
    _save_crons(crons)
    return crons[idx]


@router.delete("/crons/{cron_id}")
async def delete_cron(cron_id: str):
    crons = _load_crons()
    new = [c for c in crons if c["id"] != cron_id]
    if len(new) == len(crons):
        raise HTTPException(status_code=404, detail="计划任务不存在")
    _save_crons(new)
    return {"ok": True}


@router.post("/crons/{cron_id}/run")
async def run_cron_now(cron_id: str):
    """立即触发一次计划任务。"""
    crons = _load_crons()
    cron = next((c for c in crons if c["id"] == cron_id), None)
    if not cron:
        raise HTTPException(status_code=404, detail="计划任务不存在")

    from state import load_hosts_list
    all_hosts = load_hosts_list()

    if cron.get("host_group"):
        hosts = [h for h in all_hosts if h.get("group") == cron["host_group"]]
    elif cron.get("host_ids"):
        hosts = [h for h in all_hosts if h.get("id") in cron["host_ids"]]
    else:
        hosts = []

    if not hosts:
        raise HTTPException(status_code=400, detail="没有可执行的目标主机，请检查主机配置和 SSH 凭证")

    task_id = str(uuid.uuid4())[:8]
    task = {
        "id":           task_id,
        "name":         f"[定时] {cron['name']}",
        "command":      cron["command"],
        "status":       "pending",
        "created_at":   _NOW(),
        "started_at":   None,
        "finished_at":  None,
        "summary":      "",
        "target_count": len(hosts),
        "host_results": [],
        "cron_id":      cron_id,
    }
    tasks = _load_tasks()
    tasks.insert(0, task)
    _save_tasks(tasks)

    asyncio.create_task(_execute_task(task_id, hosts, cron["command"], cron.get("timeout", 60), cron_id))
    return {"ok": True, "task_id": task_id}


async def execute_scheduled_cron(cron_id: str) -> None:
    """由 APScheduler 调用的定时任务执行函数。"""
    crons = _load_crons()
    cron = next((c for c in crons if c["id"] == cron_id and c.get("enabled")), None)
    if not cron:
        return
    try:
        from state import load_hosts_list
        all_hosts = load_hosts_list()
        if cron.get("host_group"):
            hosts = [h for h in all_hosts if h.get("group") == cron["host_group"]]
        else:
            hosts = [h for h in all_hosts if h.get("id") in (cron.get("host_ids") or [])]
        if not hosts:
            logger.warning("[cron] 计划任务 %s 无可执行主机", cron["name"])
            return
        task_id = str(uuid.uuid4())[:8]
        task = {
            "id":           task_id,
            "name":         f"[定时] {cron['name']}",
            "command":      cron["command"],
            "status":       "pending",
            "created_at":   _NOW(),
            "started_at":   None,
            "finished_at":  None,
            "summary":      "",
            "target_count": len(hosts),
            "host_results": [],
            "cron_id":      cron_id,
        }
        tasks = _load_tasks()
        tasks.insert(0, task)
        # 只保留最近 500 条历史
        _save_tasks(tasks[:500])
        await _execute_task(task_id, hosts, cron["command"], cron.get("timeout", 60), cron_id)
        logger.info("[cron] 计划任务 %s 执行完成", cron["name"])
    except Exception as e:
        logger.error("[cron] 计划任务 %s 执行异常: %s", cron_id, e)


# ── 兼容旧接口 ──────────────────────────────────────────────────────────────────

@router.get("/playbooks")
async def list_playbooks():
    """兼容旧接口，不再扫描文件系统，直接返回空列表。"""
    return []
