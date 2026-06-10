"""Agent 工具按领域分模块。

外部仍可 `from agent.tools import call_mcp_tool, ALL_TOOLS, ...` 不变 —
backend/agent/tools.py 是兼容入口，从这里 re-export。

实际代码组织在以下子模块：
  _shared      共享 helper（权限过滤、MCP 客户端、ES base url、Jenkins client、SSH 白名单等）
  logs         日志查询类
  metrics      主机指标 / 巡检
  k8s          Kubernetes 查询 + K8S MCP 桥接
  middleware   中间件总览
  elasticsearch ES 直连工具
  knowledge    Milvus 历史召回 / 历史日报检索
  web          Firecrawl Web 检索
  report       报告导出
  mcp_bridge   MCP 通用调用
  jenkins      Jenkins CI/CD
  ssh          SSH 命令执行
"""
