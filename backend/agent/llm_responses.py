"""
自定义 LangChain ChatModel — 使用 OpenAI Responses API (/v1/responses)
用于兼容只暴露 Responses API（不支持 /v1/chat/completions）的代理或 gpt-5 等新模型。
"""
from __future__ import annotations

import json
import copy
import logging
from typing import Any, AsyncIterator, Iterator, List, Optional, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage, AIMessageChunk, BaseMessage,
    HumanMessage, SystemMessage, ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

logger = logging.getLogger(__name__)


class ResponsesApiChatModel(BaseChatModel):
    """
    调用 OpenAI Responses API (/v1/responses) 的 LangChain ChatModel。
    支持 bind_tools + LangGraph ToolNode 所需的 tool_calls / tool_call_chunks。
    """

    base_url: str
    api_key: str
    model_name: str = Field(alias="model")
    max_output_tokens: int = 4096
    # 绑定的工具（bind_tools 后填充）
    _bound_tools: List[dict] = []

    class Config:
        populate_by_name = True

    @property
    def _llm_type(self) -> str:
        return "openai-responses-api"

    # ── bind_tools ────────────────────────────────────────────────────
    def bind_tools(self, tools: Sequence[Any], **kwargs) -> "ResponsesApiChatModel":
        new = copy.copy(self)
        api_tools = []
        for t in tools:
            if hasattr(t, "name") and hasattr(t, "description"):
                schema = {}
                if hasattr(t, "args_schema") and t.args_schema:
                    try:
                        schema = t.args_schema.model_json_schema()
                    except Exception:
                        try:
                            schema = t.args_schema.schema()
                        except Exception:
                            schema = {}
                api_tools.append({
                    "type": "function",
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": schema,
                    "strict": False,
                })
            elif isinstance(t, dict):
                api_tools.append(t)
        new._bound_tools = api_tools
        return new

    # ── 消息格式转换 ──────────────────────────────────────────────────
    @staticmethod
    def _to_input(messages: List[BaseMessage]) -> List[dict]:
        """将 LangChain 消息转为 Responses API input 列表"""
        result = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                result.append({"role": "system", "content": str(msg.content)})
            elif isinstance(msg, HumanMessage):
                result.append({"role": "user", "content": str(msg.content)})
            elif isinstance(msg, AIMessage):
                # 先输出文本部分（若有）
                if msg.content:
                    result.append({"role": "assistant", "content": str(msg.content)})
                # 再输出 function_call 条目
                for tc in (msg.tool_calls or []):
                    result.append({
                        "type": "function_call",
                        "call_id": tc["id"],
                        "name": tc["name"],
                        "arguments": json.dumps(tc["args"], ensure_ascii=False),
                    })
            elif isinstance(msg, ToolMessage):
                result.append({
                    "type": "function_call_output",
                    "call_id": msg.tool_call_id,
                    "output": str(msg.content),
                })
        return result

    # ── 同步生成（供内部 fallback，实际走 async）─────────────────────
    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        raise NotImplementedError("请使用 ainvoke / astream")

    # ── 异步生成 ──────────────────────────────────────────────────────
    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        import httpx
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            http_client=httpx.AsyncClient(trust_env=False),
        )
        inp = self._to_input(messages)
        req: dict = {
            "model": self.model_name,
            "input": inp,
            "max_output_tokens": self.max_output_tokens,
        }
        if self._bound_tools:
            req["tools"] = self._bound_tools

        resp = await client.responses.create(**req)

        text = ""
        tool_calls: List[dict] = []
        for item in resp.output:
            if item.type == "message":
                for c in item.content:
                    if hasattr(c, "text"):
                        text += c.text
            elif item.type == "function_call":
                args_raw = item.arguments if isinstance(item.arguments, str) else json.dumps(item.arguments)
                try:
                    args = json.loads(args_raw)
                except Exception:
                    args = {}
                tool_calls.append({
                    "id": item.call_id,
                    "name": item.name,
                    "args": args,
                    "type": "tool_call",
                })

        ai_msg = AIMessage(content=text, tool_calls=tool_calls) if tool_calls else AIMessage(content=text)
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])

    # ── 异步流式生成 ──────────────────────────────────────────────────
    async def _astream(
        self, messages, stop=None, run_manager=None, **kwargs
    ) -> AsyncIterator[ChatGenerationChunk]:
        import httpx
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            http_client=httpx.AsyncClient(trust_env=False),
        )
        inp = self._to_input(messages)
        req: dict = {
            "model": self.model_name,
            "input": inp,
            "max_output_tokens": self.max_output_tokens,
            "stream": True,
        }
        if self._bound_tools:
            req["tools"] = self._bound_tools

        # 在流结束后再发送工具调用 chunk
        tool_calls_acc: dict[str, dict] = {}   # call_id -> {id, name, args_str}

        resp = await client.responses.create(**req)
        async for event in resp:
            etype = getattr(event, "type", "")

            # 文本 token → 立即 yield
            if etype == "response.output_text.delta":
                delta = getattr(event, "delta", "")
                if delta:
                    yield ChatGenerationChunk(message=AIMessageChunk(content=delta))

            # 新 function_call 条目出现
            elif etype == "response.output_item.added":
                item = getattr(event, "item", None)
                if item and getattr(item, "type", "") == "function_call":
                    cid = item.call_id
                    tool_calls_acc[cid] = {
                        "id": cid,
                        "name": item.name,
                        "args_str": "",
                    }

            # 工具调用参数流
            elif etype == "response.function_call_arguments.delta":
                cid = getattr(event, "call_id", "")
                delta = getattr(event, "delta", "")
                if cid in tool_calls_acc:
                    tool_calls_acc[cid]["args_str"] += delta

        # 流结束后，若有工具调用，发送最终 chunk（携带 tool_call_chunks）
        if tool_calls_acc:
            tool_call_chunks = []
            for idx, (cid, data) in enumerate(tool_calls_acc.items()):
                tool_call_chunks.append({
                    "id": data["id"],
                    "name": data["name"],
                    "args": data["args_str"],   # JSON string，由 LangChain 解析
                    "index": idx,
                    "type": "tool_call_chunk",
                })
            yield ChatGenerationChunk(
                message=AIMessageChunk(content="", tool_call_chunks=tool_call_chunks)
            )
