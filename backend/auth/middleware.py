"""Application-wide authentication middleware."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from auth.models import User
from auth.deps import has_permission
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

_AUTHENTICATED_PATHS = {
    "/api/auth/logout",
    "/api/auth/me",
    "/api/auth/password",
}

_MODULE_PREFIXES = (
    ("/api/observability/metrics", "metrics"),
    ("/api/observability/grafana", "metrics"),
    ("/api/observability/alerts", "alert"),
    ("/api/observability/traces", "skywalking"),
    ("/api/observability", "dashboard"),
    ("/api/admin", "admin"),
    ("/api/agent-config", "admin"),
    ("/api/settings", "admin"),
    ("/api/ansible", "admin"),
    ("/api/hosts", "cmdb"),
    ("/api/groups", "cmdb"),
    ("/api/ssh", "ssh"),
    ("/api/ws/ssh", "ssh"),
    ("/api/logs", "log"),
    ("/api/services", "log"),
    ("/api/analyze", "log"),
    ("/api/metrics", "metrics"),
    ("/api/report", "report"),
    ("/api/slowlog", "slowlog"),
    ("/api/agent", "agent"),
    ("/api/cc-haha", "agent"),
    ("/api/ai", "agent"),
    ("/api/rca", "agent"),
    ("/api/k8s", "container"),
    ("/api/topology", "container"),
    ("/api/middleware", "middleware"),
    ("/api/redis", "middleware"),
    ("/api/kafka", "middleware"),
    ("/api/es", "middleware"),
    ("/api/jenkins", "cicd"),
    ("/api/events", "events"),
    ("/api/tickets", "ticket"),
    ("/api/workflows", "workflow"),
    ("/api/tasks", "workflow"),
    ("/api/scheduled-tasks", "workflow"),
    ("/api/alerts", "alert"),
    ("/api/kg", "knowledge"),
    ("/api/knowledge", "knowledge"),
)

_OPERATE_GET_PREFIXES = (
    "/api/hosts/sync-all",
    "/api/report/generate",
    "/api/report/inspect/generate",
    "/api/report/slowlog/generate",
    "/api/slowlog/analyze/stream",
)


def _matches_prefix(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def _module_for_path(path: str) -> str | None:
    for prefix, module in _MODULE_PREFIXES:
        if _matches_prefix(path, prefix):
            return module
    return None


def _required_level(method: str, path: str = "") -> str:
    if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        return "operate"
    if any(_matches_prefix(path, prefix) for prefix in _OPERATE_GET_PREFIXES):
        return "operate"
    return "view"


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

        if request.url.path in _AUTHENTICATED_PATHS or user.is_superuser:
            request.state.user = user
            return await call_next(request)

        module = _module_for_path(request.url.path)
        required_level = _required_level(request.method, request.url.path)
        if module is None:
            return JSONResponse({"detail": "普通用户默认禁止访问未授权模块"}, status_code=403)
        if not await has_permission(user, db, module, required_level):
            return JSONResponse(
                {"detail": f"无权限：{module}.{required_level}"},
                status_code=403,
            )

        request.state.user = user
        return await call_next(request)
