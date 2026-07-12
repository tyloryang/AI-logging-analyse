"""AI 智能体路由 — LangGraph ReAct Agent SSE 流式输出"""
import asyncio
import json
import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, delete as sa_delete

from agent.graph import build_graph
from agent.external_executor import get_agent_executor, run_configured_executor
from auth.deps import current_user, require_permission
from auth.models import AgentConversation, User
from db import AsyncSessionLocal
from agent.ops_quick_actions import detect_mode, get_quick_reply, quick_actions_enabled
from routers.agent_config import resolve_agent_model_overrides
from state import get_user_allowed_groups, get_user_allowed_k8s_clusters

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _allowed_workspace_roots() -> tuple[Path, ...]:
    roots = [_REPO_ROOT]
    for value in os.getenv("AIOPS_AGENT_WORKSPACE_ROOTS", "").split(os.pathsep):
        value = value.strip()
        if value:
            roots.append(Path(value).expanduser().resolve())
    return tuple(dict.fromkeys(roots))


def _resolve_workspace(path: str = "") -> Path:
    candidate = Path(path.strip()).expanduser() if path.strip() else _REPO_ROOT
    candidate = candidate.resolve()
    if not candidate.is_dir():
        raise HTTPException(status_code=400, detail=f"目录不存在: {candidate}")
    if not any(candidate == root or root in candidate.parents for root in _allowed_workspace_roots()):
        raise HTTPException(status_code=403, detail="工作区不在允许的目录范围内")
    return candidate

# ── Checkpointer 懒初始化 ──────────────────────────────────────────────
_checkpointer = None
_init_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _init_lock
    if _init_lock is None:
        _init_lock = asyncio.Lock()
    return _init_lock


async def _get_checkpointer():
    """首次调用时初始化 SQLite checkpointer，失败则降级为 MemorySaver。"""
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    async with _get_lock():
        if _checkpointer is not None:
            return _checkpointer
        try:
            import aiosqlite
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "agent_checkpoints.db")

            conn = await aiosqlite.connect(db_path)
            saver = AsyncSqliteSaver(conn)
            await saver.setup()
            _checkpointer = saver
            logger.info("[agent] checkpointer → SQLite: %s", os.path.abspath(db_path))
        except Exception as exc:
            logger.warning("[agent] SQLite checkpointer 不可用，降级为 MemorySaver: %s", exc)
            from langgraph.checkpoint.memory import MemorySaver
            _checkpointer = MemorySaver()
    return _checkpointer


class AgentRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    message: str = ""
    conv_id: str = ""   # 前端生成的会话 UUID，用于多轮历史隔离
    home_dir: str = ""
    model_id: str = ""
    model_name: str = ""
    model_provider: str = ""
    model_base_url: str = ""
    model_api_key: str = ""
    model_wire_api: str = ""
    model_enable_thinking: bool | None = None
    # 执行器覆盖：langgraph | external_cli | aiops_cli
    # 留空则读取系统配置 AIOPS_AGENT_EXECUTOR
    executor: str = ""


def _build_runtime_overrides(req: AgentRequest) -> dict:
    runtime_overrides = resolve_agent_model_overrides(
        model_id=req.model_id,
        model_name=req.model_name,
        model_provider=req.model_provider,
        model_base_url=req.model_base_url,
        model_api_key=req.model_api_key,
        model_wire_api=req.model_wire_api,
        model_enable_thinking=req.model_enable_thinking,
    )
    runtime_overrides["home_dir"] = str(req.home_dir or "").strip()
    runtime_overrides["executor"] = str(req.executor or "").strip()
    # 注入 CLAUDE.md + git 上下文（参考 Claude Code 的 buildSystemPrompt）
    home_dir = runtime_overrides["home_dir"]
    if home_dir:
        runtime_overrides["project_context"] = _build_project_context(home_dir)
    return runtime_overrides


def _build_project_context(home_dir: str) -> str:
    """构建项目上下文：CLAUDE.md + git 状态（同步版，供 _build_runtime_overrides 调用）。"""
    import os, subprocess, shutil
    parts: list[str] = []

    # 1. CLAUDE.md 向上遍历
    claude_parts: list[str] = []
    cur = os.path.abspath(home_dir)
    visited: set[str] = set()
    while True:
        if cur in visited:
            break
        visited.add(cur)
        for fname in ("CLAUDE.md", "CLAUDE.local.md"):
            fp = os.path.join(cur, fname)
            if os.path.isfile(fp):
                try:
                    text = open(fp, encoding="utf-8").read().strip()
                    if text:
                        claude_parts.insert(0, f"# {fname} ({fp})\n\n{text}")
                except Exception:
                    pass
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    if claude_parts:
        parts.append("## Project Instructions (CLAUDE.md)\n\n" + "\n\n---\n\n".join(claude_parts))

    # 2. git 上下文（3秒超时，失败静默）
    if shutil.which("git") and os.path.isdir(home_dir):
        def _git(*args: str) -> str:
            try:
                r = subprocess.run(
                    ["git", "-C", home_dir, *args],
                    capture_output=True, text=True, timeout=3, encoding="utf-8", errors="replace"
                )
                return r.stdout.strip() if r.returncode == 0 else ""
            except Exception:
                return ""

        branch = _git("branch", "--show-current")
        status = _git("status", "--short")
        log    = _git("log", "--oneline", "-5")
        if branch or status:
            git_lines = [f"## Git Context ({home_dir})"]
            if branch:  git_lines.append(f"Branch: {branch}")
            if status:  git_lines.append(f"Status:\n```\n{status}\n```")
            if log:     git_lines.append(f"Recent commits:\n```\n{log}\n```")
            parts.append("\n".join(git_lines))

    return "\n\n".join(parts)


def _sse(type_: str, **kwargs) -> str:
    return f"data: {json.dumps({'type': type_, **kwargs}, ensure_ascii=False)}\n\n"


def _extract_structured(text: str) -> tuple[str, dict]:
    """
    从 AI 输出末尾提取结构化 JSON 摘要，返回 (干净文本, 结构化数据)。
    JSON 格式：{"affected_services":"...","root_cause":"...","resolution":"..."}
    """
    last_brace = text.rfind("{")
    if last_brace == -1:
        return text, {}
    end_brace = text.find("}", last_brace)
    if end_brace == -1:
        return text, {}
    candidate = text[last_brace: end_brace + 1]
    try:
        data = json.loads(candidate)
        if "root_cause" in data:
            return text[:last_brace].rstrip(), data
    except json.JSONDecodeError:
        pass
    return text, {}


def _looks_like_model_unavailable(err: str) -> bool:
    err_lower = err.lower()
    return any(token in err for token in ("暂无可用渠道", "当前分组", "无可用渠道")) or any(
        token in err_lower
        for token in (
            "no available channel",
            "unsupported model",
            "model not found",
            "unknown model",
            "does not support this model",
        )
    )


def _looks_like_auth_error(err: str) -> bool:
    err_lower = err.lower()
    if "401" in err:
        return True
    if "403" in err and _looks_like_model_unavailable(err):
        return False
    return any(
        token in err_lower
        for token in (
            "invalid api key",
            "authentication",
            "unauthorized",
            "forbidden",
            "incorrect api key",
            "permission denied",
            "insufficient permissions",
        )
    ) or "403" in err


async def _save_incident(mode: str, user_query: str, full_summary: str,
                         affected_services: str = "", root_cause: str = "",
                         resolution: str = "") -> None:
    """后台将 AI 分析结论保存到 Milvus（不阻塞主流程）。"""
    try:
        from agent.milvus_memory import get_memory
        await get_memory().save(mode, user_query, full_summary,
                                affected_services, root_cause, resolution)
    except Exception as exc:
        logger.warning("[agent] 保存到 Milvus 失败（不影响使用）: %s", exc)


async def _stream_graph(
    mode: str,
    message: str,
    conv_id: str = "",
    user: User | None = None,
    runtime_overrides: dict | None = None,
):
    """运行 LangGraph 图并将 astream_events 转换为 SSE 事件流"""
    response_parts: list[str] = []   # 累积 AI 文本，用于事后写入 Milvus

    try:
        resolved_mode = detect_mode(message) if mode == "chat" else mode
        thread_id = f"{conv_id}:{resolved_mode}" if conv_id else f"anon-{resolved_mode}"
        allowed_groups: list[str] | None = None
        allowed_k8s_clusters: list[str] | None = None
        if user and not user.is_superuser:
            allowed_groups = get_user_allowed_groups(user.id) or []
            allowed_k8s_clusters = get_user_allowed_k8s_clusters(user.id) or []
        runtime_overrides = runtime_overrides or {}
        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user.id if user else "anon",
                "is_superuser": user.is_superuser if user else True,
                "allowed_groups": allowed_groups,
                "allowed_k8s_clusters": allowed_k8s_clusters,
                "home_dir": str(runtime_overrides.get("home_dir", "")).strip(),
                "model_name": str(runtime_overrides.get("model_name", "")).strip(),
                "model_provider": str(runtime_overrides.get("model_provider", "")).strip().lower(),
            },
            "recursion_limit": 40,
        }
        # 优先用请求里的 executor 参数，其次读系统配置
        from agent.external_executor import _normalize_executor
        _raw_executor = str(runtime_overrides.get("executor", "")).strip()
        req_executor  = _normalize_executor(_raw_executor) if _raw_executor else ""
        executor_mode = req_executor or get_agent_executor("API")
        if executor_mode != "langgraph":
            logger.info("[agent] 使用外部执行器: %s", executor_mode)
            thread_id = conv_id or f"anon-{resolved_mode}"
            result = await run_configured_executor(
                message,
                thread_id,
                channel="api",
                runtime_overrides=runtime_overrides,
            )
            response_parts.append(result)
            yield _sse("token", text=result)
            yield _sse("done")
            return

        quick_reply = (
            await get_quick_reply(message, config=config)
            if quick_actions_enabled("AIOPS") and resolved_mode in {"es_ops", "k8s_ops"}
            else None
        )
        if quick_reply:
            yield _sse("token", text=quick_reply)
            yield _sse("done")
            return

        checkpointer = await _get_checkpointer()
        graph = build_graph(resolved_mode, checkpointer=checkpointer, runtime_overrides=runtime_overrides)
        # 把 CLAUDE.md + git 上下文附加到用户消息（参考 Claude Code buildSystemPrompt）
        project_ctx = str(runtime_overrides.get("project_context", "")).strip()
        final_message = (
            f"{project_ctx}\n\n---\n\n{message}" if project_ctx else message
        )
        input_state = {"messages": [HumanMessage(content=final_message)]}
        async for event in graph.astream_events(input_state, config=config, version="v2"):
            kind = event.get("event", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    content = chunk.content
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text" and c.get("text"):
                                response_parts.append(c["text"])
                                yield _sse("token", text=c["text"])
                    elif isinstance(content, str):
                        response_parts.append(content)
                        yield _sse("token", text=content)

            elif kind == "on_tool_start":
                name = event.get("name", "")
                inp = event.get("data", {}).get("input", {})
                yield _sse("tool_start", tool=name, input=inp)

            elif kind == "on_tool_end":
                name = event.get("name", "")
                output = str(event.get("data", {}).get("output", ""))
                yield _sse("tool_end", tool=name, output=output[:800])

    except Exception as e:
        err = str(e)
        if "404" in err:
            hint = (
                f"{err}\n\n"
                "可能原因：\n"
                "① AI_MODEL 与服务器加载的模型名称不一致\n"
                "② AI_BASE_URL 地址或路径错误（应包含 /v1，如 http://host:8000/v1）\n"
                "③ 若使用代理（LiteLLM 等），请检查模型是否已注册"
            )
            yield _sse("error", message=hint)
        elif _looks_like_model_unavailable(err):
            yield _sse(
                "error",
                message=(
                    "当前模型在已配置网关中不可用，或模型名与网关实际注册名不一致。\n"
                    "建议：\n"
                    "1. 切换到可用模型\n"
                    "2. 将该模型的运行时模型名改成网关真实模型名，例如 `qwen3-32b`\n"
                    "3. 检查上游网关的模型分组是否已开通该模型\n\n"
                    f"{err}"
                ),
            )
        elif _looks_like_auth_error(err):
            yield _sse("error", message=f"API 认证失败，请检查 ANTHROPIC_API_KEY 或 AI_API_KEY。\n{err}")
        elif "AI_BASE_URL" in err or "ANTHROPIC_API_KEY" in err:
            yield _sse("error", message=f"配置缺失：{err}")
        elif "recursion_limit" in err.lower() or "recursion limit" in err.lower():
            yield _sse("error", message=(
                "Agent 调用工具次数过多，已自动终止。\n\n"
                "可能原因：您的问题需要的功能超出了 Agent 工具范围。\n"
                "• 查看历史运维日报 → 请前往「运维日报」页面\n"
                "• 查看慢日志报告 → 请前往「慢日志分析」页面\n"
                "请换一种方式提问，或直接告诉 Agent 您想查什么数据。"
            ))
        else:
            logger.exception("[agent] 流式处理异常")
            yield _sse("error", message=err)

    # 提取末尾 JSON，将干净文本推给前端替换
    full_text = "".join(response_parts)
    clean_text, structured = _extract_structured(full_text)
    if structured:
        yield _sse("replace_content", text=clean_text)

    yield _sse("done")

    # 后台保存到 Milvus
    if len(clean_text) > 10:
        asyncio.create_task(_save_incident(
            resolved_mode, message, clean_text,
            affected_services=structured.get("affected_services", ""),
            root_cause=structured.get("root_cause", ""),
            resolution=structured.get("resolution", ""),
        ))


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

_DEFAULT_MESSAGES = {
    "guided":  "我想排查一个问题，请你一步一步引导我。",
    "rca":     "请分析当前系统中存在的问题和异常，给出根因分析报告。",
    "inspect": "请执行全面系统巡检，检查所有主机状态和日志异常，生成巡检报告。",
    "chat":    "你好，请介绍一下你能做什么。",
}


@router.post("/rca")
async def agent_rca(req: AgentRequest, user: User = require_permission("agent", "view")):
    message = req.message or _DEFAULT_MESSAGES["rca"]
    return StreamingResponse(_stream_graph("rca", message, req.conv_id, user, _build_runtime_overrides(req)),
                             media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/inspect")
async def agent_inspect(req: AgentRequest, user: User = require_permission("agent", "view")):
    message = req.message or _DEFAULT_MESSAGES["inspect"]
    return StreamingResponse(_stream_graph("inspect", message, req.conv_id, user, _build_runtime_overrides(req)),
                             media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/chat")
async def agent_chat(req: AgentRequest, user: User = require_permission("agent", "view")):
    message = req.message or _DEFAULT_MESSAGES["chat"]
    return StreamingResponse(_stream_graph("chat", message, req.conv_id, user, _build_runtime_overrides(req)),
                             media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/guided")
async def agent_guided(req: AgentRequest, user: User = require_permission("agent", "view")):
    message = req.message or _DEFAULT_MESSAGES["guided"]
    return StreamingResponse(_stream_graph("guided", message, req.conv_id, user, _build_runtime_overrides(req)),
                             media_type="text/event-stream", headers=_SSE_HEADERS)


# ── 历史会话 CRUD ──────────────────────────────────────────────────────

class SaveConversationRequest(BaseModel):
    mode:         str  = "chat"
    title:        str  = ""
    messages:     list = []
    project_path: str  = ""   # 关联项目目录


@router.get("/conversations")
async def list_conversations(
    user:         User = require_permission("agent", "view"),
    project_path: str  = "",
):
    """返回当前用户所有历史会话（按更新时间倒序，最多 200 条）。
    传 project_path 时只返回该项目的会话。
    """
    from fastapi import Query as Q
    async with AsyncSessionLocal() as db:
        stmt = (
            select(AgentConversation)
            .where(AgentConversation.user_id == user.id)
        )
        if project_path:
            stmt = stmt.where(AgentConversation.project_path == project_path)
        stmt = stmt.order_by(AgentConversation.updated_at.desc()).limit(200)
        result = await db.execute(stmt)
        rows = result.scalars().all()
    return [
        {
            "id":           r.id,
            "conv_id":      r.conv_id,
            "mode":         r.mode,
            "title":        r.title,
            "project_path": r.project_path or "",
            "updated_at":   r.updated_at.isoformat(),
            "created_at":   r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str, user: User = require_permission("agent", "view")):
    """获取单条历史会话的完整消息列表。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentConversation)
            .where(AgentConversation.conv_id == conv_id,
                   AgentConversation.user_id == user.id)
        )
        row = result.scalar_one_or_none()
    if not row:
        return {"conv_id": conv_id, "mode": "chat", "title": "", "messages": []}
    return {
        "conv_id":  row.conv_id,
        "mode":     row.mode,
        "title":    row.title,
        "messages": json.loads(row.messages),
    }


@router.put("/conversations/{conv_id}")
async def save_conversation(conv_id: str, req: SaveConversationRequest,
                            user: User = require_permission("agent", "view")):
    """新建或更新一条历史会话（upsert）。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentConversation)
            .where(AgentConversation.conv_id == conv_id,
                   AgentConversation.user_id == user.id)
        )
        row = result.scalar_one_or_none()
        if row:
            row.mode         = req.mode
            row.title        = req.title[:200]
            row.messages     = json.dumps(req.messages, ensure_ascii=False)
            if req.project_path:
                row.project_path = req.project_path
        else:
            db.add(AgentConversation(
                user_id      = user.id,
                conv_id      = conv_id,
                project_path = req.project_path or "",
                mode     = req.mode,
                title    = req.title[:200],
                messages = json.dumps(req.messages, ensure_ascii=False),
            ))
        await db.commit()
    return {"ok": True}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, user: User = require_permission("agent", "view")):
    """删除一条历史会话。"""
    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_delete(AgentConversation)
            .where(AgentConversation.conv_id == conv_id,
                   AgentConversation.user_id == user.id)
        )
        await db.commit()
    return {"ok": True}

@router.get("/executors/detect")
async def detect_executors(_: User = require_permission("agent", "view")):
    """检测本机可用的外部 Agent CLI（claude / codex 等）。"""
    import shutil
    candidates = [
        {"name": "Claude Code", "key": "external_cli", "cmd": "claude",
         "desc": "Anthropic Claude Code CLI (claude -p)"},
        {"name": "OpenAI Codex", "key": "external_cli", "cmd": "codex",
         "desc": "OpenAI Codex CLI"},
        {"name": "Gemini CLI",   "key": "external_cli", "cmd": "gemini",
         "desc": "Google Gemini CLI"},
        {"name": "LangGraph 内置", "key": "langgraph",  "cmd": None,
         "desc": "项目内置 ReAct Agent，无需额外安装"},
    ]
    result = []
    for c in candidates:
        available = True if c["cmd"] is None else bool(shutil.which(c["cmd"]))
        result.append({**c, "available": available,
                       "path": shutil.which(c["cmd"]) if c["cmd"] else None})
    return {"executors": result}


# ── Git 工作区接口（文件改动面板）──────────────────────────────────────────────

@router.get("/git/status")
async def git_status(path: str = "", _: User = require_permission("agent", "view")):
    """获取项目的 git status（changed/untracked 文件列表）。"""
    import asyncio, shutil
    if not shutil.which("git"):
        return {"ok": False, "error": "git 未安装"}
    workdir = str(_resolve_workspace(path))
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "-C", workdir, "status", "--porcelain", "-u",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            return {"ok": False, "error": stderr.decode("utf-8", errors="replace").strip()}
        lines = stdout.decode("utf-8", errors="replace").splitlines()
        files = []
        for line in lines:
            if len(line) < 4:
                continue
            xy, name = line[:2], line[3:].strip()
            if " -> " in name:   # rename: old -> new
                name = name.split(" -> ")[-1]
            status_map = {"M": "modified", "A": "added", "D": "deleted",
                          "R": "renamed", "?": "untracked", "!": "ignored"}
            x, y = xy[0], xy[1]
            status = status_map.get(x, status_map.get(y, "changed"))
            files.append({"file": name, "status": status, "xy": xy.strip()})
        # 当前分支
        bp = await asyncio.create_subprocess_exec(
            "git", "-C", workdir, "branch", "--show-current",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        bstdout, _ = await asyncio.wait_for(bp.communicate(), timeout=5)
        branch = bstdout.decode("utf-8", errors="replace").strip()
        return {"ok": True, "files": files, "branch": branch, "path": workdir}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "git status 超时"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/git/diff")
async def git_diff(path: str = "", file: str = "",
                   _: User = require_permission("agent", "view")):
    """获取指定文件的 git diff（unified diff 格式）。"""
    import asyncio, shutil
    if not shutil.which("git"):
        return {"ok": False, "error": "git 未安装"}
    workdir = str(_resolve_workspace(path))
    args = ["git", "-C", workdir, "diff", "HEAD", "--", file] if file else \
           ["git", "-C", workdir, "diff", "HEAD"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        diff_text = stdout.decode("utf-8", errors="replace")
        if not diff_text and file:
            # 新文件：用 git diff --cached
            proc2 = await asyncio.create_subprocess_exec(
                "git", "-C", workdir, "diff", "--cached", "--", file,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout2, _ = await asyncio.wait_for(proc2.communicate(), timeout=10)
            diff_text = stdout2.decode("utf-8", errors="replace")
        return {"ok": True, "diff": diff_text, "file": file, "path": workdir}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "git diff 超时"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ── CLAUDE.md 项目指令（参考 Claude Code 的 loadClaudeMd）────────────────────

@router.get("/claude-md")
async def read_claude_md(path: str = "", _: User = require_permission("agent", "view")):
    """读取项目目录（及父目录）中的 CLAUDE.md，向上遍历合并（同 Claude Code 行为）。"""
    import os
    workdir = str(_resolve_workspace(path))
    if not os.path.isdir(workdir):
        return {"ok": False, "error": f"目录不存在: {workdir}", "content": "", "files": []}

    parts = []
    files_found = []
    cur = os.path.abspath(workdir)
    workspace_path = Path(workdir)
    boundary = max(
        (root for root in _allowed_workspace_roots() if workspace_path == root or root in workspace_path.parents),
        key=lambda root: len(root.parts),
    )
    visited = set()
    while True:
        if cur in visited:
            break
        visited.add(cur)
        for name in ("CLAUDE.md", "CLAUDE.local.md"):
            fp = os.path.join(cur, name)
            if os.path.isfile(fp):
                try:
                    text = open(fp, encoding="utf-8").read()
                    parts.insert(0, f"# {fp}\n\n{text}")   # 父目录在前
                    files_found.insert(0, {"path": fp, "name": name})
                except Exception:
                    pass
        if Path(cur) == boundary:
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent

    return {
        "ok": True,
        "content": "\n\n---\n\n".join(parts),
        "files": files_found,
        "project_path": workdir,
    }


class ClaudeMdPayload(BaseModel):
    path: str
    content: str


@router.put("/claude-md")
async def write_claude_md(body: ClaudeMdPayload, _: User = require_permission("agent", "operate")):
    """保存 CLAUDE.md 到项目根目录。"""
    import os
    workdir = str(_resolve_workspace(body.path))
    if not workdir or not os.path.isdir(workdir):
        raise HTTPException(status_code=400, detail=f"目录不存在: {workdir}")
    fp = os.path.join(workdir, "CLAUDE.md")
    open(fp, "w", encoding="utf-8").write(body.content)
    return {"ok": True, "path": fp}


@router.get("/context-preview")
async def context_preview(path: str = "", _: User = require_permission("agent", "view")):
    """预览工作台发送消息时注入的上下文（CLAUDE.md + git 状态）。"""
    import asyncio, os, shutil
    workspace = str(_resolve_workspace(path))
    ctx = {"project_path": workspace, "claude_md": "", "git": {}, "env": {}}

    # CLAUDE.md
    try:
        r = await read_claude_md(path=workspace)
        ctx["claude_md"] = r.get("content", "")
    except Exception:
        pass

    # git context
    if shutil.which("git"):
        async def _git(args):
            try:
                p = await asyncio.create_subprocess_exec(
                    "git", "-C", workspace, *args,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                o, _ = await asyncio.wait_for(p.communicate(), 5)
                return o.decode("utf-8", errors="replace").strip()
            except Exception:
                return ""

        branch, log, status = await asyncio.gather(
            _git(["branch", "--show-current"]),
            _git(["log", "--oneline", "-5"]),
            _git(["status", "--short"]),
        )
        ctx["git"] = {"branch": branch, "log": log, "status": status}

    return ctx
