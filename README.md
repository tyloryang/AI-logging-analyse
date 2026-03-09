# 🤖 AI-Logging-Analyse

> 基于 **Loki + Claude / 本地大模型** 的智能运维日志分析平台
>
> An intelligent DevOps log analysis platform powered by Loki + AI (Claude / OpenAI-compatible local models)

---

## ✨ 功能特性

| 模块 | 功能 |
|------|------|
| 📊 **仪表盘** | 系统总览、错误 Top10 服务、服务健康状态矩阵 |
| 📋 **日志分析** | 按服务过滤、实时查询 Loki、🤖 AI 流式分析日志 |
| 📈 **指标监控** | 各服务错误数趋势条形图、汇总统计 |
| 🔔 **告警历史** | 基于错误日志自动生成告警，按严重程度分级 |
| 📝 **分析报告** | 一键生成运维日报，AI 流式输出分析内容，历史报告持久化 |

---

## 🖥️ 界面预览

### 仪表盘

```
┌──────────────────────────────────────────────────────────────────────┐
│ 🤖 AI Ops                                                            │
│ ┌──────────┐ ┌──────────────────────────────────────────────────┐   │
│ │📊 仪表盘 │ │  仪表盘                  系统总览 · 最近 24 小时 │   │
│ │📋 日志分析│ │                                                  │   │
│ │📈 指标监控│ │  ┌──────────┐ ┌──────────┐ ┌──────┐ ┌────────┐ │   │
│ │🔔 告警历史│ │  │📋        │ │❌        │ │🖥️    │ │🏥      │ │   │
│ │📝 分析报告│ │  │ 17,888   │ │  2,236   │ │  14  │ │   3    │ │   │
│ │          │ │  │总日志条数 │ │ 错误总数 │ │涉及服│ │健康服务│ │   │
│ │          │ └──────────────────────────────────────────────────┘   │
│ │          │ ┌──────────────────────────────────────────────────┐   │
│ │● Loki已连│ │ 🔥 错误 Top 10 服务                              │   │
│ │● Qwen3已 │ │  1  cloud-monitor  ████████████████░░░░  1152    │   │
│ └──────────┘ │  2  cloud-gateway  █████████████░░░░░░░   957    │   │
│              │  3  cloud-cvm-api  ██░░░░░░░░░░░░░░░░░░    49    │   │
│              └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### 日志分析页

```
┌──────────────────────────────────────────────────────────────────────┐
│ 服务列表  最近24小时▼ │  管道日志总条数  [500]   [🔄实时查询] [🤖AI分析]│
│ ─────────────────── │ ─────────────────────────────────────────────│
│ ● 全部服务     2236  │ ┌─ 🤖 AI 分析结果 ────────────────── [关闭] ┐ │
│ ● cloud-monitor 1152│ │ **错误模式识别**: cloud-monitor 存在大量      │ │
│ ● cloud-gateway  957│ │ 连接超时异常，高峰期达 1152 条/天...          │ │
│ ● cloud-cvm-api   49│ │ **根因分析**: 推测为下游依赖响应慢...▌        │ │
│ ● sslcert-rpc     43│ └────────────────────────────────────────────┘ │
│ ● xyz-cj-tx1      12│                                                │
│ ● xyz-cj-yk-2      6│ 2026-03-09 06:17:23  cloud-monitor             │
│ ● dataops-dl       6│   ERROR Connection timeout to downstream...    │
│                     │ 2026-03-09 06:17:21  cloud-gateway             │
│ ● Loki 已连接       │   ERROR Failed to forward request: timeout     │
│ ● Qwen3-32B        │ 2026-03-09 06:17:20  cloud-monitor             │
│                     │   FATAL Panic: nil pointer dereference ...     │
└──────────────────────────────────────────────────────────────────────┘
```

### 运维日报页

```
┌──────────────────────────────────────────────────────────────────────┐
│ 分析报告                                                              │
│ ┌────────────────┐  ┌────────────────────────────────────────────┐  │
│ │ 每日日报    ▼  │  │  运维日报 2026-03-09        ┌─────────┐   │  │
│ │ [▶ 立即生成日报]│  │  2026/3/9 06:25:48          │   55    │   │  │
│ │                │  │                             │ /100    │   │  │
│ │ ● 运维日报     │  │  📋 2236   🔧 14   🖥️ 27/0  └─────────┘   │  │
│ │   2026-03-09   │  │     条        个      节点    整体健康评分 │  │
│ │   55/100  [59] │  │                                            │  │
│ │                │  │  🔥 错误 Top 10 服务                       │  │
│ │                │  │   1  cloud-monitor  ██████████  1152       │  │
│ │                │  │   2  cloud-gateway  ████████     957       │  │
│ │                │  │                                            │  │
│ │                │  │  🤖 AI 分析                                │  │
│ │                │  │  当前系统整体处于亚健康状态，cloud-monitor  │  │
│ │                │  │  服务异常为主要风险源...                    │  │
│ │                │  │  ⚠️ cloud-monitor 连接超时率超过阈值        │  │
│ │                │  │  ✅ 建议扩容 cloud-monitor 实例数量         │  │
│ └────────────────┘  └────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────┐
│                   前端 Vue 3 + Vite                  │
│  Dashboard │ LogAnalysis │ Metrics │ Alerts │ Report │
│                  Axios + SSE 流式                    │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP / SSE
┌──────────────────────▼──────────────────────────────┐
│              后端 FastAPI (Python 3.11+)             │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │ LokiClient │  │  AIAnalyzer  │  │   Reports   │  │
│  │  HTTP API  │  │  Provider层  │  │  JSON存储   │  │
│  └─────┬──────┘  └──────┬───────┘  └─────────────┘  │
└────────┼────────────────┼────────────────────────────┘
         │                │
┌────────▼──────┐  ┌──────▼──────────────────────┐
│  Loki Server  │  │      AI Provider             │
│  (日志存储)   │  │  Anthropic Claude            │
│               │  │  OpenAI 兼容接口             │
└───────────────┘  │  (Qwen3/vLLM/Ollama 等)      │
                   └──────────────────────────────┘
```

---

## 🚀 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- 可访问的 Loki 服务
- AI Provider 之一（见下方配置）

### 1. 克隆项目

```bash
git clone git@github.com:tyloryang/AI-logging-analyse.git
cd AI-logging-analyse
```

### 2. 后端配置

```bash
cd backend
cp .env.example .env
```

编辑 `.env`，选择 AI Provider：

```env
# Loki 地址
LOKI_URL=http://your-loki-host:3100

# ── 选项 A：Anthropic Claude ──────────────
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
AI_MODEL=claude-opus-4-6

# ── 选项 B：本地 / 第三方 OpenAI 兼容接口 ──
AI_PROVIDER=openai
AI_BASE_URL=http://192.168.x.x:8000/v1   # vLLM / Ollama / LM Studio
AI_API_KEY=                               # 本地模型可留空
AI_MODEL=Qwen3-32B
```

### 3. 启动后端

```bash
pip install -r requirements.txt
python main.py
# → http://localhost:8000
# → API 文档: http://localhost:8000/docs
```

### 4. 启动前端

```bash
cd ../frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## ⚙️ AI Provider 支持

| Provider | 配置方式 | 适用场景 |
|----------|---------|---------|
| **Anthropic Claude** | `AI_PROVIDER=anthropic` + API Key | 云端，推理能力强 |
| **Qwen3-32B (vLLM)** | `AI_PROVIDER=openai` + `AI_BASE_URL` | 本地部署，数据不出内网 |
| **Ollama** | `AI_PROVIDER=openai` + `http://host:11434/v1` | 本地一键部署 |
| **DeepSeek** | `AI_PROVIDER=openai` + DeepSeek API URL | 低成本云端 |
| **OpenRouter** | `AI_PROVIDER=openai` + OpenRouter URL | 多模型聚合 |

> 任何支持 OpenAI Chat Completions API 格式的服务均可接入。

---

## 📡 API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（Loki + AI 状态） |
| GET | `/api/services` | 服务列表及错误数 |
| GET | `/api/logs` | 查询日志（支持服务/时间/级别过滤） |
| GET | `/api/logs/errors` | 全量错误日志 |
| GET | `/api/metrics/errors` | 各服务错误数统计 |
| GET | `/api/analyze/stream` | **流式** AI 日志分析（SSE） |
| POST | `/api/report/generate` | **流式** 生成运维日报（SSE） |
| GET | `/api/report/list` | 历史报告列表 |
| GET | `/api/report/{id}` | 报告详情 |

---

## 📁 项目结构

```
AI-logging-analyse/
├── backend/
│   ├── main.py           # FastAPI 主应用
│   ├── loki_client.py    # Loki HTTP API v1 客户端
│   ├── ai_analyzer.py    # AI 分析器（Provider 抽象层）
│   ├── requirements.txt
│   └── .env.example      # 配置模板
├── frontend/
│   └── src/
│       ├── views/
│       │   ├── Dashboard.vue       # 仪表盘
│       │   ├── LogAnalysis.vue     # 日志分析 + AI 分析
│       │   ├── MetricsMonitor.vue  # 指标监控
│       │   ├── AlertHistory.vue    # 告警历史
│       │   └── AnalysisReport.vue  # 运维日报
│       ├── components/
│       │   └── Sidebar.vue         # 侧边导航
│       └── api/index.js            # HTTP + SSE 封装
├── start.sh              # 一键启动脚本
└── README.md
```

---

## 📄 License

MIT
