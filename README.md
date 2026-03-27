<p align="center">
  <h1 align="center">🛸 AI Ops · 智能运维平台</h1>
  <p align="center">
    基于 <b>Loki · Prometheus · SkyWalking · LangGraph · AI 大模型</b> 的一站式智能运维平台<br/>
    告别人肉翻日志，让 AI 替你值夜班
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/license-MIT-blue" />
    <img src="https://img.shields.io/badge/Python-3.11+-green" />
    <img src="https://img.shields.io/badge/Vue-3.x-brightgreen" />
    <img src="https://img.shields.io/badge/FastAPI-0.115-009688" />
    <img src="https://img.shields.io/badge/AI-Claude%20%7C%20Qwen3%20%7C%20DeepSeek-blueviolet" />
  </p>
</p>

---

## 🎯 它能解决什么问题？

凌晨三点，监控告警响了。你打开 Loki，面对滚动不停的日志流：

```
{app="order-service"} |= "error" | limit 500
```

500 条刷出来，你盯着屏幕逐行扫——**快则十分钟，慢则一小时**，还不一定找到根因。

更麻烦的：

- 📦 **日志海**：微服务架构下每天轻松百万条，重复噪音占 90%
- 🔗 **上下文割裂**：日志在 Loki、指标在 Prometheus、链路在 SkyWalking，三个系统反复横跳
- 📝 **日报全靠手写**：每日运维报告汇总状态、总结问题，下班前最痛苦的半小时
- 🐢 **慢查询难定位**：MySQL 慢日志几千条，哪条 SQL 最需要加索引？
- 🌐 **链路追踪不直观**：调用链跨了五个服务，耗时在哪一段根本看不出来

**这个项目把上面所有问题收进一个页面，用 AI 帮你在 30 秒内给出结论。**

---

## ✨ 功能全景

| 模块 | 核心能力 |
|------|----------|
| 📊 **仪表盘** | 系统总览、24h 错误趋势、服务健康矩阵、组件连接状态实时检测 |
| 📋 **日志分析** | 服务/级别/关键字过滤、Loki 实时查询、Drain3 模板聚类、AI 流式根因分析 |
| 📈 **指标监控** | 各服务错误数趋势图、汇总统计 |
| 🔔 **告警历史** | 基于错误日志自动分级告警（critical / error / warning） |
| 🔗 **APM 链路追踪** | SkyWalking 接入：链路瀑布图、跨服务调用拓扑、接口耗时 TopN、性能指标趋势 |
| 📄 **运维日报** | 一键 AI 生成日报，健康评分 + Top 问题 + 处置建议，飞书/钉钉定时推送 |
| 🖥️ **主机 CMDB** | Prometheus 自动发现主机，CPU/内存/磁盘/负载实时采集，可编辑责任人/环境/角色 |
| 🔍 **主机巡检** | 阈值巡检（CPU/内存/磁盘/负载），AI 逐台分析异常，一键导出三页式 Excel |
| 🐢 **MySQL 慢日志** | SSH 读取远端慢日志，Drain3 SQL 模板聚合，多主机并行，AI 加索引/改写建议 |
| 💻 **SSH 终端** | 浏览器内 Web Terminal，凭证库 AES 加密，多标签，CMDB 一键直连 |
| 🤖 **AI 智能体** | LangGraph ReAct Agent：自动 RCA 根因分析、自主全量巡检、智能运维对话，工具调用可视化 |
| 👥 **用户权限** | 注册审批、模块级权限（view/operate）、登录失败锁定、操作审计日志 |
| ⏰ **定时推送** | APScheduler cron 自动生成运维日报 + 主机巡检日报并推送，无需外部 cron |

---

## 🖼️ 界面预览

### 仪表盘
![仪表盘](screenshots/02_dashboard.png)
> 系统总览：Loki / Prometheus / AI / SkyWalking 连接状态，24h 错误趋势，服务健康矩阵

### 日志分析
![日志分析](screenshots/03_log_analysis.png)
> 按服务/级别/关键字过滤，Drain3 模板聚类，AI 流式分析根因与建议

### APM 链路追踪
![APM](screenshots/09_apm.png)
> SkyWalking 链路瀑布图：跨服务调用全链路可视化，定位慢接口与异常 span

### MySQL 慢日志分析
![慢日志分析](screenshots/04_slowlog.png)
> SSH 读取远端慢日志，Drain3 SQL 模板聚合，AI 流式优化建议

### CMDB 巡检
![CMDB 巡检](screenshots/05_cmdb.png)
> Prometheus 自动发现主机，实时指标，阈值巡检一键导出 Excel

### SSH 终端
![SSH 终端](screenshots/06_ssh.png)
> 浏览器内 Web Terminal，凭证库 AES 加密，多标签，支持从 CMDB 一键连接

### 运维日报 + 飞书推送
![分析报告](screenshots/07_report.png)
> AI 流式生成运维日报，健康评分 + Top 问题 + 建议，历史持久化，飞书/钉钉推送

### AI 智能体
![AI 智能体](AIanalyse.png)
> LangGraph ReAct：自动根因分析，工具调用实时可视化

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    浏览器  Vue 3 + Vite                          │
│  Dashboard · 日志分析 · APM追踪 · CMDB · SSH · 慢日志 · AI智能体 │
│                  Pinia · Axios · SSE · WebSocket                  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP / SSE / WebSocket
┌──────────────────────────▼──────────────────────────────────────┐
│                   FastAPI  Python 3.11+                          │
│  routers/logs  hosts  reports  ssh  slowlog  agent  skywalking  │
│  auth/  (JWT-free Session · 注册审批 · 模块权限 · 审计日志)       │
│  agent/  (LangGraph ReAct · tools · graph · checkpointer)        │
│  scheduler.py  (APScheduler cron 定时推送)                        │
└──────┬───────────────────────────────────────┬───────────────────┘
       │                                       │
┌──────▼──────────────────┐   ┌───────────────▼───────────────────┐
│  外部数据源               │   │  本地存储                          │
│  Loki  (日志查询)        │   │  SQLite / MySQL / PostgreSQL       │
│  Prometheus (指标+发现)  │   │  Redis  (Session + 失败计数)       │
│  SkyWalking OAP (APM)   │   │  ./reports/  (日报 JSON)           │
│  AI Provider             │   │  cmdb_hosts.json  (CMDB 扩展)     │
│  (Claude / Qwen3 / 本地) │   │  SQLite  (LangGraph checkpointer) │
│  飞书 / 钉钉 Webhook     │   │  Milvus  (历史事件向量检索)         │
└──────────────────────────┘   └───────────────────────────────────┘
```

### AI 智能体执行流（LangGraph ReAct）

```mermaid
flowchart TD
    Req["POST /api/agent/{mode}"] --> Build["build_graph(mode)"]

    subgraph Graph["LangGraph ReAct"]
        S([START]) --> AN["agent_node\nLLM 规划下一步"]
        AN --> SC{有工具调用?}
        SC -->|是| TN["ToolNode 并行执行"]
        TN --> AN
        SC -->|否| E([END])
    end

    subgraph Tools["运维工具集"]
        T1["recall_similar_incidents\nMilvus 历史案例检索"]
        T2["count_errors_by_service\nLoki 错误统计"]
        T3["query_error_logs\nLoki 详情查询"]
        T4["get_host_metrics\nPrometheus 指标"]
        T5["inspect_all_hosts\n全量阈值巡检"]
    end

    TN --> T1 & T2 & T3 & T4 & T5
    E -->|"SSE 流式输出"| Client["浏览器"]
    E -->|"后台"| Save["摘要 → Milvus 向量存储"]
```

---

## 🚀 快速开始

### 环境要求

| 方式 | 依赖 |
|------|------|
| Docker 部署（推荐） | Docker 24+、Docker Compose v2 |
| 直接启动（开发） | Python 3.11+、Node.js 18+ |

**外部服务依赖：**
- Loki（日志查询）
- Prometheus + node_exporter（主机指标）
- AI Provider（Claude / Qwen3 / DeepSeek 等，二选一）
- SkyWalking OAP（APM 链路追踪，**可选**）

---

### 1. 克隆项目

```bash
git clone https://github.com/tyloryang/AI-logging-analyse.git
cd AI-logging-analyse
```

### 2. 配置环境变量

```bash
cd backend
cp .env.example .env
```

编辑 `.env`，填写必填项：

```env
# ── 必填 ──────────────────────────────────────────────────
LOKI_URL=http://your-loki-host:3100
PROMETHEUS_URL=http://your-prometheus-host:9090

# ── AI Provider（二选一）─────────────────────────────────
# 选项 A：Anthropic Claude（推荐，推理最强）
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
AI_MODEL=claude-opus-4-6

# 选项 B：本地 / 第三方 OpenAI 兼容接口
AI_PROVIDER=openai
AI_BASE_URL=http://192.168.x.x:8000/v1   # 末尾必须带 /v1
AI_API_KEY=                               # 本地可留空
AI_MODEL=Qwen3-32B

# ── 初始管理员 ────────────────────────────────────────────
ADMIN_USERNAME=admin
ADMIN_PASSWORD=Admin@123456

# ── Redis（Docker 部署已内置）────────────────────────────
REDIS_URL=redis://redis:6379/0

# ── SkyWalking OAP（可选）────────────────────────────────
SKYWALKING_OAP_URL=http://your-oap-host:12800
```

> 完整配置项见 [`backend/.env.example`](backend/.env.example)

### 3. 启动

#### 方式一：Docker Compose（推荐）

```bash
# 默认 SQLite
docker compose up -d --build

# 使用 MySQL 8
docker compose --profile mysql up -d --build

# 使用 PostgreSQL 16
docker compose --profile postgres up -d --build
```

访问 `http://localhost`，用 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 登录。

#### 方式二：直接启动（开发/测试）

```bash
chmod +x start.sh && ./start.sh
```

或分别启动：

```bash
# 后端（:8000）
cd backend && pip install -r requirements.txt && python3 main.py

# 前端（:5173，新开终端）
cd frontend && npm install && npm run dev
```

访问 `http://localhost:5173`

---

## ⚙️ 配置说明

### AI Provider

| Provider | 配置 | 推荐场景 |
|----------|------|----------|
| Anthropic Claude | `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` | 云端，推理最强 |
| Qwen3 / vLLM | `AI_PROVIDER=openai` + `AI_BASE_URL` | 本地私有化，数据不出内网 |
| DeepSeek | `AI_PROVIDER=openai` + DeepSeek API URL | 低成本云端 |
| Ollama | `AI_PROVIDER=openai` + `http://host:11434/v1` | 本地一键部署 |

> 任何支持 OpenAI Chat Completions 格式的服务均可接入。
>
> **vLLM 工具调用（Qwen3 等）需加启动参数：**
> ```bash
> --enable-auto-tool-choice --tool-call-parser hermes
> ```

### SkyWalking APM

SkyWalking OAP 提供两个端口：

| 端口 | 用途 |
|------|------|
| `11800` | gRPC（Agent 数据上报） |
| `12800` | HTTP GraphQL（**查询接口，本项目使用**） |

```env
SKYWALKING_OAP_URL=http://your-oap-host:12800
```

配置后访问 `/api/sw/test` 可测试连通性并获取详细诊断信息。

### 数据库

| 数据库 | DATABASE_URL |
|--------|-------------|
| SQLite（默认） | `sqlite+aiosqlite:///./data/aiops.db` |
| MySQL 8 | `mysql+aiomysql://user:pass@host:3306/aiops` |
| PostgreSQL 16 | `postgresql+asyncpg://user:pass@host:5432/aiops` |

### 定时推送

```env
SCHEDULE_CRON=0 9 * * *           # 每天 09:00
SCHEDULE_CHANNELS=feishu           # feishu / dingtalk / feishu,dingtalk

FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
FEISHU_KEYWORD=运维
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
DINGTALK_KEYWORD=运维
```

| cron 表达式 | 含义 |
|-------------|------|
| `0 9 * * *` | 每天 09:00 |
| `0 18 * * *` | 每天 18:00 |
| `30 8 * * 1-5` | 工作日 08:30 |
| `0 9,18 * * *` | 每天两次（09:00 和 18:00） |

---

## 📖 功能使用指南

### APM 链路追踪

APM 模块接入 SkyWalking，实现完整的分布式链路追踪能力：

1. **时间范围选择**：顶部快捷预设（5m / 15m / 1h / 3h / 6h / 24h / 3d / 7d / 30d）或自定义时间区间
2. **左侧服务列表**：自动发现所有已接入 SkyWalking Agent 的服务
3. **链路追踪 Tab**：
   - 按服务 / TraceId / 仅错误 过滤追踪列表
   - 点击任意追踪条目，展开**瀑布图**查看完整调用链
   - 瀑布图展示每个 Span 的服务名、接口、耗时（色块宽度 = 相对耗时比例）
   - 点击 Span 展开详情：tags（url/method/db.statement 等）+ 日志事件
4. **服务拓扑 Tab**：可视化服务间调用关系，点击节点过滤到对应服务
5. **性能指标 Tab**：平均响应时间、吞吐量（CPM）、错误率趋势图 + **接口耗时 TopN 排行表**

### 日志分析

1. 从左侧选择服务，设置时间范围、级别、关键字过滤
2. 点击 **AI 分析** → 流式输出根因总结和处置建议
3. 切换 **模板聚类** Tab → Drain3 自动归纳日志模式，按出现频次排列
4. 在模板聚类 Tab 点击 **AI 分析** → 基于聚类结果给出更精准的异常判断

### MySQL 慢日志分析

1. 进入「慢日志分析」，配置 SSH 凭证（凭证库 / CMDB 自动 / 手动输入）
2. 输入主机 IP，可批量添加多台
3. 设置时间段（今天 / 昨天 / 近 7 天 / 近 30 天 / 不限），点击「**获取并解析**」
4. 结果按主机分 Tab：**慢查询列表**（按耗时排序）/ **SQL 聚合**（Drain3 模板归组）/ **AI 分析建议**

### 运维日报 + 定时推送

- **手动生成**：进入「分析报告」→「立即生成日报」，AI 流式输出健康评分 + Top 问题
- **手动推送**：报告生成后点「飞书推送」或「钉钉推送」
- **定时自动**：配置 `SCHEDULE_CRON` + `SCHEDULE_CHANNELS` 后全自动，无需手动操作

### 主机巡检

1. 进入「CMDB 巡检」→「巡检报告」标签
2. 点击「**全量巡检**」→ 从 Prometheus 拉取最新指标 + 阈值判断
3. 点击「**AI 分析**」→ AI 逐台列出异常主机的 IP 和具体问题
4. 点击「**下载 Excel**」→ 三页式报告（巡检概况 / 全部主机明细 / 异常项明细）

### AI 智能体

基于 LangGraph ReAct，三种模式开箱即用：

| 模式 | 功能 |
|------|------|
| **根因分析** | 自动查错误日志、统计错误分布、拉取主机指标，输出结构化根因报告 |
| **自主巡检** | 自动遍历所有服务和主机，发现异常并给出优先级建议 |
| **智能对话** | 自由提问，Agent 按需调用工具（查日志 / 查指标 / 执行巡检） |

### 用户权限管理

**注册流程**：用户注册 → 状态 `pending` → 管理员审批激活

**权限模块**：`dashboard` · `log` · `metrics` · `alert` · `report` · `cmdb` · `inspect` · `ssh` · `slowlog` · `agent` · `skywalking` · `admin`

每个模块可独立设置 `none`（隐藏）/ `view`（只读）/ `operate`（可操作）。

---

## 📡 API 接口

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 用户注册（status=pending，等待审批） |
| POST | `/api/auth/login` | 登录（Set-Cookie: session_id） |
| POST | `/api/auth/logout` | 登出 |
| GET  | `/api/auth/me` | 当前用户信息 + 权限列表 |
| PUT  | `/api/auth/password` | 修改密码 |

### 日志

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/services` | 服务列表及错误数 |
| GET | `/api/logs` | 查询日志（服务/级别/关键字/时间范围） |
| GET | `/api/logs/templates` | Drain3 模板聚类 |
| GET | `/api/metrics/errors` | 各服务错误数统计 |
| GET | `/api/analyze/stream` | **流式** AI 日志分析（SSE） |
| GET | `/api/analyze/templates/stream` | **流式** AI 模板聚类分析（SSE） |

### APM（SkyWalking）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sw/services` | 服务列表（支持自定义时间范围） |
| GET | `/api/sw/instances` | 服务实例列表 |
| GET | `/api/sw/endpoints` | 端点搜索 |
| GET | `/api/sw/traces` | 追踪列表（支持服务/TraceId/错误过滤/分页） |
| GET | `/api/sw/traces/{traceId}` | 追踪详情（完整 Span 树） |
| GET | `/api/sw/topology` | 服务拓扑图（全局或单服务） |
| GET | `/api/sw/metrics` | 服务性能指标（响应时间/吞吐量/错误率） |
| GET | `/api/sw/endpoint-topn` | 接口耗时 TopN 排行 |
| GET | `/api/sw/test` | OAP 连通性诊断 |

### 报告

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/report/generate` | **流式** 生成运维日报（SSE） |
| GET  | `/api/report/list` | 历史报告列表 |
| GET  | `/api/report/{id}` | 报告详情 |
| POST | `/api/report/{id}/notify` | 推送飞书 / 钉钉 |
| GET  | `/api/report/inspect/generate` | **流式** 生成主机巡检日报（SSE） |
| GET  | `/api/report/inspect/{id}/excel` | 下载巡检 Excel |

### 主机

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/hosts` | 主机列表（Prometheus 发现 + CMDB + 实时指标） |
| PUT  | `/api/hosts/{instance}` | 更新 CMDB 信息 |
| GET  | `/api/hosts/inspect` | **流式** 全量巡检（SSE） |
| POST | `/api/hosts/inspect/ai` | **流式** AI 巡检分析（SSE） |
| POST | `/api/hosts/inspect/excel` | 导出巡检 Excel |

### SSH

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST/PUT/DELETE | `/api/ssh/credentials` | 凭证管理（AES 加密存储） |
| WS  | `/api/ws/ssh` | WebSocket SSH 终端 |

### 慢日志

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/slowlog/hosts` | 有 SSH 凭证的主机列表 |
| POST | `/api/slowlog/fetch` | SSH 读取并解析慢日志（Drain3 聚合） |
| GET  | `/api/slowlog/analyze/stream` | **流式** AI 优化建议（SSE） |

### AI 智能体

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/agent/rca` | **流式** 根因分析（SSE） |
| POST | `/api/agent/inspect` | **流式** 自主巡检（SSE） |
| POST | `/api/agent/chat` | **流式** 智能对话（SSE） |

SSE 事件类型：

| 事件 | 说明 |
|------|------|
| `token` | AI 输出文本片段（流式拼接） |
| `tool_start` | 工具调用开始（含工具名 + 入参） |
| `tool_end` | 工具执行结果（截取前 800 字符） |
| `done` | 流结束标志 |

---

## 📁 项目结构

```
AI-logging-analyse/
├── backend/
│   ├── main.py                  # FastAPI 应用入口 + lifespan
│   ├── state.py                 # 共享单例和配置常量
│   ├── scheduler.py             # APScheduler 定时任务
│   ├── routers/
│   │   ├── logs.py              # 日志分析 + AI 流式分析
│   │   ├── reports.py           # 运维日报 + 巡检日报 + 推送
│   │   ├── hosts.py             # CMDB + 巡检
│   │   ├── ssh.py               # SSH 终端（WebSocket）
│   │   ├── slowlog.py           # MySQL 慢日志分析
│   │   ├── skywalking.py        # APM 链路追踪
│   │   ├── agent.py             # LangGraph AI 智能体
│   │   └── health.py            # 健康检查
│   ├── agent/
│   │   ├── tools.py             # LangChain 运维工具集
│   │   ├── graph.py             # LangGraph ReAct 图
│   │   └── llm_responses.py     # OpenAI Responses API 适配
│   ├── auth/                    # 认证/权限/审计
│   ├── skywalking_client.py     # SkyWalking OAP GraphQL 客户端
│   ├── loki_client.py           # Loki HTTP API 客户端
│   ├── prom_client.py           # Prometheus HTTP API 客户端
│   ├── ai_analyzer.py           # AI 分析器（多 Provider 抽象）
│   ├── ssh_bridge.py            # WebSocket ↔ asyncssh 桥接
│   ├── slow_log_parser.py       # MySQL 慢日志解析器
│   ├── sql_cluster.py           # Drain3 SQL 模板聚合
│   ├── sw_diag.py               # SkyWalking OAP 连通性诊断脚本
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── views/
│       │   ├── Dashboard.vue        # 仪表盘
│       │   ├── LogAnalysis.vue      # 日志分析
│       │   ├── SkyWalkingView.vue   # APM 链路追踪
│       │   ├── AnalysisReport.vue   # 运维日报
│       │   ├── HostCMDB.vue         # CMDB 巡检
│       │   ├── SSHTerminal.vue      # SSH 终端
│       │   ├── SlowLogView.vue      # MySQL 慢日志
│       │   ├── AIAgent.vue          # AI 智能体
│       │   └── AdminUsers.vue       # 用户管理
│       ├── api/index.js             # HTTP + SSE 封装
│       └── components/Sidebar.vue   # 侧边栏（权限动态菜单）
├── docker-compose.yml           # 一键部署（Redis + 可选 MySQL/PostgreSQL）
├── start.sh                     # Linux 直接启动脚本
└── README.md
```

---

## 🔧 故障排查

### 后端无法启动

```bash
# 检查后端健康状态
curl http://localhost:8000/api/health

# 查看 Docker 日志
docker compose logs backend
```

### Redis 连接失败

```
aioredis.exceptions.ConnectionError
```

- Docker 部署：Redis 已内置，检查 `docker compose ps redis`
- 直接启动：确保本地 Redis 运行，设置 `REDIS_URL=redis://localhost:6379/0`

### 登录 401

首次启动前未配置密码，查看随机生成的密码：

```bash
docker compose logs backend | grep "初始管理员"
```

### AI 分析无响应

1. 访问 `/api/health` 查看 `ai_ready` 字段
2. 确认 `AI_BASE_URL` 末尾带 `/v1`（如 `http://host:8000/v1`）
3. 本地模型确认服务已启动：`curl http://your-ai-host:8000/v1/models`
4. vLLM 启动参数需包含 `--enable-auto-tool-choice --tool-call-parser hermes`

### SkyWalking 链路追踪无数据

1. 访问 `/api/sw/test` 查看详细诊断信息（OAP 地址、连接状态、服务数量）
2. 确认 OAP HTTP 端口为 `12800`（非 gRPC 的 `11800`）
3. 适当扩大时间范围（新接入的 Agent 数据可能在 7 天前）
4. 确认 SkyWalking Agent 已部署到目标服务并指向正确的 OAP 地址

### Loki / Prometheus 无数据

```bash
# 测试 Loki
curl $LOKI_URL/loki/api/v1/labels

# 测试 Prometheus
curl $PROMETHEUS_URL/api/v1/targets
```

Prometheus 主机发现需要被监控主机部署 `node_exporter`。

---

## 📄 License

[MIT](LICENSE)

---

<p align="center">
  如果这个项目对你有帮助，欢迎 ⭐ Star 支持一下！<br/>
  有问题或建议请提 <a href="https://github.com/tyloryang/AI-logging-analyse/issues">Issue</a>
</p>
