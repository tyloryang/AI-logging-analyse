"""运维知识图谱：SQLite 本地兜底 + 可选 Neo4j 关系存储。

设计取舍：sxdevops 参考项目并未真正用 neo4j，且本平台已全栈 SQLite
（aiops.db）。为避免为图谱单独运维一套 neo4j，这里用 SQLite 两张表实现
属性图：nodes(实体) + edges(关系)，支持邻居查询与两跳影响面遍历，
覆盖运维根因分析所需的「谁依赖谁、异常沿哪条边扩散」。

数据来源（build 时全量重建）：
  - CMDB 主机        → host 节点
  - K8s 集群/节点/Pod/Deployment/Service/命名空间 → 对应节点 + RUNS_ON/OWNS/EXPOSES 边
  - SkyWalking 拓扑  → service 节点 + CALLS 边
  - Pod ↔ 主机       → SCHEDULED_ON 边（按节点 IP 关联 CMDB）

节点：{id, kind, name, props(JSON), env, updated_at}
边：  {src, dst, rel, props(JSON)}
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_DB_PATH = (_BACKEND_DIR / "data" / "aiops.db").resolve()
_lock_ts = 0.0
_last_build: dict = {"at": 0.0, "nodes": 0, "edges": 0}

_NEO4J_NODE_LABEL = "KnowledgeEntity"
_NEO4J_REL_TYPE = "RELATES_TO"
_neo4j_circuit_lock = threading.Lock()
_neo4j_circuit_open_until = 0.0
_neo4j_last_error = ""


class Neo4jCircuitOpenError(RuntimeError):
    pass


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _neo4j_settings() -> dict[str, Any]:
    uri = os.getenv("NEO4J_URI", "").strip()
    return {
        "configured": bool(uri),
        "uri": uri,
        "username": os.getenv("NEO4J_USERNAME", "neo4j").strip(),
        "password": os.getenv("NEO4J_PASSWORD", ""),
        "database": os.getenv("NEO4J_DATABASE", "neo4j").strip() or "neo4j",
        "connection_timeout": _env_float("NEO4J_CONNECTION_TIMEOUT", 1.0, 0.2, 10.0),
        "connection_acquisition_timeout": _env_float("NEO4J_ACQUISITION_TIMEOUT", 1.5, 0.5, 15.0),
        "connection_write_timeout": _env_float("NEO4J_CONNECTION_WRITE_TIMEOUT", 2.0, 0.5, 15.0),
        "max_transaction_retry_time": _env_float("NEO4J_RETRY_TIME", 0.0, 0.0, 10.0),
        "failure_cooldown": _env_float("NEO4J_FAILURE_COOLDOWN", 30.0, 1.0, 300.0),
    }


def _neo4j_circuit_remaining() -> float:
    with _neo4j_circuit_lock:
        return max(0.0, _neo4j_circuit_open_until - time.monotonic())


def _record_neo4j_success() -> None:
    global _neo4j_circuit_open_until, _neo4j_last_error
    with _neo4j_circuit_lock:
        _neo4j_circuit_open_until = 0.0
        _neo4j_last_error = ""


def _record_neo4j_failure(exc: Exception, cooldown: float) -> None:
    global _neo4j_circuit_open_until, _neo4j_last_error
    with _neo4j_circuit_lock:
        _neo4j_circuit_open_until = time.monotonic() + cooldown
        _neo4j_last_error = str(exc)


@contextmanager
def _neo4j_driver() -> Iterator[tuple[Any, dict[str, Any]]]:
    config = _neo4j_settings()
    if not config["configured"]:
        raise RuntimeError("Neo4j 未配置，请设置 NEO4J_URI、NEO4J_USERNAME 和 NEO4J_PASSWORD")
    remaining = _neo4j_circuit_remaining()
    if remaining > 0:
        raise Neo4jCircuitOpenError(f"Neo4j 暂时熔断，{remaining:.1f} 秒后重试")

    driver = None
    try:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise RuntimeError("缺少 Neo4j Python 驱动，请安装 backend/requirements.txt") from exc

        auth = None
        if config["username"]:
            auth = (config["username"], config["password"])
        driver = GraphDatabase.driver(
            config["uri"],
            auth=auth,
            connection_timeout=config["connection_timeout"],
            connection_acquisition_timeout=config["connection_acquisition_timeout"],
            connection_write_timeout=config["connection_write_timeout"],
            max_transaction_retry_time=config["max_transaction_retry_time"],
        )
        yield driver, config
    except Neo4jCircuitOpenError:
        raise
    except Exception as exc:
        _record_neo4j_failure(exc, config["failure_cooldown"])
        raise
    else:
        _record_neo4j_success()
    finally:
        if driver is not None:
            try:
                driver.close()
            except Exception as exc:
                logger.debug("[kg] Neo4j driver close failed: %s", exc)


def _record_data(record: Any) -> dict[str, Any]:
    return record.data() if hasattr(record, "data") else dict(record)


def _decode_props(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError):
        return {}


def _normalize_neo4j_node(value: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(value or {})
    props = _decode_props(raw.pop("props_json", ""))
    return {
        "id": str(raw.get("id") or ""),
        "kind": str(raw.get("kind") or "entity"),
        "name": str(raw.get("name") or raw.get("id") or ""),
        "env": str(raw.get("env") or ""),
        "source": str(raw.get("source") or ""),
        "props": props,
    }


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kg_nodes (
            id         TEXT PRIMARY KEY,
            kind       TEXT NOT NULL,
            name       TEXT NOT NULL,
            env        TEXT DEFAULT '',
            props      TEXT DEFAULT '{}',
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kg_nodes_kind ON kg_nodes(kind)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kg_nodes_name ON kg_nodes(name)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kg_edges (
            src   TEXT NOT NULL,
            dst   TEXT NOT NULL,
            rel   TEXT NOT NULL,
            props TEXT DEFAULT '{}',
            PRIMARY KEY (src, dst, rel)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kg_edges_src ON kg_edges(src)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kg_edges_dst ON kg_edges(dst)")


class _GraphBuilder:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple, dict] = {}

    def node(self, kind: str, name: str, *, env: str = "", **props) -> str:
        nid = f"{kind}:{name}"
        existing = self.nodes.get(nid)
        if existing:
            existing["props"].update({k: v for k, v in props.items() if v is not None})
        else:
            self.nodes[nid] = {
                "id": nid, "kind": kind, "name": name, "env": env,
                "props": {k: v for k, v in props.items() if v is not None},
            }
        return nid

    def edge(self, src: str, dst: str, rel: str, **props) -> None:
        if not src or not dst or src == dst:
            return
        self.edges[(src, dst, rel)] = {
            "src": src, "dst": dst, "rel": rel,
            "props": {k: v for k, v in props.items() if v is not None},
        }


def _build_from_cmdb(g: _GraphBuilder) -> dict[str, str]:
    """返回 ip → host 节点 id 映射，供 K8s 节点关联。"""
    ip_to_host: dict[str, str] = {}
    try:
        from state import load_hosts_list

        for h in load_hosts_list():
            ip = str(h.get("ip") or "")
            if not ip:
                continue
            nid = g.node("host", h.get("hostname") or ip, env=h.get("env", ""),
                         ip=ip, group=h.get("group"), status=h.get("status"),
                         cpu=h.get("cpu_usage_pct"), mem=h.get("memory_usage_pct"))
            ip_to_host[ip] = nid
    except Exception as exc:
        logger.warning("[kg] CMDB 采集失败: %s", exc)
    return ip_to_host


def _build_from_k8s(g: _GraphBuilder, ip_to_host: dict[str, str]) -> None:
    try:
        from services.k8s_store import load_k8s_clusters
        from routers.kubernetes import _get_client

        clusters = load_k8s_clusters()
        for cluster in clusters[:2]:   # 控制预算，最多 2 个集群
            cid = cluster.get("id")
            cname = cluster.get("name", cid)
            cluster_nid = g.node("cluster", cname)
            try:
                core_v1, apps_v1 = _get_client(cid)
                node_ip: dict[str, str] = {}
                for n in core_v1.list_node(timeout_seconds=8).items:
                    nm = n.metadata.name
                    knid = g.node("k8s_node", nm, cluster=cname)
                    g.edge(cluster_nid, knid, "OWNS")
                    for addr in (n.status.addresses or []):
                        if addr.type == "InternalIP":
                            node_ip[nm] = addr.address
                            # K8s node ↔ CMDB host（同 IP）
                            host_nid = ip_to_host.get(addr.address)
                            if host_nid:
                                g.edge(knid, host_nid, "SAME_MACHINE")
                # Pods（限量，避免大集群爆炸）
                pods = core_v1.list_pod_for_all_namespaces(timeout_seconds=10).items[:400]
                for p in pods:
                    pod_nid = g.node("pod", f"{p.metadata.namespace}/{p.metadata.name}",
                                     ns=p.metadata.namespace, phase=p.status.phase,
                                     cluster=cname)
                    nodename = p.spec.node_name
                    if nodename:
                        g.edge(pod_nid, g.node("k8s_node", nodename, cluster=cname), "RUNS_ON")
                        host_ip = node_ip.get(nodename)
                        if host_ip and host_ip in ip_to_host:
                            g.edge(pod_nid, ip_to_host[host_ip], "SCHEDULED_ON")
                    # owner (Deployment 名近似取 pod 前缀)
                    for owner in (p.metadata.owner_references or []):
                        g.edge(g.node("workload", f"{p.metadata.namespace}/{owner.name}",
                                      kind_k8s=owner.kind), pod_nid, "MANAGES")
                # Services → 端点选择器（近似 EXPOSES 到同 ns 的 workload）
                for svc in core_v1.list_service_for_all_namespaces(timeout_seconds=8).items[:200]:
                    svc_nid = g.node("k8s_service", f"{svc.metadata.namespace}/{svc.metadata.name}",
                                     ns=svc.metadata.namespace, type=svc.spec.type)
                    g.edge(cluster_nid, svc_nid, "OWNS")
            except Exception as exc:
                logger.warning("[kg] K8s 集群 %s 采集失败: %s", cname, exc)
    except Exception as exc:
        logger.warning("[kg] K8s 采集跳过: %s", exc)


async def _build_from_skywalking(g: _GraphBuilder) -> None:
    """SkyWalking 服务调用拓扑 → service 节点 + CALLS 边。"""
    try:
        from skywalking_client import sw_client

        topo = await sw_client.get_topology(hours=1)
        if not topo:
            return
        id2name = {n.get("id"): n.get("name") for n in topo.get("nodes", [])}
        for n in topo.get("nodes", []):
            g.node("service", n.get("name", ""), sw_id=n.get("id"))
        for call in topo.get("calls", []):
            src = id2name.get(call.get("source"))
            dst = id2name.get(call.get("target"))
            if src and dst:
                g.edge(g.node("service", src), g.node("service", dst), "CALLS")
    except Exception as exc:
        logger.debug("[kg] SkyWalking 拓扑跳过: %s", exc)


async def build_graph(*, sync_neo4j: bool = False) -> dict:
    """全量重建知识图谱（async，K8s 同步调用走线程池），返回统计。"""
    import asyncio

    global _last_build
    g = _GraphBuilder()
    ip_to_host = await asyncio.to_thread(_build_from_cmdb, g)
    await asyncio.to_thread(_build_from_k8s, g, ip_to_host)
    await _build_from_skywalking(g)

    await asyncio.to_thread(_persist_graph, g)
    neo4j_result: dict[str, Any] = {"configured": _neo4j_settings()["configured"], "synced": False}
    if neo4j_result["configured"] and sync_neo4j:
        try:
            neo4j_result = await asyncio.to_thread(_persist_neo4j, g)
        except Exception as exc:
            logger.warning("[kg] Neo4j 同步失败，SQLite 图谱仍可用: %s", exc)
            neo4j_result = {"configured": True, "synced": False, "error": str(exc)}
    elif neo4j_result["configured"]:
        neo4j_result["skipped"] = "optional backend; use /api/kg/build to sync"

    _last_build = {
        "at": time.time(),
        "nodes": len(g.nodes),
        "edges": len(g.edges),
        "neo4j": neo4j_result,
    }
    logger.info("[kg] 图谱重建完成：%d 节点 / %d 边", len(g.nodes), len(g.edges))
    return _last_build


def _persist_graph(g: _GraphBuilder) -> None:
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _connect() as conn:
        _ensure_schema(conn)
        conn.execute("DELETE FROM kg_nodes")
        conn.execute("DELETE FROM kg_edges")
        conn.executemany(
            "INSERT OR REPLACE INTO kg_nodes(id,kind,name,env,props,updated_at) VALUES(?,?,?,?,?,?)",
            [(n["id"], n["kind"], n["name"], n.get("env", ""),
              json.dumps(n["props"], ensure_ascii=False), now) for n in g.nodes.values()],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO kg_edges(src,dst,rel,props) VALUES(?,?,?,?)",
            [(e["src"], e["dst"], e["rel"], json.dumps(e["props"], ensure_ascii=False))
             for e in g.edges.values()],
        )


def _persist_neo4j(g: _GraphBuilder) -> dict[str, Any]:
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    sync_id = str(time.time_ns())
    nodes = [
        {
            "id": node["id"],
            "kind": node["kind"],
            "name": node["name"],
            "env": node.get("env", ""),
            "props_json": json.dumps(node.get("props", {}), ensure_ascii=False),
            "updated_at": now,
            "sync_id": sync_id,
        }
        for node in g.nodes.values()
    ]
    edges = [
        {
            "src": edge["src"],
            "dst": edge["dst"],
            "relation": edge["rel"],
            "props_json": json.dumps(edge.get("props", {}), ensure_ascii=False),
            "updated_at": now,
        }
        for edge in g.edges.values()
    ]

    with _neo4j_driver() as (driver, config):
        driver.verify_connectivity()
        driver.execute_query(
            f"""
            CREATE CONSTRAINT knowledge_entity_id IF NOT EXISTS
            FOR (n:{_NEO4J_NODE_LABEL}) REQUIRE n.id IS UNIQUE
            """,
            database_=config["database"],
        )
        driver.execute_query(
            f"MATCH ()-[r:{_NEO4J_REL_TYPE} {{source: 'sxdevops'}}]->() DELETE r",
            database_=config["database"],
        )
        if nodes:
            driver.execute_query(
                f"""
                UNWIND $rows AS row
                MERGE (n:{_NEO4J_NODE_LABEL} {{id: row.id}})
                SET n.kind = row.kind,
                    n.name = row.name,
                    n.env = row.env,
                    n.props_json = row.props_json,
                    n.updated_at = row.updated_at,
                    n.sync_id = row.sync_id,
                    n.source = 'sxdevops'
                """,
                rows=nodes,
                database_=config["database"],
            )
        driver.execute_query(
            f"""
            MATCH (n:{_NEO4J_NODE_LABEL} {{source: 'sxdevops'}})
            WHERE coalesce(n.sync_id, '') <> $sync_id
              AND EXISTS {{
                  MATCH (n)-[:{_NEO4J_REL_TYPE} {{source: 'manual'}}]-()
              }}
            SET n.source = 'manual'
            REMOVE n.sync_id
            """,
            sync_id=sync_id,
            database_=config["database"],
        )
        driver.execute_query(
            f"""
            MATCH (n:{_NEO4J_NODE_LABEL} {{source: 'sxdevops'}})
            WHERE coalesce(n.sync_id, '') <> $sync_id
            DETACH DELETE n
            """,
            sync_id=sync_id,
            database_=config["database"],
        )
        if edges:
            driver.execute_query(
                f"""
                UNWIND $rows AS row
                MATCH (src:{_NEO4J_NODE_LABEL} {{id: row.src}})
                MATCH (dst:{_NEO4J_NODE_LABEL} {{id: row.dst}})
                MERGE (src)-[r:{_NEO4J_REL_TYPE} {{type: row.relation}}]->(dst)
                SET r.props_json = row.props_json,
                    r.updated_at = row.updated_at,
                    r.source = 'sxdevops'
                """,
                rows=edges,
                database_=config["database"],
            )
    return {
        "configured": True,
        "synced": True,
        "database": config["database"],
        "nodes": len(nodes),
        "edges": len(edges),
    }


def _find_node(conn: sqlite3.Connection, query: str) -> dict | None:
    row = conn.execute("SELECT id,kind,name,env,props FROM kg_nodes WHERE id=?", (query,)).fetchone()
    if not row:
        row = conn.execute(
            "SELECT id,kind,name,env,props FROM kg_nodes WHERE name LIKE ? OR id LIKE ? LIMIT 1",
            (f"%{query}%", f"%{query}%")).fetchone()
    if not row:
        return None
    return {"id": row[0], "kind": row[1], "name": row[2], "env": row[3],
            "props": json.loads(row[4] or "{}")}


def _sqlite_neighbors(query: str, depth: int = 1, limit: int = 40) -> dict:
    """查询实体的邻居（上下游）。depth=2 时做两跳影响面遍历。"""
    with _connect() as conn:
        _ensure_schema(conn)
        center = _find_node(conn, query)
        if not center:
            return {"found": False, "query": query,
                    "hint": "图谱中未找到该实体，可能需要先重建图谱（build）"}

        seen = {center["id"]}
        frontier = [center["id"]]
        rels: list[dict] = []
        for _ in range(max(1, min(depth, 2))):
            next_frontier = []
            for nid in frontier:
                rows = conn.execute(
                    "SELECT src,dst,rel FROM kg_edges WHERE src=? OR dst=? LIMIT ?",
                    (nid, nid, limit)).fetchall()
                for src, dst, rel in rows:
                    other = dst if src == nid else src
                    direction = "→" if src == nid else "←"
                    rels.append({"from": src, "to": dst, "rel": rel,
                                 "direction": direction, "via": nid})
                    if other not in seen:
                        seen.add(other)
                        next_frontier.append(other)
            frontier = next_frontier
            if not frontier:
                break

        # 补充邻居节点信息
        node_info = {}
        for nid in list(seen)[:limit]:
            r = conn.execute("SELECT kind,name,env FROM kg_nodes WHERE id=?", (nid,)).fetchone()
            if r:
                node_info[nid] = {"kind": r[0], "name": r[1], "env": r[2]}
        return {"found": True, "center": center, "neighbor_count": len(seen) - 1,
                "relations": rels[:limit], "nodes": node_info}


def _sqlite_stats() -> dict:
    try:
        with _connect() as conn:
            _ensure_schema(conn)
            n = conn.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()[0]
            e = conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0]
            by_kind = dict(conn.execute(
                "SELECT kind, COUNT(*) FROM kg_nodes GROUP BY kind").fetchall())
        return {"nodes": n, "edges": e, "by_kind": by_kind, "last_build": _last_build}
    except Exception as exc:
        return {"error": str(exc)}


def _execute_records(driver: Any, cypher: str, *, database: str, **parameters: Any) -> list[Any]:
    result = driver.execute_query(cypher, database_=database, **parameters)
    if hasattr(result, "records"):
        return list(result.records)
    return list(result[0])


def neo4j_status(check: bool = True) -> dict[str, Any]:
    config = _neo4j_settings()
    base = {
        "configured": config["configured"],
        "connected": False,
        "database": config["database"],
        "uri": config["uri"],
    }
    if not config["configured"]:
        return {**base, "message": "未配置 Neo4j 连接"}
    if not check:
        return base
    try:
        with _neo4j_driver() as (driver, driver_config):
            driver.verify_connectivity()
            records = _execute_records(
                driver,
                f"""
                MATCH (n:{_NEO4J_NODE_LABEL})
                WITH count(n) AS nodes
                OPTIONAL MATCH (src:{_NEO4J_NODE_LABEL})-[r:{_NEO4J_REL_TYPE}]->(:{_NEO4J_NODE_LABEL})
                RETURN nodes, count(r) AS edges
                """,
                database=driver_config["database"],
            )
            counts = _record_data(records[0]) if records else {"nodes": 0, "edges": 0}
        return {
            **base,
            "connected": True,
            "nodes": int(counts.get("nodes") or 0),
            "edges": int(counts.get("edges") or 0),
        }
    except Neo4jCircuitOpenError as exc:
        return {
            **base,
            "error": str(exc),
            "circuit_open": True,
            "retry_after_seconds": round(_neo4j_circuit_remaining(), 1),
        }
    except Exception as exc:
        return {**base, "error": str(exc)}


def graph_snapshot(limit: int = 240) -> dict[str, Any]:
    config = _neo4j_settings()
    safe_limit = max(1, min(int(limit), 500))
    if not config["configured"]:
        return {
            "configured": False,
            "connected": False,
            "source": "neo4j",
            "message": "请配置 NEO4J_URI、NEO4J_USERNAME、NEO4J_PASSWORD 后同步图谱",
            "nodes": [],
            "edges": [],
            "stats": {"nodes": 0, "edges": 0},
        }

    try:
        with _neo4j_driver() as (driver, driver_config):
            driver.verify_connectivity()
            node_records = _execute_records(
                driver,
                f"""
                MATCH (n:{_NEO4J_NODE_LABEL})
                RETURN properties(n) AS entity
                ORDER BY n.kind, n.name
                LIMIT $limit
                """,
                database=driver_config["database"],
                limit=safe_limit,
            )
            nodes = [
                _normalize_neo4j_node(_record_data(record).get("entity"))
                for record in node_records
            ]
            nodes = [node for node in nodes if node["id"]]
            node_ids = [node["id"] for node in nodes]
            edge_records: list[Any] = []
            if node_ids:
                edge_records = _execute_records(
                    driver,
                    f"""
                    MATCH (src:{_NEO4J_NODE_LABEL})-[r:{_NEO4J_REL_TYPE}]->(dst:{_NEO4J_NODE_LABEL})
                    WHERE src.id IN $node_ids AND dst.id IN $node_ids
                    RETURN src.id AS source, dst.id AS target, r.type AS relation,
                           r.props_json AS props_json, r.source AS source_type
                    ORDER BY source, target, relation
                    LIMIT $limit
                    """,
                    database=driver_config["database"],
                    node_ids=node_ids,
                    limit=safe_limit * 3,
                )
        edges = []
        for record in edge_records:
            item = _record_data(record)
            source_id = str(item.get("source") or "")
            target_id = str(item.get("target") or "")
            relation = str(item.get("relation") or "RELATED_TO")
            if not source_id or not target_id:
                continue
            edges.append({
                "id": f"{source_id}|{relation}|{target_id}",
                "source": source_id,
                "target": target_id,
                "relation": relation,
                "props": _decode_props(item.get("props_json")),
                "source_type": str(item.get("source_type") or ""),
            })
        by_kind: dict[str, int] = {}
        for node in nodes:
            by_kind[node["kind"]] = by_kind.get(node["kind"], 0) + 1
        return {
            "configured": True,
            "connected": True,
            "database": config["database"],
            "source": "neo4j",
            "nodes": nodes,
            "edges": edges,
            "stats": {"nodes": len(nodes), "edges": len(edges), "by_kind": by_kind},
        }
    except Exception as exc:
        return {
            "configured": True,
            "connected": False,
            "database": config["database"],
            "source": "neo4j",
            "error": str(exc),
            "nodes": [],
            "edges": [],
            "stats": {"nodes": 0, "edges": 0},
        }


def upsert_node(
    node_id: str,
    kind: str,
    name: str,
    *,
    env: str = "",
    props: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with _neo4j_driver() as (driver, config):
        records = _execute_records(
            driver,
            f"""
            MERGE (n:{_NEO4J_NODE_LABEL} {{id: $node_id}})
            SET n.kind = $kind,
                n.name = $name,
                n.env = $env,
                n.props_json = $props_json,
                n.updated_at = toString(datetime()),
                n.source = coalesce(n.source, 'manual')
            RETURN properties(n) AS entity
            """,
            database=config["database"],
            node_id=node_id,
            kind=kind,
            name=name,
            env=env,
            props_json=json.dumps(props or {}, ensure_ascii=False),
        )
    if not records:
        raise RuntimeError("Neo4j 节点保存失败")
    return _normalize_neo4j_node(_record_data(records[0]).get("entity"))


def delete_node(node_id: str) -> bool:
    with _neo4j_driver() as (driver, config):
        records = _execute_records(
            driver,
            f"""
            MATCH (n:{_NEO4J_NODE_LABEL} {{id: $node_id}})
            DETACH DELETE n
            RETURN 1 AS deleted
            """,
            database=config["database"],
            node_id=node_id,
        )
    return bool(records and _record_data(records[0]).get("deleted"))


def upsert_relation(
    source_id: str,
    target_id: str,
    relation: str,
    *,
    props: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_relation = relation.strip().upper()
    with _neo4j_driver() as (driver, config):
        records = _execute_records(
            driver,
            f"""
            MATCH (src:{_NEO4J_NODE_LABEL} {{id: $source_id}})
            MATCH (dst:{_NEO4J_NODE_LABEL} {{id: $target_id}})
            MERGE (src)-[r:{_NEO4J_REL_TYPE} {{type: $relation}}]->(dst)
            SET r.props_json = $props_json,
                r.updated_at = toString(datetime()),
                r.source = coalesce(r.source, 'manual')
            RETURN src.id AS source, dst.id AS target, r.type AS relation,
                   r.props_json AS props_json, r.source AS source_type
            """,
            database=config["database"],
            source_id=source_id,
            target_id=target_id,
            relation=normalized_relation,
            props_json=json.dumps(props or {}, ensure_ascii=False),
        )
    if not records:
        raise ValueError("源节点或目标节点不存在")
    item = _record_data(records[0])
    return {
        "id": f"{item['source']}|{item['relation']}|{item['target']}",
        "source": item["source"],
        "target": item["target"],
        "relation": item["relation"],
        "props": _decode_props(item.get("props_json")),
        "source_type": str(item.get("source_type") or ""),
    }


def delete_relation(source_id: str, target_id: str, relation: str) -> bool:
    with _neo4j_driver() as (driver, config):
        records = _execute_records(
            driver,
            f"""
            MATCH (src:{_NEO4J_NODE_LABEL} {{id: $source_id}})
                  -[r:{_NEO4J_REL_TYPE} {{type: $relation}}]->
                  (dst:{_NEO4J_NODE_LABEL} {{id: $target_id}})
            DELETE r
            RETURN 1 AS deleted
            """,
            database=config["database"],
            source_id=source_id,
            target_id=target_id,
            relation=relation.strip().upper(),
        )
    return bool(records and _record_data(records[0]).get("deleted"))


def _neo4j_neighbors(query: str, depth: int = 1, limit: int = 40) -> dict[str, Any]:
    safe_depth = max(1, min(int(depth), 2))
    safe_limit = max(1, min(int(limit), 200))
    with _neo4j_driver() as (driver, config):
        center_records = _execute_records(
            driver,
            f"""
            MATCH (n:{_NEO4J_NODE_LABEL})
            WHERE toLower(n.id) = toLower($query)
               OR toLower(n.name) = toLower($query)
               OR toLower(n.id) CONTAINS toLower($query)
               OR toLower(n.name) CONTAINS toLower($query)
            WITH n, CASE
                WHEN toLower(n.id) = toLower($query) THEN 0
                WHEN toLower(n.name) = toLower($query) THEN 1
                ELSE 2
            END AS rank
            ORDER BY rank, n.name
            RETURN properties(n) AS entity
            LIMIT 1
            """,
            database=config["database"],
            query=query,
        )
        if not center_records:
            return {
                "found": False,
                "query": query,
                "source": "neo4j",
                "hint": "Neo4j 图谱中未找到该实体，请先同步图谱",
            }
        center = _normalize_neo4j_node(_record_data(center_records[0]).get("entity"))
        relation_records = _execute_records(
            driver,
            f"""
            MATCH p=(center:{_NEO4J_NODE_LABEL} {{id: $center_id}})
                    -[:{_NEO4J_REL_TYPE}*1..{safe_depth}]-
                    (neighbor:{_NEO4J_NODE_LABEL})
            UNWIND relationships(p) AS r
            WITH DISTINCT r
            RETURN properties(startNode(r)) AS source_node,
                   properties(endNode(r)) AS target_node,
                   r.type AS relation
            LIMIT $limit
            """,
            database=config["database"],
            center_id=center["id"],
            limit=safe_limit,
        )

    node_info = {
        center["id"]: {"kind": center["kind"], "name": center["name"], "env": center["env"]}
    }
    relations: list[dict[str, Any]] = []
    for record in relation_records:
        item = _record_data(record)
        source = _normalize_neo4j_node(item.get("source_node"))
        target = _normalize_neo4j_node(item.get("target_node"))
        if not source["id"] or not target["id"]:
            continue
        node_info[source["id"]] = {"kind": source["kind"], "name": source["name"], "env": source["env"]}
        node_info[target["id"]] = {"kind": target["kind"], "name": target["name"], "env": target["env"]}
        relations.append({
            "from": source["id"],
            "to": target["id"],
            "rel": str(item.get("relation") or "RELATED_TO"),
            "direction": "->" if source["id"] == center["id"] else "<-",
            "via": center["id"],
        })
    return {
        "found": True,
        "source": "neo4j",
        "center": center,
        "neighbor_count": max(0, len(node_info) - 1),
        "relations": relations,
        "nodes": node_info,
    }


def neighbors(query: str, depth: int = 1, limit: int = 40, prefer_neo4j: bool = False) -> dict:
    config = _neo4j_settings()
    if prefer_neo4j and config["configured"]:
        try:
            return _neo4j_neighbors(query, depth, limit)
        except Exception as exc:
            logger.warning("[kg] Neo4j 邻居查询失败，回退 SQLite: %s", exc)
            result = _sqlite_neighbors(query, depth, limit)
            result["source"] = "sqlite-fallback"
            result["neo4j_error"] = str(exc)
            return result
    result = _sqlite_neighbors(query, depth, limit)
    result["source"] = "sqlite"
    return result


def stats() -> dict:
    sqlite_stats = _sqlite_stats()
    return {
        **sqlite_stats,
        "storage": "neo4j" if _neo4j_settings()["configured"] else "sqlite",
        "neo4j": neo4j_status(check=True),
    }
