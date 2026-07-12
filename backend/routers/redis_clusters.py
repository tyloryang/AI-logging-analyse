"""Redis 管理路由 - /api/redis/*

同时支持 Redis 单机/哨兵后端暴露的单实例，以及 Redis Cluster。
当前仅提供只读管理能力：连接测试、基础概览、节点信息与分片/槽位视图。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from redis.asyncio.cluster import RedisCluster
from redis.cluster import ClusterNode
from redis.exceptions import RedisError, ResponseError

from json_snapshot_store import read_json_file, write_json_file
from auth.deps import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/redis", tags=["redis"], dependencies=[Depends(require_admin)])

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "redis_clusters.json"
_TOTAL_HASH_SLOTS = 16384
_MODE_AUTO = "auto"
_MODE_STANDALONE = "standalone"
_MODE_CLUSTER = "cluster"
_VALID_MODES = {_MODE_AUTO, _MODE_STANDALONE, _MODE_CLUSTER}


class RedisClusterPayload(BaseModel):
    name: str
    startup_nodes: list[str] = Field(default_factory=list)
    mode: str = _MODE_AUTO
    username: str = ""
    password: str = ""
    tls: bool = False
    env: str = ""
    note: str = ""
    color: str = "#dc2626"


class RedisClusterTestPayload(RedisClusterPayload):
    cluster_id: str = ""


def _load_clusters() -> list[dict]:
    data = read_json_file(_DATA_FILE, default=[])
    return data if isinstance(data, list) else []


def _save_clusters(clusters: list[dict]) -> None:
    write_json_file(_DATA_FILE, clusters, ensure_parent=True)


def _get_cluster(cluster_id: str) -> dict:
    cluster = next((item for item in _load_clusters() if item.get("id") == cluster_id), None)
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Redis 连接 {cluster_id} 不存在")
    return cluster


def _normalize_mode(value: Any) -> str:
    mode = str(value or _MODE_AUTO).strip().lower()
    return mode if mode in _VALID_MODES else _MODE_AUTO


def _safe_cluster(cluster: dict) -> dict:
    item = dict(cluster)
    item["startup_nodes"] = _normalize_startup_nodes(item.get("startup_nodes"))
    item["mode"] = _normalize_mode(item.get("mode"))
    item["password_set"] = bool(item.pop("password", ""))
    return item


def _normalize_startup_nodes(values: Any) -> list[str]:
    if isinstance(values, str):
        raw_items = [values]
    elif isinstance(values, (list, tuple, set)):
        raw_items = list(values)
    else:
        raw_items = []

    result: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        for piece in str(item or "").replace("\r", "\n").replace(",", "\n").split("\n"):
            token = piece.strip()
            if not token:
                continue
            host, port = _parse_endpoint(token)
            endpoint = f"{host}:{port}"
            if endpoint not in seen:
                seen.add(endpoint)
                result.append(endpoint)
    return result


def _parse_endpoint(value: str) -> tuple[str, int]:
    token = str(value or "").strip()
    if not token:
        raise ValueError("空的 Redis 节点地址")

    if "://" in token:
        parsed = urlparse(token)
        host = parsed.hostname or ""
        port = parsed.port or 6379
        if not host:
            raise ValueError(f"无法解析节点地址: {value}")
        return host, int(port)

    if token.startswith("[") and "]" in token:
        host_part, _, port_part = token.rpartition(":")
        host = host_part.strip("[]")
        port = int(port_part or "6379")
        return host, port

    if ":" in token:
        host, port_text = token.rsplit(":", 1)
        return host.strip(), int(port_text or "6379")

    return token, 6379


def _connection_config_from_payload(payload: RedisClusterPayload | RedisClusterTestPayload) -> dict:
    startup_nodes = _normalize_startup_nodes(payload.startup_nodes)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="连接名称不能为空")
    if not startup_nodes:
        raise HTTPException(status_code=400, detail="至少需要一个节点地址")

    mode = _normalize_mode(payload.mode)
    return {
        "name": payload.name.strip(),
        "startup_nodes": startup_nodes,
        "mode": mode,
        "username": payload.username.strip(),
        "password": payload.password,
        "tls": bool(payload.tls),
        "env": payload.env.strip(),
        "note": payload.note.strip(),
        "color": (payload.color or "#dc2626").strip() or "#dc2626",
    }


def _flatten_redis_info(raw: Any) -> dict[str, Any]:
    """统一 redis-py INFO 返回为平坦字典。

    redis-py 5.x 在 `info("all")` 与少数 section 上会返回嵌套结构
    `{section_name: {key: value, ...}}`，而旧版本直接返回平坦
    `{key: value, ...}`。本函数兼容两种格式：把"值是 dict 的项"
    展开到外层，避免下游 `info.get("redis_version")` 等查询命中 None。

    keyspace section（`{"db0": {"keys": 100, ...}}`）不要走本函数 ——
    那里的 dict 是数据本身，不是 section 包装。
    """
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            out.update(value)
        else:
            out[key] = value
    return out


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except Exception:
        return default


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _human_bytes(value: int) -> str:
    if value <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.1f} {units[idx]}"


def _split_node_addr(addr: str) -> tuple[str, int | None, int | None, str]:
    text = str(addr or "").strip()
    hostname = ""
    if "," in text:
        text, hostname = text.split(",", 1)
        hostname = hostname.strip()

    bus_port = None
    if "@" in text:
        text, bus_text = text.split("@", 1)
        bus_port = _to_int(bus_text or None, default=0) or None

    if text.startswith("[") and "]" in text:
        host_part, _, port_text = text.rpartition(":")
        host = host_part.strip("[]")
        port = _to_int(port_text or None, default=6379)
        return host, port, bus_port, hostname

    if ":" in text:
        host, port_text = text.rsplit(":", 1)
        return host.strip(), _to_int(port_text or None, default=6379), bus_port, hostname

    return text, None, bus_port, hostname


def _count_slot_token(token: str) -> int:
    if not token or token.startswith("["):
        return 0
    if "-" in token:
        start_text, end_text = token.split("-", 1)
        start = _to_int(start_text, default=-1)
        end = _to_int(end_text, default=-1)
        if start >= 0 and end >= start:
            return end - start + 1
    return 1 if token.isdigit() else 0


def _parse_cluster_info(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")

    info: dict[str, str] = {}
    for line in str(raw or "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        info[key.strip()] = value.strip()
    return info


def _parse_cluster_nodes(raw: Any) -> list[dict]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")

    nodes: list[dict] = []
    for line in str(raw or "").splitlines():
        parts = line.strip().split()
        if len(parts) < 8:
            continue
        node_id, addr, flags_raw, master_id, ping_sent, pong_recv, config_epoch, link_state, *slot_tokens = parts
        host, port, bus_port, hostname = _split_node_addr(addr)
        flags = [flag for flag in flags_raw.split(",") if flag]
        role = "master" if "master" in flags else "replica" if ("slave" in flags or "replica" in flags) else "unknown"
        slot_ranges = [token for token in slot_tokens if not token.startswith("[")]
        slot_count = sum(_count_slot_token(token) for token in slot_ranges)
        failing_flags = {"fail", "pfail", "handshake", "noaddr"}
        connected = link_state == "connected" and not any(flag in failing_flags for flag in flags)
        status = "ok" if connected else "fail"

        nodes.append({
            "id": node_id,
            "address": addr,
            "host": host,
            "port": port,
            "bus_port": bus_port,
            "hostname": hostname,
            "flags": flags,
            "flags_text": ",".join(flags),
            "master_id": "" if master_id == "-" else master_id,
            "ping_sent": _to_int(ping_sent),
            "pong_recv": _to_int(pong_recv),
            "config_epoch": _to_int(config_epoch),
            "link_state": link_state,
            "role": role,
            "role_text": "Master" if role == "master" else "Replica" if role == "replica" else "Unknown",
            "slot_ranges": slot_ranges,
            "slot_count": slot_count,
            "connected": connected,
            "status": status,
            "myself": "myself" in flags,
        })

    nodes.sort(key=lambda item: (0 if item["role"] == "master" else 1, item["host"], item.get("port") or 0))
    return nodes


def _normalize_shards(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []

    shards: list[dict] = []
    for index, shard in enumerate(raw, start=1):
        slot_ranges: list[str] = []
        slot_count = 0
        for start, end in shard.get("slots", []) or []:
            start_int = _to_int(start)
            end_int = _to_int(end)
            if start_int == end_int:
                slot_ranges.append(str(start_int))
                slot_count += 1
            else:
                slot_ranges.append(f"{start_int}-{end_int}")
                slot_count += end_int - start_int + 1

        nodes: list[dict] = []
        for node in shard.get("nodes", []) or []:
            item = {str(k): v for k, v in dict(node).items()}
            endpoint = str(item.get("endpoint") or item.get("ip") or "").strip()
            host, port = "", None
            if endpoint:
                host, port = _parse_endpoint(endpoint)
            role = str(item.get("role") or "").lower()
            nodes.append({
                "id": str(item.get("id") or ""),
                "role": role,
                "role_text": "Master" if role == "master" else "Replica" if role == "replica" else "Node",
                "health": str(item.get("health") or ""),
                "host": host,
                "port": port,
                "endpoint": endpoint,
                "replication_offset": _to_int(item.get("replication-offset")),
            })

        shards.append({
            "id": f"shard-{index}",
            "slot_ranges": slot_ranges,
            "slot_count": slot_count,
            "nodes": nodes,
        })

    return shards


def _build_shards_from_cluster_nodes(nodes: list[dict]) -> list[dict]:
    replicas_by_master: dict[str, list[dict]] = {}
    for node in nodes:
        if node.get("role") != "replica" or not node.get("master_id"):
            continue
        replicas_by_master.setdefault(node["master_id"], []).append(node)

    shards: list[dict] = []
    for index, master in enumerate([item for item in nodes if item.get("role") == "master"], start=1):
        members = [master, *replicas_by_master.get(master["id"], [])]
        shards.append({
            "id": f"shard-{index}",
            "slot_ranges": master.get("slot_ranges", []),
            "slot_count": master.get("slot_count", 0),
            "nodes": [
                {
                    "id": item.get("id", ""),
                    "role": item.get("role", ""),
                    "role_text": item.get("role_text", ""),
                    "health": "online" if item.get("connected") else "offline",
                    "host": item.get("host", ""),
                    "port": item.get("port"),
                    "endpoint": f"{item.get('host', '')}:{item.get('port', '')}",
                }
                for item in members
            ],
        })
    return shards


def _build_single_instance_shards(nodes: list[dict]) -> list[dict]:
    if not nodes:
        return []
    node = nodes[0]
    return [{
        "id": "standalone",
        "slot_ranges": [],
        "slot_count": 0,
        "nodes": [{
            "id": node.get("id", ""),
            "role": node.get("role", "master"),
            "role_text": node.get("role_text", "Master"),
            "health": "online" if node.get("connected") else "offline",
            "host": node.get("host", ""),
            "port": node.get("port"),
            "endpoint": f"{node.get('host', '')}:{node.get('port', '')}",
        }],
    }]


def _build_node_client(config: dict, host: str, port: int) -> aioredis.Redis:
    return aioredis.Redis(
        host=host,
        port=port,
        username=config.get("username") or None,
        password=config.get("password") or None,
        ssl=bool(config.get("tls")),
        decode_responses=True,
        socket_connect_timeout=4,
        socket_timeout=4,
        health_check_interval=15,
    )


def _build_cluster_client(config: dict) -> RedisCluster:
    startup_nodes = [
        ClusterNode(host, port)
        for host, port in (_parse_endpoint(item) for item in _normalize_startup_nodes(config.get("startup_nodes")))
    ]
    return RedisCluster(
        startup_nodes=startup_nodes,
        username=config.get("username") or None,
        password=config.get("password") or None,
        ssl=bool(config.get("tls")),
        decode_responses=True,
        require_full_coverage=False,
        socket_connect_timeout=5,
        socket_timeout=5,
        health_check_interval=15,
    )


async def _detect_mode(config: dict) -> tuple[str, dict]:
    host, port = _parse_endpoint(_normalize_startup_nodes(config.get("startup_nodes"))[0])
    client = _build_node_client(config, host, port)
    try:
        info_cluster = _flatten_redis_info(await client.info("cluster"))
        cluster_enabled = str(info_cluster.get("cluster_enabled", "0")).strip() in {"1", "True", "true"}
        mode = _MODE_CLUSTER if cluster_enabled else _MODE_STANDALONE
        return mode, info_cluster
    finally:
        await client.aclose()


def _mode_label(mode: str) -> str:
    return {
        _MODE_CLUSTER: "Redis Cluster",
        _MODE_STANDALONE: "Redis 单机",
        _MODE_AUTO: "Redis 自动识别",
    }.get(mode, "Redis")


async def _resolve_runtime_mode(config: dict) -> tuple[str, dict]:
    requested = _normalize_mode(config.get("mode"))
    if requested == _MODE_AUTO:
        detected, info_cluster = await _detect_mode(config)
        return detected, {
            "requested_mode": requested,
            "detected_mode": detected,
            "cluster_info_section": info_cluster,
        }

    if requested == _MODE_CLUSTER:
        return _MODE_CLUSTER, {"requested_mode": requested, "detected_mode": _MODE_CLUSTER}

    return _MODE_STANDALONE, {"requested_mode": requested, "detected_mode": _MODE_STANDALONE}


async def _probe_standalone_node(config: dict, host: str, port: int) -> dict:
    client = _build_node_client(config, host, port)
    try:
        info = _flatten_redis_info(await client.info())
        keyspace_hits = _to_int(info.get("keyspace_hits"))
        keyspace_misses = _to_int(info.get("keyspace_misses"))
        hit_total = keyspace_hits + keyspace_misses
        used_memory = _to_int(info.get("used_memory"))
        replication_info = _flatten_redis_info(await client.info("replication"))
        server_info = _flatten_redis_info(await client.info("server"))

        return {
            "id": f"{host}:{port}",
            "address": f"{host}:{port}",
            "host": host,
            "port": port,
            "bus_port": None,
            "hostname": "",
            "flags": [],
            "flags_text": "standalone",
            "master_id": "",
            "ping_sent": 0,
            "pong_recv": 0,
            "config_epoch": 0,
            "link_state": "connected",
            "role": str(replication_info.get("role") or "master").lower(),
            "role_text": "Master" if str(replication_info.get("role") or "master").lower() == "master" else "Replica",
            "slot_ranges": [],
            "slot_count": 0,
            "connected": True,
            "status": "ok",
            "myself": True,
            "redis_version": str(server_info.get("redis_version") or info.get("redis_version") or ""),
            "connected_clients": _to_int(info.get("connected_clients")),
            "used_memory": used_memory,
            "used_memory_human": str(info.get("used_memory_human") or _human_bytes(used_memory)),
            "ops_per_sec": _to_int(info.get("instantaneous_ops_per_sec")),
            "uptime_days": _to_int(info.get("uptime_in_days")),
            "role_reported": str(replication_info.get("role") or ""),
            "master_host": str(replication_info.get("master_host") or ""),
            "master_link_status": str(replication_info.get("master_link_status") or ""),
            "keyspace_hit_rate": round((keyspace_hits / hit_total) * 100, 1) if hit_total > 0 else None,
        }
    finally:
        await client.aclose()


async def _probe_cluster_node(config: dict, node: dict) -> dict:
    host = str(node.get("host") or "").strip()
    port = _to_int(node.get("port"), default=0)
    if not host or port <= 0:
        return {}

    client = _build_node_client(config, host, port)
    try:
        info = _flatten_redis_info(await client.info())
        keyspace_hits = _to_int(info.get("keyspace_hits"))
        keyspace_misses = _to_int(info.get("keyspace_misses"))
        hit_total = keyspace_hits + keyspace_misses
        used_memory = _to_int(info.get("used_memory"))
        return {
            "redis_version": str(info.get("redis_version") or ""),
            "connected_clients": _to_int(info.get("connected_clients")),
            "used_memory": used_memory,
            "used_memory_human": str(info.get("used_memory_human") or _human_bytes(used_memory)),
            "ops_per_sec": _to_int(info.get("instantaneous_ops_per_sec")),
            "uptime_days": _to_int(info.get("uptime_in_days")),
            "role_reported": str(info.get("role") or ""),
            "master_host": str(info.get("master_host") or ""),
            "master_link_status": str(info.get("master_link_status") or ""),
            "keyspace_hit_rate": round((keyspace_hits / hit_total) * 100, 1) if hit_total > 0 else None,
        }
    except Exception as exc:
        logger.warning("[redis] probe cluster node failed %s:%s: %s", host, port, exc)
        return {
            "probe_error": str(exc),
            "connected": False,
            "status": "warn" if node.get("status") == "ok" else node.get("status", "fail"),
        }
    finally:
        await client.aclose()


def _merge_node_metrics(nodes: list[dict], metrics: list[dict]) -> list[dict]:
    merged: list[dict] = []
    for node, extra in zip(nodes, metrics):
        item = dict(node)
        if extra:
            item.update(extra)
        if item.get("probe_error") and item.get("status") == "ok":
            item["status"] = "warn"
        merged.append(item)
    return merged


def _cluster_summary(cluster: dict, mode: str, info: dict[str, str], nodes: list[dict], shards: list[dict]) -> dict:
    known_nodes = _to_int(info.get("cluster_known_nodes"), default=len(nodes))
    cluster_size = _to_int(info.get("cluster_size"), default=len([n for n in nodes if n.get("role") == "master"]))
    masters = len([node for node in nodes if node.get("role") == "master"])
    replicas = len([node for node in nodes if node.get("role") == "replica"])
    connected_nodes = len([node for node in nodes if node.get("connected")])
    unhealthy_nodes = len([node for node in nodes if node.get("status") != "ok"])
    slots_assigned = _to_int(info.get("cluster_slots_assigned"))
    slots_ok = _to_int(info.get("cluster_slots_ok"))
    slots_fail = _to_int(info.get("cluster_slots_fail"))
    slots_pfail = _to_int(info.get("cluster_slots_pfail"))
    total_memory = sum(_to_int(node.get("used_memory")) for node in nodes)
    total_clients = sum(_to_int(node.get("connected_clients")) for node in nodes)
    total_ops = sum(_to_int(node.get("ops_per_sec")) for node in nodes)
    coverage_pct = round((slots_assigned / _TOTAL_HASH_SLOTS) * 100, 1) if slots_assigned else 0.0
    versions = sorted({str(node.get("redis_version") or "") for node in nodes if node.get("redis_version")})

    if mode == _MODE_STANDALONE:
        state = "ok" if connected_nodes else "down"
        cluster_size = 1 if nodes else 0
        known_nodes = len(nodes)
        shards = shards or _build_single_instance_shards(nodes)
    else:
        state = str(info.get("cluster_state") or "unknown").lower()

    return {
        "cluster_id": cluster.get("id", ""),
        "cluster_name": cluster.get("name", ""),
        "mode": mode,
        "mode_label": _mode_label(mode),
        "cluster_state": state,
        "state_tone": "ok" if state == "ok" and unhealthy_nodes == 0 else "warn" if state in {"ok", "down"} and connected_nodes else "danger",
        "known_nodes": known_nodes,
        "cluster_size": cluster_size,
        "master_count": masters,
        "replica_count": replicas,
        "connected_nodes": connected_nodes,
        "unhealthy_nodes": unhealthy_nodes,
        "slots_assigned": slots_assigned,
        "slots_ok": slots_ok,
        "slots_fail": slots_fail,
        "slots_pfail": slots_pfail,
        "coverage_pct": coverage_pct,
        "total_memory": total_memory,
        "total_memory_human": _human_bytes(total_memory),
        "total_clients": total_clients,
        "total_ops_per_sec": total_ops,
        "versions": versions,
        "shard_count": len(shards),
    }


def _cluster_mode_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return "cluster mode is not enabled on this node" in text


async def _test_standalone_connection(config: dict) -> dict:
    host, port = _parse_endpoint(_normalize_startup_nodes(config.get("startup_nodes"))[0])
    client = _build_node_client(config, host, port)
    try:
        pong = await client.ping()
        info_server = _flatten_redis_info(await client.info("server"))
        info_replication = _flatten_redis_info(await client.info("replication"))
        return {
            "ok": bool(pong),
            "mode": _MODE_STANDALONE,
            "detected_mode": _MODE_STANDALONE,
            "redis_version": str(info_server.get("redis_version") or ""),
            "role": str(info_replication.get("role") or "master"),
            "message": "Redis 单机连接成功",
        }
    except Exception as exc:
        logger.warning("[redis] standalone test failed: %s", exc)
        return {"ok": False, "mode": _MODE_STANDALONE, "error": str(exc), "message": "Redis 单机连接失败"}
    finally:
        await client.aclose()


async def _test_cluster_connection(config: dict) -> dict:
    client = _build_cluster_client(config)
    try:
        await client.initialize()
        await client.ping()
        cluster_info = _parse_cluster_info(await client.cluster_info())
        raw_nodes = await client.cluster_nodes()
        nodes = _parse_cluster_nodes(raw_nodes)
        return {
            "ok": True,
            "mode": _MODE_CLUSTER,
            "detected_mode": _MODE_CLUSTER,
            "cluster_state": cluster_info.get("cluster_state", "unknown"),
            "known_nodes": _to_int(cluster_info.get("cluster_known_nodes"), default=len(nodes)),
            "cluster_size": _to_int(cluster_info.get("cluster_size")),
            "message": "Redis Cluster 连接成功",
        }
    except Exception as exc:
        logger.warning("[redis] cluster test failed: %s", exc)
        return {"ok": False, "mode": _MODE_CLUSTER, "error": str(exc), "message": "Redis Cluster 连接失败"}
    finally:
        await client.aclose()


async def _test_connection(config: dict) -> dict:
    runtime_mode, detect_meta = await _resolve_runtime_mode(config)
    result = await (_test_cluster_connection(config) if runtime_mode == _MODE_CLUSTER else _test_standalone_connection(config))
    result["requested_mode"] = detect_meta.get("requested_mode", _MODE_AUTO)
    result["detected_mode"] = detect_meta.get("detected_mode", runtime_mode)
    return result


async def _load_standalone_overview(cluster: dict) -> dict:
    host, port = _parse_endpoint(_normalize_startup_nodes(cluster.get("startup_nodes"))[0])
    node = await _probe_standalone_node(cluster, host, port)
    nodes = [node]
    shards = _build_single_instance_shards(nodes)
    summary = _cluster_summary(cluster, _MODE_STANDALONE, {}, nodes, shards)
    return {
        "cluster": _safe_cluster(cluster),
        "cluster_info": {},
        "summary": summary,
        "nodes": nodes,
        "shards": shards,
    }


async def _load_cluster_overview(cluster: dict) -> dict:
    client = _build_cluster_client(cluster)
    try:
        await client.initialize()
        info_raw, nodes_raw = await asyncio.gather(
            client.cluster_info(),
            client.cluster_nodes(),
        )
        cluster_info = _parse_cluster_info(info_raw)
        nodes = _parse_cluster_nodes(nodes_raw)

        try:
            shards_raw = await client.cluster_shards()
            shards = _normalize_shards(shards_raw)
        except Exception as exc:
            logger.warning("[redis] cluster_shards failed for %s: %s", cluster.get("name"), exc)
            shards = []

        metrics = await asyncio.gather(*(_probe_cluster_node(cluster, node) for node in nodes))
        nodes = _merge_node_metrics(nodes, metrics)
        if not shards:
            shards = _build_shards_from_cluster_nodes(nodes)

        return {
            "cluster": _safe_cluster(cluster),
            "cluster_info": cluster_info,
            "summary": _cluster_summary(cluster, _MODE_CLUSTER, cluster_info, nodes, shards),
            "nodes": nodes,
            "shards": shards,
        }
    finally:
        await client.aclose()


async def _load_overview(cluster: dict) -> dict:
    runtime_mode, _ = await _resolve_runtime_mode(cluster)
    if runtime_mode == _MODE_STANDALONE:
        return await _load_standalone_overview(cluster)
    return await _load_cluster_overview(cluster)


@router.get("/clusters")
async def list_clusters():
    return [_safe_cluster(item) for item in _load_clusters()]


@router.post("/clusters")
async def create_cluster(body: RedisClusterPayload):
    cluster = {
        "id": str(uuid.uuid4()),
        **_connection_config_from_payload(body),
    }
    clusters = _load_clusters()
    clusters.append(cluster)
    _save_clusters(clusters)
    return _safe_cluster(cluster)


@router.put("/clusters/{cluster_id}")
async def update_cluster(cluster_id: str, body: RedisClusterPayload):
    clusters = _load_clusters()
    index = next((idx for idx, item in enumerate(clusters) if item.get("id") == cluster_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="Redis 连接不存在")

    current = clusters[index]
    updated = _connection_config_from_payload(body)
    if not body.password:
        updated["password"] = current.get("password", "")
    clusters[index] = {**current, **updated}
    _save_clusters(clusters)
    return _safe_cluster(clusters[index])


@router.delete("/clusters/{cluster_id}")
async def delete_cluster(cluster_id: str):
    clusters = [item for item in _load_clusters() if item.get("id") != cluster_id]
    _save_clusters(clusters)
    return {"ok": True}


@router.post("/clusters/test-config")
async def test_cluster_config(body: RedisClusterTestPayload):
    cluster = _connection_config_from_payload(body)
    if body.cluster_id and not body.password:
        cluster["password"] = _get_cluster(body.cluster_id).get("password", "")
    return await _test_connection(cluster)


@router.get("/clusters/{cluster_id}/test")
async def test_cluster(cluster_id: str):
    return await _test_connection(_get_cluster(cluster_id))


@router.get("/clusters/{cluster_id}/overview")
async def cluster_overview(cluster_id: str):
    return await _load_overview(_get_cluster(cluster_id))


# ── Key Browser ────────────────────────────────────────────────────────────────

async def _get_single_client(cluster: dict, db: int = 0) -> aioredis.Redis:
    """返回单机或 Cluster 首节点的 Redis 客户端。"""
    nodes = _normalize_startup_nodes(cluster.get("startup_nodes"))
    host, port = _parse_endpoint(nodes[0])
    return aioredis.Redis(
        host=host, port=port,
        username=cluster.get("username") or None,
        password=cluster.get("password") or None,
        ssl=bool(cluster.get("tls")),
        db=db,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


@router.get("/clusters/{cluster_id}/keys")
async def scan_keys(
    cluster_id: str,
    pattern: str = "*",
    cursor: int = 0,
    count: int = 100,
    db: int = 0,
):
    """SCAN 遍历 Key 列表，返回 cursor + key 基础信息（type/ttl）。"""
    cluster = _get_cluster(cluster_id)
    client = await _get_single_client(cluster, db)
    try:
        next_cursor, keys = await client.scan(cursor=cursor, match=pattern, count=count)
        # 并行获取每个 key 的 type 和 ttl
        async def _key_meta(key: str) -> dict:
            try:
                ktype, ttl = await asyncio.gather(client.type(key), client.ttl(key))
                return {"key": key, "type": str(ktype), "ttl": int(ttl)}
            except Exception:
                return {"key": key, "type": "unknown", "ttl": -1}
        metas = await asyncio.gather(*(_key_meta(k) for k in keys))
        return {"cursor": int(next_cursor), "keys": list(metas), "db": db}
    finally:
        await client.aclose()


@router.get("/clusters/{cluster_id}/key")
async def get_key_value(cluster_id: str, key: str, db: int = 0):
    """获取 Key 的完整值（根据类型选择正确命令）。"""
    cluster = _get_cluster(cluster_id)
    client = await _get_single_client(cluster, db)
    try:
        ktype = str(await client.type(key))
        ttl   = int(await client.ttl(key))
        enc   = ""
        try:
            enc = str(await client.object_encoding(key))
        except Exception:
            pass

        value: Any = None
        length: int | None = None

        if ktype == "string":
            value = await client.get(key)
            length = len(value) if isinstance(value, str) else None

        elif ktype == "list":
            length = await client.llen(key)
            value = await client.lrange(key, 0, 199)   # 最多 200 条

        elif ktype == "hash":
            value = await client.hgetall(key)
            length = len(value)

        elif ktype == "set":
            members = await client.sscan_iter(key, count=200)
            value = [m async for m in members]
            length = await client.scard(key)

        elif ktype == "zset":
            value = await client.zrange(key, 0, 199, withscores=True)
            value = [{"member": m, "score": s} for m, s in value]
            length = await client.zcard(key)

        elif ktype == "stream":
            entries = await client.xrange(key, count=100)
            value = [{"id": eid, "fields": dict(fields)} for eid, fields in entries]
            length = await client.xlen(key)

        return {
            "key": key, "type": ktype, "ttl": ttl,
            "encoding": enc, "length": length,
            "value": value, "db": db,
        }
    except ResponseError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        await client.aclose()


class KeyDeletePayload(BaseModel):
    db: int = 0


@router.delete("/clusters/{cluster_id}/key")
async def delete_key(cluster_id: str, key: str, db: int = 0):
    cluster = _get_cluster(cluster_id)
    client = await _get_single_client(cluster, db)
    try:
        deleted = await client.delete(key)
        return {"ok": deleted > 0, "deleted": deleted}
    finally:
        await client.aclose()


class KeyTTLPayload(BaseModel):
    ttl: int   # -1 = persist, >=0 = seconds


@router.put("/clusters/{cluster_id}/key/ttl")
async def set_key_ttl(cluster_id: str, key: str, body: KeyTTLPayload, db: int = 0):
    cluster = _get_cluster(cluster_id)
    client = await _get_single_client(cluster, db)
    try:
        if body.ttl < 0:
            result = await client.persist(key)
        else:
            result = await client.expire(key, body.ttl)
        return {"ok": bool(result)}
    finally:
        await client.aclose()


# ── 监控（INFO 全量 + Slowlog）─────────────────────────────────────────────────

@router.get("/clusters/{cluster_id}/info")
async def get_redis_info(cluster_id: str, db: int = 0):
    """获取 Redis INFO all 并分段返回。"""
    cluster = _get_cluster(cluster_id)
    client = await _get_single_client(cluster, db)
    try:
        # redis-py 5.x 在 INFO all 上可能返回 {section: {...}} 嵌套字典，
        # 而旧版本返回平坦字典。统一展平后下游 info.get("redis_version") 等
        # 才能拿到真实值（这正是「监控统计无数据」问题的根因）。
        info: dict = _flatten_redis_info(await client.info("all"))
        # keyspace 段保留嵌套结构（{"db0": {"keys": ..., ...}}），不能展平
        keyspace: dict = await client.info("keyspace")
        # 按段分组
        groups: dict[str, dict] = {
            "server":      {}, "clients":     {}, "memory":  {},
            "stats":       {}, "replication": {}, "cpu":     {},
            "persistence": {}, "keyspace":    keyspace,
        }
        section_keys = {
            "server":      {"redis_version", "redis_mode", "os", "arch_bits", "uptime_in_seconds",
                            "uptime_in_days", "hz", "tcp_port", "executable", "config_file"},
            "clients":     {"connected_clients", "blocked_clients", "tracking_clients",
                            "clients_in_timeout_table", "maxclients"},
            "memory":      {"used_memory", "used_memory_human", "used_memory_rss_human",
                            "used_memory_peak_human", "used_memory_startup", "mem_fragmentation_ratio",
                            "maxmemory", "maxmemory_human", "maxmemory_policy"},
            "stats":       {"total_commands_processed", "instantaneous_ops_per_sec",
                            "total_net_input_bytes", "total_net_output_bytes",
                            "keyspace_hits", "keyspace_misses", "expired_keys",
                            "evicted_keys", "total_connections_received"},
            "replication": {"role", "connected_slaves", "master_replid", "master_repl_offset",
                            "repl_backlog_active", "repl_backlog_size"},
            "cpu":         {"used_cpu_sys", "used_cpu_user"},
            "persistence": {"rdb_changes_since_last_save", "rdb_last_save_time",
                            "rdb_last_bgsave_status", "aof_enabled"},
        }
        for key, val in info.items():
            for section, keys in section_keys.items():
                if key in keys:
                    groups[section][key] = val
                    break
        # 计算命中率
        hits   = _to_int(info.get("keyspace_hits"))
        misses = _to_int(info.get("keyspace_misses"))
        total  = hits + misses
        groups["stats"]["hit_rate"] = round(hits / total * 100, 2) if total else None
        return groups
    finally:
        await client.aclose()


@router.get("/clusters/{cluster_id}/slowlog")
async def get_slowlog(cluster_id: str, count: int = 25, db: int = 0):
    cluster = _get_cluster(cluster_id)
    client = await _get_single_client(cluster, db)
    try:
        entries = await client.slowlog_get(count)
        result = []
        for entry in entries:
            cmd = entry.get("command", b"") if isinstance(entry, dict) else b""
            if isinstance(cmd, bytes):
                cmd = cmd.decode("utf-8", errors="replace")
            args = entry.get("args", []) if isinstance(entry, dict) else []
            args_str = " ".join(
                a.decode("utf-8", errors="replace") if isinstance(a, bytes) else str(a)
                for a in args
            )
            result.append({
                "id":          entry.get("id", 0) if isinstance(entry, dict) else 0,
                "timestamp":   entry.get("start_time", 0) if isinstance(entry, dict) else 0,
                "duration_us": entry.get("duration", 0) if isinstance(entry, dict) else 0,
                "command":     f"{cmd} {args_str}".strip(),
                "client_addr": entry.get("client_addr", "") if isinstance(entry, dict) else "",
                "client_name": entry.get("client_name", "") if isinstance(entry, dict) else "",
            })
        return {"entries": result}
    finally:
        await client.aclose()


# ── 命令控制台 ─────────────────────────────────────────────────────────────────

class RedisCommandPayload(BaseModel):
    command: str
    db: int = 0


@router.post("/clusters/{cluster_id}/command")
async def run_command(cluster_id: str, body: RedisCommandPayload):
    """执行原始 Redis 命令（禁止 FLUSHALL / FLUSHDB / SHUTDOWN 等危险命令）。"""
    BLOCKED = {"flushall", "flushdb", "shutdown", "slaveof", "replicaof", "debug", "module"}

    raw = body.command.strip()
    if not raw:
        raise HTTPException(status_code=400, detail="命令不能为空")

    # 解析命令和参数（保留引号内的空格）
    import shlex
    try:
        parts = shlex.split(raw)
    except ValueError:
        parts = raw.split()

    if not parts:
        raise HTTPException(status_code=400, detail="命令不能为空")
    if parts[0].lower() in BLOCKED:
        raise HTTPException(status_code=403, detail=f"命令 {parts[0].upper()} 已被禁止执行")

    cluster = _get_cluster(cluster_id)

    # 检测运行模式：cluster 模式不支持 SELECT（db>0）
    runtime_mode, _ = await _resolve_runtime_mode(cluster)
    use_db = 0 if runtime_mode == _MODE_CLUSTER else body.db

    client = await _get_single_client(cluster, use_db)
    try:
        result = await client.execute_command(*parts)

        def _serialize(v: Any) -> Any:
            if v is None:
                return None
            if isinstance(v, bool):
                return v
            if isinstance(v, bytes):
                return v.decode("utf-8", errors="replace")
            if isinstance(v, (int, float)):
                return v
            if isinstance(v, str):
                return v
            if isinstance(v, (list, tuple)):
                return [_serialize(x) for x in v]
            if isinstance(v, dict):
                return {_serialize(k): _serialize(val) for k, val in v.items()}
            return str(v)

        return {
            "ok":       True,
            "result":   _serialize(result),
            "db_used":  use_db,
            "mode":     runtime_mode,
        }
    except ResponseError as exc:
        return {"ok": False, "error": str(exc), "db_used": use_db}
    except RedisError as exc:
        return {"ok": False, "error": f"Redis 连接错误: {exc}", "db_used": use_db}
    except Exception as exc:
        logger.error("[redis] command exec error: %s", exc, exc_info=True)
        return {"ok": False, "error": f"执行异常: {exc}", "db_used": use_db}
    finally:
        await client.aclose()
