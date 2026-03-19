"""LangGraph ReAct 图定义 — 支持三种运维 Agent 模式"""
import logging
import os
from typing import Literal

from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.prebuilt import ToolNode

from .tools import ALL_TOOLS

logger = logging.getLogger(__name__)

SYSTEM_PROMPTS = {
    "rca": (
        "你是一名资深 SRE 工程师，专注线上故障根因分析（RCA）。\n\n"
        "处理流程：\n"
        "1. 先调用 count_errors_by_service 了解哪些服务有错误及数量\n"
        "2. 对错误数最多的服务调用 query_error_logs 查看具体报错内容\n"
        "3. 调用 get_host_metrics 检查主机资源（CPU/内存/磁盘）是否异常\n"
        "4. 综合分析，输出：根因判断、影响范围、修复建议\n\n"
        "每次工具调用前简要说明你的分析思路。最终给出结构化的根因分析报告。"
    ),
    "inspect": (
        "你是一名专业运维工程师，负责执行全面系统巡检。\n\n"
        "请按以下步骤执行：\n"
        "1. 调用 get_services_list 了解服务健康状态概览\n"
        "2. 调用 count_errors_by_service 查看最近 24h 错误分布\n"
        "3. 调用 inspect_all_hosts 对全量主机执行巡检\n"
        "4. 对发现告警的主机调用 get_host_metrics 获取详细指标\n"
        "5. 综合输出完整巡检报告，分级展示（严重/警告/正常），并给出优先级建议"
    ),
    "chat": (
        "你是 AI Ops 智能运维助手，可以帮助：\n"
        "- 查询和分析日志（错误日志、特定服务日志）\n"
        "- 查看主机性能指标（CPU/内存/磁盘/负载）\n"
        "- 执行主机巡检\n"
        "- 统计服务错误情况\n\n"
        "根据用户问题按需调用工具，用简洁中文回答。"
    ),
}


def _get_llm():
    """与 ai_analyzer.py 读取完全相同的环境变量，确保配置一致"""
    provider = os.getenv("AI_PROVIDER", "anthropic").lower()

    if provider == "openai":
        base_url = os.getenv("AI_BASE_URL", "")
        api_key  = os.getenv("AI_API_KEY", "EMPTY") or "EMPTY"
        model    = os.getenv("AI_MODEL", "gpt-4")
        wire_api = os.getenv("AI_WIRE_API", "chat")

        if not base_url:
            raise ValueError("AI_PROVIDER=openai 时必须设置 AI_BASE_URL")

        if wire_api == "responses":
            # 代理只支持 /v1/responses（如 gpt-5 等新模型），使用自定义模型类
            logger.info("[agent] 使用 Responses API 模式（AI_WIRE_API=responses）")
            from agent.llm_responses import ResponsesApiChatModel
            return ResponsesApiChatModel(
                base_url=base_url,
                api_key=api_key,
                model=model,
                max_output_tokens=4096,
            )

        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model,
            max_tokens=4096,
        )

    # 默认 Anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    model   = os.getenv("AI_MODEL", "claude-opus-4-6")
    if not api_key:
        raise ValueError("AI_PROVIDER=anthropic 时必须设置 ANTHROPIC_API_KEY")

    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(
        model=model,
        api_key=api_key,
        max_tokens=4096,
    )


def build_graph(mode: str = "chat"):
    """构建指定模式的 LangGraph ReAct 图（每次请求构建，轻量）"""
    system_prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["chat"])
    llm = _get_llm().bind_tools(ALL_TOOLS)
    tool_node = ToolNode(ALL_TOOLS)

    async def agent_node(state: MessagesState):
        messages = list(state["messages"])
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=system_prompt)] + messages
        response = await llm.ainvoke(messages)
        return {"messages": [response]}

    def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")
    return graph.compile()
