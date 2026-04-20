"""根因分析 & 异常检测路由。

端点：
  POST /api/rca/analyze              — 触发 RCA（流式 SSE）
  GET  /api/rca/results              — RCA 历史列表
  GET  /api/rca/results/{id}         — RCA 详情
  GET  /api/rca/anomalies            — 异常检测记录列表
  POST /api/rca/anomalies/detect     — 手动触发一轮异常检测
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


# ── RCA 流式触发 ──────────────────────────────────────────────────────────────

class RCARequest(BaseModel):
    service: str | None = None
    alert_name: str = ""
    alert_group_id: str | None = None
    hours: float = 1.0
    extra_context: str = ""


@router.post("/api/rca/analyze/stream")
async def rca_stream(body: RCARequest):
    """流式触发根因分析，SSE 格式输出。"""
    from services.rca_engine import analyze_stream, save_rca
    from datetime import datetime, timezone
    import time

    rca_id = f"rca_{int(time.time())}"
    now_iso = datetime.now(timezone.utc).isoformat()
    parts: list[str] = []

    async def _gen():
        async for chunk in analyze_stream(
            service=body.service,
            alert_name=body.alert_name,
            hours=body.hours,
            extra_context=body.extra_context,
        ):
            parts.append(chunk)
            yield f"data: {chunk}\n\n"

        # 落库
        record = {
            "id": rca_id,
            "created_at": now_iso,
            "service": body.service or "global",
            "alert_name": body.alert_name,
            "alert_group_id": body.alert_group_id,
            "result": "".join(parts),
            "context_hours": body.hours,
        }
        save_rca(record)

        # 关联告警组
        if body.alert_group_id:
            try:
                from services.alert_dedup import update_group_status
                update_group_status(body.alert_group_id, "resolved", rca_id=rca_id)
            except Exception:
                pass

        yield f"data: [DONE]\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


@router.post("/api/rca/analyze")
async def rca_trigger(body: RCARequest):
    """后台触发 RCA（非流式），立即返回 rca_id，结果异步落库。"""
    from services.rca_engine import run_rca
    rca_id = f"pending_{int(__import__('time').time())}"

    async def _run():
        try:
            await run_rca(
                service=body.service,
                alert_name=body.alert_name,
                alert_group_id=body.alert_group_id,
                hours=body.hours,
                extra_context=body.extra_context,
            )
        except Exception as exc:
            logger.error("[rca] 后台分析失败: %s", exc)

    asyncio.create_task(_run())
    return {"ok": True, "message": "RCA 分析已启动，结果将异步写入", "rca_id": rca_id}


# ── RCA 历史查询 ──────────────────────────────────────────────────────────────

@router.get("/api/rca/results")
async def list_rca_results(limit: int = Query(50, ge=1, le=200)):
    from services.rca_engine import list_rca
    return {"results": list_rca(limit)}


@router.get("/api/rca/results/{rca_id}")
async def get_rca_result(rca_id: str):
    from services.rca_engine import get_rca
    r = get_rca(rca_id)
    if not r:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="RCA 记录不存在")
    return r


# ── 异常检测 ──────────────────────────────────────────────────────────────────

@router.get("/api/rca/anomalies")
async def list_anomalies(limit: int = Query(100, ge=1, le=500)):
    from services.anomaly_detector import list_anomalies
    return {"anomalies": list_anomalies(limit)}


@router.post("/api/rca/anomalies/detect")
async def manual_detect():
    """手动触发一轮异常检测。"""
    from services.anomaly_detector import run_detection
    anomalies = await run_detection()
    return {
        "ok": True,
        "detected": len(anomalies),
        "p0": sum(1 for a in anomalies if a["severity"] == "P0"),
        "p1": sum(1 for a in anomalies if a["severity"] == "P1"),
        "p2": sum(1 for a in anomalies if a["severity"] == "P2"),
    }
