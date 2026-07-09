"""CMDB 主机 SQLite 主存储。

设计：
  - 表 cmdb_hosts：每台主机一行，完整字段存 data JSON 列，ip/hostname 提列加索引
  - WAL + 事务 diff-upsert：只写有变化的行，进程崩溃不会留下半写状态
  - meta 表记录迁移标志，区分「空表因为删光」与「尚未从 JSON 迁移」
  - 进程内缓存（本进程是唯一写者，save 后失效；TTL 兜底外部改动）

JSON 文件（cmdb_hosts.json）降级为导出镜像与首次迁移来源，见 state.save_hosts_list。
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_TABLE = "cmdb_hosts"
_META_TABLE = "cmdb_meta"
_CACHE_TTL_SECONDS = 30.0

_lock = threading.Lock()
_cache: list[dict] | None = None
_cache_at: float = 0.0
_schema_ready = False


def _resolve_db_path() -> Path:
    """与 json_snapshot_store 同策略：DATABASE_URL 为 sqlite 时共用 aiops.db，
    否则退回独立的 data/cmdb.db（原生 sqlite3 无法连 MySQL/PG）。"""
    url = (os.getenv("DATABASE_URL", "") or "").strip()
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if url.startswith(prefix):
            raw = url.split(prefix, 1)[1]
            p = Path(raw)
            return p if p.is_absolute() else (_BACKEND_DIR / p).resolve()
    return (_BACKEND_DIR / "data" / ("cmdb.db" if url else "aiops.db")).resolve()


_DB_PATH = _resolve_db_path()


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    global _schema_ready
    if _schema_ready:
        return
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_TABLE} (
            id         TEXT PRIMARY KEY,
            ip         TEXT,
            hostname   TEXT,
            data       TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_ip ON {_TABLE}(ip)")
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_META_TABLE} (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    _schema_ready = True


def _is_migrated(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        f"SELECT value FROM {_META_TABLE} WHERE key = 'migrated'"
    ).fetchone()
    return bool(row and row[0] == "1")


def _dump_host(host: dict) -> str:
    return json.dumps(host, ensure_ascii=False, sort_keys=True, default=str)


def invalidate_cache() -> None:
    global _cache
    with _lock:
        _cache = None


def load_hosts() -> list[dict] | None:
    """返回主机列表；尚未迁移（无数据且无迁移标志）时返回 None，由上层从 JSON 导入。

    DB 读取异常时抛出，由上层决定回退策略。
    """
    global _cache, _cache_at
    with _lock:
        if _cache is not None and time.time() - _cache_at < _CACHE_TTL_SECONDS:
            return deepcopy(_cache)

    with _connect() as conn:
        _ensure_schema(conn)
        if not _is_migrated(conn):
            return None
        rows = conn.execute(
            f"SELECT data FROM {_TABLE} ORDER BY sort_order, rowid"
        ).fetchall()
    hosts = [json.loads(r[0]) for r in rows]

    with _lock:
        _cache = deepcopy(hosts)
        _cache_at = time.time()
    return hosts


def save_hosts(hosts: list[dict]) -> None:
    """全量保存（与 state.save_hosts_list 语义一致）。

    事务内 diff-upsert：内容未变的行只同步 sort_order，变化的行整行更新，
    列表中不存在的行删除。任何一步失败整体回滚，不会出现半写状态。
    """
    global _cache, _cache_at
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    for host in hosts:
        if not host.get("id"):
            host["id"] = str(uuid.uuid4())

    with _connect() as conn:
        _ensure_schema(conn)
        existing = {
            row[0]: (row[1], row[2])
            for row in conn.execute(f"SELECT id, data, sort_order FROM {_TABLE}")
        }
        keep_ids: set[str] = set()
        for order, host in enumerate(hosts):
            hid = str(host["id"])
            keep_ids.add(hid)
            payload = _dump_host(host)
            prev = existing.get(hid)
            if prev is not None and prev[0] == payload:
                if prev[1] != order:
                    conn.execute(
                        f"UPDATE {_TABLE} SET sort_order = ? WHERE id = ?",
                        (order, hid),
                    )
                continue
            conn.execute(
                f"""
                INSERT INTO {_TABLE}(id, ip, hostname, data, sort_order, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    ip=excluded.ip,
                    hostname=excluded.hostname,
                    data=excluded.data,
                    sort_order=excluded.sort_order,
                    updated_at=excluded.updated_at
                """,
                (
                    hid,
                    str(host.get("ip") or ""),
                    str(host.get("hostname") or ""),
                    payload,
                    order,
                    str(host.get("created_at") or now),
                    now,
                ),
            )
        removed = set(existing) - keep_ids
        if removed:
            conn.executemany(
                f"DELETE FROM {_TABLE} WHERE id = ?",
                [(hid,) for hid in removed],
            )
        conn.execute(
            f"INSERT INTO {_META_TABLE}(key, value) VALUES ('migrated', '1') "
            "ON CONFLICT(key) DO UPDATE SET value = '1'"
        )

    with _lock:
        _cache = deepcopy(hosts)
        _cache_at = time.time()


def stats() -> dict:
    """存储健康信息（诊断用）。"""
    try:
        with _connect() as conn:
            _ensure_schema(conn)
            count = conn.execute(f"SELECT COUNT(*) FROM {_TABLE}").fetchone()[0]
            migrated = _is_migrated(conn)
        return {"db_path": str(_DB_PATH), "host_count": count, "migrated": migrated}
    except Exception as exc:
        return {"db_path": str(_DB_PATH), "error": str(exc)}
