"""Application-wide authentication middleware."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from auth.models import User
from auth.session import get_session
from db import AsyncSessionLocal


_PUBLIC_PATHS = {
    "/",
    "/api/auth/login",
    "/api/auth/register",
    "/api/health",
    "/api/alerts/webhook",
    "/api/feishu/webhook",
    "/webhook/event",
    "/docs",
    "/openapi.json",
    "/redoc",
}
_PUBLIC_PREFIXES = (
    "/api/events/ingest/",
    "/api/public/report/inspect/",
)


def _is_public(path: str) -> bool:
    return path in _PUBLIC_PATHS or any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Require an active session for every non-public HTTP endpoint."""

    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS" or _is_public(request.url.path):
            return await call_next(request)

        session_id = request.cookies.get("session_id", "")
        if not session_id:
            return JSONResponse({"detail": "未登录"}, status_code=401)

        session = await get_session(session_id)
        if not session:
            return JSONResponse({"detail": "会话已过期，请重新登录"}, status_code=401)

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(User).where(User.id == session.get("user_id")))
            user = result.scalar_one_or_none()
        if not user or user.status != "active":
            return JSONResponse({"detail": "账号不可用"}, status_code=401)

        request.state.user = user
        return await call_next(request)
