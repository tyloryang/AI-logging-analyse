"""LangGraph Agent 工具集 — 封装 Loki / Prometheus 客户端"""
import glob
import json
import os
from datetime import datetime

from langchain_core.tools import tool
from state import loki, prom

_REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")


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

        if mcp_type == "http":
            try:
                body = _json.loads(params) if params.strip() else {}
            except Exception:
                body = {"query": params}

            endpoint = url + ("/" + action.lstrip("/") if action else "")
            import httpx
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.post(endpoint, json=body)
                resp.raise_for_status()
                result = resp.text[:2000]
            return f"**MCP [{mcp['name']}] 返回结果**\n{result}"

        else:
            return f"MCP 类型 '{mcp_type}' 暂不支持在线调用（仅支持 http 类型）"

    except FileNotFoundError:
        return "agent_config.json 不存在，请先在智能体配置页面保存配置"
    except Exception as exc:
        return f"调用 MCP 失败：{exc}"


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
            lines.append(f"- {m['name']}  类型:{m.get('type','?')}  地址:{m.get('url','?')}")
        return "\n".join(lines)
    except Exception as exc:
        return f"读取 MCP 配置失败：{exc}"


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
    # 中间件
    get_middleware_summary,
    get_middleware_instances,
    # MCP
    list_available_mcps,
    call_mcp_tool,
]
