"""CMDB 服务器场景工具：主机查找 + 一键健康诊断 + Java 进程诊断。"""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from ._shared import _allowed_groups, _filter_hosts_by_groups


def _match_hosts(query: str, hosts: list[dict]) -> list[dict]:
    q = str(query or "").strip().lower()
    if not q:
        return hosts
    return [
        h for h in hosts
        if q in str(h.get("ip", "")).lower()
        or q in str(h.get("hostname", "")).lower()
        or q in str(h.get("group", "")).lower()
        or q in str(h.get("env", "")).lower()
    ]


@tool
async def find_cmdb_host(query: str = "", config: RunnableConfig = None) -> str:
    """按 IP / 主机名 / 分组 / 环境查找 CMDB 主机，返回基本信息、SSH 凭证状态
    与最近一次指标概况。用户提到某台服务器（如 "node01"、"192.168.9.222"）时先用本工具定位。"""
    try:
        from state import load_hosts_list

        hosts = _filter_hosts_by_groups(load_hosts_list(), _allowed_groups(config))
        matched = _match_hosts(query, hosts)[:10]
        if not matched:
            return f"CMDB 中未找到匹配「{query}」的主机（共 {len(hosts)} 台可见）"

        lines = [f"**CMDB 主机（匹配 {len(matched)} 台）**"]
        for h in matched:
            cred = "有凭证" if (h.get("credential_id") or h.get("ssh_password")) else "无SSH凭证"
            metrics = []
            if h.get("cpu_usage_pct") is not None:
                metrics.append(f"CPU {h['cpu_usage_pct']}%")
            if h.get("memory_usage_pct") is not None:
                metrics.append(f"内存 {h['memory_usage_pct']}%")
            if h.get("load5") is not None:
                metrics.append(f"load5 {h['load5']}")
            lines.append(
                f"- {h.get('hostname', '-')}（{h.get('ip', '-')}）"
                f" 分组={h.get('group') or '-'} 环境={h.get('env') or '-'}"
                f" 状态={h.get('status', '-')} [{cred}]"
                + (f" 指标：{' / '.join(metrics)}" if metrics else " 指标：未采集")
                + (f" 同步于 {str(h.get('metrics_updated_at', ''))[:16]}" if h.get("metrics_updated_at") else "")
            )
        return "\n".join(lines)
    except Exception as e:
        return f"CMDB 查询失败：{e}"


@tool
async def diagnose_cmdb_host(host: str, config: RunnableConfig = None) -> str:
    """一键诊断指定服务器：Prometheus 指标证据包（CPU/内存/磁盘/负载，
    含基线与趋势）+ SSH 实时快照（top 进程 / 磁盘 / 最近内核错误）。
    用户说某台服务器慢、负载高、磁盘满、疑似异常时优先使用。host 传 IP 或主机名。"""
    try:
        from state import load_hosts_list
        from services.evidence import build_metric_evidence, evidence_to_text

        hosts = _filter_hosts_by_groups(load_hosts_list(), _allowed_groups(config))
        matched = _match_hosts(host, hosts)
        if not matched:
            return f"CMDB 中未找到主机「{host}」"
        target = matched[0]
        ip = target.get("ip", "")
        sections = [f"**主机诊断 / {target.get('hostname', ip)}（{ip}）**"]

        # 1. 指标证据包（受预算约束的模板化查询）
        try:
            pack = await build_metric_evidence(
                instance=ip, hostname=target.get("hostname"), window_minutes=60)
            sections.append(evidence_to_text(pack) or "指标证据：无数据")
        except Exception as exc:
            sections.append(f"指标证据采集失败：{exc}")

        # 2. SSH 实时快照（有凭证才执行；只读命令）
        if target.get("credential_id") or target.get("ssh_password"):
            try:
                from .ssh import execute_ssh_command

                snapshot = await execute_ssh_command.ainvoke(
                    {
                        "host": ip,
                        "command": (
                            "echo '=== TOP CPU 进程 ==='; ps aux --sort=-%cpu | head -6; "
                            "echo '=== TOP 内存进程 ==='; ps aux --sort=-%mem | head -4; "
                            "echo '=== 磁盘 ==='; df -h | awk 'NR==1 || $5+0 > 60'; "
                            "echo '=== 最近内核错误 ==='; dmesg -T 2>/dev/null | tail -5 || true"
                        ),
                    },
                    config=config,
                )
                sections.append("**SSH 实时快照：**\n" + str(snapshot)[:2000])
            except Exception as exc:
                sections.append(f"SSH 快照失败：{exc}")
        else:
            sections.append("该主机未配置 SSH 凭证，跳过实时快照（仅指标证据）。")

        return "\n\n".join(sections)
    except Exception as e:
        return f"主机诊断失败：{e}"


# SSH 发现 Java 进程（按内存占用倒序，取最高一个）
_JAVA_PS_CMD = (
    "ps -eo pid,rss,args --sort=-rss 2>/dev/null "
    "| grep -w java | grep -v grep | head -8"
)

# 对外语义化 preset → 平台 Arthas preset（routers.hosts._ARTHAS_PRESETS）
_PRESET_MAP = {
    "thread_busy": "thread_top",
    "thread_blocked": "thread_blocked",
    "deadlock": "thread_blocked",
    "jvm": "jvm",
    "memory": "memory",
    "dashboard": "dashboard",
}


@tool
async def run_java_diagnostics(host: str, preset: str = "thread_busy",
                               config: RunnableConfig = None) -> str:
    """对指定服务器上的 Java 进程执行 Arthas 诊断并返回原始输出供分析。
    自动通过 SSH 发现 Java 进程 PID（取内存占用最高的一个）再采样。
    preset 可选：thread_busy（最忙线程栈，默认）/ thread_blocked（阻塞/死锁）/
    jvm（JVM 概览）/ memory（内存与GC）/ dashboard（总览）。
    用户反馈 Java 应用 CPU 高、卡顿、疑似死锁、内存泄漏时使用。"""
    try:
        from state import load_hosts_list
        from routers.hosts import run_java_arthas, JavaArthasRequest
        from .ssh import execute_ssh_command

        hosts = _filter_hosts_by_groups(load_hosts_list(), _allowed_groups(config))
        matched = _match_hosts(host, hosts)
        if not matched:
            return f"CMDB 中未找到主机「{host}」"
        target = matched[0]
        ip = target.get("ip", "")

        if not (target.get("credential_id") or target.get("ssh_password")):
            return f"主机 {ip} 未配置 SSH 凭证，无法执行 Java 诊断。"

        # 1. 发现 Java 进程
        ps_out = await execute_ssh_command.ainvoke(
            {"host": ip, "command": _JAVA_PS_CMD}, config=config)
        ps_text = str(ps_out or "")
        procs: list[tuple[int, str]] = []
        for line in ps_text.splitlines():
            parts = line.split(None, 2)
            if len(parts) >= 2 and parts[0].isdigit():
                procs.append((int(parts[0]), parts[2] if len(parts) > 2 else ""))
        if not procs:
            return f"主机 {ip} 上未发现运行中的 Java 进程。\nps 输出：\n{ps_text[:600]}"

        pid, cmdline = procs[0]
        preset_key = _PRESET_MAP.get(preset, "thread_top")

        # 2. 对内存占用最高的 Java 进程执行 Arthas
        result = await run_java_arthas(
            target.get("id", ""),
            JavaArthasRequest(pid=pid, preset=preset_key),
        )
        output = result.get("output") if isinstance(result, dict) else str(result)
        ok = result.get("ok", True) if isinstance(result, dict) else True

        head = (f"**Java 诊断 / {target.get('hostname', ip)}（PID={pid}，"
                f"preset={preset}，{'成功' if ok else '失败'}）**\n"
                f"进程：{cmdline[:120]}")
        if len(procs) > 1:
            head += f"\n（另有 {len(procs) - 1} 个 Java 进程，本次诊断内存占用最高的 PID={pid}）"
        return head + "\n```\n" + str(output or "无输出")[-3500:] + "\n```" + \
            "\n请基于以上 Arthas 输出总结：忙碌线程与热点方法、是否存在死锁/长等待、" \
            "内存与 GC 状况，并给出优化建议。"
    except Exception as e:
        return f"Java 诊断失败：{e}（请确认目标主机已配置 SSH 凭证且运行着 Java 进程）"


__all__ = ["find_cmdb_host", "diagnose_cmdb_host", "run_java_diagnostics"]
