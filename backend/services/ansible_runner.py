"""Ansible 控制节点执行引擎。

后端进程（Windows/容器）不直接运行 ansible，而是 SSH 到一台 CMDB Linux 主机
（控制节点，需已安装 ansible + sshpass）执行 ansible / ansible-playbook：

  1. 在控制节点创建临时目录（chmod 700）
  2. 上传自动生成的 inventory（含 CMDB 主机凭证）与 playbook YAML
  3. 执行并采集完整输出，解析 PLAY RECAP / ad-hoc 块得到每主机结果
  4. 无论成败立即删除临时目录（inventory 含明文密码，不留盘）

配置存 data/ansible_config.json：{control_host_id, workdir, forks}
"""
from __future__ import annotations

import json
import logging
import re
import shlex
import uuid
from pathlib import Path

from json_snapshot_store import read_json_file, write_json_file

logger = logging.getLogger(__name__)

_CONFIG_FILE = Path(__file__).resolve().parent.parent / "data" / "ansible_config.json"
_DEFAULT_WORKDIR = "/tmp/aiops-ansible"


def load_config() -> dict:
    data = read_json_file(_CONFIG_FILE, default={})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("control_host_id", "")
    data.setdefault("workdir", _DEFAULT_WORKDIR)
    data.setdefault("forks", 5)
    return data


def save_config(config: dict) -> dict:
    data = load_config()
    data.update({
        "control_host_id": str(config.get("control_host_id") or ""),
        "workdir": str(config.get("workdir") or _DEFAULT_WORKDIR).rstrip("/") or _DEFAULT_WORKDIR,
        "forks": max(1, min(int(config.get("forks") or 5), 50)),
    })
    write_json_file(_CONFIG_FILE, data, ensure_parent=True)
    return data


def resolve_ssh_auth(host: dict) -> tuple[str, str | None, int]:
    """返回 (username, password, port)。凭证优先级：credential_id > 主机自身密码。"""
    from state import decrypt_password, load_credentials

    port = int(host.get("ssh_port") or 22)
    username = host.get("ssh_user") or "root"
    password = None

    cred_id = host.get("credential_id", "")
    if cred_id:
        cred = next((c for c in load_credentials() if c.get("id") == cred_id), None)
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
    return username, password, port


def get_control_host() -> dict:
    """解析控制节点主机记录。未配置时自动选第一台可解析出密码的主机。"""
    from state import load_hosts_list

    hosts = load_hosts_list()
    config = load_config()
    if config.get("control_host_id"):
        host = next((h for h in hosts if h.get("id") == config["control_host_id"]), None)
        if host:
            return host
    for host in hosts:
        _, password, _ = resolve_ssh_auth(host)
        if password:
            return host
    raise RuntimeError("没有可用的 Ansible 控制节点：请在 CMDB 配置主机 SSH 凭证")


_INV_HOSTNAME_RE = re.compile(r"[^a-zA-Z0-9_.-]")


def _inv_name(host: dict) -> str:
    name = str(host.get("hostname") or host.get("ip") or "host")
    return _INV_HOSTNAME_RE.sub("-", name)


def assign_inventory_names(hosts: list[dict]) -> list[tuple[str, dict]]:
    """为每台主机分配 inventory 名（重名追加 ip 后缀）。inventory 与结果映射共用。"""
    assigned: list[tuple[str, dict]] = []
    seen_names: set[str] = set()
    for host in hosts:
        ip = str(host.get("ip") or "").strip()
        if not ip:
            continue
        name = _inv_name(host)
        if name in seen_names:
            name = f"{name}-{ip.replace('.', '-')}"
        seen_names.add(name)
        assigned.append((name, host))
    return assigned


def build_inventory(hosts: list[dict]) -> str:
    """从 CMDB 主机生成 INI inventory（按 group 分组，密码走 ansible_ssh_pass/sshpass）。"""
    groups: dict[str, list[str]] = {}
    for name, host in assign_inventory_names(hosts):
        ip = str(host.get("ip") or "").strip()
        username, password, port = resolve_ssh_auth(host)
        parts = [
            name,
            f"ansible_host={ip}",
            f"ansible_port={port}",
            f"ansible_user={username}",
        ]
        if password:
            parts.append(f"ansible_ssh_pass={shlex.quote(password)}")
            parts.append(f"ansible_become_pass={shlex.quote(password)}")
        group = _INV_HOSTNAME_RE.sub("-", str(host.get("group") or "aiops")) or "aiops"
        groups.setdefault(group, []).append(" ".join(parts))

    lines: list[str] = []
    for group, entries in groups.items():
        lines.append(f"[{group}]")
        lines.extend(entries)
        lines.append("")
    lines += [
        "[all:vars]",
        "ansible_connection=ssh",
        "ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'",
        "ansible_python_interpreter=auto_silent",
        "",
    ]
    return "\n".join(lines)


async def _open_control(control_host: dict):
    import asyncssh
    from ssh_utils import ssh_connect_options

    username, password, port = resolve_ssh_auth(control_host)
    if not password:
        raise RuntimeError(f"控制节点 {control_host.get('ip')} 未配置 SSH 密码")
    return asyncssh.connect(**ssh_connect_options(
        host=control_host.get("ip", ""),
        port=port,
        username=username,
        password=password,
        connect_timeout=10,
    ))


async def check_control_node(control_host: dict) -> dict:
    """检测控制节点 ansible/sshpass 可用性。"""
    try:
        async with await _open_control(control_host) as conn:
            result = await conn.run(
                "ansible --version 2>/dev/null | head -1; "
                "command -v sshpass >/dev/null 2>&1 && echo sshpass-ok || echo sshpass-missing",
                timeout=20,
            )
            out = (result.stdout or "").strip().splitlines()
            version = out[0] if out and "ansible" in out[0] else ""
            sshpass_ok = any("sshpass-ok" in line for line in out)
            return {
                "ok": bool(version) and sshpass_ok,
                "host": control_host.get("hostname") or control_host.get("ip"),
                "ip": control_host.get("ip"),
                "ansible_version": version or "未安装",
                "sshpass": sshpass_ok,
                "hint": "" if (version and sshpass_ok) else
                        "控制节点需安装 ansible 与 sshpass：apt install ansible sshpass / yum install ansible sshpass",
            }
    except Exception as exc:
        return {
            "ok": False,
            "host": control_host.get("hostname") or control_host.get("ip"),
            "ip": control_host.get("ip"),
            "ansible_version": "",
            "sshpass": False,
            "hint": f"连接控制节点失败: {exc}",
        }


# ── 输出解析 ───────────────────────────────────────────────────────────────

_RECAP_LINE_RE = re.compile(
    r"^(\S+)\s*:\s*ok=(\d+)\s+changed=(\d+)\s+unreachable=(\d+)\s+failed=(\d+)"
    r"(?:\s+skipped=(\d+))?(?:\s+rescued=(\d+))?(?:\s+ignored=(\d+))?",
    re.MULTILINE,
)
_ADHOC_HEAD_RE = re.compile(r"^(\S+) \| (\w+!?)(?: =>)?(?: \| rc=(-?\d+) >>)?\s*$")


def parse_recap(output: str) -> dict[str, dict]:
    """解析 PLAY RECAP 段落 → {host: {ok, changed, unreachable, failed, ...}}。"""
    recap: dict[str, dict] = {}
    section = output.split("PLAY RECAP", 1)
    text = section[1] if len(section) > 1 else output
    for m in _RECAP_LINE_RE.finditer(text):
        recap[m.group(1)] = {
            "ok": int(m.group(2)),
            "changed": int(m.group(3)),
            "unreachable": int(m.group(4)),
            "failed": int(m.group(5)),
            "skipped": int(m.group(6) or 0),
        }
    return recap


def parse_adhoc_output(output: str) -> list[dict]:
    """解析 ad-hoc 模式输出块：`host | CHANGED | rc=0 >>` + 后续行为该主机 stdout。"""
    results: list[dict] = []
    current: dict | None = None
    buf: list[str] = []

    def _flush():
        if current is not None:
            current["stdout"] = "\n".join(buf).strip()
            results.append(current)

    for line in output.splitlines():
        m = _ADHOC_HEAD_RE.match(line.strip())
        if m:
            _flush()
            status = m.group(2)
            rc = int(m.group(3)) if m.group(3) is not None else (0 if status in ("SUCCESS", "CHANGED") else -1)
            current = {
                "host": m.group(1),
                "status": status.rstrip("!"),
                "rc": rc,
                "error": "" if status in ("SUCCESS", "CHANGED") else status,
            }
            buf = []
        elif current is not None:
            buf.append(line)
    _flush()
    return results


# ── 执行入口 ───────────────────────────────────────────────────────────────

async def _run_on_control(files: dict[str, str], command: str, timeout: int) -> dict:
    """上传 files 到控制节点临时目录并执行 command（cwd=临时目录），最后清理。"""
    control = get_control_host()
    config = load_config()
    run_dir = f"{config['workdir']}/run_{uuid.uuid4().hex[:10]}"

    async with await _open_control(control) as conn:
        await conn.run(f"mkdir -p {shlex.quote(run_dir)} && chmod 700 {shlex.quote(run_dir)}", check=True, timeout=15)
        try:
            for filename, content in files.items():
                target = f"{run_dir}/{filename}"
                await conn.run(f"cat > {shlex.quote(target)} && chmod 600 {shlex.quote(target)}",
                               input=content, check=True, timeout=20)
            result = await conn.run(
                f"cd {shlex.quote(run_dir)} && ANSIBLE_HOST_KEY_CHECKING=False "
                f"ANSIBLE_FORCE_COLOR=0 {command} 2>&1",
                timeout=timeout,
            )
            return {
                "rc": result.exit_status,
                "output": (result.stdout or "").strip(),
                "control_host": control.get("hostname") or control.get("ip"),
            }
        finally:
            try:
                await conn.run(f"rm -rf {shlex.quote(run_dir)}", timeout=15)
            except Exception as exc:
                logger.warning("[ansible] 清理临时目录失败 %s: %s", run_dir, exc)


def _attach_host_info(items: list[dict], hosts: list[dict]) -> None:
    """把 inventory 名映射回 CMDB 主机的 ip/hostname。"""
    name_map = {name: host for name, host in assign_inventory_names(hosts)}
    for item in items:
        host = name_map.get(str(item.get("host") or ""))
        if host:
            item["ip"] = host.get("ip", "")
            item["hostname"] = host.get("hostname") or host.get("ip", "")
        else:
            item.setdefault("ip", "")
            item.setdefault("hostname", item.get("host", ""))


async def run_adhoc(hosts: list[dict], command: str, *, become: bool = False, timeout: int = 300) -> dict:
    """ansible ad-hoc（shell 模块）执行命令，返回 {rc, output, per_host, control_host}。"""
    config = load_config()
    inventory = build_inventory(hosts)
    become_flag = "--become " if become else ""
    cmd = (
        f"ansible all -i inventory.ini -m shell -a {shlex.quote(command)} "
        f"{become_flag}--forks {config['forks']}"
    )
    result = await _run_on_control({"inventory.ini": inventory}, cmd, timeout)
    result["per_host"] = parse_adhoc_output(result["output"])
    _attach_host_info(result["per_host"], hosts)
    return result


async def run_playbook(hosts: list[dict], playbook_yaml: str, *,
                       extra_vars: dict | None = None, timeout: int = 600) -> dict:
    """执行 ansible-playbook，返回 {rc, output, recap, per_host, control_host}。"""
    config = load_config()
    inventory = build_inventory(hosts)
    extra = ""
    if extra_vars:
        extra = f"--extra-vars {shlex.quote(json.dumps(extra_vars, ensure_ascii=False))} "
    cmd = (
        f"ansible-playbook -i inventory.ini playbook.yml "
        f"{extra}--forks {config['forks']}"
    )
    result = await _run_on_control(
        {"inventory.ini": inventory, "playbook.yml": playbook_yaml}, cmd, timeout
    )
    recap = parse_recap(result["output"])
    per_host = []
    for name, stats_item in recap.items():
        failed = stats_item["failed"] > 0 or stats_item["unreachable"] > 0
        per_host.append({
            "host": name,
            "rc": 1 if failed else 0,
            "status": "FAILED" if failed else "SUCCESS",
            "error": "" if not failed else
                     ("unreachable" if stats_item["unreachable"] else f"failed={stats_item['failed']}"),
            "stdout": (
                f"ok={stats_item['ok']} changed={stats_item['changed']} "
                f"failed={stats_item['failed']} unreachable={stats_item['unreachable']} "
                f"skipped={stats_item['skipped']}"
            ),
        })
    _attach_host_info(per_host, hosts)
    result["recap"] = recap
    result["per_host"] = per_host
    return result
