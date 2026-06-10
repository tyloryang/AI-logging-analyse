"""SSH 命令执行工具（带白名单 + 黑名单防护）。"""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from ._shared import _allowed_groups, _check_safe, _filter_hosts_by_groups


@tool
async def execute_ssh_command(
    host: str,
    command: str,
    timeout: int = 30,
    config: RunnableConfig = None,
) -> str:
    """通过 SSH 在指定主机上执行命令。
    host=主机 IP 或主机名（必填，从 CMDB 中匹配）。
    command=要执行的 shell 命令（必填）。
    timeout=超时秒数（默认 30）。

    支持的操作：查看系统状态、日志、进程、磁盘、网络等运维命令。
    禁止执行：rm/dd/shutdown/reboot 等高危命令。
    """
    import asyncssh
    from state import load_hosts_list, decrypt_password, load_credentials

    danger = _check_safe(command)
    if danger:
        return f"❌ 命令被拒绝：{danger}"

    hosts = _filter_hosts_by_groups(load_hosts_list(), _allowed_groups(config))
    target = next(
        (h for h in hosts if h.get("ip") == host or h.get("hostname") == host),
        None,
    )
    if not target:
        return f"❌ 主机 '{host}' 不在 CMDB 中，请先录入"

    ip = target["ip"]
    port = int(target.get("ssh_port") or 22)
    username = target.get("ssh_user") or "root"
    password = None

    cred_id = target.get("credential_id", "")
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
        enc = target.get("ssh_password", "")
        if enc:
            try:
                password = decrypt_password(enc)
            except Exception:
                pass

    if not password:
        return f"❌ 主机 {host} 未配置 SSH 密码，无法执行命令"

    try:
        async with asyncssh.connect(
            host=ip, port=port, username=username, password=password,
            known_hosts=None, connect_timeout=10,
        ) as conn:
            result = await conn.run(command, timeout=timeout)
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            exit_code = result.exit_status

        lines = [
            f"**SSH 命令执行结果** — {username}@{ip}:{port}",
            f"**命令**: `{command}`",
            f"**退出码**: {exit_code}",
        ]
        if stdout:
            lines.append(f"**输出**:\n```\n{stdout[:4000]}\n```")
        if stderr:
            lines.append(f"**错误输出**:\n```\n{stderr[:1000]}\n```")
        if exit_code != 0 and not stderr:
            lines.append("⚠️ 命令非零退出")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ SSH 执行失败（{host}）：{e}"


__all__ = ["execute_ssh_command"]
