"""AI 智能体路由 — LangGraph ReAct Agent SSE 流式输出"""
import asyncio
import json
import logging
import os

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agent.graph import build_graph

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


async def _save_incident(mode: str, user_query: str, summary: str) -> None:
    """后台将 AI 分析结论保存到 Milvus（不阻塞主流程）。"""
    try:
        from agent.milvus_memory import get_memory
        await get_memory().save(mode, user_query, summary)
    except Exception as exc:
        logger.warning("[agent] 保存到 Milvus 失败（不影响使用）: %s", exc)


async def _stream_graph(mode: str, message: str, conv_id: str = ""):
    """运行 LangGraph 图并将 astream_events 转换为 SSE 事件流"""
    response_parts: list[str] = []   # 累积 AI 文本，用于事后写入 Milvus

    try:
        checkpointer = await _get_checkpointer()
        graph = build_graph(mode, checkpointer=checkpointer)
        input_state = {"messages": [HumanMessage(content=message)]}
        thread_id = f"{conv_id}:{mode}" if conv_id else f"anon-{mode}"
        config = {"configurable": {"thread_id": thread_id}}

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
        else:
            logger.exception("[agent] 流式处理异常")
            yield _sse("error", message=err)

    yield _sse("done")

    # 后台保存到 Milvus（不阻塞响应，仅在有实质内容时保存）
    if len(response_parts) > 5:
        summary = "".join(response_parts)
        asyncio.create_task(_save_incident(mode, message, summary))


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

_DEFAULT_MESSAGES = {
    "rca":     "请分析当前系统中存在的问题和异常，给出根因分析报告。",
    "inspect": "请执行全面系统巡检，检查所有主机状态和日志异常，生成巡检报告。",
    "chat":    "你好，请介绍一下你能做什么。",
}


@router.post("/rca")
async def agent_rca(req: AgentRequest):
    message = req.message or _DEFAULT_MESSAGES["rca"]
    return StreamingResponse(_stream_graph("rca", message, req.conv_id),
                             media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/inspect")
async def agent_inspect(req: AgentRequest):
    message = req.message or _DEFAULT_MESSAGES["inspect"]
    return StreamingResponse(_stream_graph("inspect", message, req.conv_id),
                             media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/chat")
async def agent_chat(req: AgentRequest):
    message = req.message or _DEFAULT_MESSAGES["chat"]
    return StreamingResponse(_stream_graph("chat", message, req.conv_id),
                             media_type="text/event-stream", headers=_SSE_HEADERS)
