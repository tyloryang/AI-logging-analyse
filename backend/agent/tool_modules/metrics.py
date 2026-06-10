"""主机指标 / 全量巡检工具。"""
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from state import prom

from ._shared import _allowed_groups, _filter_hosts_by_groups


@tool
async def get_host_metrics(instance: str = "", config: RunnableConfig = None) -> str:
    """获取主机实时性能指标（CPU/内存/磁盘/负载/TCP连接数）。instance=主机IP或实例地址（空=返回全部主机）。"""
    try:
        from state import load_hosts_list

        allowed_groups = _allowed_groups(config)
        cmdb_hosts = _filter_hosts_by_groups(load_hosts_list(), allowed_groups)
        allowed_ips = {host.get("ip", "") for host in cmdb_hosts if host.get("ip")}
        hosts = await prom.discover_hosts()
        metrics = await prom.get_all_host_metrics()
        partitions = await prom.get_all_partitions()
        lines = []
        for h in hosts:
            inst = h.get("instance", "")
            ip = h.get("ip", "")
            if allowed_groups is not None and ip not in allowed_ips:
                continue
            if instance and instance not in inst and instance not in ip:
                continue
            m = metrics.get(inst, {})
            parts = partitions.get(inst, [])
            max_disk = max((p.get("usage_pct", 0) for p in parts), default=None)
            state_label = "在线" if h.get("state") == "up" else "离线"
            hostname = h.get("hostname") or ip or inst
            cpu = f"{m.get('cpu_usage', '-')}%"
            mem = f"{m.get('mem_usage', '-')}%"
            disk = f"{max_disk}%" if max_disk is not None else "-"
            load = m.get("load5", "-")
            tcp = m.get("tcp_estab", "-")
            lines.append(
                f"[{state_label}] {hostname}({ip})  CPU:{cpu} 内存:{mem} 磁盘:{disk} 负载:{load} TCP:{tcp}"
            )
        if not lines:
            return "未找到主机数据"
        return f"主机指标（{len(lines)} 台）：\n" + "\n".join(lines)
    except Exception as e:
        return f"获取主机指标失败：{e}"


@tool
async def inspect_all_hosts(config: RunnableConfig = None) -> str:
    """执行全量主机巡检，检查所有在线主机的 CPU/内存/磁盘/负载是否超过阈值。返回所有异常项和总体状态。"""
    from state import load_hosts_list
    try:
        allowed_groups = _allowed_groups(config)
        cmdb_hosts = _filter_hosts_by_groups(load_hosts_list(), allowed_groups)
        instances = [f"{h['ip']}:9100" for h in cmdb_hosts if h.get("ip")]
        if not instances:
            return "当前用户权限范围内没有可巡检的主机"
        results = await prom.inspect_hosts(instances)
        if not results:
            return "巡检无结果"
        status_label = {"normal": "正常", "warning": "警告", "critical": "严重"}
        normal_count = warning_count = critical_count = 0
        issue_lines = []
        for r in results:
            overall = r.get("overall", "normal")
            if overall == "normal":
                normal_count += 1
            elif overall == "warning":
                warning_count += 1
            else:
                critical_count += 1
            hostname = r.get("hostname") or r.get("instance", "?")
            ip = r.get("ip", "")
            label = status_label.get(overall, overall)
            issues = [c for c in r.get("checks", []) if c.get("status") != "normal"]
            if issues:
                issue_lines.append(f"[{label}] {hostname}({ip})")
                for issue in issues:
                    issue_lines.append(f"  ⚠ {issue.get('item')}: {issue.get('value')}")
        summary = (
            f"巡检完成：{len(results)} 台主机 | "
            f"正常 {normal_count} | 警告 {warning_count} | 严重 {critical_count}"
        )
        if issue_lines:
            return summary + "\n\n异常详情：\n" + "\n".join(issue_lines)
        return summary + "\n\n所有主机状态正常 ✓"
    except Exception as e:
        return f"巡检失败：{e}"


__all__ = ["get_host_metrics", "inspect_all_hosts"]
