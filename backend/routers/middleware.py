"""中间件监控路由 — /api/middleware/*

通过 Prometheus 查询 MySQL / Redis / Kafka / Nginx / RabbitMQ 等中间件指标。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/middleware", tags=["middleware"])

# 支持的中间件类型及其 Prometheus job 匹配前缀
_MW_TYPES = {
    "mysql":     {"label": "MySQL",     "icon": "db",     "job_pattern": "mysql"},
    "redis":     {"label": "Redis",     "icon": "cache",  "job_pattern": "redis"},
    "kafka":     {"label": "Kafka",     "icon": "queue",  "job_pattern": "kafka"},
    "nginx":     {"label": "Nginx",     "icon": "web",    "job_pattern": "nginx"},
    "rabbitmq":  {"label": "RabbitMQ",  "icon": "queue",  "job_pattern": "rabbit"},
    "mongodb":   {"label": "MongoDB",   "icon": "db",     "job_pattern": "mongo"},
    "postgres":  {"label": "PostgreSQL","icon": "db",     "job_pattern": "postgres"},
    "elasticsearch": {"label": "Elasticsearch", "icon": "search", "job_pattern": "elastic"},
}


async def _safe_query(prom, query: str):
    try:
        return await prom.query_instant(query) or []
    except Exception:
        return []


@router.get("/instances")
async def list_instances():
    """返回 Prometheus 中发现的中间件实例列表及基础状态。"""
    from state import prom

    # 获取所有 targets 的 up 状态
    up_results = await _safe_query(prom, 'up')

    instances = []
    seen = set()
    for item in up_results:
        metric = item.get("metric", {})
        job    = metric.get("job", "")
        inst   = metric.get("instance", "")
        key    = f"{job}/{inst}"
        if key in seen:
            continue
        seen.add(key)

        # 匹配中间件类型
        mw_type = None
        for t, cfg in _MW_TYPES.items():
            if cfg["job_pattern"].lower() in job.lower():
                mw_type = t
                break
        if not mw_type:
            continue

        val = item.get("value", [None, "0"])
        status = "up" if str(val[-1]) == "1" else "down"
        instances.append({
            "id":       key,
            "type":     mw_type,
            "label":    _MW_TYPES[mw_type]["label"],
            "icon":     _MW_TYPES[mw_type]["icon"],
            "job":      job,
            "instance": inst,
            "status":   status,
            "statusClass": "ok" if status == "up" else "err",
        })

    instances.sort(key=lambda x: (x["type"], x["instance"]))
    return instances


@router.get("/metrics/{mw_type}")
async def get_metrics(mw_type: str):
    """查询指定中间件类型的关键指标。"""
    from state import prom

    cfg = _MW_TYPES.get(mw_type)
    if not cfg:
        return {"type": mw_type, "metrics": []}

    job_pattern = cfg["job_pattern"]

    metrics: list[dict] = []

    if mw_type == "mysql":
        queries = [
            ("QPS",         f'rate(mysql_global_status_queries{{job=~".*{job_pattern}.*"}}[5m])'),
            ("连接数",       f'mysql_global_status_threads_connected{{job=~".*{job_pattern}.*"}}'),
            ("慢查询/s",    f'rate(mysql_global_status_slow_queries{{job=~".*{job_pattern}.*"}}[5m])'),
            ("InnoDB缓存命中率", f'rate(mysql_global_status_innodb_buffer_pool_read_requests{{job=~".*{job_pattern}.*"}}[5m])'),
        ]
    elif mw_type == "redis":
        queries = [
            ("命令数/s",    f'rate(redis_commands_processed_total{{job=~".*{job_pattern}.*"}}[5m])'),
            ("连接客户端数", f'redis_connected_clients{{job=~".*{job_pattern}.*"}}'),
            ("内存使用MB",   f'redis_memory_used_bytes{{job=~".*{job_pattern}.*"}} / 1024 / 1024'),
            ("缓存命中率",   f'redis_keyspace_hits_total{{job=~".*{job_pattern}.*"}} / (redis_keyspace_hits_total{{job=~".*{job_pattern}.*"}} + redis_keyspace_misses_total{{job=~".*{job_pattern}.*"}})'),
        ]
    elif mw_type == "kafka":
        queries = [
            ("消息入/s",    f'rate(kafka_server_brokertopicmetrics_messagesinpersec{{job=~".*{job_pattern}.*"}}[5m])'),
            ("分区数",      f'kafka_server_replicamanager_partitioncount{{job=~".*{job_pattern}.*"}}'),
        ]
    elif mw_type == "nginx":
        queries = [
            ("请求/s",      f'rate(nginx_http_requests_total{{job=~".*{job_pattern}.*"}}[5m])'),
            ("活跃连接",    f'nginx_connections_active{{job=~".*{job_pattern}.*"}}'),
            ("4xx/s",       f'rate(nginx_http_requests_total{{job=~".*{job_pattern}.*",status=~"4.."}}[5m])'),
            ("5xx/s",       f'rate(nginx_http_requests_total{{job=~".*{job_pattern}.*",status=~"5.."}}[5m])'),
        ]
    else:
        queries = [
            ("存活状态", f'up{{job=~".*{job_pattern}.*"}}'),
        ]

    for name, query in queries:
        results = await _safe_query(prom, query)
        for item in results:
            val_raw = item.get("value", [None, "0"])
            try:
                val = float(val_raw[-1])
            except Exception:
                val = 0.0
            metrics.append({
                "name":     name,
                "instance": item.get("metric", {}).get("instance", ""),
                "value":    round(val, 3),
                "query":    query,
            })

    return {"type": mw_type, "label": cfg["label"], "metrics": metrics}


@router.get("/summary")
async def middleware_summary():
    """所有发现的中间件类型汇总。"""
    instances = await list_instances()
    summary: dict[str, dict] = {}
    for inst in instances:
        t = inst["type"]
        if t not in summary:
            summary[t] = {"label": _MW_TYPES[t]["label"], "icon": _MW_TYPES[t]["icon"], "total": 0, "up": 0}
        summary[t]["total"] += 1
        if inst["status"] == "up":
            summary[t]["up"] += 1
    return list(summary.values())
