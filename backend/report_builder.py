"""报告数据采集 + 元数据构建的公共函数

Router（SSE 流式）和 Scheduler（非流式）共用同一套数据采集逻辑，
避免两处分别维护导致行为不一致。
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone, date as date_cls, timedelta
from typing import Optional

from state import loki, prom, analyzer, load_hosts_list, load_groups

logger = logging.getLogger(__name__)


# ── 运维日报 ──────────────────────────────────────────────────────────────────

_ERROR_KEYWORD_PATTERNS = [
    ("OutOfMemoryError", re.compile(r"\bOutOfMemoryError\b", re.I)),
    ("NullPointerException", re.compile(r"\bNullPointerException\b", re.I)),
    ("SQL异常", re.compile(r"\b(?:SQLException|SQLSyntaxErrorException|deadlock)\b", re.I)),
    ("连接超时", re.compile(r"\b(?:connect(?:ion)? timed? out|connection timeout)\b", re.I)),
    ("请求超时", re.compile(r"\b(?:read timed? out|request timeout|timeout)\b", re.I)),
    ("连接拒绝", re.compile(r"\b(?:connection refused|connect refused)\b", re.I)),
    ("连接重置", re.compile(r"\b(?:connection reset|broken pipe)\b", re.I)),
    ("HTTP 5xx", re.compile(r"\b5\d\d\b")),
    ("认证失败", re.compile(r"\b(?:unauthorized|forbidden|authentication failed)\b", re.I)),
    ("资源不足", re.compile(r"\b(?:too many open files|no space left|resource exhausted)\b", re.I)),
]
_EXCEPTION_RE = re.compile(r"\b([A-Z][A-Za-z0-9_.]*(?:Exception|Error))\b")


def _log_service(log: dict) -> str:
    labels = log.get("labels") or {}
    return str(
        log.get("service")
        or labels.get("app")
        or labels.get("application")
        or labels.get("service")
        or labels.get("job")
        or "未标记服务"
    )


def _log_line(log: dict) -> str:
    return str(log.get("line") or log.get("message") or "")


def _extract_error_keyword(line: str) -> str:
    for label, pattern in _ERROR_KEYWORD_PATTERNS:
        if pattern.search(line):
            return label
    match = _EXCEPTION_RE.search(line)
    if match:
        return match.group(1).split(".")[-1]
    return "其他错误"


def _keyword_action(keyword: str) -> str:
    if keyword in {"连接超时", "请求超时", "连接拒绝", "连接重置"}:
        return "优先检查下游依赖、网络连通性与连接池"
    if keyword in {"OutOfMemoryError", "资源不足"}:
        return "优先检查资源水位、容量限制与泄漏风险"
    if keyword in {"SQL异常"}:
        return "优先检查数据库可用性、SQL 兼容性与事务锁"
    if keyword in {"HTTP 5xx"}:
        return "优先结合接口 5xx 与调用链定位失败入口"
    return "建议结合代表性日志与调用链确认根因"


def summarize_service_errors(
    error_counts: dict[str, int],
    error_logs: list[dict],
) -> tuple[list[dict], list[dict]]:
    """生成每个微服务一句话摘要，以及跨服务高频错误关键字统计。"""
    service_keywords: dict[str, Counter] = defaultdict(Counter)
    keyword_services: dict[str, set[str]] = defaultdict(set)
    keyword_counts: Counter = Counter()

    for log in error_logs:
        service = _log_service(log)
        keyword = _extract_error_keyword(_log_line(log))
        service_keywords[service][keyword] += 1
        keyword_counts[keyword] += 1
        keyword_services[keyword].add(service)

    service_names = list(error_counts)
    for service in service_keywords:
        if service not in service_names:
            service_names.append(service)

    summaries = []
    for service in service_names:
        keywords = [item for item, _ in service_keywords.get(service, Counter()).most_common(3)]
        if keywords:
            keyword_text = "、".join(keywords)
            sentence = f"{service} 主要出现 {keyword_text}，{_keyword_action(keywords[0])}。"
        else:
            keyword_text = "缺少代表性样本"
            sentence = f"{service} 检测到异常但当前样本不足，建议补充日志采样后确认根因。"
        summaries.append({
            "service": service,
            "keywords": keywords,
            "summary": sentence,
        })

    keyword_stats = [
        {
            "keyword": keyword,
            "count": count,
            "services": sorted(keyword_services[keyword]),
        }
        for keyword, count in keyword_counts.most_common(10)
    ]
    return summaries, keyword_stats


async def collect_interface_status(hours: int = 24) -> dict:
    """从 http_server 指标生成日报用接口健康概览；无指标时明确标记未采集。"""
    window = f"{max(1, min(int(hours), 168))}h"
    labels = "application,app,service,uri,method"
    metric = "http_server_requests_seconds_count"
    bucket = "http_server_requests_seconds_bucket"
    queries = {
        "requests": f"sum by ({labels}) (increase({metric}[{window}]))",
        "errors": f'sum by ({labels}) (increase({metric}{{status=~"5.."}}[{window}]))',
        "p95": (
            f"histogram_quantile(0.95, sum by (le,{labels}) "
            f"(rate({bucket}[5m]))) * 1000"
        ),
    }

    async def safe_query(query: str) -> list[dict]:
        try:
            return await prom.query_instant(query, timeout=20)
        except Exception as exc:
            logger.warning("[report_builder][interface] query failed: %s", exc)
            return []

    request_rows, error_rows, p95_rows = await asyncio.gather(
        safe_query(queries["requests"]),
        safe_query(queries["errors"]),
        safe_query(queries["p95"]),
    )

    def row_key(item: dict) -> tuple[str, ...]:
        metric_labels = item.get("metric") or {}
        return tuple(str(metric_labels.get(label) or "") for label in labels.split(","))

    rows: dict[tuple[str, ...], dict] = {}

    def merge(items: list[dict], field: str) -> None:
        for item in items:
            key = row_key(item)
            labels_dict = item.get("metric") or {}
            row = rows.setdefault(key, {
                "application": (
                    labels_dict.get("application")
                    or labels_dict.get("app")
                    or labels_dict.get("service")
                    or "-"
                ),
                "uri": labels_dict.get("uri") or "-",
                "method": labels_dict.get("method") or "-",
            })
            try:
                row[field] = float((item.get("value") or [None, 0])[1])
            except (TypeError, ValueError, IndexError):
                row[field] = 0.0

    merge(request_rows, "requests")
    merge(error_rows, "errors")
    merge(p95_rows, "p95_ms")

    result_rows = []
    severity = {"normal": 0, "warning": 1, "critical": 2}
    overall = "normal"
    for row in rows.values():
        requests = float(row.get("requests") or 0)
        errors = float(row.get("errors") or 0)
        ratio = round(errors / requests * 100, 2) if requests > 0 else 0.0
        p95 = round(float(row.get("p95_ms") or 0), 1)
        status = (
            "critical" if ratio >= 5 or p95 >= 2000
            else "warning" if ratio >= 1 or p95 >= 1000
            else "normal"
        )
        row.update({
            "request_count": round(requests),
            "error_ratio": ratio,
            "p95_ms": p95,
            "status": status,
        })
        result_rows.append(row)
        if severity[status] > severity[overall]:
            overall = status

    result_rows.sort(
        key=lambda item: (
            severity[item["status"]],
            item["error_ratio"],
            item["p95_ms"],
        ),
        reverse=True,
    )
    return {
        "available": bool(request_rows or error_rows or p95_rows),
        "status": overall if result_rows else "unknown",
        "monitored_interfaces": len(result_rows),
        "abnormal_interfaces": sum(1 for row in result_rows if row["status"] != "normal"),
        "rows": result_rows[:20],
    }


async def collect_daily_data() -> dict:
    """采集运维日报所需原始数据，返回包含 meta 和 ai_inputs 的字典。"""
    error_counts = await loki.count_errors_by_service(hours=24)
    error_logs   = await loki.query_error_logs(hours=24, limit=1000)
    services     = await loki.get_services()

    total_error_count = sum(error_counts.values())
    total_logs        = total_error_count * 8   # 估算：错误日志约占总量 1/8
    active_alerts     = len(error_counts)       # 有错误的服务数

    service_summaries, error_keywords = summarize_service_errors(error_counts, error_logs)
    interface_status = await collect_interface_status(hours=24)

    try:
        hosts = await prom.discover_hosts()
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
        "service_error_summaries": service_summaries,
        "error_keywords": error_keywords,
        "interface_status": interface_status,
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
        "service_error_summaries": service_summaries,
        "error_keywords": error_keywords,
        "interface_status": interface_status,
    }


# ── 主机巡检日报 ──────────────────────────────────────────────────────────────

def _extract_result_ip(result: dict) -> str:
    return (result.get("ip") or result.get("instance", "").split(":")[0]).strip()


def _build_missing_host_result(host: dict, fallback_error: str = "") -> dict:
    ip = (host.get("ip") or "").strip()
    return {
        "instance": f"{ip}:9100",
        "ip": ip,
        "hostname": host.get("hostname") or ip,
        "os": host.get("os_version") or host.get("platform", ""),
        "job": "",
        "state": "missing",
        "group": host.get("group", ""),
        "env": host.get("env", ""),
        "overall": "warning",
        "checks": [{
            "item": "Prometheus 数据",
            "value": "无指标",
            "status": "warning",
            "threshold": "需要安装 node_exporter 或检查 Prometheus 配置",
        }, {
            "item": "SSH/Python 兜底",
            "value": fallback_error or "未获取到指标",
            "status": "warning",
            "threshold": "请检查 SSH 凭证、网络连通性和目标主机 Python/shell 环境",
        }],
        "metrics": {},
        "partitions": [],
        "metrics_source": "missing",
    }


def _build_host_brief(result: dict) -> dict:
    metrics = result.get("metrics") or {}
    return {
        "instance":   result.get("instance", ""),
        "hostname":   result.get("hostname") or result.get("instance", ""),
        "ip":         result.get("ip", ""),
        "os":         result.get("os", ""),
        "job":        result.get("job", ""),
        "state":      result.get("state", ""),
        "group":      result.get("group", ""),
        "group_name": result.get("group_name", ""),
        "env":        result.get("env", ""),
        "role":       result.get("role", ""),
        "owner":      result.get("owner", ""),
        "datacenter": result.get("datacenter", ""),
        "overall":    result.get("overall", "normal"),
        "cpu_pct":    metrics.get("cpu_usage"),
        "cpu_cores":  result.get("cpu_cores"),
        "mem_pct":    metrics.get("mem_usage"),
        "mem_total":  metrics.get("mem_total_gb") or result.get("memory_gb"),
        "load1":      metrics.get("load1"),
        "load5":      metrics.get("load5"),
        "load15":     metrics.get("load15"),
        "net_recv":   metrics.get("net_recv_mbps"),
        "net_send":   metrics.get("net_send_mbps"),
        "disk_read":  metrics.get("disk_read_mbps"),
        "disk_write": metrics.get("disk_write_mbps"),
        "tcp_estab":  metrics.get("tcp_estab"),
        "tcp_tw":     metrics.get("tcp_tw"),
        "uptime_s":   metrics.get("uptime_seconds"),
        "checks":     result.get("checks", []),
        "partitions": result.get("partitions", []),
        "process_top10": result.get("process_top10", []),
        "process_error": result.get("process_error", ""),
        "metrics_source": result.get("metrics_source", "prometheus"),
    }


def _build_scope_note(cmdb_total: int, extra_count: int, fallback_count: int = 0) -> str:
    note = f"统计口径：按 CMDB 主机 {cmdb_total} 台统计，正常/警告/严重数量均以 CMDB 主机为基准。"
    if fallback_count:
        note += f" Prometheus 无指标时已对 {fallback_count} 台主机执行 SSH/Python 兜底采集。"
    if extra_count:
        note += f" Prometheus 额外发现 {extra_count} 个非 CMDB 实例（通常为容器 IP 或临时节点），已单独列出且不计入上方统计。"
    return note


async def _collect_process_top10(hosts: list[dict]) -> dict[str, dict]:
    """并发采集巡检表格所需的 Top 10 进程；单机失败不影响整份报告。"""
    if not hosts:
        return {}
    from routers.hosts import _read_host_processes, _ssh_error_msg

    sem = asyncio.Semaphore(5)

    async def collect_one(host: dict) -> tuple[str, dict]:
        ip = str(host.get("ip") or "").strip()
        if not ip:
            return "", {"data": [], "error": "未配置 IP"}
        if not (host.get("credential_id") or host.get("ssh_password")):
            return ip, {"data": [], "error": "未配置 SSH 凭证"}
        async with sem:
            try:
                return ip, {
                    "data": await _read_host_processes(
                        host,
                        limit=10,
                        prioritize_services=False,
                    ),
                    "error": "",
                }
            except Exception as exc:
                return ip, {"data": [], "error": _ssh_error_msg(exc, host)}

    pairs = await asyncio.gather(*(collect_one(host) for host in hosts))
    return {ip: payload for ip, payload in pairs if ip}


async def collect_inspect_data(
    instances: Optional[list] = None,
    group_id: str = "",
    group_name: str = "",
) -> dict:
    """采集主机巡检所需数据，按 CMDB 主机口径返回结果。"""
    all_cmdb_hosts = [host for host in load_hosts_list() if host.get("ip")]
    target_hosts = all_cmdb_hosts
    if group_id:
        target_hosts = [host for host in target_hosts if host.get("group") == group_id]
    if instances is not None:
        wanted_ips = {str(item).split(":")[0].strip() for item in instances if str(item).strip()}
        target_hosts = [host for host in target_hosts if (host.get("ip") or "").strip() in wanted_ips]

    try:
        prom_results = await prom.inspect_hosts(instances=None)
    except Exception as e:
        logger.warning("[report_builder] 巡检数据获取失败: %s", e)
        prom_results = []

    prom_map: dict[str, dict] = {}
    for result in prom_results:
        ip = _extract_result_ip(result)
        if ip and ip not in prom_map:
            prom_map[ip] = result

    missing_hosts = [host for host in target_hosts if (host.get("ip") or "").strip() not in prom_map]
    fallback_map: dict[str, dict] = {}

    async def collect_fallbacks() -> dict[str, dict]:
        if not missing_hosts:
            return {}
        try:
            from routers.hosts import _collect_inspection_fallbacks
            return await _collect_inspection_fallbacks(missing_hosts)
        except Exception as e:
            logger.warning("[report_builder] SSH/Python 兜底采集失败: %s", e)
            return {}

    fallback_map, process_map = await asyncio.gather(
        collect_fallbacks(),
        _collect_process_top10(target_hosts),
    )

    group_names = {
        str(group.get("id") or ""): str(group.get("name") or "")
        for group in load_groups()
    }

    results: list[dict] = []
    cmdb_ips = {(host.get("ip") or "").strip() for host in target_hosts if host.get("ip")}
    for host in target_hosts:
        ip = (host.get("ip") or "").strip()
        if not ip:
            continue
        if ip in prom_map:
            merged = dict(prom_map[ip])
            merged["hostname"] = host.get("hostname") or merged.get("hostname") or ip
            merged["os"] = host.get("os_version") or merged.get("os") or host.get("platform", "")
            merged["cpu_cores"] = host.get("cpu_cores") or merged.get("cpu_cores")
            merged["memory_gb"] = host.get("memory_gb") or merged.get("memory_gb")
            merged["disk_gb"] = host.get("disk_gb") or merged.get("disk_gb")
            merged["group"] = host.get("group", "")
            merged["env"] = host.get("env", "")
            merged["metrics_source"] = merged.get("metrics_source", "prometheus")
            selected = merged
        elif fallback_map.get(ip, {}).get("ok") and fallback_map[ip].get("result"):
            selected = dict(fallback_map[ip]["result"])
        else:
            fallback_error = fallback_map.get(ip, {}).get("error", "")
            selected = _build_missing_host_result(host, fallback_error=fallback_error)

        group_key = str(host.get("group") or "")
        process_payload = process_map.get(ip, {})
        selected.update({
            "group": group_key,
            "group_name": group_names.get(group_key) or "未分组",
            "env": host.get("env", ""),
            "role": host.get("role", ""),
            "owner": host.get("owner", ""),
            "datacenter": host.get("datacenter", ""),
            "process_top10": process_payload.get("data", []),
            "process_error": process_payload.get("error", ""),
        })
        results.append(selected)

    extra_prometheus_hosts: list[dict] = []
    if not group_id and instances is None:
        extras_by_ip: dict[str, dict] = {}
        for result in prom_results:
            ip = _extract_result_ip(result)
            if not ip or ip in cmdb_ips or ip in extras_by_ip:
                continue
            extras_by_ip[ip] = _build_host_brief({
                **result,
                "group": "",
                "env": "",
            })
        extra_prometheus_hosts = sorted(
            extras_by_ip.values(),
            key=lambda item: (
                {"critical": 2, "warning": 1}.get(item.get("overall", "normal"), 0),
                item.get("ip", ""),
            ),
            reverse=True,
        )

    results.sort(
        key=lambda item: {"critical": 2, "warning": 1}.get(item.get("overall", "normal"), 0),
        reverse=True,
    )

    summary = {
        "total":    len(results),
        "normal":   sum(1 for r in results if r.get("overall") == "normal"),
        "warning":  sum(1 for r in results if r.get("overall") == "warning"),
        "critical": sum(1 for r in results if r.get("overall") == "critical"),
        "cmdb_total": len(results),
        "prometheus_extra_count": len(extra_prometheus_hosts),
        "scope": "cmdb",
        "metrics_updated_count": sum(1 for r in results if r.get("metrics") or r.get("partitions")),
        "metrics_fallback_count": sum(1 for r in results if r.get("metrics_source") == "ssh_python"),
        "metrics_missing_count": sum(1 for r in results if not (r.get("metrics") or r.get("partitions"))),
    }
    if group_name:
        summary["group_name"] = group_name
    summary["scope_note"] = _build_scope_note(
        summary["cmdb_total"],
        summary["prometheus_extra_count"],
        summary["metrics_fallback_count"],
    )

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

    all_hosts_brief = [_build_host_brief(result) for result in results]
    severity = {"critical": 2, "warning": 1, "normal": 0}
    grouped: dict[str, list[dict]] = defaultdict(list)
    for host in all_hosts_brief:
        grouped[host.get("group_name") or "未分组"].append(host)
    group_sections = []
    for name, hosts in grouped.items():
        hosts.sort(
            key=lambda item: (
                severity.get(item.get("overall", "normal"), 0),
                item.get("ip", ""),
            ),
            reverse=True,
        )
        group_sections.append({
            "group_name": name,
            "total": len(hosts),
            "critical": sum(1 for item in hosts if item.get("overall") == "critical"),
            "warning": sum(1 for item in hosts if item.get("overall") == "warning"),
            "normal": sum(1 for item in hosts if item.get("overall") == "normal"),
            "hosts": hosts,
        })
    group_sections.sort(
        key=lambda item: (item["critical"], item["warning"], item["total"]),
        reverse=True,
    )

    health_score = await analyzer.calculate_host_health_score(summary)

    return {
        "results":       results,
        "summary":       summary,
        "top_issues":    [{"item": k, "count": v} for k, v in top_issues],
        "abnormal_hosts": abnormal_hosts[:20],
        "all_hosts":     all_hosts_brief,
        "group_sections": group_sections,
        "prometheus_extra_hosts": extra_prometheus_hosts,
        "scope_note":    summary["scope_note"],
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
        "group_sections": data.get("group_sections", []),
        "prometheus_extra_hosts": data.get("prometheus_extra_hosts", []),
        "prometheus_extra_count": len(data.get("prometheus_extra_hosts", [])),
        "summary_scope_note": data.get("scope_note", ""),
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
    for result in host_results:
        result["status"] = (
            "critical" if result["max_query_time"] >= alert_sec or result["alert_count"] > 0
            else "warning" if result["total"] > 0
            else "normal"
        )
    host_results.sort(
        key=lambda item: (
            item["status"] == "critical",
            item["alert_count"],
            item["max_query_time"],
        ),
        reverse=True,
    )

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
        health_score = 60 if errors else 100
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
        "threshold_sec":  threshold_sec,
        "alert_sec":      alert_sec,
        "total_queries":  total_queries,
        "alert_queries":  alert_queries,
        "avg_query_time": round(avg_qt, 2),
        "max_query_time": round(max_qt, 3),
        "hosts_count":    len(host_results),
        "critical_hosts": sum(1 for r in host_results if r["status"] == "critical"),
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

    prompt = f"""你是 MySQL 数据库性能专家，请基于以下慢查询结果给出可执行的优化报告。

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
**请按结果优先的结构输出**：
1. 直接结论：用 2-3 句话说明问题等级、主要瓶颈和是否需要立即处理
2. 优先级清单：P0/P1/P2 排序，明确主机 IP、SQL 模板和判断依据
3. SQL 优化方案：逐个重点模板给出索引建议、改写方向和 EXPLAIN 验证项；信息不足时明确写“需补充表结构/执行计划”，不要臆造字段
4. 主机级结论：每台主机一句话，先列告警主机
5. 验证与回滚：说明优化后的观测指标、验证方法和回滚条件

使用中文输出，格式清晰，避免复述目标配置和大段统计数字，把篇幅集中在慢 SQL 结果、根因与处理动作。"""
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
