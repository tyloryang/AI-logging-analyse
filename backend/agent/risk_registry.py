"""工具风险注册表 + RiskGuard 决策函数。

为 LangGraph 编排层提供"这个工具该不该让 LLM 自主调"的统一答案。
默认从严：未登记的工具被当作 write_high，需要人工审批。
"""
from __future__ import annotations

import logging
from enum import Enum
from typing import Iterable

logger = logging.getLogger(__name__)


class ToolRisk(str, Enum):
    """工具风险等级。

    - READ          只读，无副作用，LLM 可任意调用
    - WRITE_LOW     有写但易回滚（导出报告、写本地文件等）
    - WRITE_HIGH    写且可能影响业务（改 ConfigMap、调 MCP 通用接口）
    - DESTRUCTIVE   删除 / 不可逆 / 影响多服务（删 Deployment、drop 数据等）
    """

    READ = "read"
    WRITE_LOW = "write_low"
    WRITE_HIGH = "write_high"
    DESTRUCTIVE = "destructive"


# tool_name → ToolRisk
# 名称来自 backend/agent/tools.py 的 @tool 装饰器函数名
TOOL_RISK: dict[str, ToolRisk] = {
    # ── 平台自身信息（只读）──
    "get_platform_overview": ToolRisk.READ,
    # ── 日志类（全读）──
    "query_error_logs": ToolRisk.READ,
    "count_errors_by_service": ToolRisk.READ,
    "query_recent_logs": ToolRisk.READ,
    "get_services_list": ToolRisk.READ,
    # ── 主机指标（全读）──
    "get_host_metrics": ToolRisk.READ,
    "inspect_all_hosts": ToolRisk.READ,
    # ── K8s 查询（全读）──
    "get_k8s_summary": ToolRisk.READ,
    "get_k8s_pods": ToolRisk.READ,
    "get_k8s_nodes": ToolRisk.READ,
    "get_k8s_namespaces": ToolRisk.READ,
    "get_k8s_deployments": ToolRisk.READ,
    "get_k8s_services": ToolRisk.READ,
    # ── 中间件查询（全读）──
    "get_middleware_summary": ToolRisk.READ,
    "get_middleware_instances": ToolRisk.READ,
    "es_list_indices": ToolRisk.READ,
    "es_cluster_health": ToolRisk.READ,
    "es_search": ToolRisk.READ,
    "es_get_index_mapping": ToolRisk.READ,
    # ── 知识库（全读）──
    "recall_similar_incidents": ToolRisk.READ,
    "search_daily_reports": ToolRisk.READ,
    # ── Web 检索（读，但走外网，归 LOW）──
    "firecrawl_search_web": ToolRisk.WRITE_LOW,
    "firecrawl_scrape_url": ToolRisk.WRITE_LOW,
    # ── 写本地文件 / 触发报告生成（LOW，可重生成）──
    "export_report_pdf": ToolRisk.WRITE_LOW,
    # ── MCP 通用调用：调到啥不一定，从严 HIGH ──
    "call_mcp_tool": ToolRisk.WRITE_HIGH,
    "call_k8s_mcp": ToolRisk.WRITE_HIGH,
    "list_mcp_tools": ToolRisk.READ,
    "list_k8s_mcp_tools": ToolRisk.READ,
    "list_available_mcps": ToolRisk.READ,
    # ── Prometheus 直连 ──
    "promql_query": ToolRisk.READ,
    "get_metric_history": ToolRisk.READ,
    # ── 告警池 & 代码图谱 ──
    "get_current_alerts": ToolRisk.READ,
    "codegraph_query": ToolRisk.READ,
    # ── Jenkins CI/CD ──
    "jenkins_get_all_jobs": ToolRisk.READ,
    "jenkins_search_jobs": ToolRisk.READ,
    "jenkins_get_build_info": ToolRisk.READ,
    "jenkins_get_build_logs": ToolRisk.READ,
    "jenkins_get_running_builds": ToolRisk.READ,
    "jenkins_get_queue": ToolRisk.READ,
    "jenkins_get_test_results": ToolRisk.READ,
    "jenkins_get_failed_jobs": ToolRisk.READ,        # 一键筛失败任务，只读
    "jenkins_diagnose_build": ToolRisk.READ,         # 日志+根因分析，只读
    "jenkins_analyze_failures": ToolRisk.READ,       # 一句话出完整报告，只读
    "jenkins_build_job": ToolRisk.WRITE_HIGH,        # 触发构建 = 业务变更
    "jenkins_retry_last_build": ToolRisk.WRITE_HIGH, # 同参数重跑构建
    "jenkins_cancel_queue_item": ToolRisk.WRITE_LOW, # 取消队列可回滚
    # ── SSH 命令执行（已有内置黑名单，但 OS 命令仍归 HIGH）──
    "execute_ssh_command": ToolRisk.WRITE_HIGH,
}


class GuardDecision(str, Enum):
    EXECUTE = "execute"
    APPROVAL = "approval"
    DENY = "deny"


def risk_of(tool_name: str) -> ToolRisk:
    """未登记的工具一律按 WRITE_HIGH 处理（白名单制 + 默认从严）。"""
    return TOOL_RISK.get(tool_name, ToolRisk.WRITE_HIGH)


def risk_guard(
    tool_name: str,
    confirm_mode: str = "ask",
    behaviors_auto: bool = False,
    llm_confidence: float | None = None,
) -> GuardDecision:
    """决策：这个工具调用应该 直接放行 / 进审批队列 / 拒绝。

    参数：
        tool_name        — 工具函数名
        confirm_mode     — agent_config.basic.confirm_mode："auto" | "ask"
        behaviors_auto   — behaviors.auto 开关（自动执行动作）
        llm_confidence   — 调用方传入的 LLM 置信度，0-1；None 表示未知

    决策表：
        READ         → EXECUTE
        WRITE_LOW    → confirm_mode=auto OR behaviors_auto=True → EXECUTE，否则 APPROVAL
        WRITE_HIGH   → 必须 behaviors_auto=True 且 confidence>=0.85 → EXECUTE，否则 APPROVAL
        DESTRUCTIVE  → 始终 APPROVAL（除非显式白名单，本函数不放行）
    """
    risk = risk_of(tool_name)

    if risk is ToolRisk.READ:
        return GuardDecision.EXECUTE

    if risk is ToolRisk.WRITE_LOW:
        if behaviors_auto or confirm_mode == "auto":
            return GuardDecision.EXECUTE
        return GuardDecision.APPROVAL

    if risk is ToolRisk.WRITE_HIGH:
        if behaviors_auto and (llm_confidence is not None and llm_confidence >= 0.85):
            return GuardDecision.EXECUTE
        return GuardDecision.APPROVAL

    # DESTRUCTIVE 或未知（已 fallback 到 WRITE_HIGH，这里其实进不来）
    return GuardDecision.APPROVAL


def filter_callable_tools(tool_names: Iterable[str], confirm_mode: str = "ask") -> list[str]:
    """根据当前 confirm_mode 把超出"允许 LLM 自主调用"的工具过滤掉。

    适合在编排层动态裁剪工具白名单：ask 模式下隐藏所有 WRITE_HIGH+，让模型连尝试都不尝试。
    """
    out: list[str] = []
    for name in tool_names:
        risk = risk_of(name)
        if confirm_mode == "auto":
            if risk is not ToolRisk.DESTRUCTIVE:
                out.append(name)
        else:
            if risk in (ToolRisk.READ, ToolRisk.WRITE_LOW):
                out.append(name)
    return out


__all__ = [
    "ToolRisk",
    "GuardDecision",
    "TOOL_RISK",
    "risk_of",
    "risk_guard",
    "filter_callable_tools",
]
