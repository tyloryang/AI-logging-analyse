"""LangGraph Agent 工具集 — 兼容入口。

历史上本文件是 1800 行的"巨型工具箱"。2026-06 重构按领域拆分到
`backend/agent/tool_modules/` 子包，本文件改为纯 re-export 兼容层：

  - 所有 `@tool` 函数仍可 `from agent.tools import xxx` 导入（保持
    feishu_bot / es_quick_actions / k8s_quick_actions 等下游不破坏）
  - 所有共享 helper 也 re-export（部分历史代码直接用 `_filter_hosts_by_groups` 等）
  - `ALL_TOOLS` 在这里聚合，与拆分前完全一致顺序

新增工具请直接放到对应 domain 子模块 + 加进 `__all__`，最后在本文件的
`ALL_TOOLS` 列表追加引用。
"""
from __future__ import annotations

# ── 共享 helper（保持历史兼容，少数下游代码可能直接 import 这些）────────────
from .tool_modules._shared import (  # noqa: F401
    _AGENT_CONFIG_PATH,
    _DANGER_PATTERNS,
    _REPORTS_DIR,
    _SAFE_CMDS,
    _allowed_groups,
    _allowed_k8s_clusters,
    _call_es_mcp_list_indices,
    _call_sse_mcp,
    _call_sse_mcp_raw,
    _call_sse_mcp_sync,
    _call_streamable_http_mcp,
    _call_streamable_http_mcp_raw,
    _check_safe,
    _configurable,
    _es_base_url,
    _filter_hosts_by_groups,
    _find_enabled_mcp,
    _format_es_indices_result,
    _is_es_mcp,
    _is_k8s_mcp_name,
    _jenkins_client,
    _list_sse_mcp_tools_sync,
    _list_streamable_http_mcp_tools_sync,
    _mcp_content_to_text,
    _normalize_sse_url,
    _visible_k8s_clusters,
)

# ── 各领域 @tool 函数 ─────────────────────────────────────────────────────────
from .tool_modules.elasticsearch import (  # noqa: F401
    es_cluster_health,
    es_get_index_mapping,
    es_list_indices,
    es_search,
)
from .tool_modules.jenkins import (  # noqa: F401
    jenkins_build_job,
    jenkins_cancel_queue_item,
    jenkins_diagnose_build,
    jenkins_get_all_jobs,
    jenkins_get_build_info,
    jenkins_get_build_logs,
    jenkins_get_failed_jobs,
    jenkins_get_queue,
    jenkins_get_running_builds,
    jenkins_get_test_results,
    jenkins_retry_last_build,
    jenkins_search_jobs,
)
from .tool_modules.k8s import (  # noqa: F401
    call_k8s_mcp,
    get_k8s_deployments,
    get_k8s_namespaces,
    get_k8s_nodes,
    get_k8s_pods,
    get_k8s_services,
    get_k8s_summary,
    list_k8s_mcp_tools,
)
from .tool_modules.knowledge import (  # noqa: F401
    recall_similar_incidents,
    search_daily_reports,
)
from .tool_modules.logs import (  # noqa: F401
    count_errors_by_service,
    get_services_list,
    query_error_logs,
    query_recent_logs,
)
from .tool_modules.mcp_bridge import (  # noqa: F401
    call_mcp_tool,
    list_available_mcps,
    list_mcp_tools,
)
from .tool_modules.metrics import (  # noqa: F401
    get_host_metrics,
    inspect_all_hosts,
)
from .tool_modules.middleware import (  # noqa: F401
    get_middleware_instances,
    get_middleware_summary,
)
from .tool_modules.platform import get_platform_overview  # noqa: F401
from .tool_modules.report import export_report_pdf  # noqa: F401
from .tool_modules.ssh import execute_ssh_command  # noqa: F401
from .tool_modules.web import (  # noqa: F401
    firecrawl_scrape_url,
    firecrawl_search_web,
)

# ── 聚合：所有可见工具（顺序与重构前一致）─────────────────────────────────────
ALL_TOOLS = [
    get_platform_overview,
    recall_similar_incidents,
    firecrawl_search_web,
    firecrawl_scrape_url,
    search_daily_reports,
    export_report_pdf,
    query_error_logs,
    count_errors_by_service,
    get_services_list,
    get_host_metrics,
    inspect_all_hosts,
    query_recent_logs,
    # K8s
    get_k8s_summary,
    get_k8s_pods,
    get_k8s_nodes,
    get_k8s_namespaces,
    get_k8s_deployments,
    get_k8s_services,
    # 中间件
    get_middleware_summary,
    get_middleware_instances,
    # ES 直连工具
    es_list_indices,
    es_cluster_health,
    es_search,
    es_get_index_mapping,
    # MCP
    list_available_mcps,
    list_k8s_mcp_tools,
    list_mcp_tools,
    call_k8s_mcp,
    call_mcp_tool,
    # Jenkins CI/CD
    jenkins_get_all_jobs,
    jenkins_search_jobs,
    jenkins_build_job,
    jenkins_get_build_info,
    jenkins_get_build_logs,
    jenkins_get_running_builds,
    jenkins_get_queue,
    jenkins_cancel_queue_item,
    jenkins_get_test_results,
    # Jenkins 高层复合工具（诊断链路专用）
    jenkins_get_failed_jobs,
    jenkins_diagnose_build,
    jenkins_retry_last_build,
    # SSH 命令执行
    execute_ssh_command,
]
