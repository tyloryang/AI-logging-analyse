"""LangGraph Agent 工具集 — 封装 Loki / Prometheus 客户端"""
from datetime import datetime

from langchain_core.tools import tool
from state import loki, prom


@tool
async def query_error_logs(service: str = "", hours: int = 24, keyword: str = "", limit: int = 50) -> str:
    """查询错误日志。service=服务名(空=全部), hours=最近N小时, keyword=关键词过滤, limit=返回条数上限。适合排查具体服务的错误信息。"""
    try:
        logs = await loki.query_logs(
            service=service, hours=hours, limit=limit, level="error", keyword=keyword
        )
        if not logs:
            return f"最近 {hours}h 内未发现错误日志" + (f"（服务：{service}）" if service else "")
        lines = []
        for log in logs[:limit]:
            ts = str(log.get("timestamp", ""))[:19]
            svc = log.get("service", "?")
            msg = str(log.get("message", ""))[:200]
            lines.append(f"[{ts}][{svc}] {msg}")
        return f"共 {len(logs)} 条错误日志：\n" + "\n".join(lines)
    except Exception as e:
        return f"查询错误日志失败：{e}"


@tool
async def count_errors_by_service(hours: int = 24) -> str:
    """统计各服务错误数量排名，用于快速定位问题服务。hours=统计时间范围（小时）。"""
    try:
        errors = await loki.count_errors_by_service(hours)
        if not errors:
            return f"最近 {hours}h 无错误日志"
        sorted_errors = sorted(errors.items(), key=lambda x: x[1], reverse=True)
        total = sum(errors.values())
        lines = [f"最近 {hours}h 错误汇总（共 {total} 条，{len(errors)} 个服务）："]
        for svc, cnt in sorted_errors[:20]:
            lines.append(f"  {svc}: {cnt} 条")
        return "\n".join(lines)
    except Exception as e:
        return f"统计错误失败：{e}"


@tool
async def get_services_list() -> str:
    """获取所有被监控的服务列表及错误状态。了解系统中有哪些服务时使用。"""
    try:
        services = await loki.get_services()
        if not services:
            return "未发现任何服务"
        with_errors = sorted(
            [s for s in services if s.get("error_count", 0) > 0],
            key=lambda x: x.get("error_count", 0), reverse=True
        )
        healthy_count = len(services) - len(with_errors)
        lines = [f"共 {len(services)} 个服务，{healthy_count} 健康，{len(with_errors)} 有错误"]
        for s in with_errors[:15]:
            lines.append(f"  ⚠ {s['name']}: {s.get('error_count')} 条错误")
        return "\n".join(lines)
    except Exception as e:
        return f"获取服务列表失败：{e}"


@tool
async def get_host_metrics(instance: str = "") -> str:
    """获取主机实时性能指标（CPU/内存/磁盘/负载/TCP连接数）。instance=主机IP或实例地址（空=返回全部主机）。"""
    try:
        hosts = await prom.discover_hosts()
        metrics = await prom.get_all_host_metrics()
        partitions = await prom.get_all_partitions()
        lines = []
        for h in hosts:
            inst = h.get("instance", "")
            ip = h.get("ip", "")
            if instance and instance not in inst and instance not in ip:
                continue
            m = metrics.get(inst, {})
            parts = partitions.get(inst, [])
            max_disk = max((p.get("usage_pct", 0) for p in parts), default=None)
            state = "在线" if h.get("state") == "up" else "离线"
            hostname = h.get("hostname") or ip or inst
            cpu = f"{m.get('cpu_usage', '-')}%"
            mem = f"{m.get('mem_usage', '-')}%"
            disk = f"{max_disk}%" if max_disk is not None else "-"
            load = m.get("load5", "-")
            tcp = m.get("tcp_estab", "-")
            lines.append(
                f"[{state}] {hostname}({ip})  CPU:{cpu} 内存:{mem} 磁盘:{disk} 负载:{load} TCP:{tcp}"
            )
        if not lines:
            return "未找到主机数据"
        return f"主机指标（{len(lines)} 台）：\n" + "\n".join(lines)
    except Exception as e:
        return f"获取主机指标失败：{e}"


@tool
async def inspect_all_hosts() -> str:
    """执行全量主机巡检，检查所有在线主机的 CPU/内存/磁盘/负载是否超过阈值。返回所有异常项和总体状态。"""
    try:
        hosts = await prom.discover_hosts()
        instances = [h["instance"] for h in hosts if h.get("state") == "up"]
        if not instances:
            return "未发现在线主机"
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


@tool
async def query_recent_logs(service: str = "", hours: int = 1, level: str = "", keyword: str = "", limit: int = 30) -> str:
    """查询最近的日志（可指定级别）。level=error/warn/info（空=全部级别）。适合查看服务最近运行情况。"""
    try:
        logs = await loki.query_logs(
            service=service, hours=hours, limit=limit, level=level, keyword=keyword
        )
        if not logs:
            return "未找到符合条件的日志"
        lines = []
        for log in logs[:limit]:
            ts = str(log.get("timestamp", ""))[:19]
            svc = log.get("service", "?")
            lvl = str(log.get("level", "?")).upper()
            msg = str(log.get("message", ""))[:200]
            lines.append(f"[{ts}][{lvl}][{svc}] {msg}")
        return f"共 {len(logs)} 条日志：\n" + "\n".join(lines)
    except Exception as e:
        return f"查询日志失败：{e}"


@tool
async def recall_similar_incidents(query: str, top_k: int = 3) -> str:
    """从历史运维事件库中检索与当前问题语义相似的历史案例（根因分析报告、巡检结论等）。
    分析新问题前优先调用，查看是否有类似历史事件和已知解决方案。
    query=描述当前问题的关键词或问句, top_k=返回最相似的案例数。
    """
    try:
        from agent.milvus_memory import get_memory
        hits = await get_memory().search(query, top_k)
        if not hits:
            return "历史事件库中未找到相似案例。"
        lines = [f"找到 {len(hits)} 条相似历史案例：\n"]
        for i, h in enumerate(hits, 1):
            ts = datetime.fromtimestamp(h["created_at"]).strftime("%Y-%m-%d %H:%M")
            mode_label = {"rca": "根因分析", "inspect": "巡检", "chat": "对话"}.get(h["mode"], h["mode"])
            lines.append(f"【案例 {i}】相似度={h['score']} | {mode_label} | {ts}")
            lines.append(f"  问题：{h['user_query']}")
            if h.get("affected_services"):
                lines.append(f"  涉及：{h['affected_services']}")
            if h.get("root_cause"):
                lines.append(f"  根因：{h['root_cause']}")
            if h.get("resolution"):
                lines.append(f"  处置：{h['resolution']}")
            elif h.get("full_summary"):
                excerpt = h["full_summary"][:400] + ("..." if len(h["full_summary"]) > 400 else "")
                lines.append(f"  详情：{excerpt}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"检索历史案例失败（Milvus 不可用）：{e}"


ALL_TOOLS = [
    recall_similar_incidents,
    query_error_logs,
    count_errors_by_service,
    get_services_list,
    get_host_metrics,
    inspect_all_hosts,
    query_recent_logs,
]
