"""Elasticsearch 集群管理路由 — /api/es/*

后端代理模式：避免前端直连 ES 的 CORS 问题。
集群配置持久化到 data/es_clusters.json。
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/es", tags=["elasticsearch"])

_DATA_FILE = Path(__file__).parent.parent / "data" / "es_clusters.json"


# ── 持久化 ───────────────────────────────────────────────────────────────────

def _load_clusters() -> list[dict]:
    if _DATA_FILE.exists():
        try:
            return json.loads(_DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_clusters(clusters: list[dict]) -> None:
    _DATA_FILE.parent.mkdir(exist_ok=True)
    _DATA_FILE.write_text(json.dumps(clusters, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_cluster(cluster_id: str) -> dict:
    c = next((c for c in _load_clusters() if c["id"] == cluster_id), None)
    if not c:
        raise HTTPException(404, f"集群 {cluster_id} 不存在")
    return c


# ── 集群 CRUD ────────────────────────────────────────────────────────────────

class ClusterCreate(BaseModel):
    name: str
    host: str
    username: str = ""
    password: str = ""
    api_key: str = ""
    env: str = ""
    note: str = ""
    color: str = "#4f8ef7"


@router.get("/clusters")
async def list_clusters():
    clusters = _load_clusters()
    return [
        {k: v for k, v in c.items() if k not in ("password", "api_key")}
        for c in clusters
    ]


@router.post("/clusters")
async def add_cluster(body: ClusterCreate):
    cluster = {
        "id":       str(uuid.uuid4()),
        "name":     body.name,
        "host":     body.host.rstrip("/"),
        "username": body.username,
        "password": body.password,
        "api_key":  body.api_key,
        "env":      body.env,
        "note":     body.note,
        "color":    body.color,
    }
    clusters = _load_clusters()
    clusters.append(cluster)
    _save_clusters(clusters)
    return {k: v for k, v in cluster.items() if k not in ("password", "api_key")}


@router.put("/clusters/{cluster_id}")
async def update_cluster(cluster_id: str, body: ClusterCreate):
    clusters = _load_clusters()
    idx = next((i for i, c in enumerate(clusters) if c["id"] == cluster_id), None)
    if idx is None:
        raise HTTPException(404, "集群不存在")
    clusters[idx].update({
        "name":     body.name,
        "host":     body.host.rstrip("/"),
        "username": body.username,
        "env":      body.env,
        "note":     body.note,
        "color":    body.color,
    })
    if body.password:
        clusters[idx]["password"] = body.password
    if body.api_key:
        clusters[idx]["api_key"] = body.api_key
    _save_clusters(clusters)
    return {k: v for k, v in clusters[idx].items() if k not in ("password", "api_key")}


@router.delete("/clusters/{cluster_id}")
async def delete_cluster(cluster_id: str):
    clusters = [c for c in _load_clusters() if c["id"] != cluster_id]
    _save_clusters(clusters)
    return {"ok": True}


# ── 连接测试 ─────────────────────────────────────────────────────────────────

@router.get("/clusters/{cluster_id}/test")
async def test_cluster(cluster_id: str):
    c = _get_cluster(cluster_id)
    try:
        async with httpx.AsyncClient(timeout=8, verify=False) as client:
            r = await client.get(c["host"] + "/", headers=_auth_headers(c))
        data = r.json()
        return {
            "ok":           r.status_code < 400,
            "status_code":  r.status_code,
            "cluster_name": data.get("cluster_name", ""),
            "version":      data.get("version", {}).get("number", ""),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── ES API 代理 ───────────────────────────────────────────────────────────────

def _auth_headers(c: dict) -> dict:
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept":       "application/json",
    }
    if c.get("api_key"):
        headers["Authorization"] = f"ApiKey {c['api_key']}"
    elif c.get("username"):
        import base64
        cred = base64.b64encode(f"{c['username']}:{c.get('password','')}".encode()).decode()
        headers["Authorization"] = f"Basic {cred}"
    return headers


@router.api_route(
    "/clusters/{cluster_id}/proxy/{es_path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "HEAD"],
)
async def proxy_es(cluster_id: str, es_path: str, request: Request):
    """将任意 ES API 请求代理到目标集群，保留 query string。"""
    c = _get_cluster(cluster_id)
    qs = str(request.url).split("?", 1)
    query_string = "?" + qs[1] if len(qs) > 1 else ""

    url = f"{c['host']}/{es_path}{query_string}"
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=30, verify=False) as client:
            resp = await client.request(
                method=request.method,
                url=url,
                headers=_auth_headers(c),
                content=body or None,
            )
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=resp.headers.get("content-type", "application/json"),
        )
    except httpx.ConnectError as exc:
        raise HTTPException(502, f"无法连接 ES 集群: {exc}")
    except httpx.TimeoutException:
        raise HTTPException(504, "ES 请求超时")
    except Exception as exc:
        raise HTTPException(502, f"代理请求失败: {exc}")


# ── 便捷聚合 API ──────────────────────────────────────────────────────────────

@router.get("/clusters/{cluster_id}/overview")
async def cluster_overview(cluster_id: str):
    """聚合集群健康 + 统计信息，减少前端多次请求。"""
    c = _get_cluster(cluster_id)

    async def _get(path: str) -> Any:
        try:
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                r = await client.get(f"{c['host']}/{path}", headers=_auth_headers(c))
                return r.json() if r.is_success else None
        except Exception:
            return None

    health, stats, nodes_info = await _parallel_fetch(
        _get("_cluster/health"),
        _get("_cluster/stats"),
        _get("_cat/nodes?h=name,ip,heap.percent,disk.used_percent,cpu,master,node.role&format=json"),
    )
    return {
        "health":     health,
        "stats":      stats,
        "nodes_info": nodes_info,
    }


async def _parallel_fetch(*coros):
    import asyncio
    return await asyncio.gather(*coros, return_exceptions=False)


@router.get("/clusters/{cluster_id}/indices")
async def list_indices(cluster_id: str):
    c = _get_cluster(cluster_id)
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            r = await client.get(
                f"{c['host']}/_cat/indices?h=health,status,index,pri,rep,docs.count,docs.deleted,store.size,pri.store.size&s=index&format=json",
                headers=_auth_headers(c),
            )
        return r.json() if r.is_success else []
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.get("/clusters/{cluster_id}/nodes")
async def list_nodes(cluster_id: str):
    c = _get_cluster(cluster_id)
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as client:
            r = await client.get(
                f"{c['host']}/_cat/nodes?h=name,ip,heap.percent,ram.percent,disk.used_percent,cpu,master,node.role,load_1m&format=json&v",
                headers=_auth_headers(c),
            )
        return r.json() if r.is_success else []
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.get("/clusters/{cluster_id}/shards")
async def list_shards(cluster_id: str, index: str = ""):
    c = _get_cluster(cluster_id)
    path = f"_cat/shards/{index}?h=index,shard,prirep,state,docs,store,node,unassigned.reason&format=json" if index else "_cat/shards?h=index,shard,prirep,state,docs,store,node,unassigned.reason&format=json"
    try:
        async with httpx.AsyncClient(timeout=20, verify=False) as client:
            r = await client.get(f"{c['host']}/{path}", headers=_auth_headers(c))
        return r.json() if r.is_success else []
    except Exception as exc:
        raise HTTPException(502, str(exc))
