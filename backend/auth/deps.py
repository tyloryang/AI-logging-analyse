"""FastAPI 依赖：current_user / require_permission"""
import os
import functools
from fastapi import Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from cachetools import TTLCache
from db import get_db
from auth.models import User, Permission
from auth.session import get_session

NO_AUTH = os.getenv("NO_AUTH", "").lower() in ("1", "true", "yes")

# 权限等级数值
LEVEL_RANK = {"none": 0, "view": 1, "operate": 2}

# 用户权限 LRU 缓存（60s）
_perm_cache: TTLCache = TTLCache(maxsize=256, ttl=60)


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="未登录")
    data = await get_session(session_id)
    if not data:
        raise HTTPException(status_code=401, detail="会话已过期，请重新登录")
    user_id = data["user_id"]
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or user.status != "active":
        raise HTTPException(status_code=401, detail="账号不可用")
    return user


async def _get_permissions(user_id: str, db: AsyncSession) -> dict:
    """加载用户权限，带 TTL 缓存"""
    if user_id in _perm_cache:
        return _perm_cache[user_id]
    result = await db.execute(
        select(Permission).where(Permission.user_id == user_id)
    )
    perms = {p.module_id: p.level for p in result.scalars()}
    _perm_cache[user_id] = perms
    return perms


def require_permission(module: str, level: str = "view"):
    """路由装饰器：检查用户对指定模块的权限"""
    def dependency(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
        return user, db, module, level

    async def checker(ctx=Depends(dependency)):
        user, db, mod, lv = ctx
        if user.is_superuser:
            return user
        perms = await _get_permissions(user.id, db)
        user_level = perms.get(mod, "none")
        if LEVEL_RANK.get(user_level, 0) < LEVEL_RANK.get(lv, 0):
            raise HTTPException(status_code=403, detail=f"无权限：{mod}.{lv}")
        return user

    return Depends(checker)


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
