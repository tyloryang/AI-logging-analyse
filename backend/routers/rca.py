"""RCA and anomaly detection routes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


class RCARequest(BaseModel):
    service: str | None = None
    alert_name: str = ""
    alert_group_id: str | None = None
    hours: float = 1.0
    extra_context: str = ""
    source_type: str = "manual"
    source_id: str = ""
    source_name: str = ""
    source_labels: dict[str, str] = Field(default_factory=dict)
    inspection_summary: dict[str, Any] = Field(default_factory=dict)
    inspection_results: list[dict[str, Any]] = Field(default_factory=list)


class RCAConfirmRequest(BaseModel):
    hypothesis_id: str
    note: str = ""
    confirmed_by: str = ""
    decision: str = "confirmed"
    resolve_alert: bool = False


@router.post("/api/rca/analyze/stream")
async def rca_stream(body: RCARequest):
    """Compatibility stream endpoint. The new UI uses async trigger + polling."""
    from services.rca_engine import analyze_stream

    async def _gen():
        async for chunk in analyze_stream(
            service=body.service,
            alert_name=body.alert_name,
            hours=body.hours,
            extra_context=body.extra_context,
        ):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")


@router.post("/api/rca/analyze")
async def rca_trigger(body: RCARequest):
    from services.rca_engine import create_pending_rca, run_rca

    pending = create_pending_rca(
        service=body.service,
        alert_name=body.alert_name,
        alert_group_id=body.alert_group_id,
        hours=body.hours,
        extra_context=body.extra_context,
        source_type=body.source_type,
        source_id=body.source_id,
        source_name=body.source_name,
        source_labels=body.source_labels,
    )

    if body.alert_group_id:
        try:
            from services.alert_dedup import update_group_status

            update_group_status(body.alert_group_id, "analyzing", rca_id=pending["id"])
        except Exception as exc:
            logger.warning("[rca] failed to mark alert group analyzing: %s", exc)

    async def _run():
        try:
            await run_rca(
                service=body.service,
                alert_name=body.alert_name,
                alert_group_id=body.alert_group_id,
                hours=body.hours,
                extra_context=body.extra_context,
                source_type=body.source_type,
                source_id=body.source_id,
                source_name=body.source_name,
                source_labels=body.source_labels,
                inspection_summary=body.inspection_summary,
                inspection_results=body.inspection_results,
                existing_id=pending["id"],
            )
        except Exception as exc:
            logger.error("[rca] async RCA failed: %s", exc)

    asyncio.create_task(_run())
    return {
        "ok": True,
        "message": "RCA flow started",
        "rca_id": pending["id"],
        "record": pending,
    }


@router.get("/api/rca/results")
async def list_rca_results(limit: int = Query(50, ge=1, le=200)):
    from services.rca_engine import list_rca

    return {"results": list_rca(limit)}


@router.get("/api/rca/results/{rca_id}")
async def get_rca_result(rca_id: str):
    from services.rca_engine import get_rca

    record = get_rca(rca_id)
    if not record:
        raise HTTPException(status_code=404, detail="RCA record not found")
    return record


@router.post("/api/rca/results/{rca_id}/confirm")
async def confirm_rca_result(rca_id: str, body: RCAConfirmRequest):
    from services.rca_engine import confirm_rca

    try:
        return confirm_rca(
            rca_id,
            hypothesis_id=body.hypothesis_id,
            note=body.note,
            confirmed_by=body.confirmed_by,
            decision=body.decision,
            resolve_alert=body.resolve_alert,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/rca/expert-cases")
async def list_rca_expert_cases(limit: int = Query(50, ge=1, le=200)):
    from services.rca_engine import list_expert_cases

    return {"cases": list_expert_cases(limit)}


@router.get("/api/rca/feedback")
async def get_rca_feedback():
    from services.rca_engine import get_feedback_profile

    return get_feedback_profile()


@router.get("/api/rca/anomalies")
async def list_anomalies(limit: int = Query(100, ge=1, le=500)):
    from services.anomaly_detector import list_anomalies

    return {"anomalies": list_anomalies(limit)}


@router.post("/api/rca/anomalies/detect")
async def manual_detect():
    from services.anomaly_detector import run_detection

    anomalies = await run_detection()
    return {
        "ok": True,
        "detected": len(anomalies),
        "p0": sum(1 for item in anomalies if item["severity"] == "P0"),
        "p1": sum(1 for item in anomalies if item["severity"] == "P1"),
        "p2": sum(1 for item in anomalies if item["severity"] == "P2"),
    }
