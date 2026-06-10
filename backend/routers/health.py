"""Health check router.

Route: GET /api/health
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from cachetools import TTLCache
from fastapi import APIRouter
from fastapi.responses import Response

from observability.llm_metrics import metrics_response
from skywalking_client import SKYWALKING_OAP_URL, check_connectivity as sw_check
from state import LOKI_URL, PROMETHEUS_URL, analyzer, loki, prom

logger = logging.getLogger(__name__)
router = APIRouter()

_health_cache: TTLCache = TTLCache(maxsize=1, ttl=10)
_health_lock = asyncio.Lock()


async def _check_loki() -> bool:
    try:
        await loki._request_json("/loki/api/v1/labels", timeout=httpx.Timeout(5.0))
        return True
    except Exception as exc:
        logger.warning("[health] Loki connectivity failed: %s", exc)
        return False


async def _check_prom() -> bool:
    try:
        await prom.query("up", timeout=5)
        return True
    except Exception as exc:
        logger.warning("[health] Prometheus connectivity failed: %s", exc)
        return False


async def _build_health_payload() -> dict:
    loki_ok, prom_ok, sw_ok = await asyncio.gather(_check_loki(), _check_prom(), sw_check())

    try:
        ai_name = analyzer.provider_name
        ai_ok = True
    except Exception as exc:
        ai_name = str(exc)
        ai_ok = False

    return {
        "status": "ok",
        "version": "2.0",
        "loki_connected": loki_ok,
        "loki_url": LOKI_URL,
        "prometheus_connected": prom_ok,
        "prometheus_url": PROMETHEUS_URL,
        "ai_provider": ai_name,
        "ai_ready": ai_ok,
        "skywalking_connected": sw_ok,
        "skywalking_url": SKYWALKING_OAP_URL,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/api/health")
async def health():
    cached = _health_cache.get("payload")
    if cached is not None:
        return cached

    async with _health_lock:
        cached = _health_cache.get("payload")
        if cached is not None:
            return cached

        payload = await _build_health_payload()
        _health_cache["payload"] = payload
        return payload


@router.get("/api/metrics")
async def prometheus_metrics():
    """Prometheus 抓取端点：暴露 aiops_llm_* 指标。

    无 prometheus_client 时返回提示文本，Prom 抓取不报错只是没数据。
    """
    body, content_type = metrics_response()
    return Response(content=body, media_type=content_type)
