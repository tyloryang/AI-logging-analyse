"""Redis Session 封装"""
import os
import uuid
import json
import redis.asyncio as aioredis
from typing import Optional

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SESSION_TTL = int(os.getenv("SESSION_TTL_SECONDS", "28800"))
LOGIN_FAIL_MAX = int(os.getenv("LOGIN_FAIL_MAX", "5"))
LOGIN_FAIL_WINDOW = int(os.getenv("LOGIN_FAIL_WINDOW", "600"))

_redis: Optional[aioredis.Redis] = None

def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def create_session(user_id: str, username: str, ip: str) -> str:
    r = get_redis()
    session_id = str(uuid.uuid4())
    await r.hset(f"session:{session_id}", mapping={
        "user_id": user_id,
        "username": username,
        "ip": ip,
    })
    await r.expire(f"session:{session_id}", SESSION_TTL)
    return session_id


async def get_session(session_id: str) -> Optional[dict]:
    r = get_redis()
    data = await r.hgetall(f"session:{session_id}")
    if not data:
        return None
    # 滑动续期
    await r.expire(f"session:{session_id}", SESSION_TTL)
    return data


async def delete_session(session_id: str):
    r = get_redis()
    await r.delete(f"session:{session_id}")


async def incr_fail(username: str) -> int:
    r = get_redis()
    key = f"login_fail:{username}"
    count = await r.incr(key)
    await r.expire(key, LOGIN_FAIL_WINDOW)
    return count


async def clear_fail(username: str):
    r = get_redis()
    await r.delete(f"login_fail:{username}")


async def set_locked(user_id: str):
    r = get_redis()
    await r.set(f"locked:{user_id}", "1")


async def is_locked(user_id: str) -> bool:
    r = get_redis()
    return bool(await r.exists(f"locked:{user_id}"))


async def clear_locked(user_id: str):
    r = get_redis()
    await r.delete(f"locked:{user_id}")


async def check_redis() -> bool:
    try:
        r = get_redis()
        await r.ping()
        return True
    except Exception:
        return False
