# 02. 代码模块地图

## 1. 根目录

```text
loki-log-analyse/
├── backend/       # FastAPI、Agent、领域服务、外部系统客户端、测试
├── frontend/      # Vue 3 管理台
├── cli/           # Ink/React 终端客户端
├── k8s/           # Kubernetes 部署资源
├── docs/          # 设计、部署和源码教程
├── reports/       # 报告产物目录之一
├── docker-compose.yml
└── deploy.sh
```

## 2. 后端分层地图

```text
backend/
├── main.py                    # FastAPI 组合根与 lifespan
├── state.py                   # Loki/Prometheus/SkyWalking 等共享客户端状态
├── runtime_env.py             # 环境与运行时设置刷新
├── db.py                      # SQLAlchemy engine/session/base
├── auth/                      # 登录、会话、RBAC、审计、中间件
├── routers/                   # HTTP/SSE 接口层
├── services/                  # RCA、证据、知识图谱、工作流等领域服务
├── agent/
│   ├── graph.py               # LangGraph ReAct 图
│   ├── tools.py               # 工具汇总与导出
│   ├── risk_registry.py       # 风险与确认策略
│   ├── external_executor.py   # 外部执行器适配
│   ├── milvus_memory.py       # 对话/知识记忆
│   └── tool_modules/          # 按领域拆分的 Agent 工具
├── observability/             # LLM 指标、trace、脱敏与降级
├── *_client.py                # Loki/Jenkins/SkyWalking 等协议客户端
├── report_builder.py          # 日报数据聚合与构造
├── report_store.py            # 报告元数据持久化
├── slow_log_parser.py         # MySQL 慢日志解析
└── tests/                     # unittest 风格回归测试
```

## 3. Router 按领域分组

| 领域 | 主要文件 | 代表接口 |
| --- | --- | --- |
| 认证与管理 | `auth/router.py`、`auth/admin_router.py` | `/api/auth/*`、`/api/admin/*` |
| 日志 | `routers/logs.py` | `/api/logs/*`、`/api/analyze/*` |
| 报告与慢日志 | `routers/reports.py`、`routers/slowlog.py` | `/api/report/*`、`/api/slowlog/*` |
| Agent | `routers/agent.py`、`routers/agent_config.py` | `/api/agent/*`、`/api/agent-config/*` |
| 可观测性 | `routers/observability.py`、`routers/skywalking.py` | `/api/observability/*`、`/api/sw/*` |
| 告警/RCA/事件 | `routers/alerts.py`、`routers/rca.py`、`routers/events.py` | `/api/alerts/*`、`/api/rca/*`、`/api/events/*` |
| 基础设施 | `kubernetes.py`、`hosts.py`、`ssh.py` | `/api/k8s/*`、`/api/hosts/*`、`/api/ssh/*` |
| 中间件 | `elasticsearch.py`、`redis_clusters.py`、`kafka_clusters.py` | `/api/es/*`、`/api/redis/*`、`/api/kafka/*` |
| 自动化 | `ansible_tasks.py`、`workflows.py`、`tickets.py` | `/api/ansible/*`、`/api/workflows/*`、`/api/tickets/*` |
| 图与知识 | `knowledge_graph.py`、`knowledge.py`、`topology.py` | `/api/kg/*`、`/api/knowledge/*`、`/api/topology/*` |

## 4. Agent 工具地图

[`backend/agent/tool_modules`](../../backend/agent/tool_modules) 按外部能力拆分：

| 模块 | 负责内容 |
| --- | --- |
| `logs.py` | Loki 查询、错误日志、模板与上下文 |
| `prometheus.py` / `metrics.py` | 指标即时/区间查询与指标分析 |
| `k8s.py` | Kubernetes 资源读取和受控操作 |
| `ssh.py` | 主机与远程命令能力 |
| `elasticsearch.py` | ES 集群、索引和查询 |
| `jenkins.py` | Jenkins 作业、构建与队列 |
| `middleware.py` | 中间件健康与指标 |
| `alerting.py` | 告警查询与处置 |
| `graph.py` / `knowledge.py` | 图谱和平台知识 |
| `mcp_bridge.py` | 已配置 MCP 的桥接调用 |
| `report.py` | 报告查询与生成能力 |
| `codegraph.py` | 源码结构分析工具能力 |
| `web.py` | Web 抓取或外部信息能力 |

[`backend/agent/tools.py`](../../backend/agent/tools.py) 是工具汇总层；[`backend/agent/graph.py`](../../backend/agent/graph.py) 根据确认模式筛选模型可见工具，并用受控工具节点执行。

## 5. Service 与 Client 的区别

- `*_client.py`：面向某个外部协议，负责 HTTP/GraphQL/SDK 调用、认证和响应转换；
- `services/*.py`：面向业务语义，负责组合多个数据源、规则、状态和持久化；
- `routers/*.py`：面向 HTTP 契约，负责参数、权限、SSE/下载响应和错误映射。

例如 RCA 不应写成一个巨大的 Router：Router 接收请求，`rca_localizer` 计算候选，`rca_engine` 聚合证据与分析，`evidence` 定义证据记录，最后由 Router 输出结果或 SSE。

## 6. 前端地图

```text
frontend/src/
├── main.js                   # Vue/Pinia/Router 启动
├── App.vue                   # 根布局
├── router/index.js           # 路由、懒加载、登录与权限守卫
├── stores/auth.js            # 当前用户、权限与登录状态
├── api/index.js              # HTTP、SSE、文件下载契约
├── components/
│   ├── Sidebar.vue
│   ├── AIOpsAssistantFloat.vue
│   └── CommandPalette.vue
└── views/                    # 业务页面
```

页面数量多，不建议按文件名字母顺序阅读。先按一条用户旅程选择 `View -> api -> Router -> Service/Client`。

## 7. 测试地图

当前测试集中覆盖高风险边界：

- Agent prompt、受控工具、风险注册表和安全；
- 认证中间件、会话、数据库迁移和 Webhook 安全；
- 告警分类/批量状态、事件接入；
- RCA 引擎、知识图谱 Neo4j；
- 慢日志解析、SSH/Java 诊断命令；
- 报告构建、Kubeconfig 导入、工具分组。

阅读实现时优先打开同名测试，它通常比页面文案更准确地表达行为契约。

## 8. 模块定位法

遇到需求时按以下顺序定位：

```text
用户看到的页面或 CLI 命令
  -> frontend/src/api/index.js 或 cli/index.mjs
  -> backend/routers/对应领域.py
  -> services/、agent/ 或 *_client.py
  -> db/Redis/文件/外部系统
  -> backend/tests/对应测试
```

## 9. 自检

1. 为什么“修改一个页面”仍可能需要检查 Router 与 Service？
2. `tool_modules/k8s.py` 与 `routers/kubernetes.py` 的调用者和安全边界有什么不同？
3. 哪些问题应先看 Client，哪些问题应先看 Service？

