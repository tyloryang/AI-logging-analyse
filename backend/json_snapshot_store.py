from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parent
_DATA_DIR = _BACKEND_DIR / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)
_SNAPSHOT_TABLE = "json_snapshots"
_TEXT_SNAPSHOT_TABLE = "text_snapshots"


def _resolve_snapshot_db() -> Path:
    url = (os.getenv("DATABASE_URL", "") or "").strip()
    if url.startswith("sqlite+aiosqlite:///"):
        raw = url.split("sqlite+aiosqlite:///", 1)[1]
        p = Path(raw)
        return p if p.is_absolute() else (_BACKEND_DIR / p).resolve()
    if url.startswith("sqlite:///"):
        raw = url.split("sqlite:///", 1)[1]
        p = Path(raw)
        return p if p.is_absolute() else (_BACKEND_DIR / p).resolve()
    return (_DATA_DIR / "state_snapshots.db").resolve()


_SNAPSHOT_DB = _resolve_snapshot_db()
_TABLE_READY = False
_TEXT_TABLE_READY = False


def _connect() -> sqlite3.Connection:
    if _SNAPSHOT_DB.parent:
        _SNAPSHOT_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_SNAPSHOT_DB), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _ensure_table() -> None:
    global _TABLE_READY
    if _TABLE_READY:
        return
    try:
        with _connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_SNAPSHOT_TABLE} (
                    file_key   TEXT PRIMARY KEY,
                    file_path  TEXT NOT NULL,
                    payload    TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        _TABLE_READY = True
    except Exception as exc:
        logger.warning("[json_snapshot] ensure table failed: %s", exc)


def _ensure_text_table() -> None:
    global _TEXT_TABLE_READY
    if _TEXT_TABLE_READY:
        return
    try:
        with _connect() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {_TEXT_SNAPSHOT_TABLE} (
                    file_key   TEXT PRIMARY KEY,
                    file_path  TEXT NOT NULL,
                    payload    TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
        _TEXT_TABLE_READY = True
    except Exception as exc:
        logger.warning("[json_snapshot] ensure text table failed: %s", exc)


def snapshot_key(path: Path) -> str:
    return str(path.resolve())


def load_json_snapshot(path: Path) -> Any | None:
    _ensure_table()
    try:
        with _connect() as conn:
            row = conn.execute(
                f"SELECT payload FROM {_SNAPSHOT_TABLE} WHERE file_key = ?",
                (snapshot_key(path),),
            ).fetchone()
        if not row:
            return None
        return json.loads(row[0])
    except Exception as exc:
        logger.warning("[json_snapshot] load failed for %s: %s", path, exc)
        return None


_SAVED_HASHES: dict[str, int] = {}


def save_json_snapshot(path: Path, data: Any) -> None:
    _ensure_table()
    try:
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        # 内容未变化则跳过写库: read_json_file 每次读都会调本函数,
        # k8s/CMDB 等高频路径反复读同一配置, 无节流会造成 SQLite 写放大
        key = snapshot_key(path)
        digest = hash(payload)
        if _SAVED_HASHES.get(key) == digest:
            return
        now = datetime.now(timezone.utc).isoformat()
        with _connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {_SNAPSHOT_TABLE}(file_key, file_path, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(file_key) DO UPDATE SET
                    file_path=excluded.file_path,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (key, str(path), payload, now),
            )
        _SAVED_HASHES[key] = digest
    except Exception as exc:
        logger.warning("[json_snapshot] save failed for %s: %s", path, exc)


def load_text_snapshot(path: Path) -> str | None:
    _ensure_text_table()
    try:
        with _connect() as conn:
            row = conn.execute(
                f"SELECT payload FROM {_TEXT_SNAPSHOT_TABLE} WHERE file_key = ?",
                (snapshot_key(path),),
            ).fetchone()
        return row[0] if row else None
    except Exception as exc:
        logger.warning("[json_snapshot] load text failed for %s: %s", path, exc)
        return None


def save_text_snapshot(path: Path, payload: str) -> None:
    _ensure_text_table()
    try:
        now = datetime.now(timezone.utc).isoformat()
        with _connect() as conn:
            conn.execute(
                f"""
                INSERT INTO {_TEXT_SNAPSHOT_TABLE}(file_key, file_path, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(file_key) DO UPDATE SET
                    file_path=excluded.file_path,
                    payload=excluded.payload,
                    updated_at=excluded.updated_at
                """,
                (snapshot_key(path), str(path), payload, now),
            )
    except Exception as exc:
        logger.warning("[json_snapshot] save text failed for %s: %s", path, exc)


def write_json_file(path: Path, data: Any, *, ensure_parent: bool = False) -> None:
    if ensure_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    save_json_snapshot(path, data)


def read_json_file(path: Path, default: Any = None, *, ensure_parent: bool = False) -> Any:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        save_json_snapshot(path, data)
        return data
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.warning("[json_snapshot] file read failed for %s: %s", path, exc)

    backup = load_json_snapshot(path)
    if backup is None:
        return default

    try:
        if ensure_parent:
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(backup, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.warning("[json_snapshot] restored %s from sqlite snapshot", path)
    except Exception as exc:
        logger.warning("[json_snapshot] restore file failed for %s: %s", path, exc)
    return backup
