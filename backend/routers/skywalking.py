"""SkyWalking APM 路由

端点前缀：/api/sw/
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from skywalking_client import sw_client

logger = logging.getLogger(__name__)
router = APIRouter()


def _wrap(exc: Exception):
    logger.warning("[SkyWalking] API error: %s", exc)
    raise HTTPException(status_code=500, detail=str(exc))


# ── 服务列表 ──────────────────────────────────────────────────────────────────

@router.get("/api/sw/services")
async def get_sw_services(hours: int = Query(1)):
    try:
        return await sw_client.get_services(hours)
    except Exception as e:
        _wrap(e)


# ── 服务实例 ──────────────────────────────────────────────────────────────────

@router.get("/api/sw/instances")
async def get_sw_instances(
    service_id: str = Query(...),
    hours: int = Query(1),
):
    try:
        return await sw_client.get_instances(service_id, hours)
    except Exception as e:
        _wrap(e)


# ── 端点列表 ──────────────────────────────────────────────────────────────────

@router.get("/api/sw/endpoints")
async def get_sw_endpoints(
    service_id: str = Query(...),
    keyword: str = Query(""),
    limit: int = Query(50),
):
    try:
        return await sw_client.get_endpoints(service_id, keyword, limit)
    except Exception as e:
        _wrap(e)


# ── 追踪列表 ──────────────────────────────────────────────────────────────────

@router.get("/api/sw/traces")
async def get_sw_traces(
    service_id:  Optional[str] = Query(None),
    endpoint_id: Optional[str] = Query(None),
    trace_id:    Optional[str] = Query(None),
    hours:       int           = Query(1),
    start_time:  Optional[str] = Query(None),
    end_time:    Optional[str] = Query(None),
    error_only:  bool          = Query(False),
    page:        int           = Query(1),
    page_size:   int           = Query(20),
):
    try:
        return await sw_client.get_traces(
            service_id=service_id,
            endpoint_id=endpoint_id,
            trace_id=trace_id,
            hours=hours,
            start_time=start_time,
            end_time=end_time,
            error_only=error_only,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        _wrap(e)


# ── 追踪详情 ──────────────────────────────────────────────────────────────────

@router.get("/api/sw/traces/{trace_id:path}")
async def get_sw_trace_detail(trace_id: str):
    try:
        spans = await sw_client.get_trace_detail(trace_id)
        return {"traceId": trace_id, "spans": spans}
    except Exception as e:
        _wrap(e)


# ── 服务拓扑 ──────────────────────────────────────────────────────────────────

@router.get("/api/sw/topology")
async def get_sw_topology(
    hours:      int           = Query(1),
    service_id: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time:   Optional[str] = Query(None),
):
    try:
        return await sw_client.get_topology(
            hours=hours,
            service_id=service_id,
            start_time=start_time,
            end_time=end_time,
        )
    except Exception as e:
        _wrap(e)


# ── 性能指标 ──────────────────────────────────────────────────────────────────

@router.get("/api/sw/metrics")
async def get_sw_metrics(
    service_name: str           = Query(...),
    hours:        int           = Query(1),
    start_time:   Optional[str] = Query(None),
    end_time:     Optional[str] = Query(None),
):
    try:
        return await sw_client.get_service_metrics(
            service_name=service_name,
            hours=hours,
            start_time=start_time,
            end_time=end_time,
        )
    except Exception as e:
        _wrap(e)
