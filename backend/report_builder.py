"""报告数据采集 + 元数据构建的公共函数

Router（SSE 流式）和 Scheduler（非流式）共用同一套数据采集逻辑，
避免两处分别维护导致行为不一致。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, date as date_cls, timedelta
from typing import Optional

from state import loki, prom, analyzer

logger = logging.getLogger(__name__)


# ── 运维日报 ──────────────────────────────────────────────────────────────────

async def collect_daily_data() -> dict:
    """采集运维日报所需原始数据，返回包含 meta 和 ai_inputs 的字典。"""
    error_counts = await loki.count_errors_by_service(hours=24)
    error_logs   = await loki.query_error_logs(hours=24, limit=1000)
    services     = await loki.get_services()

    total_error_count = sum(error_counts.values())
    total_logs        = total_error_count * 8   # 估算：错误日志约占总量 1/8
    active_alerts     = len(error_counts)       # 有错误的服务数

    try:
        hosts       = await prom.discover_hosts()
        node_normal = sum(1 for h in hosts if h.get("state") == "up")
        node_status = {"normal": node_normal, "abnormal": len(hosts) - node_normal}
    except Exception:
        node_status = {"normal": 0, "abnormal": 0}

    health_score = await analyzer.calculate_health_score(
        total_logs, total_error_count, active_alerts, node_status["abnormal"]
    )

    now       = datetime.now(timezone.utc)
    report_id = now.strftime("%Y%m%d%H%M%S")

    meta = {
        "id":            report_id,
        "type":          "daily",
        "title":         f"运维日报 {now.strftime('%Y-%m-%d')}",
        "created_at":    now.isoformat(),
        "health_score":  health_score,
        "total_logs":    total_logs,
        "total_errors":  total_error_count,
        "service_count": len(services),
        "active_alerts": active_alerts,
        "node_status":   node_status,
        "top10_errors":  [
            {"service": k, "count": v}
            for k, v in list(error_counts.items())[:10]
        ],
    }

    return {
        "meta":          meta,
        "error_counts":  error_counts,
        "error_logs":    error_logs,
        "total_logs":    total_logs,
        "service_count": len(services),
        "node_status":   node_status,
        "active_alerts": active_alerts,
    }


# ── 主机巡检日报 ──────────────────────────────────────────────────────────────

async def collect_inspect_data(instances: Optional[list] = None) -> dict:
    """采集主机巡检所需数据，返回 results + summary + meta_base。"""
    try:
        results = await prom.inspect_hosts(instances=instances)
    except Exception as e:
        logger.warning("[report_builder] 巡检数据获取失败: %s", e)
        results = []

    summary = {
        "total":    len(results),
        "normal":   sum(1 for r in results if r.get("overall") == "normal"),
        "warning":  sum(1 for r in results if r.get("overall") == "warning"),
        "critical": sum(1 for r in results if r.get("overall") == "critical"),
    }

    issue_cnt: dict[str, int] = {}
    for r in results:
        for c in r.get("checks", []):
            if c.get("status") != "normal":
                key = c.get("item", "未知")
                issue_cnt[key] = issue_cnt.get(key, 0) + 1
    top_issues = sorted(issue_cnt.items(), key=lambda x: x[1], reverse=True)[:10]

    abnormal_hosts = sorted(
        [r for r in results if r.get("overall") != "normal"],
        key=lambda r: {"critical": 2, "warning": 1}.get(r.get("overall", "normal"), 0),
        reverse=True,
    )

    all_hosts_brief = []
    for r in results:
        m = r.get("metrics") or {}
        all_hosts_brief.append({
            "hostname":   r.get("hostname") or r.get("instance", ""),
            "ip":         r.get("ip", ""),
            "os":         r.get("os", ""),
            "state":      r.get("state", ""),
            "overall":    r.get("overall", "normal"),
            "cpu_pct":    m.get("cpu_usage"),
            "mem_pct":    m.get("mem_usage"),
            "mem_total":  m.get("mem_total_gb"),
            "load5":      m.get("load5"),
            "net_recv":   m.get("net_recv_mbps"),
            "net_send":   m.get("net_send_mbps"),
            "tcp_estab":  m.get("tcp_estab"),
            "uptime_s":   m.get("uptime_seconds"),
            "checks":     r.get("checks", []),
            "partitions": r.get("partitions", []),
        })

    health_score = await analyzer.calculate_host_health_score(summary)

    return {
        "results":       results,
        "summary":       summary,
        "top_issues":    [{"item": k, "count": v} for k, v in top_issues],
        "abnormal_hosts": abnormal_hosts[:20],
        "all_hosts":     all_hosts_brief,
        "health_score":  health_score,
    }


def build_inspect_meta(
    data: dict,
    group_id: str = "",
    group_name: str = "",
) -> dict:
    """用 collect_inspect_data() 的结果构建报告 meta dict。"""
    now       = datetime.now(timezone.utc)
    suffix    = f"_{group_id}" if group_id else ""
    report_id = "inspect_" + now.strftime("%Y%m%d%H%M%S") + suffix
    title_tag = f"【{group_name}】" if group_name else ""

    return {
        "id":             report_id,
        "type":           "inspect",
        "group_id":       group_id,
        "group_name":     group_name,
        "title":          f"主机巡检日报{title_tag} {now.strftime('%Y-%m-%d')}",
        "created_at":     now.isoformat(),
        "health_score":   data["health_score"],
        "host_summary":   data["summary"],
        "top_issues":     data["top_issues"],
        "abnormal_hosts": data["abnormal_hosts"],
        "all_hosts":      data["all_hosts"],
    }


# ── 慢日志报告 ────────────────────────────────────────────────────────────────

async def collect_slowlog_data(config: dict) -> dict | None:
    """SSH 采集所有目标主机慢日志，返回聚合数据；未配置或采集失败返回 None。"""
    from slow_log_parser import parse_slow_log, build_summary
    from sql_cluster import cluster_slow_queries
    from routers.slowlog import _read_remote_file, _resolve_credential

    if not config.get("targets"):
        return None

    date_days     = max(1, int(config.get("date_days", 1)))
    threshold_sec = float(config.get("threshold_sec", 1.0))
    alert_sec     = float(config.get("alert_sec", 10.0))
    today         = date_cls.today()
    date_from     = (today - timedelta(days=date_days - 1)).strftime("%Y-%m-%d")
    date_to       = today.strftime("%Y-%m-%d")

    host_results: list[dict] = []
    all_entries:  list[dict] = []
    errors:       list[dict] = []

    for t in config["targets"]:
        host_ip  = (t.get("host_ip") or "").strip()
        log_path = t.get("log_path") or "/mysqldata/mysql/data/3306/mysql-slow.log"
        if not host_ip:
            continue
        try:
            username, password, host, port = _resolve_credential(
                host_ip,
                credential_id=t.get("credential_id", ""),
                username=t.get("ssh_user", ""),
                password=t.get("ssh_password", ""),
                port=int(t.get("ssh_port", 22)),
            )
            text    = await _read_remote_file(host, port, username, password, log_path,
                                              date_from=date_from)
            entries = parse_slow_log(
                text, date_from=date_from, date_to=date_to,
                threshold_sec=threshold_sec, alert_sec=alert_sec,
            )
            try:
                clusters = cluster_slow_queries(entries)
            except Exception:
                clusters = []
            s = build_summary(entries)
            for e in entries:
                all_entries.append({**e, "_host_ip": host_ip})
            host_results.append({
                "host_ip":        host_ip,
                "total":          s.get("total", 0),
                "alert_count":    s.get("alert_count", 0),
                "avg_query_time": s.get("avg_query_time", 0),
                "max_query_time": s.get("max_query_time", 0),
                "top_clusters": [
                    {k: c[k] for k in
                     ("rank", "template", "count", "total_time", "avg_time", "max_time", "alert_count")
                     if k in c}
                    for c in clusters[:5]
                ],
            })
        except Exception as e:
            logger.warning("[report_builder][slowlog] %s 失败: %s", host_ip, e)
            errors.append({"host_ip": host_ip, "error": str(e)})

    total_queries = sum(r["total"] for r in host_results)
    alert_queries = sum(r["alert_count"] for r in host_results)
    avg_qt = (
        sum(r["avg_query_time"] * r["total"] for r in host_results) / total_queries
        if total_queries else 0.0
    )
    max_qt = max((r["max_query_time"] for r in host_results), default=0.0)

    top_slow_brief = [
        {
            "host_ip":       e.get("_host_ip", ""),
            "query_time":    e.get("query_time", 0),
            "rows_examined": e.get("rows_examined", 0),
            "sql_brief":     e.get("sql", "")[:200],
        }
        for e in sorted(all_entries, key=lambda e: e.get("query_time", 0), reverse=True)[:10]
    ]

    # 健康评分
    if total_queries == 0:
        health_score = 50
    else:
        deduct = 0
        ratio = alert_queries / total_queries
        if ratio > 0.3:   deduct += 40
        elif ratio > 0.1: deduct += 20
        if max_qt > 60:   deduct += 20
        elif max_qt > 30: deduct += 10
        if avg_qt > 10:   deduct += 15
        elif avg_qt > 5:  deduct += 8
        health_score = max(0, 100 - deduct)

    now = datetime.now(timezone.utc)
    return {
        "id":             "slowlog_" + now.strftime("%Y%m%d%H%M%S"),
        "type":           "slowlog",
        "title":          f"MySQL 慢日志报告 {now.strftime('%Y-%m-%d')}",
        "created_at":     now.isoformat(),
        "health_score":   health_score,
        "date_from":      date_from,
        "date_to":        date_to,
        "total_queries":  total_queries,
        "alert_queries":  alert_queries,
        "avg_query_time": round(avg_qt, 2),
        "max_query_time": round(max_qt, 3),
        "hosts_count":    len(host_results),
        "host_results":   host_results,
        "top_slow":       top_slow_brief,
        "errors":         errors,
        # 供 AI prompt 使用的中间数据
        "_all_entries":   all_entries,
        "_threshold_sec": threshold_sec,
        "_alert_sec":     alert_sec,
    }


def build_slowlog_ai_prompt(data: dict) -> str:
    """基于 collect_slowlog_data() 的结果构建 AI 分析 prompt（共用于 router 和 scheduler）。"""
    host_results   = data["host_results"]
    top_slow_brief = data["top_slow"]
    total_queries  = data["total_queries"]
    alert_queries  = data["alert_queries"]
    avg_qt         = data["avg_query_time"]
    max_qt         = data["max_query_time"]
    date_from      = data["date_from"]
    date_to        = data["date_to"]
    threshold_sec  = data.get("_threshold_sec", 1.0)
    alert_sec      = data.get("_alert_sec", 10.0)
    all_entries    = data.get("_all_entries", [])

    prompt = f"""你是 MySQL 数据库性能专家，请分析以下慢查询汇总并给出优化建议。

**报告概况**
- 分析时间段：{date_from} ~ {date_to}
- 分析主机数：{len(host_results)} 台
- 慢查询总数：{total_queries}（≥{threshold_sec}s）
- 告警数（≥{alert_sec}s）：{alert_queries}
- 平均耗时：{round(avg_qt, 2)}s
- 最大耗时：{round(max_qt, 2)}s

**各主机情况**
"""
    for hr in host_results:
        prompt += (
            f"- {hr['host_ip']}：{hr['total']} 条慢查询，"
            f"{hr['alert_count']} 条告警，最大耗时 {hr['max_query_time']}s\n"
        )

    if top_slow_brief:
        prompt += "\n**TOP 10 最慢查询**\n"
        for i, s in enumerate(top_slow_brief, 1):
            sql_preview = s["sql_brief"][:200] + ("..." if len(s["sql_brief"]) >= 200 else "")
            prompt += (
                f"\n[{i}] 主机={s['host_ip']} 耗时={s['query_time']}s "
                f"扫描行={s['rows_examined']}\n"
                f"SQL: {sql_preview}\n"
            )

    # 跨主机聚合模板
    all_clusters: list[dict] = []
    for hr in host_results:
        for c in hr.get("top_clusters", [])[:3]:
            all_clusters.append({**c, "host_ip": hr["host_ip"]})
    all_clusters.sort(key=lambda x: x.get("total_time", 0), reverse=True)
    if all_clusters:
        prompt += "\n**SQL 模板聚合 Top（按总耗时排序）**\n"
        for i, c in enumerate(all_clusters[:8], 1):
            prompt += (
                f"\n[{i}] {c['host_ip']} 出现 {c['count']} 次，"
                f"总耗时 {c['total_time']}s，单次最大 {c['max_time']}s\n"
                f"模板: {c['template'][:200]}\n"
            )

    prompt += """
**请按以下结构输出分析报告**：
1. 整体评估（问题等级：严重/警告/正常）
2. 主要问题分析（高频/高耗时 SQL 的根因）
3. 具体优化建议（加索引、改写 SQL、分页、缓存等可操作方案）
4. 各主机重点关注事项
5. 优先处理顺序

使用中文输出，格式清晰，给出可操作的建议。"""
    return prompt


def build_slowlog_ai_prompt_short(data: dict) -> str:
    """简短版 prompt，用于定时推送（控制 token 用量）。"""
    host_results   = data["host_results"]
    top_slow_brief = data["top_slow"]
    total_queries  = data["total_queries"]
    alert_queries  = data["alert_queries"]
    avg_qt         = data["avg_query_time"]
    max_qt         = data["max_query_time"]
    date_from      = data["date_from"]
    date_to        = data["date_to"]

    prompt = (
        f"你是 MySQL 数据库性能专家，请简要分析以下慢查询汇总并给出优化建议。\n"
        f"时间段：{date_from} ~ {date_to}，主机 {len(host_results)} 台，"
        f"慢查询 {total_queries} 条，告警 {alert_queries} 条，"
        f"平均耗时 {round(avg_qt, 2)}s，最大耗时 {round(max_qt, 1)}s。\n"
    )
    for hr in host_results:
        prompt += f"- {hr['host_ip']}：{hr['total']} 条，{hr['alert_count']} 告警\n"
    if top_slow_brief:
        prompt += "\nTOP 5：\n"
        for i, s in enumerate(top_slow_brief[:5], 1):
            prompt += f"[{i}] {s['host_ip']} {s['query_time']}s  SQL: {s['sql_brief'][:150]}\n"
    prompt += "\n请给出整体评估和关键优化建议（200字以内）。使用中文。"
    return prompt
