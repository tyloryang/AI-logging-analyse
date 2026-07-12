"""Session 存储 —— 优先 Redis，无 Redis 自动退回内存字典（单进程）"""
import os
import uuid
import time
import asyncio
import logging
from typing import Optional

SESSION_TTL       = int(os.getenv("SESSION_TTL_SECONDS", "28800"))   # 8 h
LOGIN_FAIL_MAX    = int(os.getenv("LOGIN_FAIL_MAX", "5"))
LOGIN_FAIL_WINDOW = int(os.getenv("LOGIN_FAIL_WINDOW", "600"))
LOGIN_IP_FAIL_MAX = int(os.getenv("LOGIN_IP_FAIL_MAX", "20"))

# ─────────────────────────────────────────────────────────
# 内存后端（fallback）
# ─────────────────────────────────────────────────────────
class _MemStore:
    """简单的 TTL 字典，替代 Redis，适合单进程部署。"""
    def __init__(self):
        self._data: dict[str, tuple[dict, float]] = {}   # key → (value, expire_at)

    def _now(self) -> float:
        return time.monotonic()

    def _gc(self):
        now = self._now()
        expired = [k for k, (_, exp) in self._data.items() if exp <= now]
        for k in expired:
            del self._data[k]

    async def hset(self, key: str, mapping: dict):
        self._gc()
        existing, exp = self._data.get(key, ({}, self._now() + SESSION_TTL))
        existing.update(mapping)
        self._data[key] = (existing, exp)

    async def hgetall(self, key: str) -> dict:
        self._gc()
        item = self._data.get(key)
        if item is None:
            return {}
        val, exp = item
        if exp <= self._now():
            del self._data[key]
            return {}
        return dict(val)

    async def expire(self, key: str, ttl: int):
        item = self._data.get(key)
        if item:
            self._data[key] = (item[0], self._now() + ttl)

    async def delete(self, key: str):
        self._data.pop(key, None)

    async def incr(self, key: str) -> int:
        self._gc()
        item = self._data.get(key, ({"v": "0"}, self._now() + LOGIN_FAIL_WINDOW))
        val = int(item[0].get("v", "0")) + 1
        self._data[key] = ({"v": str(val)}, item[1])
        return val

    async def get(self, key: str):
        self._gc()
        item = self._data.get(key)
        if item is None:
            return None
        return item[0].get("v")

    async def set(self, key: str, value: str):
        self._data[key] = ({"v": value}, self._now() + SESSION_TTL * 10)

    async def exists(self, key: str) -> int:
        item = self._data.get(key)
        if item and item[1] > self._now():
            return 1
        return 0

    async def ping(self) -> bool:
        return True


# ─────────────────────────────────────────────────────────
# Redis 后端（可选）
# ─────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "")
ALLOW_MEMORY_FALLBACK = os.getenv("SESSION_ALLOW_MEMORY_FALLBACK", "").strip().lower() in {
    "1", "true", "yes", "on",
}

_backend: Optional[object] = None
logger = logging.getLogger(__name__)


def _get_backend():
    global _backend
    if _backend is not None:
        return _backend
    if REDIS_URL:
        try:
            import redis.asyncio as aioredis
            _backend = aioredis.from_url(REDIS_URL, decode_responses=True)
        except Exception:
            if not ALLOW_MEMORY_FALLBACK:
                raise
            _backend = _MemStore()
    else:
        _backend = _MemStore()
    return _backend


def _fallback_to_mem_store(reason: str, exc: Exception | None = None):
    """Downgrade to the in-memory store when Redis fails at runtime."""
    global _backend
    if not isinstance(_backend, _MemStore):
        if exc is not None:
            logger.warning(
                "[auth.session] backend failure during %s, falling back to in-memory store: %s",
                reason,
                exc,
            )
        _backend = _MemStore()
    return _backend


async def _call_backend(method: str, *args, **kwargs):
    backend = _get_backend()
    try:
        return await getattr(backend, method)(*args, **kwargs)
    except Exception as exc:
        if isinstance(backend, _MemStore):
            raise
        if not ALLOW_MEMORY_FALLBACK:
            raise
        backend = _fallback_to_mem_store(method, exc)
        return await getattr(backend, method)(*args, **kwargs)


# ─────────────────────────────────────────────────────────
# 公共 API（与原来接口完全相同）
# ─────────────────────────────────────────────────────────

async def create_session(user_id: str, username: str, ip: str) -> str:
    session_id = str(uuid.uuid4())
    await _call_backend("hset", f"session:{session_id}", mapping={
        "user_id": user_id,
        "username": username,
        "ip": ip,
    })
    await _call_backend("expire", f"session:{session_id}", SESSION_TTL)
    return session_id


async def get_session(session_id: str) -> Optional[dict]:
    data = await _call_backend("hgetall", f"session:{session_id}")
    if not data:
        return None
    await _call_backend("expire", f"session:{session_id}", SESSION_TTL)
    return data


async def delete_session(session_id: str):
    await _call_backend("delete", f"session:{session_id}")


async def incr_fail(username: str) -> int:
    key = f"login_fail:{username}"
    count = await _call_backend("incr", key)
    await _call_backend("expire", key, LOGIN_FAIL_WINDOW)
    return count


async def clear_fail(username: str):
    await _call_backend("delete", f"login_fail:{username}")


async def incr_ip_fail(ip: str) -> int:
    key = f"login_ip_fail:{ip or 'unknown'}"
    count = await _call_backend("incr", key)
    await _call_backend("expire", key, LOGIN_FAIL_WINDOW)
    return count


async def is_ip_limited(ip: str) -> bool:
    value = await _call_backend("get", f"login_ip_fail:{ip or 'unknown'}")
    return int(value or 0) >= LOGIN_IP_FAIL_MAX


async def set_locked(user_id: str):
    await _call_backend("set", f"locked:{user_id}", "1")


async def is_locked(user_id: str) -> bool:
    return bool(await _call_backend("exists", f"locked:{user_id}"))


async def clear_locked(user_id: str):
    await _call_backend("delete", f"locked:{user_id}")


async def check_redis() -> bool:
    try:
        return await _call_backend("ping")
    except Exception:
        return False
