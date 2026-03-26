"""健康检查路由。

路由：GET /api/health
"""
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter

from state import loki, prom, analyzer, LOKI_URL, LOKI_USERNAME, LOKI_PASSWORD, PROMETHEUS_URL
from skywalking_client import check_connectivity as sw_check, SKYWALKING_OAP_URL

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/health")
async def health():
    async def _check_loki():
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as c:
                kw = {"url": f"{LOKI_URL}/loki/api/v1/labels"}
                if LOKI_USERNAME:
                    kw["auth"] = (LOKI_USERNAME, LOKI_PASSWORD)
                resp = await c.get(**kw)
                return resp.status_code == 200
        except Exception as e:
            logger.warning("[health] Loki 连接失败: %s", e)
            return False

    async def _check_prom():
        try:
            await prom.query("up", timeout=5)
            return True
        except Exception as e:
            logger.warning("[health] Prometheus 连接失败: %s", e)
            return False

    loki_ok, prom_ok, sw_ok = await asyncio.gather(_check_loki(), _check_prom(), sw_check())

    try:
        ai_name = analyzer.provider_name
        ai_ok   = True
    except Exception as e:
        ai_name = str(e)
        ai_ok   = False

    return {
        "status":               "ok",
        "version":              "2.0",
        "loki_connected":       loki_ok,
        "loki_url":             LOKI_URL,
        "prometheus_connected": prom_ok,
        "prometheus_url":       PROMETHEUS_URL,
        "ai_provider":            ai_name,
        "ai_ready":               ai_ok,
        "skywalking_connected":   sw_ok,
        "skywalking_url":         SKYWALKING_OAP_URL,
        "timestamp":              datetime.now(timezone.utc).isoformat(),
    }
