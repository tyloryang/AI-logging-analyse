"""知识图谱 REST 端点 — /api/kg/*

  POST /api/kg/build          全量重建图谱
  GET  /api/kg/stats          图谱统计
  GET  /api/kg/neighbors      查询实体上下游/影响面
"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth.deps import current_user
from auth.models import User
from services import knowledge_graph as kg

router = APIRouter(prefix="/api/kg", tags=["knowledge-graph"])

_RELATION_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


class NodePayload(BaseModel):
    id: str = Field(..., min_length=1, max_length=240)
    kind: str = Field(default="entity", min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=240)
    env: str = Field(default="", max_length=80)
    props: dict[str, Any] = Field(default_factory=dict)


class RelationPayload(BaseModel):
    source_id: str = Field(..., min_length=1, max_length=240)
    target_id: str = Field(..., min_length=1, max_length=240)
    relation: str = Field(..., min_length=1, max_length=64)
    props: dict[str, Any] = Field(default_factory=dict)


def _validate_relation(value: str) -> str:
    relation = value.strip().upper()
    if not _RELATION_PATTERN.fullmatch(relation):
        raise HTTPException(status_code=422, detail="关系类型仅支持字母、数字和下划线，且必须以字母开头")
    return relation


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=503, detail=str(exc))


@router.post("/build")
async def build(_: User = Depends(current_user)):
    return await kg.build_graph(sync_neo4j=True)


@router.get("/stats")
async def get_stats():
    return await asyncio.to_thread(kg.stats)


@router.get("/status")
async def get_status():
    return await asyncio.to_thread(kg.neo4j_status, True)


@router.get("/graph")
async def get_graph(limit: int = Query(240, ge=1, le=500)):
    return await asyncio.to_thread(kg.graph_snapshot, limit)


@router.get("/neighbors")
async def get_neighbors(
    entity: str = Query(..., description="服务名/Pod/主机/节点名或 IP"),
    depth: int = Query(1, ge=1, le=2),
    backend: str = Query("sqlite", pattern="^(sqlite|neo4j)$"),
):
    return await asyncio.to_thread(kg.neighbors, entity, depth, 40, backend == "neo4j")


@router.post("/nodes")
async def upsert_node(payload: NodePayload, _: User = Depends(current_user)):
    try:
        node = await asyncio.to_thread(
            kg.upsert_node,
            payload.id.strip(),
            payload.kind.strip(),
            payload.name.strip(),
            env=payload.env.strip(),
            props=payload.props,
        )
        return {"ok": True, "node": node}
    except Exception as exc:
        raise _service_error(exc) from exc


@router.delete("/nodes")
async def delete_node(
    node_id: str = Query(..., min_length=1, max_length=240),
    _: User = Depends(current_user),
):
    try:
        deleted = await asyncio.to_thread(kg.delete_node, node_id.strip())
        if not deleted:
            raise HTTPException(status_code=404, detail="节点不存在")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise _service_error(exc) from exc


@router.post("/relations")
async def upsert_relation(payload: RelationPayload, _: User = Depends(current_user)):
    relation = _validate_relation(payload.relation)
    if payload.source_id.strip() == payload.target_id.strip():
        raise HTTPException(status_code=422, detail="源节点和目标节点不能相同")
    try:
        edge = await asyncio.to_thread(
            kg.upsert_relation,
            payload.source_id.strip(),
            payload.target_id.strip(),
            relation,
            props=payload.props,
        )
        return {"ok": True, "edge": edge}
    except Exception as exc:
        raise _service_error(exc) from exc


@router.delete("/relations")
async def delete_relation(
    source_id: str = Query(..., min_length=1, max_length=240),
    target_id: str = Query(..., min_length=1, max_length=240),
    relation: str = Query(..., min_length=1, max_length=64),
    _: User = Depends(current_user),
):
    try:
        deleted = await asyncio.to_thread(
            kg.delete_relation,
            source_id.strip(),
            target_id.strip(),
            _validate_relation(relation),
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="关系不存在")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise _service_error(exc) from exc
