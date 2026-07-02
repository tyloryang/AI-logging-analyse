"""按领域分组的工具视图。

不搬运 tools.py 中任何代码（其它模块按名 import 仍然有效），仅提供：
  - DOMAIN_TOOLS:  domain → [tool_name, ...]    （8 个领域分类）
  - READ_ONLY_TOOLS / SAFE_AUTO_TOOLS:           按风险等级过滤的子集
  - tools_for_runtime(...):  根据 confirm_mode + behaviors_auto 动态裁剪 ALL_TOOLS

graph.py 在 bind_tools / 构造 ToolNode 时可改用这里的视图，把高风险工具
从模型可见列表里直接拿掉，降低"模型尝试调用 + guard 拒绝"的浪费。
"""
from __future__ import annotations

from .risk_registry import GuardDecision, ToolRisk, filter_callable_tools, risk_of

# 8 个领域的工具名清单。新增工具只需在这里挂一次，guard 与白名单同时生效。
DOMAIN_TOOLS: dict[str, list[str]] = {
    "logs": [
        "query_error_logs",
        "count_errors_by_service",
        "query_recent_logs",
        "get_services_list",
    ],
    "platform": [
        "get_platform_overview",
    ],
    "metrics": [
        "get_host_metrics",
        "inspect_all_hosts",
    ],
    "k8s": [
        "get_k8s_summary",
        "get_k8s_pods",
        "get_k8s_nodes",
        "get_k8s_namespaces",
        "get_k8s_deployments",
        "get_k8s_services",
        "call_k8s_mcp",
        "list_k8s_mcp_tools",
    ],
    "middleware": [
        "get_middleware_summary",
        "get_middleware_instances",
        "es_list_indices",
        "es_cluster_health",
        "es_search",
        "es_get_index_mapping",
    ],
    "knowledge": [
        "recall_similar_incidents",
        "search_daily_reports",
    ],
    "web": [
        "firecrawl_search_web",
        "firecrawl_scrape_url",
    ],
    "report": [
        "export_report_pdf",
    ],
    "mcp_bridge": [
        "list_available_mcps",
        "list_mcp_tools",
        "call_mcp_tool",
    ],
    "cicd": [
        "jenkins_get_all_jobs",
        "jenkins_search_jobs",
        "jenkins_get_build_info",
        "jenkins_get_build_logs",
        "jenkins_get_running_builds",
        "jenkins_get_queue",
        "jenkins_get_test_results",
        "jenkins_build_job",
        "jenkins_cancel_queue_item",
        "jenkins_get_failed_jobs",
        "jenkins_diagnose_build",
        "jenkins_retry_last_build",
        "jenkins_analyze_failures",
    ],
    "ssh": [
        "execute_ssh_command",
    ],
}


def _flatten() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for names in DOMAIN_TOOLS.values():
        for n in names:
            if n in seen:
                continue
            seen.add(n)
            out.append(n)
    return out


ALL_TOOL_NAMES: list[str] = _flatten()
READ_ONLY_TOOLS: list[str] = [n for n in ALL_TOOL_NAMES if risk_of(n) is ToolRisk.READ]
SAFE_AUTO_TOOLS: list[str] = [
    n for n in ALL_TOOL_NAMES
    if risk_of(n) in (ToolRisk.READ, ToolRisk.WRITE_LOW)
]


def names_for_runtime(confirm_mode: str = "ask") -> list[str]:
    """根据 confirm_mode 返回模型可见的工具名清单。

      confirm_mode=ask  → 只暴露 READ + WRITE_LOW（模型连 high 都尝试不了）
      confirm_mode=auto → 暴露除 DESTRUCTIVE 外的全部
    """
    return filter_callable_tools(ALL_TOOL_NAMES, confirm_mode=confirm_mode)


def tools_for_runtime(all_tools: list, confirm_mode: str = "ask") -> list:
    """把 ALL_TOOLS（@tool 对象列表）按 confirm_mode 裁剪后返回。

    输入是 graph.py 已有的 `from .tools import ALL_TOOLS` 列表，
    输出是过滤后的子集（保持原工具对象身份不变，bind_tools 直接可用）。
    """
    allowed = set(names_for_runtime(confirm_mode))
    return [t for t in all_tools if getattr(t, "name", "") in allowed]


__all__ = [
    "DOMAIN_TOOLS",
    "ALL_TOOL_NAMES",
    "READ_ONLY_TOOLS",
    "SAFE_AUTO_TOOLS",
    "names_for_runtime",
    "tools_for_runtime",
]
