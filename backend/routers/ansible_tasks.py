"""任务中心 — 双引擎执行：Ansible（控制节点）/ SSH 直连。

执行引擎：
  ansible  — SSH 到控制节点执行 ansible ad-hoc / ansible-playbook（services.ansible_runner）
  ssh      — asyncssh 直连逐台执行（无 ansible 依赖的回退方式）

端点：
  GET  /api/ansible/tasks           — 任务执行历史列表
  POST /api/ansible/tasks           — 手动触发即时任务（engine 可选 ansible/ssh）
  GET  /api/ansible/tasks/{id}      — 任务详情+输出
  DELETE /api/ansible/tasks/{id}    — 删除历史记录
  GET  /api/ansible/crons           — 计划任务列表
  POST /api/ansible/crons           — 创建计划任务
  PUT  /api/ansible/crons/{id}      — 更新计划任务
  DELETE /api/ansible/crons/{id}    — 删除计划任务
  POST /api/ansible/crons/{id}/run  — 立即触发计划任务
  GET/POST/PUT/DELETE /api/ansible/playbooks — Playbook 管理
  POST /api/ansible/playbooks/{id}/run       — 执行 Playbook
  GET/PUT /api/ansible/config       — Ansible 控制节点配置
  POST /api/ansible/config/check    — 检测控制节点可用性
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from json_snapshot_store import read_json_file, write_json_file
from auth.deps import require_admin
from ssh_utils import ssh_connect_options

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ansible", tags=["ansible"], dependencies=[Depends(require_admin)])

_DATA_DIR   = Path(__file__).parent.parent / "data"
_TASKS_FILE = _DATA_DIR / "ansible_tasks.json"
_CRONS_FILE = _DATA_DIR / "ansible_crons.json"
_PLAYBOOKS_FILE = _DATA_DIR / "ansible_playbooks.json"

TaskStatus = Literal["pending", "running", "success", "failed", "cancelled"]

_NOW = lambda: datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

# ── 持久化 ─────────────────────────────────────────────────────────────────────

def _load_tasks() -> list[dict]:
    data = read_json_file(_TASKS_FILE, default=[])
    return data if isinstance(data, list) else []

def _save_tasks(tasks: list[dict]) -> None:
    write_json_file(_TASKS_FILE, tasks, ensure_parent=True)

def _load_crons() -> list[dict]:
    data = read_json_file(_CRONS_FILE, default=[])
    return data if isinstance(data, list) else []

def _save_crons(crons: list[dict]) -> None:
    write_json_file(_CRONS_FILE, crons, ensure_parent=True)


_PLAYBOOK_SEEDS = [
    {
        "id": "pb_inspect",
        "name": "系统巡检",
        "description": "采集磁盘/内存/负载/系统信息，汇总输出",
        "yaml": """---
- name: 系统巡检
  hosts: all
  gather_facts: yes
  tasks:
    - name: 磁盘使用
      shell: df -h --output=target,pcent | tail -n +2 | sort -k2 -hr | head -10
      register: disk
      changed_when: false
    - name: 内存与负载
      shell: free -m | awk 'NR==2{printf "内存 %s/%sMB (%.0f%%)", $3, $2, $3/$2*100}'; echo " | 负载 $(cat /proc/loadavg | cut -d' ' -f1-3)"
      register: memload
      changed_when: false
    - name: 巡检结果
      debug:
        msg: "{{ ansible_hostname }} ({{ ansible_default_ipv4.address | default('?') }}) 内核 {{ ansible_kernel }} 运行 {{ (ansible_uptime_seconds / 86400) | round(1) }} 天 | {{ memload.stdout }} | 磁盘: {{ disk.stdout_lines | join(' / ') }}"
""",
    },
    {
        "id": "pb_log_clean",
        "name": "日志清理",
        "description": "清理 N 天前的轮转日志与 journal（默认 7 天，变量 keep_days）",
        "yaml": """---
- name: 日志清理
  hosts: all
  become: yes
  vars:
    keep_days: 7
  tasks:
    - name: 清理轮转日志
      shell: find /var/log -type f \\( -name "*.gz" -o -name "*.log.[0-9]*" -o -name "*.old" \\) -mtime +{{ keep_days }} -delete -print | head -50
      register: cleaned
      changed_when: cleaned.stdout != ""
    - name: 收缩 journal
      shell: command -v journalctl >/dev/null && journalctl --vacuum-time={{ keep_days }}d 2>&1 | tail -1 || echo "no journalctl"
      register: journal
      changed_when: false
    - name: 清理结果
      debug:
        msg: "已删除 {{ cleaned.stdout_lines | length }} 个文件 | {{ journal.stdout }}"
""",
    },
    {
        "id": "pb_service",
        "name": "服务管理",
        "description": "重启指定 systemd 服务并确认状态（变量 service_name 必填）",
        "yaml": """---
- name: 服务管理
  hosts: all
  become: yes
  vars:
    service_name: ""
    service_state: restarted
  tasks:
    - name: 校验变量
      fail:
        msg: "请通过 extra_vars 传入 service_name"
      when: service_name == ""
    - name: "{{ service_state }} {{ service_name }}"
      systemd:
        name: "{{ service_name }}"
        state: "{{ service_state }}"
    - name: 确认状态
      shell: systemctl is-active {{ service_name }} && systemctl status {{ service_name }} --no-pager -l | head -5
      register: status
      changed_when: false
    - name: 服务状态
      debug:
        msg: "{{ status.stdout_lines }}"
""",
    },
    {
        "id": "pb_package",
        "name": "软件包安装",
        "description": "跨发行版安装软件包（变量 package_name 必填）",
        "yaml": """---
- name: 软件包安装
  hosts: all
  become: yes
  vars:
    package_name: ""
  tasks:
    - name: 校验变量
      fail:
        msg: "请通过 extra_vars 传入 package_name"
      when: package_name == ""
    - name: 安装 {{ package_name }}
      package:
        name: "{{ package_name }}"
        state: present
""",
    },
]


def _load_playbooks() -> list[dict]:
    data = read_json_file(_PLAYBOOKS_FILE, default=None)
    if not isinstance(data, list):
        now = _NOW()
        data = [{**seed, "builtin": True, "created_at": now, "updated_at": now}
                for seed in _PLAYBOOK_SEEDS]
        write_json_file(_PLAYBOOKS_FILE, data, ensure_parent=True)
    return data


def _save_playbooks(playbooks: list[dict]) -> None:
    write_json_file(_PLAYBOOKS_FILE, playbooks, ensure_parent=True)

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
            **ssh_connect_options(
                host=ip,
                port=port,
                username=username,
                password=password,
                connect_timeout=10,
            )
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


async def _run_via_ssh(hosts: list[dict], command: str, timeout: int) -> tuple[list[dict], str]:
    """SSH 直连引擎：逐台并发执行，返回 (host_results, raw_output)。"""
    results = await asyncio.gather(
        *[_ssh_exec_host(h, command, timeout) for h in hosts],
        return_exceptions=True,
    )
    host_results = []
    for r in results:
        if isinstance(r, Exception):
            host_results.append({"error": str(r), "rc": -1, "stdout": "", "stderr": ""})
        else:
            host_results.append(r)
    return host_results, ""


async def _run_via_ansible(hosts: list[dict], command: str, timeout: int,
                           playbook_yaml: str = "", extra_vars: dict | None = None) -> tuple[list[dict], str]:
    """Ansible 引擎：控制节点执行 ad-hoc 或 playbook，返回 (host_results, raw_output)。"""
    from services import ansible_runner

    if playbook_yaml:
        result = await ansible_runner.run_playbook(
            hosts, playbook_yaml, extra_vars=extra_vars, timeout=timeout)
    else:
        result = await ansible_runner.run_adhoc(hosts, command, timeout=timeout)

    host_results = [{
        "ip":       item.get("ip", ""),
        "hostname": item.get("hostname") or item.get("host", ""),
        "rc":       item.get("rc", -1),
        "stdout":   item.get("stdout", ""),
        "stderr":   "",
        "error":    item.get("error", ""),
    } for item in result.get("per_host", [])]

    # ansible 整体失败（如控制节点/语法错误）但没有 per_host 结果时兜底
    if not host_results and result.get("rc", 1) != 0:
        raise RuntimeError((result.get("output") or "ansible 执行失败")[-2000:])
    return host_results, result.get("output", "")


async def _execute_task(task_id: str, hosts: list[dict], command: str,
                        timeout: int = 60, cron_id: str = "",
                        engine: str = "ssh", playbook_yaml: str = "",
                        extra_vars: dict | None = None) -> None:
    """按 engine 执行到所有目标主机，写入任务历史。"""
    tasks = _load_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return

    task["status"] = "running"
    task["started_at"] = _NOW()
    _save_tasks(tasks)

    try:
        if engine == "ansible":
            host_results, raw_output = await _run_via_ansible(
                hosts, command, timeout, playbook_yaml, extra_vars)
        else:
            host_results, raw_output = await _run_via_ssh(hosts, command, timeout)

        success_count = sum(1 for r in host_results if r.get("rc") == 0)
        fail_count = len(host_results) - success_count

        task["status"] = "success" if fail_count == 0 else ("failed" if success_count == 0 else "partial")
        task["finished_at"] = _NOW()
        task["host_results"] = host_results
        task["raw_output"] = raw_output[-20000:] if raw_output else ""
        task["summary"] = f"成功 {success_count} 台，失败 {fail_count} 台"

    except Exception as e:
        task["status"] = "failed"
        task["finished_at"] = _NOW()
        task["summary"] = str(e)[:500]

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
    engine:     Literal["ssh", "ansible"] = "ssh"


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
        "engine":      body.engine,
        "type":        "adhoc",
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

    asyncio.create_task(_execute_task(task_id, hosts, body.command, body.timeout, engine=body.engine))
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
    engine:      Literal["ssh", "ansible"] = "ssh"


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
        "engine":      body.engine,
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
        "engine":      body.engine,
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
        "engine":       cron.get("engine", "ssh"),
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

    asyncio.create_task(_execute_task(
        task_id, hosts, cron["command"], cron.get("timeout", 60), cron_id,
        engine=cron.get("engine", "ssh"),
    ))
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
            "engine":       cron.get("engine", "ssh"),
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
        await _execute_task(
            task_id, hosts, cron["command"], cron.get("timeout", 60), cron_id,
            engine=cron.get("engine", "ssh"),
        )
        logger.info("[cron] 计划任务 %s 执行完成", cron["name"])
    except Exception as e:
        logger.error("[cron] 计划任务 %s 执行异常: %s", cron_id, e)


# ── Playbook 管理 ───────────────────────────────────────────────────────────────

class PlaybookPayload(BaseModel):
    name:        str
    description: str = ""
    yaml:        str


class PlaybookRunRequest(BaseModel):
    host_ids:   list[str] = []
    host_group: str = ""
    extra_vars: dict = {}
    timeout:    int = 600


def _resolve_target_hosts(host_ids: list[str], host_group: str) -> list[dict]:
    from state import load_hosts_list
    all_hosts = load_hosts_list()
    if host_group:
        hosts = [h for h in all_hosts if h.get("group") == host_group]
    elif host_ids:
        hosts = [h for h in all_hosts if h.get("id") in host_ids]
    else:
        hosts = []
    if not hosts:
        raise HTTPException(status_code=400, detail="目标主机列表为空，请指定 host_ids 或 host_group")
    return hosts


@router.get("/playbooks")
async def list_playbooks():
    return _load_playbooks()


@router.post("/playbooks")
async def create_playbook(body: PlaybookPayload):
    playbooks = _load_playbooks()
    now = _NOW()
    playbook = {
        "id":          f"pb_{uuid.uuid4().hex[:8]}",
        "name":        body.name.strip(),
        "description": body.description.strip(),
        "yaml":        body.yaml,
        "builtin":     False,
        "created_at":  now,
        "updated_at":  now,
    }
    playbooks.append(playbook)
    _save_playbooks(playbooks)
    return playbook


@router.put("/playbooks/{playbook_id}")
async def update_playbook(playbook_id: str, body: PlaybookPayload):
    playbooks = _load_playbooks()
    playbook = next((p for p in playbooks if p["id"] == playbook_id), None)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook 不存在")
    playbook.update({
        "name":        body.name.strip(),
        "description": body.description.strip(),
        "yaml":        body.yaml,
        "updated_at":  _NOW(),
    })
    _save_playbooks(playbooks)
    return playbook


@router.delete("/playbooks/{playbook_id}")
async def delete_playbook(playbook_id: str):
    playbooks = _load_playbooks()
    target = next((p for p in playbooks if p["id"] == playbook_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Playbook 不存在")
    _save_playbooks([p for p in playbooks if p["id"] != playbook_id])
    return {"ok": True}


@router.post("/playbooks/{playbook_id}/run")
async def run_playbook_task(playbook_id: str, body: PlaybookRunRequest):
    playbook = next((p for p in _load_playbooks() if p["id"] == playbook_id), None)
    if not playbook:
        raise HTTPException(status_code=404, detail="Playbook 不存在")
    hosts = _resolve_target_hosts(body.host_ids, body.host_group)

    task_id = str(uuid.uuid4())[:8]
    task = {
        "id":          task_id,
        "name":        f"[Playbook] {playbook['name']}",
        "command":     f"ansible-playbook {playbook['name']}",
        "engine":      "ansible",
        "type":        "playbook",
        "playbook_id": playbook_id,
        "extra_vars":  body.extra_vars,
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

    asyncio.create_task(_execute_task(
        task_id, hosts, "", body.timeout,
        engine="ansible", playbook_yaml=playbook["yaml"], extra_vars=body.extra_vars,
    ))
    return task


# ── Ansible 控制节点配置 ────────────────────────────────────────────────────────

class AnsibleConfigPayload(BaseModel):
    control_host_id: str = ""
    workdir:         str = "/tmp/aiops-ansible"
    forks:           int = 5


@router.get("/config")
async def get_ansible_config():
    from services import ansible_runner
    config = ansible_runner.load_config()
    try:
        control = ansible_runner.get_control_host()
        config["control_host"] = {
            "id": control.get("id"),
            "ip": control.get("ip"),
            "hostname": control.get("hostname"),
        }
    except Exception as exc:
        config["control_host"] = None
        config["control_error"] = str(exc)
    return config


@router.put("/config")
async def update_ansible_config(body: AnsibleConfigPayload):
    from services import ansible_runner
    return ansible_runner.save_config(body.model_dump())


@router.post("/config/check")
async def check_ansible_config():
    from services import ansible_runner
    try:
        control = ansible_runner.get_control_host()
    except Exception as exc:
        return {"ok": False, "hint": str(exc), "ansible_version": "", "sshpass": False}
    return await ansible_runner.check_control_node(control)
