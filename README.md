<p align="center">
  <img src="screenshots/首页监控大盘.jpg" alt="AIOps 智能运维平台" width="100%" style="border-radius:12px"/>
</p>

<h1 align="center">SxDevOps · AIOps 智能运维平台</h1>

<p align="center">
  <b>让 AI 替你值夜班 — 告警感知 · 根因分析 · 自动巡检 · 一站式运维</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue?style=flat-square" />
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Vue-3.5-42b883?style=flat-square&logo=vue.js&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/LangGraph-ReAct-FF6B35?style=flat-square" />
  <img src="https://img.shields.io/badge/K8s-Ready-326CE5?style=flat-square&logo=kubernetes&logoColor=white" />
  <img src="https://img.shields.io/badge/Qwen3-32B-orange?style=flat-square" />
</p>

---

## 📖 项目简介

**SxDevOps AIOps** 是一套以 **AI 大模型为核心驱动**的企业级智能运维平台。整合 Loki、Prometheus、SkyWalking、AlertManager 等可观测性数据，通过 **LangGraph ReAct 智能体**实现：

- 🔍 **自动根因分析**：30 秒内从海量日志和指标中定位故障根因
- 🤖 **AI 智能助手**：自然语言交互，支持四层思考推理框架，工具执行全链路追踪可视化
- 📊 **K8s 可视化**：2D 粒子流动拓扑图、资源关系图、部署流程动画
- 🏠 **CMDB 资产管理**：SSH 凭证管理、批量同步、主机巡检
- 📅 **AI 运维日报**：每日自动生成健康评分报告，推送飞书/钉钉
- 🔔 **AlertManager 集成**：高可用 3 副本告警集群，Webhook 实时接入

支持 **Docker Compose 一键启动** 和 **Kubernetes 生产级部署**，AI 模型兼容 Anthropic Claude、Qwen3-32B、DeepSeek、GPT-5 等主流大模型。

---

## ✨ 核心功能

### 🧠 AI 智能助手

- **四层思考框架**（参考 Hermes Memory v4）：
  - `L1 感知层` — 识别任务类型和关键实体
  - `L2 检索层` — 多源并发：日志 + 指标 + K8s + 告警 + 历史记忆
  - `L3 推理层` — 跨维度关联：时间 × 实体 × 因果链路
  - `L4 沉淀层` — 每次输出提炼可复用运维规律
- **Trace 追踪面板**（参考 OpenCowork）：右侧实时显示工具执行步骤、耗时、输入输出
- **9 种模型预设**：Qwen3-32B/8B、DeepSeek-R1/V3、Claude Opus/Sonnet、GPT-5 等一键切换
- **自动模型识别**：自动检测 Qwen3/QwQ 系列，强制 `chat` 模式 + `enable_thinking: false`，防止 400 错误
- **多种对话模式**：RCA 根因分析 / 全面巡检 / 自由对话 / 引导式问答
- **MCP 工具集成**：支持 Prometheus MCP、K8s MCP、Redis MCP 等外部工具扩展

### ☸️ K8s 可视化（参考 k8study.cn 风格）

| 视图 | 说明 |
|------|------|
| **系统架构图** | 完整服务拓扑，hover 高亮调用链路，粒子流动显示流量方向 |
| **K8s 部署流程** | kubectl → APIServer → etcd → 调度器 → Kubelet → Pod 全链路动画 |
| **K8s 服务图** | Service → Deployment → Pod → Node 四层实时拓扑，动态画布宽度防重叠 |
| **K8s 资源关系图** | 22 个核心资源节点，23 条关系连线，hover 高亮依赖链路 |
- 所有视图支持**滚轮缩放 + 拖拽平移**，深色主题适配

### 📊 可观测性

- **日志中心**：Loki 游标分页（突破 4MB 限制）、Drain3 自动聚类降噪、AI 流式根因分析、关键字链路追踪
- **指标监控**：Prometheus 多维指标、主机自动发现、CPU/内存/磁盘/负载可视化
- **链路追踪**：SkyWalking APM 瀑布图、服务拓扑、P99/P95 性能分析
- **告警中心**：AlertManager 高可用 3 副本集群（NodePort :30093），告警去重聚合，飞书/钉钉实时推送
- **Grafana 内嵌**：API Key 自动看板发现，支持多看板

### 🏠 CMDB 主机管理

- **资产管理**：JumpServer 标准字段，Excel/CSV 导入导出
- **批量凭证应用**：一键为多台主机应用 SSH 凭证，支持按分组批量设置
- **SSH 同步**：一键同步全量主机系统信息（CPU 核数、内存、OS、版本）
- **上次同步时间**：颜色标识数据新鲜度（绿=24h内、黄=24-72h、红=超3天）
- **进程列表**：Top10 进程查看，服务类型识别（Java/Nginx/Redis/MySQL）
- **Java 诊断**：Arthas 集成 + async-profiler 火焰图，自动探测 Java 路径

### 🖥️ 容器管理

- **K8s 集群管理**：多集群支持，Deployment/StatefulSet/DaemonSet/Job 全类型
- **Pod 日志**：实时日志流，UTC 时间自动转换为东八区（`2026-05-10T05:37Z` → `2026-05-10 13:37 +08`）
- **SSH Web 终端**：浏览器直连 SSH，AES 加密凭证库，CMDB 一键连接
- **容器内 SSH**：可直接管理容器内部进程

### 📋 运维管理

| 模块 | 说明 |
|------|------|
| **AI 运维日报** | 健康评分 + Top 问题分析，定时生成并推送 |
| **巡检报告** | 全量主机巡检，阈值判断，AI 逐台分析，Excel 导出 |
| **慢日志分析** | SSH 读取 MySQL 慢日志，Drain3 SQL 聚合，AI 优化建议 |
| **任务中心** | SSH 批量执行，无 Ansible 依赖 |
| **Jenkins CI/CD** | 多实例支持，Views 分类管理 |
| **飞书 Bot** | 群机器人交互问答，@机器人触发 AI 分析 |
| **工单系统** | 发布工单、SQL 审计工单、事件处理、审批流 |

### 🔐 权限与安全

- **RBAC 权限**：12+ 模块细粒度权限控制
- **AI 数据范围控制**：普通用户查询的主机/K8s 资源自动按分组裁剪，AI 不能越权查询
- **用户管理**：注册审批流、分组分配、SSH 凭证 AES 加密
- **操作审计**：登录失败锁定，会话 TTL 管理

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Vue 3.5 前端                              │
│  Pinia · Vue Router · xterm.js · SVG 拓扑动画 · 暗色主题     │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP / WebSocket / SSE
┌─────────────────────▼───────────────────────────────────────┐
│                  FastAPI 后端 (Python 3.11)                  │
│                                                             │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  LangGraph ReAct │  │  APScheduler │  │  Auth & RBAC │  │
│  │  智能体（4模式）  │  │  定时任务     │  │  权限管理    │  │
│  └────────┬─────────┘  └──────────────┘  └──────────────┘  │
│           │                                                  │
│  ┌────────▼─────────────────────────────────────────────┐   │
│  │                  工具层 / 数据客户端                  │   │
│  │  LokiClient · PromClient · SkyWalkingClient          │   │
│  │  SSHBridge · Drain3 · ReportBuilder · Notifier       │   │
│  │  MilvusMemory · Firecrawl · MCP SDK                  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
      │          │          │          │           │
 ┌────▼───┐ ┌───▼──────┐ ┌─▼────┐ ┌──▼──────┐ ┌──▼──────────┐
 │  Loki  │ │Prometheus│ │  SW  │ │  Redis  │ │AlertManager │
 │  日志  │ │  指标    │ │ APM  │ │  会话   │ │  告警中心   │
 └────────┘ └──────────┘ └──────┘ └─────────┘ └─────────────┘
      │
 ┌────▼──────────────────────────────────────────────────┐
 │  AI Provider（智能选择）                              │
 │  Anthropic Claude · Qwen3-32B · DeepSeek · GPT-5     │
 │  自动识别模型类型，防止参数配错                        │
 └───────────────────────────────────────────────────────┘
```

### 🤖 AI Agent 工具集（22+）

LangGraph ReAct 智能体内置工具，按**四层思考框架**分类：

| 层级 | 工具 |
|------|------|
| **L2 检索层** | 查询错误日志、最近日志、错误统计、主机指标、K8s Pods/Nodes/Services、历史记忆召回、历史日报搜索 |
| **L3 推理/执行层** | SSH 命令执行、全量主机巡检、MCP 工具调用 |
| **L4 沉淀层** | 运维日报生成、PDF 报告导出 |

---

## 🚀 快速开始

### 环境要求

- Docker 20.10+ & Docker Compose v2
- 或 Python 3.11+ & Node.js 18+

### 1. 克隆仓库

```bash
git clone https://github.com/tyloryang/AI-logging-analyse.git
cd AI-logging-analyse
```

### 2. 配置环境变量

```bash
cp backend/.env.example backend/.env
```

**最小配置（必填）：**

```env
# 数据源
LOKI_URL=http://your-loki:3100
PROMETHEUS_URL=http://your-prometheus:9090

# AI 模型（选其一）

# ── 选项 A：Qwen3-32B（推荐国内用户）────────
AI_PROVIDER=openai
AI_BASE_URL=https://api.vveai.com/v1    # 或其他 OpenAI 兼容接口
AI_API_KEY=sk-xxxxxxxx
AI_MODEL=qwen3-32b
# 注意：Qwen3 系列无需设置 AI_WIRE_API，后端自动处理

# ── 选项 B：Anthropic Claude ────────────────
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
AI_MODEL=claude-sonnet-4-6

# ── 选项 C：本地 vLLM / Ollama ──────────────
AI_PROVIDER=openai
AI_BASE_URL=http://192.168.x.x:8000/v1
AI_API_KEY=EMPTY
AI_MODEL=your-local-model
```

### 3. Docker Compose 启动

```bash
docker-compose up -d
```

| 服务 | 地址 |
|------|------|
| 前端 | http://localhost |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

默认账号：`admin` / `Admin@123456`

### 4. 本地开发

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 前端（新终端）
cd frontend
npm install
npm run dev   # http://localhost:5173
```

---

## ☸️ Kubernetes 部署

```bash
cd k8s

# 1. 编辑配置
vim configmap.yaml   # 数据源地址
vim secret.yaml      # API Key 和密码

# 2. 一键部署
bash deploy.sh
```

| 服务 | NodePort |
|------|----------|
| 前端 | :30090 |
| 后端 | :30800 |
| 飞书 Bot | :30801 |
| Grafana | :30300 |
| AlertManager | :30093 |

---

## 📁 目录结构

```
AI-logging-analyse/
├── backend/
│   ├── main.py                  # FastAPI 入口
│   ├── routers/                 # 25+ 业务 Router
│   │   ├── agent.py             # AI 智能助手接口
│   │   ├── logs.py              # 日志查询（游标分页）
│   │   ├── hosts.py             # CMDB + Java 诊断
│   │   ├── kubernetes.py        # K8s 多集群管理
│   │   ├── alerts.py            # AlertManager Webhook
│   │   ├── reports.py           # AI 日报 + PDF 导出
│   │   ├── ssh.py               # WebSocket SSH 终端
│   │   ├── slowlog.py           # MySQL 慢日志分析
│   │   ├── elasticsearch.py     # ES 集群管理
│   │   ├── jenkins.py           # CI/CD 多实例
│   │   └── ...
│   ├── agent/
│   │   ├── graph.py             # LangGraph ReAct（四层思考）
│   │   ├── tools.py             # 22+ 运维工具
│   │   └── milvus_memory.py     # 向量检索记忆
│   ├── ai_analyzer.py           # AI Provider 抽象层
│   ├── runtime_env.py           # 运行时配置热加载
│   └── loki_client.py           # Loki 游标分页客户端
├── frontend/
│   └── src/views/               # 40+ 页面视图
│       ├── K8sTopologyView.vue  # K8s 拓扑 + 架构图
│       ├── K8sResourceRelationView.vue  # 资源关系图
│       ├── AIAgent.vue          # AI 助手（Trace 面板）
│       ├── HostCMDB.vue         # CMDB 资产管理
│       ├── ContainerView.vue    # 容器 + SSH 终端
│       └── ...
├── k8s/                         # K8s 部署清单
├── docker-compose.yml
├── backend/.env.example
└── README.md
```

---

## ⚙️ 环境变量参考

| 变量 | 默认 | 说明 |
|------|------|------|
| `LOKI_URL` | — | Loki 地址（必填）|
| `PROMETHEUS_URL` | — | Prometheus 地址（必填）|
| `AI_PROVIDER` | `anthropic` | `anthropic` 或 `openai` |
| `AI_BASE_URL` | — | OpenAI 兼容接口地址 |
| `AI_API_KEY` | — | API Key |
| `AI_MODEL` | `claude-opus-4-6` | 模型名（Qwen3 系列自动适配）|
| `AI_WIRE_API` | 自动 | `chat`/`responses`（留空自动识别）|
| `AI_ENABLE_THINKING` | `0` | 扩展思考（QwQ/R1 等推理模型填 1）|
| `SKYWALKING_OAP_URL` | — | SkyWalking OAP |
| `GRAFANA_URL` | — | Grafana 地址 |
| `FEISHU_WEBHOOK` | — | 飞书机器人 Webhook |
| `DINGTALK_WEBHOOK` | — | 钉钉机器人 Webhook |
| `SCHEDULE_CRON` | `0 9 * * *` | 日报定时（cron 表达式）|
| `REDIS_URL` | `redis://redis:6379/0` | Redis 会话 |
| `MILVUS_HOST` | — | Milvus 向量库（可选，历史案例召回）|
| `ADMIN_USERNAME` | `admin` | 初始管理员 |
| `ADMIN_PASSWORD` | `Admin@123456` | 初始密码 |

---

## 🛠️ 主要依赖

**后端**

| 依赖 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.115 | Web 框架 |
| LangGraph | ≥0.2.35 | ReAct 智能体 |
| Anthropic SDK | ≥0.40 | Claude API |
| OpenAI SDK | ≥1.50 | OpenAI 兼容 |
| SQLAlchemy | ≥2.0 | 异步 ORM |
| APScheduler | ≥3.10 | 定时任务 |
| Drain3 | ≥0.9.11 | 日志/SQL 聚类 |
| asyncssh | ≥2.14 | SSH 桥接 |
| kubernetes | ≥29.0 | K8s 客户端 |

**前端**

| 依赖 | 版本 | 用途 |
|------|------|------|
| Vue | 3.5.13 | 前端框架 |
| Vue Router | 4.4 | 路由 |
| Pinia | 2.2 | 状态管理 |
| xterm.js | 5.3 | Web SSH 终端 |
| Axios | 1.7 | HTTP 客户端 |

---

## 📄 License

[MIT](LICENSE) © 2025 tyloryang
