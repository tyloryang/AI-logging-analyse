"""AI 智能体路由 — LangGraph ReAct Agent SSE 流式输出"""
import asyncio
import json
import logging
import os
import re

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from sqlalchemy import select, delete as sa_delete

from agent.graph import build_graph
from agent.external_executor import get_agent_executor, run_configured_executor
from auth.deps import current_user, require_permission
from auth.models import AgentConversation, User
from db import AsyncSessionLocal
from agent.ops_quick_actions import detect_mode, get_quick_reply, quick_actions_enabled
from state import get_user_allowed_groups, get_user_allowed_k8s_clusters

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])

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
    message: str = ""
    conv_id: str = ""   # 前端生成的会话 UUID，用于多轮历史隔离


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


async def _stream_graph(mode: str, message: str, conv_id: str = "", user: User | None = None):
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
        config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user.id if user else "anon",
                "is_superuser": user.is_superuser if user else True,
                "allowed_groups": allowed_groups,
                "allowed_k8s_clusters": allowed_k8s_clusters,
            },
            "recursion_limit": 40,
        }
        executor_mode = get_agent_executor("API")
        if executor_mode != "langgraph" and user and not user.is_superuser:
            logger.warning(
                "[agent] 普通用户 %s 请求已强制使用 langgraph，避免外部执行器绕过数据权限",
                user.username,
            )
            executor_mode = "langgraph"
        if executor_mode != "langgraph":
            logger.info("[agent] 使用外部执行器: %s", executor_mode)
            thread_id = conv_id or f"anon-{resolved_mode}"
            result = await run_configured_executor(message, thread_id, channel="api")
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
        graph = build_graph(resolved_mode, checkpointer=checkpointer)
        input_state = {"messages": [HumanMessage(content=message)]}
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
        elif "401" in err or "403" in err:
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
    return StreamingResponse(_stream_graph("rca", message, req.conv_id, user),
                             media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/inspect")
async def agent_inspect(req: AgentRequest, user: User = require_permission("agent", "view")):
    message = req.message or _DEFAULT_MESSAGES["inspect"]
    return StreamingResponse(_stream_graph("inspect", message, req.conv_id, user),
                             media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/chat")
async def agent_chat(req: AgentRequest, user: User = require_permission("agent", "view")):
    message = req.message or _DEFAULT_MESSAGES["chat"]
    return StreamingResponse(_stream_graph("chat", message, req.conv_id, user),
                             media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/guided")
async def agent_guided(req: AgentRequest, user: User = require_permission("agent", "view")):
    message = req.message or _DEFAULT_MESSAGES["guided"]
    return StreamingResponse(_stream_graph("guided", message, req.conv_id, user),
                             media_type="text/event-stream", headers=_SSE_HEADERS)


# ── 历史会话 CRUD ──────────────────────────────────────────────────────

class SaveConversationRequest(BaseModel):
    mode: str = "chat"
    title: str = ""
    messages: list = []


@router.get("/conversations")
async def list_conversations(user: User = require_permission("agent", "view")):
    """返回当前用户所有历史会话（按更新时间倒序，最多 100 条）。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AgentConversation)
            .where(AgentConversation.user_id == user.id)
            .order_by(AgentConversation.updated_at.desc())
            .limit(100)
        )
        rows = result.scalars().all()
    return [
        {
            "id":         r.id,
            "conv_id":    r.conv_id,
            "mode":       r.mode,
            "title":      r.title,
            "updated_at": r.updated_at.isoformat(),
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
            row.mode     = req.mode
            row.title    = req.title[:200]
            row.messages = json.dumps(req.messages, ensure_ascii=False)
        else:
            db.add(AgentConversation(
                user_id  = user.id,
                conv_id  = conv_id,
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
