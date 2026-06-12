"""Kafka 管理路由 - /api/kafka/*

支持 Kafka 0.10+（含 kafka_2.12-2.8.2），基于 aiokafka AdminClient。
只读管理为主：连接测试、集群概览、Broker/Topic/分区视图、消费组 Lag 监控；
写操作提供 Topic 创建/删除（删除属高危，前端二次确认）。
数据持久化到 data/kafka_clusters.json，模式与 redis_clusters 一致。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from json_snapshot_store import read_json_file, write_json_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/kafka", tags=["kafka"])

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "kafka_clusters.json"

_VALID_SECURITY = {"PLAINTEXT", "SASL_PLAINTEXT", "SSL", "SASL_SSL"}
_VALID_SASL = {"PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"}
_REQUEST_TIMEOUT_MS = 10000


class KafkaClusterPayload(BaseModel):
    name: str
    bootstrap_servers: list[str] = Field(default_factory=list)
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: str = "PLAIN"
    username: str = ""
    password: str = ""
    env: str = ""
    note: str = ""
    color: str = "#0ea5e9"


class KafkaClusterTestPayload(KafkaClusterPayload):
    cluster_id: str = ""


class TopicCreatePayload(BaseModel):
    name: str
    partitions: int = Field(3, ge=1, le=512)
    replication_factor: int = Field(1, ge=1, le=16)
    configs: dict[str, str] = Field(default_factory=dict)


# ── 存储 ──────────────────────────────────────────────────────────────────────

def _load_clusters() -> list[dict]:
    data = read_json_file(_DATA_FILE, default=[])
    return data if isinstance(data, list) else []


def _save_clusters(clusters: list[dict]) -> None:
    write_json_file(_DATA_FILE, clusters, ensure_parent=True)


def _get_cluster(cluster_id: str) -> dict:
    cluster = next((c for c in _load_clusters() if c.get("id") == cluster_id), None)
    if not cluster:
        raise HTTPException(status_code=404, detail=f"Kafka 连接 {cluster_id} 不存在")
    return cluster


def _safe_cluster(cluster: dict) -> dict:
    item = dict(cluster)
    item["bootstrap_servers"] = _normalize_servers(item.get("bootstrap_servers"))
    item["password_set"] = bool(item.pop("password", ""))
    return item


def _normalize_servers(values: Any) -> list[str]:
    if isinstance(values, str):
        raw = [values]
    elif isinstance(values, (list, tuple, set)):
        raw = list(values)
    else:
        raw = []

    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        for piece in str(item or "").replace("\r", "\n").replace(",", "\n").split("\n"):
            token = piece.strip()
            if not token:
                continue
            if ":" not in token:
                token = f"{token}:9092"
            if token not in seen:
                seen.add(token)
                result.append(token)
    return result


def _config_from_payload(payload: KafkaClusterPayload) -> dict:
    servers = _normalize_servers(payload.bootstrap_servers)
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="连接名称不能为空")
    if not servers:
        raise HTTPException(status_code=400, detail="至少需要一个 bootstrap server 地址")
    security = payload.security_protocol.strip().upper() or "PLAINTEXT"
    if security not in _VALID_SECURITY:
        raise HTTPException(status_code=400, detail=f"不支持的 security_protocol: {security}")
    sasl = payload.sasl_mechanism.strip().upper() or "PLAIN"
    if sasl not in _VALID_SASL:
        raise HTTPException(status_code=400, detail=f"不支持的 sasl_mechanism: {sasl}")
    return {
        "name": payload.name.strip(),
        "bootstrap_servers": servers,
        "security_protocol": security,
        "sasl_mechanism": sasl,
        "username": payload.username.strip(),
        "password": payload.password,
        "env": payload.env.strip(),
        "note": payload.note.strip(),
        "color": (payload.color or "#0ea5e9").strip() or "#0ea5e9",
    }


# ── 客户端构造 ────────────────────────────────────────────────────────────────

def _client_kwargs(cluster: dict) -> dict:
    kwargs: dict = {
        "bootstrap_servers": _normalize_servers(cluster.get("bootstrap_servers")),
        "security_protocol": cluster.get("security_protocol") or "PLAINTEXT",
        "request_timeout_ms": _REQUEST_TIMEOUT_MS,
    }
    if "SASL" in kwargs["security_protocol"]:
        kwargs["sasl_mechanism"] = cluster.get("sasl_mechanism") or "PLAIN"
        kwargs["sasl_plain_username"] = cluster.get("username") or None
        kwargs["sasl_plain_password"] = cluster.get("password") or None
    return kwargs


async def _with_admin(cluster: dict, fn):
    """打开 AdminClient 执行 fn(admin)，确保关闭。统一异常转 HTTP 502。"""
    admin = AIOKafkaAdminClient(**_client_kwargs(cluster))
    try:
        await admin.start()
        return await fn(admin)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("[kafka] admin op failed for %s: %s", cluster.get("name"), exc)
        raise HTTPException(status_code=502, detail=f"Kafka 连接/操作失败: {exc}")
    finally:
        try:
            await admin.close()
        except Exception:
            pass


async def _end_offsets(cluster: dict, partitions: list[TopicPartition]) -> dict:
    """用无组消费者获取分区 LogEndOffset。"""
    if not partitions:
        return {}
    consumer = AIOKafkaConsumer(**_client_kwargs(cluster), enable_auto_commit=False)
    try:
        await consumer.start()
        return await consumer.end_offsets(partitions)
    finally:
        try:
            await consumer.stop()
        except Exception:
            pass


def _node_dict(node: Any) -> dict:
    """broker 节点元数据 → dict（兼容 tuple/对象两种返回）。"""
    if isinstance(node, dict):
        return {
            "id": node.get("node_id", node.get("id")),
            "host": node.get("host", ""),
            "port": node.get("port"),
            "rack": node.get("rack") or "",
        }
    return {
        "id": getattr(node, "nodeId", getattr(node, "id", None)),
        "host": getattr(node, "host", ""),
        "port": getattr(node, "port", None),
        "rack": getattr(node, "rack", None) or "",
    }


# ── 连接 CRUD ─────────────────────────────────────────────────────────────────

@router.get("/clusters")
async def list_clusters():
    return [_safe_cluster(c) for c in _load_clusters()]


@router.post("/clusters")
async def create_cluster(body: KafkaClusterPayload):
    cluster = {"id": str(uuid.uuid4()), **_config_from_payload(body)}
    clusters = _load_clusters()
    clusters.append(cluster)
    _save_clusters(clusters)
    return _safe_cluster(cluster)


@router.put("/clusters/{cluster_id}")
async def update_cluster(cluster_id: str, body: KafkaClusterPayload):
    clusters = _load_clusters()
    index = next((i for i, c in enumerate(clusters) if c.get("id") == cluster_id), None)
    if index is None:
        raise HTTPException(status_code=404, detail="Kafka 连接不存在")
    current = clusters[index]
    updated = _config_from_payload(body)
    if not body.password:
        updated["password"] = current.get("password", "")
    clusters[index] = {**current, **updated}
    _save_clusters(clusters)
    return _safe_cluster(clusters[index])


@router.delete("/clusters/{cluster_id}")
async def delete_cluster(cluster_id: str):
    clusters = [c for c in _load_clusters() if c.get("id") != cluster_id]
    _save_clusters(clusters)
    return {"ok": True}


# ── 连接测试 ──────────────────────────────────────────────────────────────────

async def _test_connection(cluster: dict) -> dict:
    try:
        async def _probe(admin: AIOKafkaAdminClient):
            meta = await admin.describe_cluster()
            brokers = [_node_dict(b) for b in meta.get("brokers", [])]
            api_version = getattr(admin, "_client", None)
            version_text = ""
            if api_version is not None:
                ver = getattr(api_version, "api_version", None)
                if ver:
                    version_text = ".".join(str(v) for v in ver)
            return {
                "ok": True,
                "cluster_id": meta.get("cluster_id", ""),
                "controller_id": meta.get("controller_id"),
                "broker_count": len(brokers),
                "brokers": brokers,
                "api_version": version_text,
                "message": f"Kafka 连接成功（{len(brokers)} 个 Broker）",
            }
        return await _with_admin(cluster, _probe)
    except HTTPException as exc:
        return {"ok": False, "error": str(exc.detail), "message": "Kafka 连接失败"}


@router.post("/clusters/test-config")
async def test_cluster_config(body: KafkaClusterTestPayload):
    cluster = _config_from_payload(body)
    if body.cluster_id and not body.password:
        cluster["password"] = _get_cluster(body.cluster_id).get("password", "")
    return await _test_connection(cluster)


@router.get("/clusters/{cluster_id}/test")
async def test_cluster(cluster_id: str):
    return await _test_connection(_get_cluster(cluster_id))


# ── 集群概览 ──────────────────────────────────────────────────────────────────

@router.get("/clusters/{cluster_id}/overview")
async def cluster_overview(cluster_id: str):
    cluster = _get_cluster(cluster_id)

    async def _build(admin: AIOKafkaAdminClient):
        meta, topic_names, groups_raw = await asyncio.gather(
            admin.describe_cluster(),
            admin.list_topics(),
            admin.list_consumer_groups(),
        )
        brokers = [_node_dict(b) for b in meta.get("brokers", [])]
        controller_id = meta.get("controller_id")

        user_topics = sorted(t for t in topic_names if not t.startswith("__"))
        internal_topics = sorted(t for t in topic_names if t.startswith("__"))

        # Topic 元数据：统计分区与副本
        partition_total = 0
        under_replicated = 0
        topics_meta = await admin.describe_topics(list(topic_names)) if topic_names else []
        for tm in topics_meta:
            for p in tm.get("partitions", []):
                partition_total += 1
                if len(p.get("isr", [])) < len(p.get("replicas", [])):
                    under_replicated += 1

        groups = [
            {"group_id": g[0], "protocol_type": g[1] if len(g) > 1 else ""}
            for g in (groups_raw or [])
        ]

        # broker 版本探测（best-effort，2.x 返回如 2.8-IV1）
        version_text = ""
        try:
            from aiokafka.admin.config_resource import ConfigResource, ConfigResourceType
            if brokers:
                res = ConfigResource(ConfigResourceType.BROKER, str(brokers[0]["id"]))
                cfg_resp = await admin.describe_configs([res])
                for resp in cfg_resp:
                    for resource in getattr(resp, "resources", []):
                        for entry in resource[4]:
                            if entry[0] == "inter.broker.protocol.version":
                                version_text = str(entry[1])
        except Exception as exc:
            logger.debug("[kafka] version probe failed: %s", exc)

        return {
            "cluster": _safe_cluster(cluster),
            "summary": {
                "cluster_id": meta.get("cluster_id", ""),
                "controller_id": controller_id,
                "broker_count": len(brokers),
                "topic_count": len(user_topics),
                "internal_topic_count": len(internal_topics),
                "partition_count": partition_total,
                "under_replicated_partitions": under_replicated,
                "consumer_group_count": len(groups),
                "broker_version": version_text,
                "state_tone": "danger" if not brokers else "warn" if under_replicated else "ok",
            },
            "brokers": [
                {**b, "is_controller": b["id"] == controller_id}
                for b in sorted(brokers, key=lambda x: x["id"] or 0)
            ],
            "consumer_groups": groups,
        }

    return await _with_admin(cluster, _build)


# ── Topic 管理 ────────────────────────────────────────────────────────────────

@router.get("/clusters/{cluster_id}/topics")
async def list_topics(cluster_id: str, include_internal: bool = False):
    cluster = _get_cluster(cluster_id)

    async def _build(admin: AIOKafkaAdminClient):
        names = await admin.list_topics()
        if not include_internal:
            names = [t for t in names if not t.startswith("__")]
        if not names:
            return {"topics": []}
        metas = await admin.describe_topics(sorted(names))
        # 各 Topic 消息总量（end offset 求和，近似值）
        partitions: list[TopicPartition] = []
        for tm in metas:
            for p in tm.get("partitions", []):
                partitions.append(TopicPartition(tm["topic"], p["partition"]))
        try:
            ends = await _end_offsets(cluster, partitions)
        except Exception as exc:
            logger.debug("[kafka] end_offsets failed: %s", exc)
            ends = {}

        topics = []
        for tm in metas:
            parts = tm.get("partitions", [])
            replication = len(parts[0].get("replicas", [])) if parts else 0
            msg_total = sum(
                ends.get(TopicPartition(tm["topic"], p["partition"]), 0)
                for p in parts
            )
            under = sum(1 for p in parts if len(p.get("isr", [])) < len(p.get("replicas", [])))
            topics.append({
                "name": tm["topic"],
                "internal": tm.get("is_internal", tm["topic"].startswith("__")),
                "partitions": len(parts),
                "replication_factor": replication,
                "message_count": msg_total,
                "under_replicated": under,
            })
        topics.sort(key=lambda t: t["name"])
        return {"topics": topics}

    return await _with_admin(cluster, _build)


@router.get("/clusters/{cluster_id}/topics/{topic}")
async def topic_detail(cluster_id: str, topic: str):
    cluster = _get_cluster(cluster_id)

    async def _build(admin: AIOKafkaAdminClient):
        metas = await admin.describe_topics([topic])
        if not metas:
            raise HTTPException(status_code=404, detail=f"Topic {topic} 不存在")
        tm = metas[0]
        parts = tm.get("partitions", [])
        tps = [TopicPartition(topic, p["partition"]) for p in parts]
        try:
            ends = await _end_offsets(cluster, tps)
        except Exception:
            ends = {}

        partitions = []
        for p in sorted(parts, key=lambda x: x["partition"]):
            tp = TopicPartition(topic, p["partition"])
            partitions.append({
                "partition": p["partition"],
                "leader": p.get("leader"),
                "replicas": p.get("replicas", []),
                "isr": p.get("isr", []),
                "end_offset": ends.get(tp, 0),
                "under_replicated": len(p.get("isr", [])) < len(p.get("replicas", [])),
            })

        # Topic 配置（best-effort）
        configs: list[dict] = []
        try:
            from aiokafka.admin.config_resource import ConfigResource, ConfigResourceType
            cfg_resp = await admin.describe_configs([ConfigResource(ConfigResourceType.TOPIC, topic)])
            for resp in cfg_resp:
                for resource in getattr(resp, "resources", []):
                    for entry in resource[4]:
                        name, value = str(entry[0]), entry[1]
                        is_default = bool(entry[3]) if len(entry) > 3 else False
                        if not is_default:
                            configs.append({"name": name, "value": "" if value is None else str(value)})
        except Exception as exc:
            logger.debug("[kafka] topic config probe failed: %s", exc)

        return {
            "name": topic,
            "partition_count": len(partitions),
            "message_count": sum(p["end_offset"] for p in partitions),
            "partitions": partitions,
            "configs": sorted(configs, key=lambda c: c["name"]),
        }

    return await _with_admin(cluster, _build)


@router.post("/clusters/{cluster_id}/topics")
async def create_topic(cluster_id: str, body: TopicCreatePayload):
    cluster = _get_cluster(cluster_id)
    name = body.name.strip()
    if not name or name.startswith("__"):
        raise HTTPException(status_code=400, detail="非法的 Topic 名称")

    async def _create(admin: AIOKafkaAdminClient):
        await admin.create_topics([
            NewTopic(
                name=name,
                num_partitions=body.partitions,
                replication_factor=body.replication_factor,
                topic_configs=body.configs or None,
            )
        ])
        return {"ok": True, "name": name, "message": f"Topic {name} 创建成功"}

    return await _with_admin(cluster, _create)


@router.delete("/clusters/{cluster_id}/topics/{topic}")
async def delete_topic(cluster_id: str, topic: str):
    cluster = _get_cluster(cluster_id)
    if topic.startswith("__"):
        raise HTTPException(status_code=403, detail="禁止删除内部 Topic")

    async def _delete(admin: AIOKafkaAdminClient):
        await admin.delete_topics([topic])
        return {"ok": True, "message": f"Topic {topic} 已删除"}

    return await _with_admin(cluster, _delete)


# ── 消费组 ────────────────────────────────────────────────────────────────────

@router.get("/clusters/{cluster_id}/groups")
async def list_groups(cluster_id: str):
    cluster = _get_cluster(cluster_id)

    async def _build(admin: AIOKafkaAdminClient):
        groups_raw = await admin.list_consumer_groups()
        group_ids = [g[0] for g in (groups_raw or [])]
        if not group_ids:
            return {"groups": []}
        described = await admin.describe_consumer_groups(group_ids)
        groups = []
        for d in described:
            for g in getattr(d, "groups", [d]):
                gid = getattr(g, "group", None) or (g[1] if isinstance(g, (list, tuple)) and len(g) > 1 else "")
                state = getattr(g, "state", None) or (g[2] if isinstance(g, (list, tuple)) and len(g) > 2 else "")
                members = getattr(g, "members", None)
                if members is None and isinstance(g, (list, tuple)) and len(g) > 5:
                    members = g[5]
                groups.append({
                    "group_id": str(gid),
                    "state": str(state),
                    "member_count": len(members or []),
                })
        groups.sort(key=lambda x: x["group_id"])
        return {"groups": groups}

    return await _with_admin(cluster, _build)


@router.get("/clusters/{cluster_id}/groups/{group_id}/lag")
async def group_lag(cluster_id: str, group_id: str):
    """消费组各分区 committed offset vs end offset → Lag。"""
    cluster = _get_cluster(cluster_id)

    async def _build(admin: AIOKafkaAdminClient):
        offsets = await admin.list_consumer_group_offsets(group_id)
        if not offsets:
            return {"group_id": group_id, "total_lag": 0, "partitions": []}
        tps = list(offsets.keys())
        try:
            ends = await _end_offsets(cluster, tps)
        except Exception:
            ends = {}
        partitions = []
        total_lag = 0
        for tp, om in sorted(offsets.items(), key=lambda x: (x[0].topic, x[0].partition)):
            committed = om.offset if om.offset >= 0 else 0
            end = ends.get(tp, 0)
            lag = max(end - committed, 0)
            total_lag += lag
            partitions.append({
                "topic": tp.topic,
                "partition": tp.partition,
                "committed": committed,
                "end_offset": end,
                "lag": lag,
            })
        return {"group_id": group_id, "total_lag": total_lag, "partitions": partitions}

    return await _with_admin(cluster, _build)
