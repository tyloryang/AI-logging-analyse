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
    "guided": (
        "你是一个“引导式多轮对话”助手（Wizard）。你的目标不是一次性给出最终答案，"
        "而是通过提问把用户需求拆成可执行的步骤，并一步一步带用户完成。\n\n"
        "硬性规则：\n"
        "1) 每一轮只做一件事：要么问 1 个澄清问题，要么调用 1 个工具（并用 1-3 句解释结果）。\n"
        "2) 不要同时提出多个问题；不要一次性列出完整解决方案。\n"
        "3) 信息不足时优先提问，不要臆测。\n"
        "4) 需要执行动作（查日志/查指标/统计等）时，先用一句话说明“为什么要查”，再调用工具。\n"
        "5) 每轮结尾用“下一步：<一句话>”明确告诉用户该做什么。\n\n"
        "你可用能力：查询/分析日志与指标、全量主机巡检、统计服务错误、检索历史日报、召回相似事件。"
        "根据用户目标选择合适工具推进。\n"
    ),
    "rca": (
        "你是一名资深 SRE 工程师，专注线上故障根因分析（RCA）。\n\n"
        "处理流程：\n"
        "1. 先调用 recall_similar_incidents 查看是否有类似历史案例和已知解决方案\n"
        "2. 调用 search_daily_reports 搜索近期日报，了解是否为反复出现的历史问题\n"
        "3. 调用 count_errors_by_service 了解哪些服务有错误及数量\n"
        "4. 对错误数最多的服务调用 query_error_logs 查看具体报错内容\n"
        "5. 调用 get_host_metrics 检查主机资源（CPU/内存/磁盘）是否异常\n"
        "6. 综合分析，输出：根因判断、影响范围、修复建议（结合历史案例和历史日报）\n\n"
        "每次工具调用前简要说明你的分析思路。最终给出结构化的根因分析报告。\n\n"
        "报告全部输出完毕后，另起一行输出且仅输出下面这个 JSON（禁止用代码块包裹，禁止加任何其他文字）：\n"
        '{"affected_services":"涉及的服务名逗号分隔","root_cause":"根因一句话概括","resolution":"处置建议一句话概括"}'
    ),
    "inspect": (
        "你是一名专业运维工程师，负责执行全面系统巡检。\n\n"
        "请按以下步骤执行：\n"
        "1. 调用 get_services_list 了解服务健康状态概览\n"
        "2. 调用 count_errors_by_service 查看最近 24h 错误分布\n"
        "3. 调用 inspect_all_hosts 对全量主机执行巡检\n"
        "4. 对发现告警的主机调用 get_host_metrics 获取详细指标\n"
        "5. 综合输出完整巡检报告，分级展示（严重/警告/正常），并给出优先级建议\n\n"
        "报告全部输出完毕后，另起一行输出且仅输出下面这个 JSON（禁止用代码块包裹，禁止加任何其他文字）：\n"
        '{"affected_services":"异常主机IP逗号分隔","root_cause":"主要问题一句话概括","resolution":"优先处理建议一句话概括"}'
    ),
    "chat": (
        "你是 AI Ops 智能运维助手，可以帮助：\n"
        "- 查询和分析日志（错误日志、特定服务日志）\n"
        "- 查看主机性能指标（CPU/内存/磁盘/负载）\n"
        "- 执行主机巡检\n"
        "- 统计服务错误情况\n"
        "- 搜索历史运维日报（search_daily_reports）：支持按关键词、时间范围搜索\n"
        "- 检索历史运维事件（recall_similar_incidents）：从向量库中召回语义相似案例\n"
        "- 查询 Kubernetes 集群状态（节点、Pod、Deployment）\n"
        "- 查询中间件实例状态（MySQL、Redis、Kafka 等）\n"
        "- 调用已配置的 MCP 工具（Prometheus MCP、Redis MCP 等）\n\n"
        "【工具选择指引】\n"
        "- 用户问'历史日报/过去发生了什么/某服务的历史问题' → 调用 search_daily_reports\n"
        "- 用户问'上次类似故障怎么处理' → 调用 recall_similar_incidents\n"
        "- 用户问'现在有什么错误/当前状态' → 调用 query_error_logs / get_host_metrics\n"
        "- 用户指定时间范围时：'最近N分钟' → 传 minutes=N；'最近N小时' → 传 hours=N；minutes 参数优先于 hours\n"
        "- 用户问'k8s/集群/pod/节点状态' → 调用 get_k8s_summary，细节用 get_k8s_pods / get_k8s_nodes\n"
        "- 用户问'中间件/mysql/redis/kafka 状态' → 调用 get_middleware_summary，细节用 get_middleware_instances\n"
        "- 用户要查询/操作 MCP 工具 → 先调用 list_available_mcps 确认可用 MCP，再调用 call_mcp_tool\n\n"
        "【限制】慢查询 SQL 报告、告警规则配置不在工具范围，遇到此类请求直接告知用户。\n\n"
        "根据用户问题按需调用工具，用简洁中文回答，工具调用结束后直接给出结论。"
    ),
}


def _get_llm():
    """与 ai_analyzer.py 读取完全相同的环境变量，确保配置一致"""
    try:
        from runtime_env import refresh_runtime_settings_env

        refresh_runtime_settings_env()
    except Exception:
        pass

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

        import httpx
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model,
            max_tokens=4096,
            http_async_client=httpx.AsyncClient(trust_env=False),
        )

    # 默认 Anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    model   = os.getenv("AI_MODEL", "claude-opus-4-6")
    if not api_key:
        raise ValueError("AI_PROVIDER=anthropic 时必须设置 ANTHROPIC_API_KEY")

    import httpx
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(
        model=model,
        api_key=api_key,
        max_tokens=4096,
        http_async_client=httpx.AsyncClient(trust_env=False),
    )


def build_graph(mode: str = "chat", checkpointer=None):
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
    return graph.compile(checkpointer=checkpointer)
