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
from pydantic import Field, ConfigDict

logger = logging.getLogger(__name__)


class ResponsesApiChatModel(BaseChatModel):
    """
    调用 OpenAI Responses API (/v1/responses) 的 LangChain ChatModel。
    支持 bind_tools + LangGraph ToolNode 所需的 tool_calls / tool_call_chunks。
    """

    model_config = ConfigDict(protected_namespaces=(), populate_by_name=True)

    base_url: str
    api_key: str
    model_name: str = Field(alias="model")
    max_output_tokens: int = 4096
    # 绑定的工具（bind_tools 后填充）
    _bound_tools: List[dict] = []

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
        """将 LangChain 消息转为 Responses API input 列表。

        Responses API 要求 function_call / function_call_output 的 call_id
        非空字符串；某些 OpenAI 兼容代理（qwen / deepseek gateway 等）
        会把 id 字段命名成 tool_call_id 或返回空串，这里做兜底：
        - AIMessage.tool_calls 里 id 为空 → 跳过该 tool_call（避免 400）
        - ToolMessage.tool_call_id 为空 → 跳过该输出（避免 400）
        """
        import logging as _lg
        _logger = _lg.getLogger(__name__)

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
                # 再输出 function_call 条目（call_id 空的直接丢弃，避免 400）
                for tc in (msg.tool_calls or []):
                    cid = (tc.get("id") or "").strip() if isinstance(tc, dict) else ""
                    if not cid:
                        _logger.warning(
                            "[llm_responses] 丢弃 call_id 为空的 tool_call: name=%s",
                            tc.get("name") if isinstance(tc, dict) else "?",
                        )
                        continue
                    result.append({
                        "type": "function_call",
                        "call_id": cid,
                        "name": tc["name"],
                        "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
                    })
            elif isinstance(msg, ToolMessage):
                cid = (getattr(msg, "tool_call_id", "") or "").strip()
                if not cid:
                    _logger.warning("[llm_responses] 丢弃 tool_call_id 为空的 ToolMessage")
                    continue
                result.append({
                    "type": "function_call_output",
                    "call_id": cid,
                    "output": str(msg.content),
                })

        # ── 一致性清理：Responses API 要求 function_call 与 function_call_output
        #    严格配对；LangGraph 中断/工具报错时可能只留下一半，这里剔除孤儿避免 400。
        call_ids = {
            item.get("call_id")
            for item in result
            if item.get("type") == "function_call" and item.get("call_id")
        }
        output_ids = {
            item.get("call_id")
            for item in result
            if item.get("type") == "function_call_output" and item.get("call_id")
        }
        orphans = (call_ids ^ output_ids)
        if orphans:
            _logger.warning(
                "[llm_responses] 剔除 %d 个孤儿 function_call/output，call_id=%s",
                len(orphans), list(orphans)[:5],
            )
            result = [
                item for item in result
                if item.get("type") not in ("function_call", "function_call_output")
                or item.get("call_id") not in orphans
            ]

        # 每项都最终校验：function_call / function_call_output 必须有非空 call_id
        cleaned = []
        for idx, item in enumerate(result):
            itype = item.get("type")
            if itype in ("function_call", "function_call_output"):
                if not (item.get("call_id") or "").strip():
                    _logger.error(
                        "[llm_responses] 意外发现 %s 缺 call_id，input[%d] 已丢弃 payload=%s",
                        itype, idx, item,
                    )
                    continue
            cleaned.append(item)
        return cleaned

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
            http_client=httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(120.0)),
        )
        inp = self._to_input(messages)
        req: dict = {
            "model": self.model_name,
            "input": inp,
            "max_output_tokens": self.max_output_tokens,
        }
        if self._bound_tools:
            req["tools"] = self._bound_tools

        # 调试日志：打印 input 各项 type + call_id 摘要，便于排查 400
        import logging as _lg
        _dbg = _lg.getLogger(__name__)
        if _dbg.isEnabledFor(_lg.DEBUG):
            summary = [
                {"i": i, "type": x.get("type") or x.get("role"), "call_id": x.get("call_id"), "name": x.get("name")}
                for i, x in enumerate(inp)
            ]
            _dbg.debug("[llm_responses] Responses input=%s", summary)

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
                # 兼容代理：优先 call_id，回退 id
                cid = (getattr(item, "call_id", None) or getattr(item, "id", None) or "").strip()
                if not cid:
                    import uuid as _uuid
                    cid = f"call_{_uuid.uuid4().hex[:12]}"
                tool_calls.append({
                    "id": cid,
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
            http_client=httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(120.0)),
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

        # 调试日志：同上
        import logging as _lg
        _dbg = _lg.getLogger(__name__)
        if _dbg.isEnabledFor(_lg.DEBUG):
            summary = [
                {"i": i, "type": x.get("type") or x.get("role"), "call_id": x.get("call_id"), "name": x.get("name")}
                for i, x in enumerate(inp)
            ]
            _dbg.debug("[llm_responses] Responses stream input=%s", summary)

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
                    # 兼容代理：优先 call_id，回退 id，最终生成占位
                    cid = (getattr(item, "call_id", None) or getattr(item, "id", None) or "").strip()
                    if not cid:
                        import uuid as _uuid
                        cid = f"call_{_uuid.uuid4().hex[:12]}"
                    tool_calls_acc[cid] = {
                        "id": cid,
                        "name": item.name,
                        "args_str": "",
                    }

            # 工具调用参数流
            elif etype == "response.function_call_arguments.delta":
                cid = getattr(event, "call_id", None) or getattr(event, "item_id", None) or ""
                cid = str(cid).strip()
                delta = getattr(event, "delta", "")
                if cid and cid in tool_calls_acc:
                    tool_calls_acc[cid]["args_str"] += delta
                elif tool_calls_acc:
                    # 代理没回传 call_id 时把 delta 追加到最近的一个（单工具场景常见）
                    last_cid = next(reversed(tool_calls_acc))
                    tool_calls_acc[last_cid]["args_str"] += delta

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
