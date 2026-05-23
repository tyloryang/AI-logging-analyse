"""
cc-haha 集成路由 — 启动/停止/代理 cc-haha Bun 服务

cc-haha 是 Claude Code 源码重建版，提供真实的 Claude Code 对话引擎。
本路由负责：
1. 启动/停止 cc-haha Bun 服务（子进程）
2. 代理 HTTP REST 请求（/api/sessions, /api/settings 等）
3. 代理 WebSocket 连接（/ws/{sessionId}）
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.responses import StreamingResponse

from auth.deps import current_user, require_permission
from auth.models import User
from fastapi import Depends

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cc-haha", tags=["cc-haha"])

# ── cc-haha 服务状态 ──────────────────────────────────────────────────────────

_CC_PROC: subprocess.Popen | None = None
_CC_PORT: int = 35729   # cc-haha 默认端口，可通过环境变量覆盖
_CC_HOST = "127.0.0.1"

def _get_cc_port() -> int:
    return int(os.getenv("CC_HAHA_PORT", str(_CC_PORT)))

def _get_cc_base() -> str:
    return f"http://{_CC_HOST}:{_get_cc_port()}"

def _get_cc_haha_dir() -> str:
    """cc-haha 项目目录，从环境变量读取。"""
    return os.getenv("CC_HAHA_DIR", "").strip()


# ── 服务管理接口 ──────────────────────────────────────────────────────────────

@router.get("/status")
async def cc_status(_: Any = Depends(require_permission("agent", "view"))):
    """检测 cc-haha 服务是否在线。"""
    global _CC_PROC
    running = False
    pid = None
    if _CC_PROC is not None:
        ret = _CC_PROC.poll()
        if ret is None:
            running = True
            pid = _CC_PROC.pid

    # 尝试 HTTP 探活
    reachable = False
    if running:
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                r = await client.get(f"{_get_cc_base()}/api/sessions")
                reachable = r.status_code < 500
        except Exception:
            pass

    return {
        "running": running,
        "reachable": reachable,
        "pid": pid,
        "port": _get_cc_port(),
        "base_url": _get_cc_base(),
        "cc_haha_dir": _get_cc_haha_dir(),
        "bun_installed": bool(shutil.which("bun")),
    }


@router.post("/start")
async def cc_start(_: Any = Depends(require_permission("agent", "view"))):
    """启动 cc-haha Bun 服务。"""
    global _CC_PROC
    if _CC_PROC is not None and _CC_PROC.poll() is None:
        return {"ok": True, "message": "cc-haha 已在运行", "pid": _CC_PROC.pid}

    cc_dir = _get_cc_haha_dir()
    if not cc_dir or not Path(cc_dir).is_dir():
        raise HTTPException(
            status_code=400,
            detail="CC_HAHA_DIR 未配置或目录不存在。请在系统配置中设置 cc-haha 项目路径。"
        )
    if not shutil.which("bun"):
        raise HTTPException(status_code=400, detail="未找到 bun 命令，请先安装 Bun: https://bun.sh")

    port = _get_cc_port()
    env = os.environ.copy()
    env["PORT"] = str(port)
    env["HOST"] = _CC_HOST

    try:
        _CC_PROC = subprocess.Popen(
            ["bun", "run", "server"],
            cwd=cc_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        # 等待服务启动（最多 10 秒）
        for _ in range(20):
            await asyncio.sleep(0.5)
            try:
                async with httpx.AsyncClient(timeout=1) as client:
                    r = await client.get(f"http://{_CC_HOST}:{port}/api/sessions")
                    if r.status_code < 500:
                        return {"ok": True, "message": f"cc-haha 已启动（端口 {port}）", "pid": _CC_PROC.pid}
            except Exception:
                pass
        return {"ok": True, "message": "cc-haha 进程已启动，服务可能还在初始化中", "pid": _CC_PROC.pid}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"启动失败: {exc}")


@router.post("/stop")
async def cc_stop(_: Any = Depends(require_permission("agent", "view"))):
    """停止 cc-haha Bun 服务。"""
    global _CC_PROC
    if _CC_PROC is None or _CC_PROC.poll() is not None:
        return {"ok": True, "message": "cc-haha 未在运行"}
    _CC_PROC.terminate()
    try:
        _CC_PROC.wait(timeout=5)
    except subprocess.TimeoutExpired:
        _CC_PROC.kill()
    _CC_PROC = None
    return {"ok": True, "message": "cc-haha 已停止"}


# ── HTTP 代理（/api/cc-haha/proxy/* → cc-haha /api/*）────────────────────────

@router.api_route("/proxy/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def cc_proxy(
    request: Request,
    path: str,
    _: Any = Depends(require_permission("agent", "view")),
):
    """代理 HTTP 请求到 cc-haha 后端。"""
    target = f"{_get_cc_base()}/api/{path}"
    body   = await request.body()
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.request(
                method  = request.method,
                url     = target,
                content = body,
                headers = headers,
                params  = dict(request.query_params),
            )
        return StreamingResponse(
            resp.aiter_bytes(),
            status_code = resp.status_code,
            headers     = dict(resp.headers),
            media_type  = resp.headers.get("content-type", "application/json"),
        )
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="cc-haha 服务不可达，请先启动服务")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"代理错误: {exc}")


# ── WebSocket 代理（/api/cc-haha/ws/{sessionId} → cc-haha ws://…/{sessionId}）

@router.websocket("/ws/{session_id}")
async def cc_websocket_proxy(
    ws: WebSocket,
    session_id: str,
):
    """代理 WebSocket 连接到 cc-haha 后端（双向透传）。"""
    from auth.session import get_session
    session_cookie = ws.cookies.get("session_id")
    if session_cookie:
        sess = await get_session(session_cookie)
        if not sess:
            await ws.close(code=4401, reason="未登录")
            return
    else:
        await ws.close(code=4401, reason="未登录")
        return

    await ws.accept()
    cc_ws_url = f"ws://{_CC_HOST}:{_get_cc_port()}/ws/{session_id}"

    try:
        import websockets
        async with websockets.connect(cc_ws_url) as cc_ws:
            logger.info("[cc-haha] WS proxy connected: session=%s", session_id)

            async def _client_to_cc():
                try:
                    async for msg in ws.iter_text():
                        await cc_ws.send(msg)
                except Exception:
                    pass

            async def _cc_to_client():
                try:
                    async for msg in cc_ws:
                        await ws.send_text(msg if isinstance(msg, str) else msg.decode())
                except Exception:
                    pass

            await asyncio.gather(_client_to_cc(), _cc_to_client())
    except Exception as exc:
        logger.warning("[cc-haha] WS proxy error: %s", exc)
        try:
            await ws.close(code=1011, reason=str(exc))
        except Exception:
            pass
