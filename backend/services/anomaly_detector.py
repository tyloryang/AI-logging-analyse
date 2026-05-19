"""Simple anomaly detector backed by Prometheus queries."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from json_snapshot_store import read_json_file, write_json_file

logger = logging.getLogger(__name__)

_ANOMALY_FILE = Path(__file__).resolve().parent.parent / "data" / "anomalies.json"
_PROM_TIMEOUT = 12.0

_STATIC_RULES = [
    {
        "name": "CPU usage too high",
        "promql": '100 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100',
        "threshold": 90.0,
        "unit": "%",
        "severity": "P0",
    },
    {
        "name": "Memory usage too high",
        "promql": '100 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100',
        "threshold": 90.0,
        "unit": "%",
        "severity": "P0",
    },
    {
        "name": "HTTP 5xx ratio too high",
        "promql": 'sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m])) * 100',
        "threshold": 5.0,
        "unit": "%",
        "severity": "P0",
    },
    {
        "name": "Disk usage warning",
        "promql": '100 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100',
        "threshold": 80.0,
        "unit": "%",
        "severity": "P1",
    },
]

_DYNAMIC_METRICS = [
    {
        "name": "Request QPS anomaly",
        "promql": 'sum(rate(http_requests_total[5m]))',
        "unit": "req/s",
    },
    {
        "name": "P99 latency anomaly",
        "promql": 'histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le)) * 1000',
        "unit": "ms",
    },
]


def _load() -> list[dict]:
    data = read_json_file(_ANOMALY_FILE, default=[])
    return data if isinstance(data, list) else []


def _save(records: list[dict]) -> None:
    write_json_file(_ANOMALY_FILE, records[-500:], ensure_parent=True)


def list_anomalies(limit: int = 100) -> list[dict]:
    return list(reversed(_load()))[:limit]


async def _prom_instant(promql: str) -> float | None:
    try:
        import state

        result = await asyncio.wait_for(state.prom.query(promql), timeout=_PROM_TIMEOUT)
        if result:
            return float(result[0].get("value", [0, 0])[1] or 0)
    except Exception:
        pass
    return None


async def _prom_range(promql: str, start: int, end: int, step: int = 300) -> list[float]:
    try:
        import state

        url = f"{state.PROMETHEUS_URL}/api/v1/query_range"
        params = {"query": promql, "start": start, "end": end, "step": step}
        auth = (state.PROMETHEUS_USERNAME, state.PROMETHEUS_PASSWORD) if state.PROMETHEUS_USERNAME else None
        async with httpx.AsyncClient(timeout=_PROM_TIMEOUT) as client:
            request_kwargs: dict = {"params": params}
            if auth:
                request_kwargs["auth"] = auth
            resp = await client.get(url, **request_kwargs)
            resp.raise_for_status()
            data = resp.json()

        values: list[float] = []
        for series in data.get("data", {}).get("result", []):
            for _, value in series.get("values", []):
                try:
                    values.append(float(value))
                except Exception:
                    pass
        return values
    except Exception:
        return []


def _stddev(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return mean, math.sqrt(variance)


def _is_monotone_rise(values: list[float], n: int = 3, min_slope: float = 0.05) -> bool:
    if len(values) < n:
        return False
    tail = values[-n:]
    if not all(tail[idx] < tail[idx + 1] for idx in range(n - 1)):
        return False
    slope = (tail[-1] - tail[0]) / max(tail[0], 1)
    return slope > min_slope


async def _detect_static() -> list[dict]:
    now_iso = datetime.now(timezone.utc).isoformat()
    found: list[dict] = []
    values = await asyncio.gather(*(_prom_instant(rule["promql"]) for rule in _STATIC_RULES))
    for rule, value in zip(_STATIC_RULES, values):
        if value is None or value < rule["threshold"]:
            continue
        found.append(
            {
                "type": "static",
                "name": rule["name"],
                "value": round(value, 2),
                "threshold": rule["threshold"],
                "unit": rule["unit"],
                "severity": rule["severity"],
                "detected_at": now_iso,
                "detail": f"Current value {value:.2f}{rule['unit']} exceeded {rule['threshold']}{rule['unit']}",
            }
        )
    return found


async def _detect_dynamic() -> list[dict]:
    now = int(time.time())
    history_start = now - 7 * 24 * 3600
    now_iso = datetime.now(timezone.utc).isoformat()

    async def _detect_metric(metric: dict) -> list[dict]:
        current, history, recent = await asyncio.gather(
            _prom_instant(metric["promql"]),
            _prom_range(metric["promql"], history_start, now - 300, step=300),
            _prom_range(metric["promql"], now - 900, now, step=60),
        )
        if current is None or not history:
            return []

        mean, std = _stddev(history)
        upper_3sigma = mean + 3 * std
        metric_found: list[dict] = []

        if std > 0 and current > upper_3sigma:
            metric_found.append(
                {
                    "type": "dynamic_3sigma",
                    "name": metric["name"],
                    "value": round(current, 3),
                    "baseline": round(mean, 3),
                    "sigma": round(std, 3),
                    "unit": metric["unit"],
                    "severity": "P0" if current > mean + 5 * std else "P1",
                    "detected_at": now_iso,
                    "detail": f"Current value {current:.3f} exceeded 7d mean {mean:.3f} + 3sigma ({upper_3sigma:.3f})",
                }
            )

        if _is_monotone_rise(recent) and not any(item["name"] == metric["name"] for item in metric_found):
            metric_found.append(
                {
                    "type": "trend",
                    "name": f"{metric['name']} (rising)",
                    "value": round(current, 3),
                    "unit": metric["unit"],
                    "severity": "P1",
                    "detected_at": now_iso,
                    "detail": f"Recent 15m stayed monotonic. Current value {current:.3f}{metric['unit']}",
                }
            )

        return metric_found

    found: list[dict] = []
    results = await asyncio.gather(*(_detect_metric(metric) for metric in _DYNAMIC_METRICS))
    for metric_found in results:
        found.extend(metric_found)
    return found


async def run_detection() -> list[dict]:
    try:
        static_results, dynamic_results = await asyncio.gather(_detect_static(), _detect_dynamic())
        anomalies = static_results + dynamic_results
    except Exception as exc:
        logger.error("[anomaly] detection failed: %s", exc)
        return []

    if not anomalies:
        return []

    existing = _load()
    existing.extend(anomalies)
    _save(existing)

    p0 = [item for item in anomalies if item["severity"] == "P0"]
    p1 = [item for item in anomalies if item["severity"] == "P1"]

    for anomaly in p0:
        try:
            from services.alert_dedup import ingest_alerts

            ingest_alerts(
                [
                    {
                        "status": "firing",
                        "labels": {"alertname": anomaly["name"], "severity": "critical", "service": "system"},
                        "annotations": {"summary": anomaly["detail"]},
                    }
                ]
            )
        except Exception as exc:
            logger.warning("[anomaly] failed to write P0 alert: %s", exc)

        asyncio.create_task(_trigger_rca(anomaly))

    for anomaly in p1:
        try:
            from services.alert_dedup import ingest_alerts

            ingest_alerts(
                [
                    {
                        "status": "firing",
                        "labels": {"alertname": anomaly["name"], "severity": "warning", "service": "system"},
                        "annotations": {"summary": anomaly["detail"]},
                    }
                ]
            )
        except Exception as exc:
            logger.warning("[anomaly] failed to write P1 alert: %s", exc)

    logger.info(
        "[anomaly] detection finished, P0=%d P1=%d P2=%d",
        len(p0),
        len(p1),
        len(anomalies) - len(p0) - len(p1),
    )
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
        logger.warning("[anomaly] RCA trigger failed: %s", exc)
