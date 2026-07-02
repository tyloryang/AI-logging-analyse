"""LangGraph ReAct 图定义 — 支持多种运维 Agent 模式"""
import logging
import os
from typing import Literal

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, MessagesState, START, END

from .risk_registry import GuardDecision, risk_guard, risk_of
from .tool_groups import tools_for_runtime
from .tools import ALL_TOOLS

logger = logging.getLogger(__name__)

# 单条 ToolMessage content 截断上限（防止超长结果撑爆下一轮 prompt）
_TOOL_RESULT_TRUNCATE = 10000


def _build_guarded_tools_node(tools: list):
    """构造一个带 RiskGuard 的 tools 节点替代 prebuilt ToolNode。

    LangGraph 在 tools 节点拿到 last message 的 tool_calls，逐个跑：
      1. 查 risk_registry 决定 EXECUTE / APPROVAL / DENY
      2. EXECUTE 才真正调 tool.ainvoke；其它返回审批提示 ToolMessage 让 LLM 改变策略
      3. 每次调用都打日志，便于审计

    runtime_overrides 通过 RunnableConfig 注入；读取 confirm_mode / behaviors_auto。
    """
    tool_map = {getattr(t, "name", ""): t for t in tools}

    async def guarded_tools_node(state: MessagesState, config: RunnableConfig | None = None):
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", None) or []
        if not tool_calls:
            return {"messages": []}

        configurable = (config or {}).get("configurable", {}) if isinstance(config, dict) else {}
        try:
            from routers.agent_config import get_agent_runtime_context

            runtime_ctx = get_agent_runtime_context()
        except Exception as exc:
            logger.warning("[guard] failed to read runtime ctx: %s", exc)
            runtime_ctx = {"confirm_mode": "ask", "behaviors_auto": False}

        confirm_mode = configurable.get("confirm_mode") or runtime_ctx.get("confirm_mode", "ask")
        behaviors_auto = bool(configurable.get("behaviors_auto", runtime_ctx.get("behaviors_auto", False)))

        out_messages: list = []
        for call in tool_calls:
            name = call.get("name") or ""
            args = call.get("args") or {}
            call_id = call.get("id") or ""

            decision = risk_guard(
                tool_name=name,
                confirm_mode=confirm_mode,
                behaviors_auto=behaviors_auto,
            )

            if decision is not GuardDecision.EXECUTE:
                risk_label = risk_of(name).value
                content = (
                    f"⛔ RiskGuard 已拦截工具 `{name}`。\n"
                    f"  风险等级: {risk_label}\n"
                    f"  当前模式: confirm_mode={confirm_mode}, behaviors.auto={behaviors_auto}\n"
                    f"  原因: 该工具需要人工审批后才能执行。\n"
                    f"请在回复里告知用户：(1) 该操作涉及的具体影响；(2) 请用户在 UI 上点击审批或"
                    f"明确回复'确认执行'；或 (3) 改用只读类工具进一步收集信息。"
                )
                out_messages.append(
                    ToolMessage(content=content, tool_call_id=call_id, name=name)
                )
                logger.info("[guard] BLOCKED tool=%s decision=%s confirm_mode=%s auto=%s",
                            name, decision.value, confirm_mode, behaviors_auto)
                continue

            tool = tool_map.get(name)
            if tool is None:
                out_messages.append(
                    ToolMessage(
                        content=f"❌ 未注册的工具: {name}（可能未加入 ALL_TOOLS）",
                        tool_call_id=call_id,
                        name=name,
                    )
                )
                logger.warning("[guard] unknown tool %s", name)
                continue

            try:
                result = await tool.ainvoke(args, config=config)
                text = str(result)
                if len(text) > _TOOL_RESULT_TRUNCATE:
                    text = text[:_TOOL_RESULT_TRUNCATE] + f"\n...<截断，原长度 {len(str(result))}>"
                out_messages.append(
                    ToolMessage(content=text, tool_call_id=call_id, name=name)
                )
                logger.info("[guard] EXECUTED tool=%s args_keys=%s",
                            name, sorted(args.keys()) if isinstance(args, dict) else "-")
            except Exception as exc:
                out_messages.append(
                    ToolMessage(
                        content=f"工具 {name} 执行异常：{exc}",
                        tool_call_id=call_id,
                        name=name,
                    )
                )
                logger.exception("[guard] tool %s execution failed", name)

        return {"messages": out_messages}

    return guarded_tools_node

REACT_GUIDELINES = (
    "【ReAct 工作方式】\n"
    "- 你需要边分析边执行：先判断目标，再选择工具，再根据工具结果继续下一步，直到能给出结论。\n"
    "- 能通过工具查询的信息直接查询，不要把每一步都变成追问用户；只有缺少关键参数或涉及高风险操作时才提问确认。\n"
    "- 不要输出隐藏推理链路；可以输出可审计的执行轨迹、工具调用摘要、观察结果和最终建议。\n"
    "- 工具失败时要继续尝试备用工具或降级方案，并在最终回答里说明已尝试的路径。\n\n"
)

# 四层思考框架（参考 Hermes Memory v4 设计理念）
# L1 感知层：类比 Hermes Typed Schema — 先分类，不同类型任务触发不同策略
# L2 检索层：类比 Hermes 5路检索融合 — 多源并发，不做单一路径检索
# L3 推理层：类比 Hindsight Mental Models — 跨维度关联，找根因
# L4 沉淀层：类比 Hermes 反思层 — 每次输出都提炼可复用模式
FOUR_LAYER_THINKING = (
    "【四层思考框架 — 请严格按层推进】\n\n"
    "═══ L1 · 感知层 ═══\n"
    "首先识别任务类型（平台信息/能力咨询/故障排查/性能分析/K8s运维/巡检/报告生成），\n"
    "锁定关键实体（服务名/主机IP/命名空间/时间范围），\n"
    "输出1句：「本次任务：<类型>，核心实体：<实体>」\n\n"
    "═══ L2 · 检索层 ═══\n"
    "多源并发收集数据（不要串行等待）：\n"
    "• 平台通道：get_platform_overview（平台能力、接入组件、AI/MCP/模型配置）\n"
    "• 日志通道：query_error_logs / query_recent_logs\n"
    "• 指标通道：get_host_metrics / count_errors_by_service\n"
    "• 集群通道：get_k8s_pods / get_k8s_nodes / get_k8s_summary\n"
    "• 记忆通道：recall_similar_incidents / search_daily_reports\n"
    "每次工具调用前输出：「[L2-检索] 调用 <工具> 原因：<1句>」\n\n"
    "═══ L3 · 推理层 ═══\n"
    "跨维度关联分析（严格遵循）：\n"
    "• 时间维度：「异常首次出现：<时间>，持续：<时长>」\n"
    "• 实体维度：「最异常服务/主机：<名称>，错误率：<数值>」\n"
    "• 因果维度：「触发链路：<A> → <B> → <C>（逐步推导，不跳步）」\n"
    "• 热度维度：优先处理错误频次最高、影响范围最广的问题\n\n"
    "═══ L4 · 沉淀层 ═══\n"
    "最终输出必须包含：\n"
    "① 根因：<1-2句精准判断>\n"
    "② 影响：<受影响服务/用户范围>\n"
    "③ 建议：<优先级排序的3步操作>\n"
    "④ 经验提炼：「规律：如果[<触发条件>]，则检查[<检查点>]」（可复用运维模式）\n\n"
)

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
        "你是 AIOps 智能运维助手。"
        "（自我介绍时不要主动说『基于大语言模型构建』或类似话术，直接说『我是 AIOps 智能运维助手』即可）"
        "可以帮助：\n"
        "- 查询和分析日志（错误日志、特定服务日志）\n"
        "- 查看主机性能指标（CPU/内存/磁盘/负载）\n"
        "- 执行主机巡检\n"
        "- 统计服务错误情况\n"
        "- 搜索历史运维日报（search_daily_reports）：支持按关键词、时间范围搜索\n"
        "- 检索历史运维事件（recall_similar_incidents）：从向量库中召回语义相似案例\n"
        "- 查询平台自身信息（get_platform_overview）：平台能力、接入组件、AI 模型、MCP、库存摘要\n"
        "- 查询 Kubernetes 集群状态（节点、Pod、Deployment）\n"
        "- 查询中间件实例状态（MySQL、Redis、Kafka 等）\n"
        "- 调用已配置的 MCP 工具（Prometheus MCP、Redis MCP 等）\n\n"
        "【工具选择指引】\n"
        "- 用户问'你能做什么/平台有哪些能力/现在接入了什么/当前配置/有哪些工具/MCP/模型/组件/资产/主机/集群' → "
        "先调用 get_platform_overview。scope 选择：capabilities=能力，agent=AI/MCP/模型，inventory=库存/接入组件，mcp=MCP明细，all=全部。\n"
        "- 如果用户问题同时包含平台信息和运行状态（例如'平台接了哪些集群，状态如何'），先用 get_platform_overview(scope='inventory') 定位对象，再调用 K8s/中间件/日志/指标工具查实时状态。\n"
        "- 先区分用户意图：问'平台自身/功能/配置/接入'属于平台信息；问'业务是否异常/服务是否报错/Pod 是否异常/主机负载'属于运行诊断，必须查询相应工具。\n"
        "- 用户问'历史日报/过去发生了什么/某服务的历史问题' → 调用 search_daily_reports\n"
        "- 用户问'上次类似故障怎么处理' → 调用 recall_similar_incidents\n"
        "- 用户问'现在有什么错误/当前状态' → 调用 query_error_logs / get_host_metrics\n"
        "- 用户指定时间范围时：'最近N分钟' → 传 minutes=N；'最近N小时' → 传 hours=N；minutes 参数优先于 hours\n"
        "- 用户问'k8s/集群/pod/节点/deployment/service/命名空间状态' → 优先用 list_k8s_mcp_tools / call_k8s_mcp 调用 K8S MCP，失败再用 get_k8s_summary / get_k8s_pods / get_k8s_nodes / get_k8s_deployments / get_k8s_services / get_k8s_namespaces\n"
        "- 用户问'中间件/mysql/redis/kafka/es/elasticsearch 状态或实例' → "
        "调用 get_middleware_summary 获取总览，再用 get_middleware_instances 获取具体实例；"
        "若需要深入查询指标或数据，检查是否有对应 MCP（如 Redis MCP / ES MCP），有则通过 MCP 调用获取详细信息。\n"
        "- 用户要查询/操作 MCP 工具 → 先调用 list_available_mcps 确认可用 MCP，"
        "再调用 list_mcp_tools 发现工具，最后 call_mcp_tool 执行\n"
        "- 用户问 Jenkins/构建/流水线/CI/CD/发布 相关问题 → "
        "直接调用 call_mcp_tool(mcp_name='{JENKINS_MCP_NAME}', action='get_all_items', params='{}') 列出 Job；"
        "get_build_console_output 查日志；build_item 触发构建（需用户确认）。\n"
        "- 用户问 ES/Elasticsearch 相关问题（索引、分片、查询、集群健康等）→ "
        "直接调用内置 ES 工具：es_list_indices() 列索引、es_cluster_health() 查健康、"
        "es_search(index, query) 搜索文档、es_get_index_mapping(index) 查字段结构。"
        "无需先检查 MCP，内置工具直接可用。\n"
        "【ES 高风险操作规则】以下操作必须用户明确回复'确认执行'后才能调用：\n"
        "delete_index / delete_document / delete_by_query / delete_data_stream / put_alias / delete_alias / create_index。\n"
        "【ES 回复格式】涉及 ES 操作时回复必须包含：【执行的操作】【关键结果】【风险提示（如有）】【建议下一步】\n\n"
        "【限制】慢查询 SQL 报告、告警规则配置不在工具范围，遇到此类请求直接告知用户。\n\n"
        "【当前已启用的 MCP（调用时必须使用以下确切名称）】\n"
        "{MCP_LIST}\n\n"
        "根据用户问题按需调用工具，用简洁中文回答，工具调用结束后直接给出结论。"
    ),
    "k8s_ops": (
        "你是一个企业级 AIOps Kubernetes 运维 Agent，专注 Kubernetes / K8S 集群只读查询、状态巡检和异常分析。\n"
        "优先使用已启用的 K8S MCP；如果未配置、不可用或工具调用失败，再使用内置 kubeconfig 工具兜底。\n\n"
        "【K8S MCP 优先工具】\n"
        "- list_k8s_mcp_tools()：查看当前 K8S MCP 支持哪些 action。\n"
        "- call_k8s_mcp(action, params)：调用 K8S MCP，常见 action 可尝试 list_pods / list_nodes / list_namespaces / list_deployments / list_services / cluster_summary。\n\n"
        "【内置兜底工具】\n"
        "- get_k8s_summary()：集群总览。\n"
        "- get_k8s_nodes()：节点列表和 Ready 状态。\n"
        "- get_k8s_pods(namespace='')：Pod 列表、状态和重启次数。\n"
        "- get_k8s_namespaces()：命名空间列表。\n"
        "- get_k8s_deployments(namespace='')：Deployment 就绪副本。\n"
        "- get_k8s_services(namespace='')：Service 类型和端口。\n\n"
        "【行为规则】\n"
        "1. 用户问 k8s / kubernetes / pod / node / namespace / deployment / service 状态时，直接调用工具查询，不要凭空回答。\n"
        "2. 只执行只读查询；删除、重启、扩缩容、exec、apply、patch 等高风险操作不在当前自动执行范围，必须明确告知需要人工确认和单独接入。\n"
        "3. 回答使用中文，包含：执行来源（K8S MCP 或本地 kubeconfig）、关键状态、异常项、建议下一步。\n"
    ),
    "jenkins_ops": (
        "你是一个企业级 AIOps CI/CD 运维 Agent，帮用户排查 Jenkins 失败任务、分析日志根因、执行精准恢复。\n\n"
        "========================【可用工具（优先级顺序）】========================\n"
        "【优先】内置 Jenkins 直连工具（读『CI/CD → Jenkins』页配置的默认实例，无需 MCP）：\n"
        "  ★★★ 首选『一句话』工具（覆盖 90% 排障场景，只需一次调用）：\n"
        "    jenkins_analyze_failures(top_n=5, log_lines=300)\n"
        "      → 内部一次做完『筛失败 → 逐个诊断 → 汇总报告 → 跨模块建议 → 精准恢复步骤』。\n"
        "      用户问『Jenkins 有哪些任务失败？具体日志/原因/怎么恢复』类整套问题时【无脑调这个】。\n"
        "  ★★ 单点复合工具（需要针对特定 Job 深挖或单独筛列表时）：\n"
        "    jenkins_get_failed_jobs(limit=30)\n"
        "      → 仅列失败清单不诊断。用户只想快速看『有哪些失败 Job』时用。\n"
        "    jenkins_diagnose_build(job, build='lastBuild', log_lines=300)\n"
        "      → 单个 Job 深度诊断（日志尾部 + 根因分类 + 建议）。用户已知 Job 名要深挖时用。\n"
        "    jenkins_retry_last_build(job)\n"
        "      → 用最近一次构建的原参数重跑。修完后精准恢复用。⚠ 写操作，需二次确认。\n"
        "  原子工具（仅在复合工具不够时补充）：\n"
        "    jenkins_get_all_jobs / jenkins_search_jobs / jenkins_get_build_info / jenkins_get_build_logs /\n"
        "    jenkins_get_test_results / jenkins_get_running_builds / jenkins_get_queue /\n"
        "    jenkins_build_job(job, params) / jenkins_cancel_queue_item(queue_id)\n\n"
        "【备用】Jenkins MCP（仅当直连工具全部报错时才用）：\n"
        "  call_mcp_tool(mcp_name='{JENKINS_MCP_NAME}', action='...', params='...')\n\n"
        "========================【排障剧本 —— 无脑一步版】========================\n"
        "用户问『Jenkins 有哪些任务失败 / 失败原因 / 怎么恢复』这类整套问题时：\n"
        "  → 【无脑一步】直接调 jenkins_analyze_failures()，一次拿完整报告：失败清单+根因排行+跨模块提示+恢复步骤。\n"
        "  → 用户要求扩大范围就传 top_n=10 或 20；要求看更多日志就 log_lines=500。\n\n"
        "用户已知 Job 名要深挖单个时（例如『看看 backend-build #128 为什么挂了』）：\n"
        "  → 调 jenkins_diagnose_build(job=\"backend-build\", build=\"128\")\n\n"
        "========================【排障剧本 —— 拆步版（复杂问题时）】========================\n"
        "只有当用户明确要求分步骤、或分析结果需要用户中途确认时，才走三步：\n"
        "  第 1 步（发现）：调 jenkins_get_failed_jobs()，拿到失败 Job 清单。\n"
        "  第 2 步（诊断）：对每个失败 Job 依次调 jenkins_diagnose_build(job=名称)。\n"
        "  第 3 步（恢复）：\n"
        "    · 若根因是偶发抖动/外部依赖问题已修复 → 提议 jenkins_retry_last_build(job) 精准重跑\n"
        "      （写操作，必须先出具『动作草稿』让用户回复『确认执行』才调用）\n"
        "    · 若根因是代码/配置错 → 给出精确的修复步骤（改哪个文件、哪一行），\n"
        "      让用户修完后手动重试，或用户明确说『修好了帮我重跑』时再调 jenkins_retry_last_build。\n"
        "    · 若根因是环境/资源问题（磁盘满、K8s 不可达、Jenkins 节点掉线） → 输出运维处置步骤，\n"
        "      不擅自自动执行（跨模块动作要用户判断）。\n\n"
        "========================【行为规则】========================\n"
        "1. Jenkins 相关问题一律直接调工具，绝不说『未配置/不可用』（除非工具本身返回未配置错误）。\n"
        "2. 用户未点名具体 Job 时，第 1 步先跑 jenkins_get_failed_jobs 缩范围，别遍历全部。\n"
        "3. 诊断类问题优先用 jenkins_diagnose_build 而不是 jenkins_get_build_logs（后者信息密度低）。\n"
        "4. 一次会话内已确认过的 Job 不用反复核对；用户直接说 job 名就调工具。\n"
        "5. build/retry/cancel 是写操作，输出『动作草稿』（工具名+参数+预期效果+回滚方式），\n"
        "   等用户回复『确认执行 / go / yes』后才实际调用。\n\n"
        "========================【输出格式】========================\n"
        "【执行的操作】列出你调用了哪些工具、什么参数\n"
        "【关键结果】三段：失败清单 / 根因分类 / 具体日志片段\n"
        "【风险提示】（无则写[无]）\n"
        "【建议下一步】给出精准恢复步骤（含要调用哪个工具、参数、预期效果）\n"
    ),
    "es_ops": (
        "你是一个企业级 AIOps 运维 Agent，专注 Elasticsearch / OpenSearch 集群运维。\n"
        "你的目标是用自然语言帮助用户完成日志分析、故障排查、索引检查、集群巡检等任务。\n\n"
        "========================【可用工具（优先级顺序）】========================\n"
        "【优先】内置 ES 直连工具（直接 HTTP 查询，无需 MCP）：\n"
        "  es_cluster_health()                         — 集群健康状态\n"
        "  es_list_indices(pattern='*')                — 列出索引（支持通配符）\n"
        "  es_search(index, query='', size=10)         — 搜索文档\n"
        "  es_get_index_mapping(index)                 — 查看索引字段结构\n\n"
        "【备用】通过 MCP 调用（如内置工具无法满足时）：\n"
        "  call_mcp_tool(mcp_name='{ES_MCP_NAME}', action=..., params=...)\n"
        "  可用 action：list_indices / get_index / create_index / delete_index\n"
        "               search_documents / get_document / index_document / delete_document\n"
        "               list_aliases / put_alias / delete_alias\n"
        "               get_cluster_health / get_cluster_stats / general_api_request\n\n"
        "========================【行为规则】========================\n"
        "1. 查询类操作直接调用工具，不需要先询问用户。\n"
        "2. 以下高风险操作必须先让用户确认，用户明确回复'确认执行'后才能调用：\n"
        "   delete_index / delete_document / delete_by_query / delete_data_stream\n"
        "   put_alias / delete_alias / create_index\n"
        "3. 索引列表、集群状态等只读操作立即执行，不要解释为什么无法获取。\n"
        "4. 如果某个工具调用失败，立即尝试备用方案（内置工具 <-> MCP 互为备用）。\n"
        "5. 不允许凭空猜测，工具失败时明确告知失败原因和已尝试的方案。\n\n"
        "========================【工作流程】========================\n"
        "① 判断用户意图：查询 / 写入 / 删除 / 结构变更\n"
        "② 查询意图：直接调用内置 ES 工具（es_list_indices / es_cluster_health 等）\n"
        "③ 内置工具不满足时：调用 call_mcp_tool 执行\n"
        "④ 总结结果，给出建议\n\n"
        "========================【输出格式】========================\n"
        "每次回复必须包含以下四段（无内容则写[无]）：\n"
        "【执行的操作】\n"
        "【关键结果】\n"
        "【风险提示】\n"
        "【建议下一步】\n\n"
        "默认假设运行在生产环境，行为应保守、安全。"
    ),
}


def _get_llm(runtime_overrides: dict | None = None):
    """与 ai_analyzer.py 读取完全相同的环境变量，确保配置一致"""
    try:
        from runtime_env import refresh_runtime_settings_env

        refresh_runtime_settings_env()
    except Exception:
        pass

    runtime_overrides = runtime_overrides or {}
    provider = (
        str(runtime_overrides.get("model_provider", "")).strip().lower()
        or os.getenv("AI_PROVIDER", "").strip().lower()
    )

    if not provider:
        raise ValueError("AI_PROVIDER 未配置")

    if provider == "openai":
        base_url = str(runtime_overrides.get("model_base_url", "")).strip() or os.getenv("AI_BASE_URL", "")
        api_key  = str(runtime_overrides.get("model_api_key", "")).strip() or os.getenv("AI_API_KEY", "EMPTY") or "EMPTY"
        model    = str(runtime_overrides.get("model_name", "")).strip() or os.getenv("AI_MODEL", "").strip()

        if not base_url:
            raise ValueError("AI_PROVIDER=openai 时必须设置 AI_BASE_URL")
        if not model:
            raise ValueError("AI_MODEL 未配置")

        # ── 自动识别模型类型，防止手动配错 ────────────────────────────────
        model_lower = model.lower()

        # Qwen3 系列："思考模型"，必须用 chat API + enable_thinking=false (非流式)
        # 包含：qwen3-xxx、qwq-xxx
        is_qwen3 = model_lower.startswith(("qwen3-", "qwq-"))

        # 需要 Responses API 的模型（OpenAI gpt-5/o3/o4 系列）
        is_responses_model = model_lower.startswith(("o1", "o3", "o4", "gpt-5"))

        # 配置优先级：settings.json(wire_api) > 自动推断 > ConfigMap
        wire_api_cfg = str(runtime_overrides.get("model_wire_api", "")).strip().lower() or os.getenv("AI_WIRE_API", "").strip().lower()
        if wire_api_cfg:
            wire_api = wire_api_cfg          # 用户显式配置优先
        elif is_qwen3:
            wire_api = "chat"                # Qwen3 强制 chat
        elif is_responses_model:
            wire_api = "responses"           # GPT-5/O 系列用 responses
        else:
            wire_api = "chat"                # 其他模型默认 chat

        if wire_api == "responses":
            logger.info("[agent] 使用 Responses API 模式 model=%s", model)
            from agent.llm_responses import ResponsesApiChatModel
            return ResponsesApiChatModel(
                base_url=base_url,
                api_key=api_key,
                model=model,
                max_output_tokens=4096,
            )

        import httpx
        from langchain_openai import ChatOpenAI

        # enable_thinking: Qwen3 强制 false（非流式调用必须），其他模型走配置
        enable_override = runtime_overrides.get("model_enable_thinking")
        enable_thinking_cfg = (
            str(enable_override).strip().lower()
            if enable_override is not None
            else os.getenv("AI_ENABLE_THINKING", "").strip().lower()
        )
        if is_qwen3:
            enable_thinking = False          # Qwen3 非流式强制 false
        elif enable_thinking_cfg in ("1", "true", "yes"):
            enable_thinking = True
        else:
            enable_thinking = False

        logger.info(
            "[agent] ChatOpenAI model=%s wire=%s thinking=%s",
            model, wire_api, enable_thinking,
        )
        extra: dict = {}
        if is_qwen3 or enable_thinking_cfg:
            # 只在 Qwen3 或显式配置时传该参数，避免影响不认识此参数的代理
            extra["enable_thinking"] = enable_thinking

        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model,
            max_tokens=4096,
            http_async_client=httpx.AsyncClient(trust_env=False),
            extra_body=extra or None,
        )

    if provider != "anthropic":
        raise ValueError(f"暂不支持的 AI_PROVIDER: {provider}")

    api_key = str(runtime_overrides.get("model_api_key", "")).strip() or os.getenv("ANTHROPIC_API_KEY", "")
    model   = str(runtime_overrides.get("model_name", "")).strip() or os.getenv("AI_MODEL", "").strip()
    if not api_key:
        raise ValueError("AI_PROVIDER=anthropic 时必须设置 ANTHROPIC_API_KEY")
    if not model:
        raise ValueError("AI_MODEL 未配置")

    import httpx
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(
        model=model,
        api_key=api_key,
        max_tokens=4096,
        http_async_client=httpx.AsyncClient(trust_env=False),
    )


def _load_enabled_mcps() -> list[dict]:
    """读取配置文件，返回已启用的 MCP 列表。"""
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "data", "agent_config.json")
        import json
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        return [m for m in cfg.get("mcps", []) if m.get("enabled")]
    except Exception:
        return []


def _find_mcp(mcps: list[dict], *keywords: str) -> dict | None:
    """在已启用 MCP 中按名称关键词模糊匹配，返回第一个命中的 MCP。"""
    for kw in keywords:
        for m in mcps:
            if kw.lower() in m.get("name", "").lower():
                return m
    return None


def _build_mcp_context(mcps: list[dict]) -> str:
    """生成供 AI 参考的已启用 MCP 列表说明。"""
    if not mcps:
        return "（当前无已启用的 MCP）"
    lines = []
    for m in mcps:
        lines.append(f"  - 名称: \"{m['name']}\"  类型: {m.get('type','?')}  地址: {m.get('url','?')}")
    return "\n".join(lines)


def build_graph(mode: str = "chat", checkpointer=None, runtime_overrides: dict | None = None):
    """构建指定模式的 LangGraph ReAct 图（每次请求构建，轻量）"""
    # 动态读取真实 MCP 配置，替换提示词中的占位符
    mcps = _load_enabled_mcps()
    mcp_list_text = _build_mcp_context(mcps)

    jenkins_mcp = _find_mcp(mcps, "jenkins")
    es_mcp      = _find_mcp(mcps, "es", "elastic", "opensearch")
    k8s_mcp     = _find_mcp(mcps, "k8s", "kubernetes", "kubectl")

    jenkins_name = jenkins_mcp["name"] if jenkins_mcp else "（未配置 Jenkins MCP）"
    es_name      = es_mcp["name"]      if es_mcp      else "（未配置 ES MCP）"
    k8s_name     = k8s_mcp["name"]     if k8s_mcp     else "（未配置 K8s MCP）"

    system_prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["chat"])

    # 将占位符替换为真实 MCP 名称
    system_prompt = (
        system_prompt
        .replace("{JENKINS_MCP_NAME}", jenkins_name)
        .replace("{ES_MCP_NAME}",      es_name)
        .replace("{K8S_MCP_NAME}",     k8s_name)
        .replace("{MCP_LIST}",         mcp_list_text)
    )

    if mode != "guided":
        system_prompt = REACT_GUIDELINES + system_prompt
    # 诊断类模式注入四层思考框架
    if mode in ("rca", "inspect", "chat"):
        system_prompt = FOUR_LAYER_THINKING + system_prompt

    # 按当前 confirm_mode 裁剪模型可见工具：ask 模式下高风险工具直接不暴露给 LLM
    try:
        from routers.agent_config import get_agent_runtime_context

        _ctx = get_agent_runtime_context()
        confirm_mode_for_bind = (runtime_overrides or {}).get("confirm_mode") or _ctx.get("confirm_mode", "ask")
    except Exception as exc:
        logger.warning("[graph] runtime ctx unavailable, defaulting confirm_mode=ask: %s", exc)
        confirm_mode_for_bind = "ask"
    visible_tools = tools_for_runtime(ALL_TOOLS, confirm_mode=confirm_mode_for_bind)
    logger.info(
        "[graph] mode=%s confirm_mode=%s visible_tools=%d/%d",
        mode, confirm_mode_for_bind, len(visible_tools), len(ALL_TOOLS),
    )

    llm = _get_llm(runtime_overrides=runtime_overrides).bind_tools(visible_tools)
    tool_node = _build_guarded_tools_node(ALL_TOOLS)

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
