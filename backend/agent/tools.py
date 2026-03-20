"""LangGraph Agent 工具集 — 封装 Loki / Prometheus 客户端"""
import glob
import json
import os
from datetime import datetime

from langchain_core.tools import tool
from state import loki, prom

_REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")


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


ALL_TOOLS = [
    recall_similar_incidents,
    search_daily_reports,
    query_error_logs,
    count_errors_by_service,
    get_services_list,
    get_host_metrics,
    inspect_all_hosts,
    query_recent_logs,
]
