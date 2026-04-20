"""异常检测器（Anomaly Detector）。

策略：
1. 静态阈值：CPU > 90%，内存 > 90%，错误率 > 5%
2. 动比（3σ）：当前值超出7天同时段均值 ± 3σ
3. 趋势：连续 3 个采样点单调上升且斜率超阈值

严重度：
  P0 → 触发 RCA + 推送飞书
  P1 → 写入告警聚合器
  P2 → 只写异常记录，不推送
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_ANOMALY_FILE = Path(__file__).resolve().parent.parent / "data" / "anomalies.json"
_PROM_TIMEOUT  = 12.0

# 静态阈值配置
_STATIC_RULES = [
    {
        "name": "CPU 使用率过高",
        "promql": '100 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100',
        "threshold": 90.0,
        "unit": "%",
        "severity": "P0",
    },
    {
        "name": "内存使用率过高",
        "promql": '100 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100',
        "threshold": 90.0,
        "unit": "%",
        "severity": "P0",
    },
    {
        "name": "HTTP 错误率偏高",
        "promql": 'sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100',
        "threshold": 5.0,
        "unit": "%",
        "severity": "P0",
    },
    {
        "name": "磁盘使用率预警",
        "promql": '100 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100',
        "threshold": 80.0,
        "unit": "%",
        "severity": "P1",
    },
]

# 动比检测指标
_DYNAMIC_METRICS = [
    {
        "name": "请求 QPS 异常",
        "promql": 'sum(rate(http_requests_total[5m]))',
        "unit": "req/s",
    },
    {
        "name": "P99 响应时间异常",
        "promql": 'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) * 1000',
        "unit": "ms",
    },
]


# ── 持久化 ────────────────────────────────────────────────────────────────────

def _load() -> list[dict]:
    if _ANOMALY_FILE.exists():
        try:
            return json.loads(_ANOMALY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(records: list[dict]) -> None:
    _ANOMALY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _ANOMALY_FILE.write_text(
        json.dumps(records[-500:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_anomalies(limit: int = 100) -> list[dict]:
    return list(reversed(_load()))[:limit]


# ── Prometheus 查询工具 ────────────────────────────────────────────────────────

async def _prom_instant(promql: str) -> float | None:
    """执行 Prometheus 即时查询，返回单个数值。"""
    try:
        import state
        result = await asyncio.wait_for(state.prom.query(promql), timeout=_PROM_TIMEOUT)
        if result:
            return float(result[0].get("value", [0, 0])[1] or 0)
    except Exception:
        pass
    return None


async def _prom_range(promql: str, start: int, end: int, step: int = 300) -> list[float]:
    """执行 Prometheus 范围查询，返回 [value, ...] 列表。"""
    try:
        import state
        url = f"{state.PROMETHEUS_URL}/api/v1/query_range"
        params = {"query": promql, "start": start, "end": end, "step": step}
        auth = (state.PROMETHEUS_USERNAME, state.PROMETHEUS_PASSWORD) if state.PROMETHEUS_USERNAME else None
        async with httpx.AsyncClient(timeout=_PROM_TIMEOUT) as client:
            kw: dict = {"params": params}
            if auth:
                kw["auth"] = auth
            r = await client.get(url, **kw)
            r.raise_for_status()
            data = r.json()
        values = []
        for series in data.get("data", {}).get("result", []):
            for _, v in series.get("values", []):
                try:
                    values.append(float(v))
                except Exception:
                    pass
        return values
    except Exception:
        return []


# ── 检测逻辑 ──────────────────────────────────────────────────────────────────

def _stddev(values: list[float]) -> tuple[float, float]:
    """返回 (均值, 标准差)。"""
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    variance = sum((x - mean) ** 2 for x in values) / n
    return mean, math.sqrt(variance)


def _is_monotone_rise(values: list[float], n: int = 3, min_slope: float = 0.05) -> bool:
    """判断最后 n 个点是否单调上升且斜率 > min_slope。"""
    if len(values) < n:
        return False
    tail = values[-n:]
    if not all(tail[i] < tail[i + 1] for i in range(n - 1)):
        return False
    slope = (tail[-1] - tail[0]) / max(tail[0], 1)
    return slope > min_slope


async def _detect_static() -> list[dict]:
    """静态阈值检测。"""
    now_iso = datetime.now(timezone.utc).isoformat()
    found: list[dict] = []
    for rule in _STATIC_RULES:
        val = await _prom_instant(rule["promql"])
        if val is None:
            continue
        if val >= rule["threshold"]:
            found.append({
                "type":      "static",
                "name":      rule["name"],
                "value":     round(val, 2),
                "threshold": rule["threshold"],
                "unit":      rule["unit"],
                "severity":  rule["severity"],
                "detected_at": now_iso,
                "detail":    f"当前值 {val:.2f}{rule['unit']} 超过阈值 {rule['threshold']}{rule['unit']}",
            })
    return found


async def _detect_dynamic() -> list[dict]:
    """动比（3σ）+ 趋势检测。"""
    now = int(time.time())
    # 7 天历史数据（每 5 分钟一个点）
    history_start = now - 7 * 24 * 3600
    now_iso = datetime.now(timezone.utc).isoformat()
    found: list[dict] = []

    for metric in _DYNAMIC_METRICS:
        promql = metric["promql"]
        current = await _prom_instant(promql)
        if current is None:
            continue

        history = await _prom_range(promql, history_start, now - 300, step=300)
        if not history:
            continue

        mean, std = _stddev(history)
        upper_3sigma = mean + 3 * std

        # 3σ 异常
        if std > 0 and current > upper_3sigma:
            found.append({
                "type":       "dynamic_3sigma",
                "name":       metric["name"],
                "value":      round(current, 3),
                "baseline":   round(mean, 3),
                "sigma":      round(std, 3),
                "unit":       metric["unit"],
                "severity":   "P0" if current > mean + 5 * std else "P1",
                "detected_at": now_iso,
                "detail":     f"当前值 {current:.3f} 超过历史7天均值 {mean:.3f} + 3σ ({upper_3sigma:.3f})",
            })

        # 趋势检测（最近 15 分钟，步长1分钟）
        recent = await _prom_range(promql, now - 900, now, step=60)
        if _is_monotone_rise(recent):
            # 避免与 3σ 重复上报同一指标
            if not any(a["name"] == metric["name"] for a in found):
                found.append({
                    "type":       "trend",
                    "name":       f"{metric['name']}（持续上升）",
                    "value":      round(current, 3),
                    "unit":       metric["unit"],
                    "severity":   "P1",
                    "detected_at": now_iso,
                    "detail":     f"最近15分钟持续单调上升，当前值 {current:.3f}{metric['unit']}",
                })

    return found


# ── 主入口（定时调用） ────────────────────────────────────────────────────────

async def run_detection() -> list[dict]:
    """执行一轮完整异常检测，返回发现的异常列表。"""
    try:
        static_results, dynamic_results = await asyncio.gather(
            _detect_static(),
            _detect_dynamic(),
        )
        anomalies = static_results + dynamic_results
    except Exception as exc:
        logger.error("[anomaly] 检测异常: %s", exc)
        return []

    if not anomalies:
        return []

    # 持久化
    existing = _load()
    existing.extend(anomalies)
    _save(existing)

    # 按严重度分流
    p0 = [a for a in anomalies if a["severity"] == "P0"]
    p1 = [a for a in anomalies if a["severity"] == "P1"]

    # P0 → 写入告警聚合器 + 触发 RCA
    for a in p0:
        try:
            from services.alert_dedup import ingest_alerts
            ingest_alerts([{
                "status": "firing",
                "labels": {"alertname": a["name"], "severity": "critical", "service": "system"},
                "annotations": {"summary": a["detail"]},
            }])
        except Exception as exc:
            logger.warning("[anomaly] 写入告警聚合器失败: %s", exc)

        asyncio.create_task(_trigger_rca(a))

    # P1 → 写入告警聚合器
    for a in p1:
        try:
            from services.alert_dedup import ingest_alerts
            ingest_alerts([{
                "status": "firing",
                "labels": {"alertname": a["name"], "severity": "warning", "service": "system"},
                "annotations": {"summary": a["detail"]},
            }])
        except Exception as exc:
            logger.warning("[anomaly] P1 写入失败: %s", exc)

    logger.info("[anomaly] 检测完成，P0=%d P1=%d P2=%d",
                len(p0), len(p1), len(anomalies) - len(p0) - len(p1))
    return anomalies


async def _trigger_rca(anomaly: dict) -> None:
    try:
        from services.rca_engine import run_rca
        await run_rca(
            service=None,
            alert_name=anomaly["name"],
            hours=0.5,
            extra_context=anomaly["detail"],
        )
    except Exception as exc:
        logger.warning("[anomaly] 触发 RCA 失败: %s", exc)
