"""LangGraph Agent 工具集 — 封装 Loki / Prometheus 客户端"""
import asyncio
import concurrent.futures
import glob
import json
import os
import re
from datetime import datetime

from langchain_core.tools import tool
from state import loki, prom

_REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")


def _call_sse_mcp_sync(sse_url: str, method: str, params: dict) -> list:
    """在全新事件循环中同步执行 SSE MCP 调用，避免 anyio TaskGroup 与外层 asyncio 冲突。"""
    async def _inner():
        from mcp.client.sse import sse_client
        from mcp import ClientSession
        async with sse_client(sse_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(method, params)
        return result.content or []

    return asyncio.run(_inner())


def _list_sse_mcp_tools_sync(sse_url: str) -> list:
    """在全新事件循环中同步列出 SSE MCP 工具，避免 anyio TaskGroup 冲突。"""
    async def _inner():
        from mcp.client.sse import sse_client
        from mcp import ClientSession
        async with sse_client(sse_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                resp = await session.list_tools()
        return resp.tools

    return asyncio.run(_inner())


def _normalize_sse_url(sse_url: str) -> str:
    url = sse_url.rstrip("/")
    if not url.endswith("/sse"):
        return f"{url}/sse"
    return url


def _mcp_content_to_text(content: list) -> str:
    parts = []
    for item in content:
        text = getattr(item, "text", None) or str(item)
        parts.append(text)
    return "\n".join(parts) if parts else "(无返回内容)"


async def _call_sse_mcp_raw(sse_url: str, method: str, params: dict) -> str:
    loop = asyncio.get_event_loop()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        content = await loop.run_in_executor(
            pool, lambda: _call_sse_mcp_sync(_normalize_sse_url(sse_url), method, params)
        )
    return _mcp_content_to_text(content)


async def _call_sse_mcp(mcp_name: str, sse_url: str, method: str, params: dict) -> str:
    """通过 MCP SDK 正确调用 SSE 类型的 MCP 服务器（线程隔离，避免 TaskGroup 冲突）。"""
    try:
        output = await _call_sse_mcp_raw(sse_url, method, params)
        return f"**MCP [{mcp_name}] 返回结果**\n{output[:3000]}"
    except Exception as exc:
        return f"SSE MCP 调用失败：{exc}"


@tool
async def query_error_logs(service: str = "", hours: int = 24, minutes: int = 0, keyword: str = "", limit: int = 50) -> str:
    """查询错误日志。service=服务名(空=全部), hours=最近N小时, minutes=最近N分钟(优先于hours，如5分钟传minutes=5), keyword=关键词过滤, limit=返回条数上限。"""
    actual_hours = minutes / 60.0 if minutes > 0 else hours
    time_label = f"{minutes}分钟" if minutes > 0 else f"{hours}小时"
    try:
        logs = await loki.query_logs(
            service=service, hours=actual_hours, limit=limit, level="error", keyword=keyword
        )
        if not logs:
            return f"最近 {time_label} 内未发现错误日志" + (f"（服务：{service}）" if service else "")
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
async def count_errors_by_service(hours: int = 24, minutes: int = 0) -> str:
    """统计各服务错误数量排名，用于快速定位问题服务。hours=统计时间范围（小时），minutes=统计时间范围（分钟，优先于hours，如最近5分钟传minutes=5）。"""
    actual_hours = minutes / 60.0 if minutes > 0 else hours
    time_label = f"{minutes}分钟" if minutes > 0 else f"{hours}小时"
    try:
        errors = await loki.count_errors_by_service(actual_hours)
        if not errors:
            return f"最近 {time_label} 无错误日志"
        sorted_errors = sorted(errors.items(), key=lambda x: x[1], reverse=True)
        total = sum(errors.values())
        lines = [f"最近 {time_label} 错误汇总（共 {total} 条，{len(errors)} 个服务）："]
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
async def query_recent_logs(service: str = "", hours: int = 1, minutes: int = 0, level: str = "", keyword: str = "", limit: int = 30) -> str:
    """查询最近的日志（可指定级别）。level=error/warn/info（空=全部级别）。minutes=最近N分钟（优先于hours，如最近10分钟传minutes=10）。适合查看服务最近运行情况。"""
    actual_hours = minutes / 60.0 if minutes > 0 else hours
    time_label = f"{minutes}分钟" if minutes > 0 else f"{hours}小时"
    try:
        logs = await loki.query_logs(
            service=service, hours=actual_hours, limit=limit, level=level, keyword=keyword
        )
        if not logs:
            return f"最近 {time_label} 内未找到符合条件的日志"
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
        if hits is None or not hits:
            return "历史事件库中未找到相似案例（库可能为空或 Milvus/Embedding 暂时不可用）。"
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


@tool
async def search_daily_reports(keyword: str = "", days: int = 30, limit: int = 8) -> str:
    """搜索历史运维日报/巡检日报/慢日志报告。
    keyword=关键词或问题描述（支持语义搜索，如"网络故障""磁盘满""calico"）。
    days=搜索最近N天（默认30，0=不限）。
    limit=最多返回条数（默认8）。
    适合：分析历史故障趋势、某服务反复出现的问题、特定时间段系统状况。
    """
    try:
        # ── 路径1：文件关键词精确搜索 ──────────────────────────────
        pattern  = os.path.join(_REPORTS_DIR, "*.json")
        files    = sorted(glob.glob(pattern), reverse=True)
        kw_lower = keyword.lower().strip()

        # 时间过滤
        if days > 0:
            from datetime import timezone, timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)

            def _in_range(path: str) -> bool:
                try:
                    name = os.path.basename(path).replace(".json", "").lstrip("inspctolwg_")
                    # 取文件名里的时间戳部分（inspect_/slowlog_ 前缀后面）
                    ts = "".join(filter(str.isdigit, os.path.basename(path)))[:14]
                    dt = datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                    return dt >= cutoff
                except Exception:
                    return True
            files = [f for f in files if _in_range(f)]

        file_matched: list[dict] = []
        for fpath in files:
            try:
                with open(fpath, encoding="utf-8") as fp:
                    report = json.load(fp)
            except Exception:
                continue
            if kw_lower:
                search_text = (
                    report.get("title", "") + " " +
                    report.get("ai_analysis", "") + " " +
                    " ".join(e.get("service", "") for e in report.get("top10_errors", [])) + " " +
                    " ".join(i.get("item", "") for i in report.get("top_issues", []))
                ).lower()
                if kw_lower not in search_text:
                    continue
            file_matched.append(report)
            if len(file_matched) >= limit:
                break

        # ── 路径2：Milvus 语义搜索（有关键词时才做）──────────────
        milvus_hits: list[dict] = []
        if keyword:
            try:
                from agent.report_memory import get_report_memory
                hits = await get_report_memory().search(keyword, top_k=limit)
                # 时间过滤
                if days > 0:
                    import time as _time
                    cutoff_ts = _time.time() - days * 86400
                    hits = [h for h in hits if h.get("created_at", 0) >= cutoff_ts]
                milvus_hits = hits
            except Exception as exc:
                logger.debug("[search_daily_reports] Milvus 搜索失败: %s", exc)

        # ── 合并去重（文件匹配优先，Milvus 补充语义结果）──────────
        seen_ids: set[str] = set()
        merged: list[tuple[str, dict]] = []  # (来源标签, 报告dict)

        for r in file_matched:
            rid = r.get("id", "")
            if rid not in seen_ids:
                seen_ids.add(rid)
                merged.append(("关键词", r))

        for h in milvus_hits:
            rid = h.get("report_id", "")
            if rid and rid not in seen_ids:
                seen_ids.add(rid)
                # 转为统一格式
                merged.append(("语义", {
                    "id":          rid,
                    "title":       h.get("title", ""),
                    "created_at":  "",
                    "health_score":h.get("health_score", "-"),
                    "ai_analysis": h.get("ai_summary", ""),
                    "_top_issues": h.get("top_issues", ""),
                    "_score":      h.get("score", 0),
                    "_type":       h.get("report_type", ""),
                }))

        merged = merged[:limit]

        if not merged:
            scope   = f"最近 {days} 天" if days > 0 else "所有时间"
            kw_hint = f"（关键词：{keyword}）" if keyword else ""
            return f"{scope}内未找到匹配的日报{kw_hint}。"

        lines = [f"找到 {len(merged)} 条历史日报（关键词匹配+语义匹配）：\n"]
        for src, r in merged:
            date_str     = r.get("created_at", "")[:10] or r.get("date_str", "")
            score        = r.get("health_score", "-")
            analysis     = r.get("ai_analysis", "")
            summary      = analysis[:350].replace("\n", " ") + ("…" if len(analysis) > 350 else "")
            top_issues   = (
                ", ".join(e.get("service", "") for e in r.get("top10_errors", [])[:3])
                or ", ".join(i.get("item", "") for i in r.get("top_issues", [])[:3])
                or r.get("_top_issues", "")
                or "无"
            )
            sim_hint = f"  相似度：{r['_score']}" if "_score" in r else ""
            lines.append(
                f"【{r.get('title', date_str)}】[{src}]{sim_hint}\n"
                f"  日期：{date_str}  健康评分：{score}/100\n"
                f"  主要问题：{top_issues}\n"
                f"  分析摘要：{summary}\n"
            )

        return "\n".join(lines)
    except Exception as e:
        return f"搜索历史日报失败：{e}"


# ── Kubernetes 工具 ────────────────────────────────────────────────────────────

@tool
async def get_k8s_summary() -> str:
    """查询 Kubernetes 集群总览：节点数、Pod 数、Deployment 数、命名空间列表。
    用户询问 k8s 状态、集群情况、容器平台状态时使用。"""
    try:
        from routers.kubernetes import _get_client
        core_v1, apps_v1 = _get_client()
        nodes = core_v1.list_node(timeout_seconds=8)
        pods  = core_v1.list_pod_for_all_namespaces(timeout_seconds=8)
        deps  = apps_v1.list_deployment_for_all_namespaces(timeout_seconds=8)
        ns    = core_v1.list_namespace(timeout_seconds=8)

        total_nodes = len(nodes.items)
        ready_nodes = sum(
            1 for n in nodes.items
            if any(c.type == "Ready" and c.status == "True" for c in n.status.conditions)
        )
        total_pods   = len(pods.items)
        running_pods = sum(1 for p in pods.items if (p.status.phase or "") == "Running")
        total_deps   = len(deps.items)
        ready_deps   = sum(
            1 for d in deps.items
            if (d.status.ready_replicas or 0) >= (d.spec.replicas or 1)
        )
        ns_names = [n.metadata.name for n in ns.items]

        def _icon(ok, total): return "[正常]" if ok == total else f"[{total-ok}个异常]"

        lines = [
            "**K8s 集群总览**",
            f"节点：{ready_nodes}/{total_nodes} 就绪 {_icon(ready_nodes, total_nodes)}",
            f"Pod：{running_pods}/{total_pods} 运行中 {_icon(running_pods, total_pods)}",
            f"Deployment：{ready_deps}/{total_deps} 就绪 {_icon(ready_deps, total_deps)}",
            f"命名空间：{', '.join(ns_names[:12]) or '无'}",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"K8s 连接失败：{e}（请检查系统配置中的 kubeconfig）"


@tool
async def get_k8s_pods(namespace: str = "") -> str:
    """查询 Kubernetes Pod 列表及运行状态。
    namespace=命名空间（空=全部命名空间）。
    用户询问某个命名空间的 Pod 状态、哪些 Pod 异常/重启时使用。"""
    try:
        from routers.kubernetes import _get_client
        core_v1, _ = _get_client()
        if namespace:
            pods = core_v1.list_namespaced_pod(namespace, timeout_seconds=8)
        else:
            pods = core_v1.list_pod_for_all_namespaces(timeout_seconds=8)

        if not pods.items:
            return f"命名空间 {namespace or '全部'} 下无 Pod"

        lines = [f"**Pod 列表**（{namespace or '全部命名空间'}，共 {len(pods.items)} 个）\n"]
        # 优先展示非 Running 的
        items = sorted(pods.items, key=lambda p: (p.status.phase == "Running", p.metadata.name))
        for p in items[:30]:
            ns   = p.metadata.namespace
            name = p.metadata.name
            phase = p.status.phase or "?"
            restarts = sum(
                cs.restart_count for cs in (p.status.container_statuses or [])
            )
            flag = "" if phase == "Running" else "[异常] "
            lines.append(f"{flag}[{ns}] {name}  状态:{phase}  重启:{restarts}次")
        if len(pods.items) > 30:
            lines.append(f"...（共 {len(pods.items)} 个，仅展示前 30 个）")
        return "\n".join(lines)
    except Exception as e:
        return f"查询 Pod 失败：{e}"


@tool
async def get_k8s_nodes() -> str:
    """查询 Kubernetes 节点列表及状态（CPU/内存分配、是否就绪）。
    用户询问节点健康状态、节点资源时使用。"""
    try:
        from routers.kubernetes import _get_client
        core_v1, _ = _get_client()
        nodes = core_v1.list_node(timeout_seconds=8)
        if not nodes.items:
            return "集群无节点"
        lines = [f"**节点列表**（共 {len(nodes.items)} 个）\n"]
        for n in nodes.items:
            name   = n.metadata.name
            ready  = next(
                (c.status for c in n.status.conditions if c.type == "Ready"),
                "Unknown"
            )
            cpu    = n.status.capacity.get("cpu", "?")
            mem    = n.status.capacity.get("memory", "?")
            flag   = "" if ready == "True" else "[异常] "
            lines.append(f"{flag}{name}  Ready:{ready}  CPU:{cpu}  内存:{mem}")
        return "\n".join(lines)
    except Exception as e:
        return f"查询节点失败：{e}"


# ── 中间件工具 ─────────────────────────────────────────────────────────────────

@tool
async def get_k8s_namespaces() -> str:
    """查询 Kubernetes 命名空间列表。"""
    try:
        from routers.kubernetes import list_namespaces

        namespaces = await list_namespaces()
        if not namespaces:
            return "当前集群没有命名空间数据"

        lines = [f"**命名空间列表**（共 {len(namespaces)} 个）\n"]
        for item in namespaces[:30]:
            lines.append(
                f"{item.get('name', '?')}  状态:{item.get('status', '?')}  创建:{item.get('age', '?')}"
            )
        if len(namespaces) > 30:
            lines.append(f"... 共 {len(namespaces)} 个，仅展示前 30 个")
        return "\n".join(lines)
    except Exception as exc:
        return f"查询命名空间失败：{exc}"


@tool
async def get_k8s_deployments(namespace: str = "") -> str:
    """查询 Kubernetes Deployment 列表及就绪状态。namespace=命名空间（空=全部）。"""
    try:
        from routers.kubernetes import list_deployments

        deployments = await list_deployments(namespace)
        if not deployments:
            return f"命名空间 {namespace or '全部'} 下无 Deployment"

        lines = [
            f"**Deployment 列表**（{namespace or '全部命名空间'}，共 {len(deployments)} 个）\n"
        ]
        items = sorted(
            deployments,
            key=lambda item: (
                item.get("status") == "Ready",
                item.get("namespace", ""),
                item.get("name", ""),
            ),
        )
        for item in items[:30]:
            flag = "" if item.get("status") == "Ready" else "[异常] "
            lines.append(
                f"{flag}[{item.get('namespace', '?')}] {item.get('name', '?')}  "
                f"状态:{item.get('status', '?')}  副本:{item.get('ready', 0)}/{item.get('desired', 0)}"
            )
        if len(deployments) > 30:
            lines.append(f"... 共 {len(deployments)} 个，仅展示前 30 个")
        return "\n".join(lines)
    except Exception as exc:
        return f"查询 Deployment 失败：{exc}"


@tool
async def get_k8s_services(namespace: str = "") -> str:
    """查询 Kubernetes Service 列表及暴露端口。namespace=命名空间（空=全部）。"""
    try:
        from routers.kubernetes import list_services

        services = await list_services(namespace)
        if not services:
            return f"命名空间 {namespace or '全部'} 下无 Service"

        lines = [f"**Service 列表**（{namespace or '全部命名空间'}，共 {len(services)} 个）\n"]
        for item in services[:30]:
            ports = ",".join(item.get("ports", []) or []) or "-"
            lines.append(
                f"[{item.get('namespace', '?')}] {item.get('name', '?')}  "
                f"类型:{item.get('type', '?')}  ClusterIP:{item.get('clusterIP', '-') or '-'}  端口:{ports}"
            )
        if len(services) > 30:
            lines.append(f"... 共 {len(services)} 个，仅展示前 30 个")
        return "\n".join(lines)
    except Exception as exc:
        return f"查询 Service 失败：{exc}"


@tool
async def get_middleware_summary() -> str:
    """查询中间件总览：MySQL / Redis / Kafka / Elasticsearch 等实例数量和健康状态。
    用户询问中间件状态、数据库状态、消息队列状态时使用。"""
    try:
        from routers.middleware import middleware_summary
        data = await middleware_summary()
        if not data:
            return "暂无中间件数据（Prometheus 中未发现中间件 target）"
        lines = ["**中间件总览**\n"]
        for item in data:
            icon = item.get("icon", "")
            label = item.get("label", item.get("type", "?"))
            total = item.get("total", "?")
            up = item.get("up", "?")
            ok = item.get("up") == item.get("total")
            status_mark = "[正常]" if ok else "[异常]"
            lines.append(f"{status_mark} {icon} {label} — {up}/{total} 实例正常")
        return "\n".join(lines)
    except Exception as exc:
        return f"查询中间件失败：{exc}"


@tool
async def get_middleware_instances(middleware_type: str = "") -> str:
    """查询具体中间件实例列表及连接信息。
    middleware_type = mysql / redis / kafka / elasticsearch / 留空=全部。
    用户询问某类中间件的实例详情时使用。"""
    try:
        from routers.middleware import list_instances
        instances = await list_instances()
        if middleware_type:
            instances = [i for i in instances if i.get("type", "").lower() == middleware_type.lower()]
        if not instances:
            return f"未找到{'类型：' + middleware_type + ' 的' if middleware_type else '任何'}中间件实例"
        lines = [f"**中间件实例列表**（{middleware_type or '全部'}，共 {len(instances)} 个）\n"]
        for inst in instances[:20]:
            status = "[正常]" if inst.get("status") == "up" else "[异常]"
            lines.append(
                f"{status} [{inst.get('label', inst.get('type',''))}] "
                f"{inst.get('instance','')}  job:{inst.get('job','?')}"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"查询中间件实例失败：{exc}"


# ── MCP 工具调用 ───────────────────────────────────────────────────────────────

def _is_es_mcp(name: str) -> bool:
    lower = name.lower()
    return "es" in lower or "elastic" in lower or "opensearch" in lower


def _format_es_indices_result(raw: str, pattern: str = "*", limit: int = 80) -> str:
    try:
        data = json.loads(raw)
    except Exception:
        return raw[:3000]

    if not isinstance(data, list):
        return raw[:3000]
    if not data:
        return f"ES 未找到匹配 '{pattern}' 的索引"

    health_counts: dict[str, int] = {}
    for item in data:
        if isinstance(item, dict):
            health = str(item.get("health") or "unknown")
            health_counts[health] = health_counts.get(health, 0) + 1

    health_text = "，".join(f"{k}:{v}" for k, v in sorted(health_counts.items()))
    lines = [
        f"**MCP [ES MCP] 索引列表**（pattern={pattern}，共 {len(data)} 个，{health_text}）",
        "",
        f"{'索引名':<46} {'健康':>7} {'状态':>7} {'文档数':>10} {'大小':>10} {'主分片':>6} {'副本':>4}",
        "-" * 98,
    ]
    for item in data[:limit]:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"{str(item.get('index', '')):<46} "
            f"{str(item.get('health', '?')):>7} "
            f"{str(item.get('status', '?')):>7} "
            f"{str(item.get('docs.count', '0')):>10} "
            f"{str(item.get('store.size', '?')):>10} "
            f"{str(item.get('pri', '?')):>6} "
            f"{str(item.get('rep', '?')):>4}"
        )
    if len(data) > limit:
        lines.append(f"... 仅展示前 {limit} 个，剩余 {len(data) - limit} 个可用更精确 pattern 过滤。")
    return "\n".join(lines)


async def _call_es_mcp_list_indices(mcp_name: str, url: str, body: dict) -> str:
    pattern = str(body.get("pattern") or body.get("index") or body.get("name") or "*").strip() or "*"
    raw = await _call_sse_mcp_raw(
        url,
        "general_api_request",
        {
            "method": "GET",
            "path": f"/_cat/indices/{pattern}",
            "params": {
                "format": "json",
                "s": "index",
                "h": "index,health,status,docs.count,store.size,pri,rep",
            },
        },
    )
    return _format_es_indices_result(raw, pattern=pattern)


def _find_enabled_mcp(
    keywords: tuple[str, ...],
    preferred_names: tuple[str, ...] = (),
) -> dict | None:
    cfg_file = os.path.join(os.path.dirname(__file__), "..", "data", "agent_config.json")
    try:
        with open(cfg_file, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return None

    preferred_map = {name.lower(): idx for idx, name in enumerate(preferred_names)}
    matches = [
        item
        for item in cfg.get("mcps", [])
        if item.get("enabled")
        and any(keyword.lower() in str(item.get("name", "")).lower() for keyword in keywords)
    ]
    if not matches:
        return None

    def _score(item: dict) -> tuple[int, int, str]:
        name = str(item.get("name", ""))
        lower = name.lower()
        preferred_rank = preferred_map.get(lower, len(preferred_map) + 1)
        keyword_rank = min(
            (
                idx
                for idx, keyword in enumerate(keywords)
                if keyword.lower() in lower
            ),
            default=len(keywords) + 1,
        )
        return (preferred_rank, keyword_rank, name)

    return sorted(matches, key=_score)[0]


@tool
async def call_mcp_tool(mcp_name: str, action: str, params: str = "{}") -> str:
    """调用已配置的 MCP（Model Context Protocol）工具执行操作。
    mcp_name=MCP 名称（如 'Prometheus MCP'、'Redis MCP'），
    action=要执行的动作或接口路径（如 'query' / '/metrics'），
    params=JSON 格式参数字符串（如 '{"query":"up"}'）。
    使用前先确认 MCP 已在智能体配置中启用。"""
    import json as _json
    try:
        # 读取 agent_config 找到对应 MCP
        cfg_file = os.path.join(os.path.dirname(__file__), "..", "data", "agent_config.json")
        with open(cfg_file, encoding="utf-8") as f:
            cfg = _json.load(f)

        mcp = next(
            (m for m in cfg.get("mcps", [])
             if m.get("name", "").lower() == mcp_name.lower() and m.get("enabled")),
            None,
        )
        if not mcp:
            enabled_names = [m["name"] for m in cfg.get("mcps", []) if m.get("enabled")]
            return (
                f"MCP '{mcp_name}' 未找到或未启用。\n"
                f"当前已启用的 MCP：{', '.join(enabled_names) or '无'}"
            )

        mcp_type = mcp.get("type", "http")
        url      = mcp.get("url", "").rstrip("/")

        try:
            body = _json.loads(params) if params.strip() else {}
        except Exception:
            body = {"query": params}

        import httpx

        if mcp_type == "http":
            endpoint = url + ("/" + action.lstrip("/") if action else "")
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.post(endpoint, json=body)
                resp.raise_for_status()
                result = resp.text[:2000]
            return f"**MCP [{mcp['name']}] 返回结果**\n{result}"

        elif mcp_type == "sse":
            if _is_es_mcp(mcp["name"]) and action in ("list_indices", "cat_indices"):
                return await _call_es_mcp_list_indices(mcp["name"], url, body)
            return await _call_sse_mcp(mcp["name"], url, action, body)

        else:
            return f"MCP 类型 '{mcp_type}' 暂不支持在线调用（支持 http / sse 类型）"

    except FileNotFoundError:
        return "agent_config.json 不存在，请先在智能体配置页面保存配置"
    except Exception as exc:
        return f"调用 MCP 失败：{exc}"


@tool
async def call_k8s_mcp(action: str, params: str = "{}") -> str:
    """调用已启用的 Kubernetes / K8S MCP。
    action=工具名，例如 list_pods / list_nodes / list_namespaces / list_deployments / list_services。"""
    mcp = _find_enabled_mcp(
        keywords=("k8s", "kubernetes", "kube"),
        preferred_names=("K8S MCP", "Kubernetes MCP"),
    )
    if not mcp:
        return "未找到已启用的 K8S MCP，请先在智能体配置中添加并启用名称包含 K8S / Kubernetes / Kube 的 MCP。"
    return await call_mcp_tool.ainvoke(
        {
            "mcp_name": str(mcp.get("name", "")),
            "action": action,
            "params": params,
        }
    )


@tool
async def list_mcp_tools(mcp_name: str) -> str:
    """列出指定 MCP 服务器支持的工具（actions）清单，调用前先用此工具发现可用操作。
    mcp_name=MCP 名称（如 'ES MCP'）。"""
    import json as _json
    import httpx
    try:
        cfg_file = os.path.join(os.path.dirname(__file__), "..", "data", "agent_config.json")
        with open(cfg_file, encoding="utf-8") as f:
            cfg = _json.load(f)
        mcp = next(
            (m for m in cfg.get("mcps", [])
             if m.get("name", "").lower() == mcp_name.lower() and m.get("enabled")),
            None,
        )
        if not mcp:
            return f"MCP '{mcp_name}' 未找到或未启用"

        mcp_type = mcp.get("type", "http")
        url = mcp.get("url", "").rstrip("/")

        if mcp_type == "sse":
            try:
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    raw_tools = await loop.run_in_executor(
                        pool, lambda: _list_sse_mcp_tools_sync(_normalize_sse_url(url))
                    )
                tools = [{"name": t.name, "description": t.description or ""} for t in raw_tools]
            except Exception as e:
                return f"获取 SSE MCP 工具列表失败：{e}"
        else:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url + "/tools/list", json={})
                resp.raise_for_status()
                data = resp.json()
            tools = data.get("result", {}).get("tools", data.get("tools", []))

        if not tools:
            return f"MCP [{mcp_name}] 工具列表为空"

        lines = [f"**MCP [{mcp_name}] 可用工具（共 {len(tools)} 个）**\n"]
        for t in tools:
            name = t.get("name", "?") if isinstance(t, dict) else t
            desc = t.get("description", "") if isinstance(t, dict) else ""
            lines.append(f"- {name}：{desc}")
        return "\n".join(lines)
    except Exception as exc:
        return f"获取 MCP 工具列表失败：{exc}"


@tool
async def list_k8s_mcp_tools() -> str:
    """列出已启用 Kubernetes / K8S MCP 支持的工具。"""
    mcp = _find_enabled_mcp(
        keywords=("k8s", "kubernetes", "kube"),
        preferred_names=("K8S MCP", "Kubernetes MCP"),
    )
    if not mcp:
        return "未找到已启用的 K8S MCP，请先在智能体配置中添加并启用名称包含 K8S / Kubernetes / Kube 的 MCP。"
    return await list_mcp_tools.ainvoke({"mcp_name": str(mcp.get("name", ""))})


@tool
async def list_available_mcps() -> str:
    """列出当前已配置并启用的 MCP 工具列表，用于了解可用的 MCP 能力后再决定调用哪个。"""
    import json as _json
    try:
        cfg_file = os.path.join(os.path.dirname(__file__), "..", "data", "agent_config.json")
        with open(cfg_file, encoding="utf-8") as f:
            cfg = _json.load(f)
        mcps = cfg.get("mcps", [])
        enabled = [m for m in mcps if m.get("enabled")]
        if not enabled:
            return "当前无已启用的 MCP，请在智能体配置页面添加并启用 MCP"
        lines = [f"**已启用 MCP（共 {len(enabled)} 个）**\n"]
        for m in enabled:
            t = m.get('type', '?')
            callable_mark = "" if t in ("http", "sse") else " [不支持在线调用]"
            lines.append(f"- {m['name']}  类型:{t}  地址:{m.get('url','?')}{callable_mark}")
        return "\n".join(lines)
    except Exception as exc:
        return f"读取 MCP 配置失败：{exc}"


def _es_base_url() -> str:
    """从环境变量或配置文件读取 ES 地址，默认 http://192.168.9.226:9200"""
    url = os.getenv("ES_URL", "").strip().rstrip("/")
    if url:
        return url
    try:
        cfg_file = os.path.join(os.path.dirname(__file__), "..", "data", "agent_config.json")
        with open(cfg_file, encoding="utf-8") as f:
            cfg = json.load(f)
        for m in cfg.get("mcps", []):
            if "es" in m.get("name", "").lower() and m.get("enabled"):
                raw = m.get("url", "")
                # MCP 地址推导 ES 地址：去掉 /sse 后缀，端口 8000 → 9200
                raw = re.sub(r'/sse$', '', raw)
                raw = re.sub(r':8000', ':9200', raw)
                return raw.rstrip("/")
    except Exception:
        pass
    return "http://192.168.9.226:9200"


@tool
async def es_list_indices(pattern: str = "*") -> str:
    """列出 Elasticsearch 索引。pattern=索引名模式（支持通配符，默认 * 列全部）。
    返回索引名、文档数、存储大小、健康状态等。"""
    import httpx
    base = _es_base_url()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{base}/_cat/indices/{pattern}",
                params={"format": "json", "s": "index", "h": "index,health,status,docs.count,store.size,pri,rep"},
            )
            resp.raise_for_status()
            data = resp.json()
        if not data:
            return f"ES 未找到匹配 '{pattern}' 的索引"
        lines = [f"**Elasticsearch 索引列表（共 {len(data)} 个）**\n"]
        lines.append(f"{'索引名':<40} {'健康':>6} {'状态':>6} {'文档数':>10} {'大小':>8} {'主分片':>6} {'副本':>4}")
        lines.append("-" * 85)
        for idx in data:
            lines.append(
                f"{idx.get('index',''):<40} "
                f"{idx.get('health','?'):>6} "
                f"{idx.get('status','?'):>6} "
                f"{idx.get('docs.count','0'):>10} "
                f"{idx.get('store.size','?'):>8} "
                f"{idx.get('pri','?'):>6} "
                f"{idx.get('rep','?'):>4}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"查询 ES 索引失败：{e}"


@tool
async def es_cluster_health() -> str:
    """获取 Elasticsearch 集群健康状态，包括节点数、分片数、未分配分片等关键指标。"""
    import httpx
    base = _es_base_url()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            h = (await client.get(f"{base}/_cluster/health", params={"format": "json"})).json()
            s = (await client.get(f"{base}/_cluster/stats",  params={"format": "json"})).json()
        status_icon = {"green": "[正常]", "yellow": "[警告]", "red": "[异常]"}.get(h.get("status", ""), "[未知]")
        lines = [
            f"**ES 集群健康 {status_icon}**",
            f"集群名称  : {h.get('cluster_name')}",
            f"状态      : {h.get('status')}",
            f"节点总数  : {h.get('number_of_nodes')}  数据节点: {h.get('number_of_data_nodes')}",
            f"分片      : 活跃主分片 {h.get('active_primary_shards')} / 活跃总分片 {h.get('active_shards')}",
            f"未分配分片: {h.get('unassigned_shards')}",
            f"初始化中  : {h.get('initializing_shards')}",
            f"索引数    : {s.get('indices', {}).get('count', '?')}",
            f"文档总数  : {s.get('indices', {}).get('docs', {}).get('count', '?')}",
            f"存储总量  : {s.get('indices', {}).get('store', {}).get('size_in_bytes', 0) // 1024 // 1024} MB",
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"查询 ES 集群状态失败：{e}"


@tool
async def es_search(index: str, query: str = "", size: int = 10, fields: str = "") -> str:
    """在 Elasticsearch 中搜索文档。
    index=索引名（必填），query=查询关键词（空则返回最新文档），
    size=返回条数（默认10，最大50），fields=指定返回字段（逗号分隔，空则返回全部）。"""
    import httpx
    base = _es_base_url()
    size = min(size, 50)
    body: dict = {"size": size, "sort": [{"@timestamp": {"order": "desc"}}]}
    if query:
        body["query"] = {"query_string": {"query": query}}
    else:
        body["query"] = {"match_all": {}}
    if fields:
        body["_source"] = [f.strip() for f in fields.split(",")]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{base}/{index}/_search", json=body)
            resp.raise_for_status()
            data = resp.json()
        hits = data.get("hits", {})
        total = hits.get("total", {})
        total_count = total.get("value", 0) if isinstance(total, dict) else total
        docs = hits.get("hits", [])
        lines = [f"**ES [{index}] 搜索结果**  总命中: {total_count} 条，返回 {len(docs)} 条\n"]
        for doc in docs:
            src = doc.get("_source", {})
            ts = src.get("@timestamp", src.get("timestamp", ""))
            msg = str(src)[:300]
            lines.append(f"[{ts}] {msg}")
        return "\n".join(lines)
    except Exception as e:
        return f"ES 搜索失败：{e}"


@tool
async def es_get_index_mapping(index: str) -> str:
    """获取 Elasticsearch 索引的字段映射（mapping），了解索引结构和字段类型。
    index=索引名（必填）。"""
    import httpx
    base = _es_base_url()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base}/{index}/_mapping")
            resp.raise_for_status()
            data = resp.json()
        props = {}
        for idx_data in data.values():
            props.update(idx_data.get("mappings", {}).get("properties", {}))
        if not props:
            return f"索引 [{index}] 无 mapping 信息"
        lines = [f"**索引 [{index}] 字段映射（共 {len(props)} 个字段）**\n"]
        for field, info in list(props.items())[:50]:
            ftype = info.get("type", "object")
            lines.append(f"  {field}: {ftype}")
        if len(props) > 50:
            lines.append(f"  ... 共 {len(props)} 个字段，仅展示前 50 个")
        return "\n".join(lines)
    except Exception as e:
        return f"获取 ES mapping 失败：{e}"


# ── Jenkins CI/CD 工具 ─────────────────────────────────────────────────────────

def _jenkins_client():
    from jenkins_client import JenkinsClient
    import json, os
    from pathlib import Path
    cfg_file = Path(__file__).resolve().parent.parent / "data" / "jenkins.json"
    cfg = {}
    if cfg_file.exists():
        try:
            cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    url      = cfg.get("url")      or os.getenv("JENKINS_URL", "")
    username = cfg.get("username") or os.getenv("JENKINS_USERNAME", "")
    token    = cfg.get("token")    or os.getenv("JENKINS_TOKEN", "")
    if not url:
        return None, "Jenkins 未配置，请在系统设置中填写 Jenkins URL、用户名和 API Token"
    return JenkinsClient(url, username, token), None


@tool
async def jenkins_get_all_jobs() -> str:
    """获取 Jenkins 所有 Job 列表，包含最近构建状态。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        jobs = await client.get_all_jobs()
        if not jobs:
            return "Jenkins 中没有找到任何 Job"
        lines = [f"**Jenkins Job 列表（共 {len(jobs)} 个）**\n"]
        for j in jobs[:50]:
            color = j.get("color", "")
            status = {"blue": "✅成功", "red": "❌失败", "yellow": "⚠️不稳定", "notbuilt": "⭕未构建", "aborted": "⏹已中止"}.get(color, color)
            lb = j.get("lastBuild") or {}
            build_info = f"#{lb.get('number', '-')} {lb.get('result', '-')}" if lb else "无构建"
            lines.append(f"- **{j['name']}** {status} | 最近构建: {build_info}")
        if len(jobs) > 50:
            lines.append(f"\n... 共 {len(jobs)} 个 Job，仅展示前 50 个")
        return "\n".join(lines)
    except Exception as e:
        return f"获取 Job 列表失败：{e}"


@tool
async def jenkins_search_jobs(query: str) -> str:
    """按关键字搜索 Jenkins Job。query=搜索关键字（必填）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        jobs = await client.search_jobs(query)
        if not jobs:
            return f"未找到包含「{query}」的 Job"
        lines = [f"**搜索「{query}」结果（{len(jobs)} 个）**\n"]
        for j in jobs:
            lb = j.get("lastBuild") or {}
            lines.append(f"- **{j['name']}** | 最近构建: #{lb.get('number', '-')} {lb.get('result', '-')}")
        return "\n".join(lines)
    except Exception as e:
        return f"搜索失败：{e}"


@tool
async def jenkins_build_job(job: str, params: str = "") -> str:
    """触发 Jenkins Job 构建。
    job=Job名称（必填）。
    params=构建参数，格式为 JSON 字符串如 '{"BRANCH":"main","ENV":"prod"}'（可选）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        parsed_params = None
        if params.strip():
            import json
            parsed_params = json.loads(params)
        queue_id = await client.build_job(job, parsed_params)
        return f"✅ 已触发 Job **{job}** 构建，队列 ID: {queue_id}。可稍后用 jenkins_get_build_info 查询构建结果。"
    except Exception as e:
        return f"触发构建失败：{e}"


@tool
async def jenkins_get_build_info(job: str, build: str = "lastBuild") -> str:
    """获取 Jenkins Job 构建信息。
    job=Job名称（必填）。build=构建号，如 42 或 lastBuild（默认最新）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        info = await client.get_build_info(job, build)
        result = info.get("result") or "进行中"
        duration_s = info.get("duration", 0) // 1000
        ts = info.get("timestamp", 0) // 1000
        from datetime import datetime
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else "-"
        url = info.get("url", "")
        lines = [
            f"**{job} #{info.get('number', build)} 构建信息**",
            f"- 结果：{'✅ 成功' if result=='SUCCESS' else ('❌ 失败' if result=='FAILURE' else result)}",
            f"- 耗时：{duration_s}s",
            f"- 触发时间：{dt}",
            f"- 链接：{url}",
        ]
        causes = [c.get("shortDescription","") for a in info.get("actions",[]) for c in a.get("causes",[]) if a.get("causes")]
        if causes:
            lines.append(f"- 触发原因：{'; '.join(causes)}")
        return "\n".join(lines)
    except Exception as e:
        return f"获取构建信息失败：{e}"


@tool
async def jenkins_get_build_logs(job: str, build: str = "lastBuild", lines: int = 100) -> str:
    """获取 Jenkins 构建日志。
    job=Job名称（必填）。build=构建号或 lastBuild（默认最新）。lines=返回行数（默认100）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        log = await client.get_build_logs(job, build, lines)
        return f"**{job} #{build} 日志（末尾 {lines} 行）**\n\n```\n{log}\n```"
    except Exception as e:
        return f"获取日志失败：{e}"


@tool
async def jenkins_get_running_builds() -> str:
    """获取 Jenkins 当前正在运行的所有构建。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        builds = await client.get_running_builds()
        if not builds:
            return "当前没有正在运行的构建"
        lines = [f"**正在运行的构建（{len(builds)} 个）**\n"]
        for b in builds:
            eta = b.get("estimatedDuration", 0) // 1000
            lines.append(f"- **{b.get('job', '-')}** #{b.get('number', '-')} | 预估剩余 {eta}s")
        return "\n".join(lines)
    except Exception as e:
        return f"获取运行中构建失败：{e}"


@tool
async def jenkins_get_queue() -> str:
    """获取 Jenkins 构建队列（等待构建的任务）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        items = await client.get_queue_items()
        if not items:
            return "构建队列为空"
        lines = [f"**构建队列（{len(items)} 个）**\n"]
        for item in items:
            task = item.get("task", {})
            lines.append(f"- 队列 ID: {item.get('id')} | Job: {task.get('name', '-')} | 原因: {item.get('why', '-')}")
        return "\n".join(lines)
    except Exception as e:
        return f"获取队列失败：{e}"


@tool
async def jenkins_cancel_queue_item(queue_id: int) -> str:
    """取消 Jenkins 队列中等待的构建。queue_id=队列 ID（必填，从 jenkins_get_queue 中获取）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        ok = await client.cancel_queue_item(queue_id)
        return f"{'✅ 已取消' if ok else '❌ 取消失败'} 队列 ID {queue_id} 的构建"
    except Exception as e:
        return f"取消失败：{e}"


@tool
async def jenkins_get_test_results(job: str, build: str = "lastBuild") -> str:
    """获取 Jenkins 构建的测试报告（需要 JUnit/TestNG 插件）。
    job=Job名称（必填）。build=构建号或 lastBuild（默认最新）。"""
    client, err = _jenkins_client()
    if err:
        return err
    try:
        result = await client.get_test_results(job, build)
        total   = result.get("totalCount", 0)
        failed  = result.get("failCount", 0)
        skipped = result.get("skipCount", 0)
        passed  = total - failed - skipped
        lines = [
            f"**{job} #{build} 测试报告**",
            f"- 总计：{total} | ✅通过：{passed} | ❌失败：{failed} | ⏭跳过：{skipped}",
        ]
        if failed > 0:
            fail_cases = [s for s in result.get("suites", []) for c in s.get("cases", []) if c.get("status") in ("FAILED","REGRESSION")]
            for c in fail_cases[:5]:
                lines.append(f"  ❌ {c.get('className','')}.{c.get('name','')}")
            if len(fail_cases) > 5:
                lines.append(f"  ... 共 {len(fail_cases)} 个失败用例")
        return "\n".join(lines)
    except Exception as e:
        return f"获取测试报告失败（可能该构建无测试报告）：{e}"


ALL_TOOLS = [
    recall_similar_incidents,
    search_daily_reports,
    query_error_logs,
    count_errors_by_service,
    get_services_list,
    get_host_metrics,
    inspect_all_hosts,
    query_recent_logs,
    # K8s
    get_k8s_summary,
    get_k8s_pods,
    get_k8s_nodes,
    get_k8s_namespaces,
    get_k8s_deployments,
    get_k8s_services,
    # 中间件
    get_middleware_summary,
    get_middleware_instances,
    # ES 直连工具（绕过 MCP，直接查询 ES HTTP API）
    es_list_indices,
    es_cluster_health,
    es_search,
    es_get_index_mapping,
    # MCP
    list_available_mcps,
    list_k8s_mcp_tools,
    list_mcp_tools,
    call_k8s_mcp,
    call_mcp_tool,
    # Jenkins CI/CD
    jenkins_get_all_jobs,
    jenkins_search_jobs,
    jenkins_build_job,
    jenkins_get_build_info,
    jenkins_get_build_logs,
    jenkins_get_running_builds,
    jenkins_get_queue,
    jenkins_cancel_queue_item,
    jenkins_get_test_results,
]
