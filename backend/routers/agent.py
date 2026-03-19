"""AI 智能体路由 — LangGraph ReAct Agent SSE 流式输出"""
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from agent.graph import build_graph

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentRequest(BaseModel):
    message: str = ""
    conv_id: str = ""   # 前端生成的会话 UUID，用于多轮历史隔离


def _sse(type_: str, **kwargs) -> str:
    return f"data: {json.dumps({'type': type_, **kwargs}, ensure_ascii=False)}\n\n"


async def _stream_graph(mode: str, message: str, conv_id: str = ""):
    """运行 LangGraph 图并将 astream_events 转换为 SSE 事件流"""
    try:
        graph = build_graph(mode)
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
                                yield _sse("token", text=c["text"])
                    elif isinstance(content, str):
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
        # 提示常见配置问题
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
