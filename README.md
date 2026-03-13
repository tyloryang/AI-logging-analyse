# AI-Logging-Analyse

> 基于 **Loki + Prometheus + Claude / 本地大模型** 的智能运维日志分析平台
>
> An intelligent DevOps platform powered by Loki + Prometheus + AI (Claude / OpenAI-compatible local models)

---

## 功能特性

| 模块 | 功能 |
|------|------|
| **仪表盘** | 系统总览、错误 Top10 服务、服务健康状态矩阵 |
| **日志分析** | 按服务/级别过滤、实时查询 Loki、AI 流式分析、Drain3 模板聚类 |
| **指标监控** | 各服务错误数趋势条形图、汇总统计 |
| **告警历史** | 基于错误日志自动生成告警，按严重程度分级 |
| **分析报告** | 一键生成运维日报，AI 流式输出，历史报告持久化，飞书/钉钉推送 |
| **定时推送** | APScheduler 按 cron 表达式自动生成并推送日报 |
| **主机 CMDB** | Prometheus 自动发现主机，采集 CPU/内存/磁盘/负载指标，可编辑责任人/环境/角色/备注 |
| **主机巡检** | 阈值巡检（CPU/内存/磁盘告警），AI 流式巡检分析，一键导出 Excel 报告 |
| **SSH 终端** | 浏览器内 Web Terminal，统一凭证库（AES 加密存储），一键连接主机 |

---

## 界面预览

### 仪表盘

```
┌──────────────────────────────────────────────────────────────────────┐
│  AI Ops                                                              │
│ ┌──────────┐ ┌──────────────────────────────────────────────────┐   │
│ │ 仪表盘   │ │  仪表盘                  系统总览 · 最近 24 小时 │   │
│ │ 日志分析 │ │                                                  │   │
│ │ 指标监控 │ │  ┌──────────┐ ┌──────────┐ ┌──────┐ ┌────────┐ │   │
│ │ 告警历史 │ │  │ 17,888   │ │  2,236   │ │  14  │ │   3    │ │   │
│ │ 分析报告 │ │  │总日志条数 │ │ 错误总数 │ │涉及服│ │健康服务│ │   │
│ │ 主机CMDB │ └──────────────────────────────────────────────────┘   │
│ │          │ ┌──────────────────────────────────────────────────┐   │
│ │● Loki已连│ │  错误 Top 10 服务                                │   │
│ │● Qwen3已 │ │  1  cloud-monitor  ████████████  1152            │   │
│ └──────────┘ │  2  cloud-gateway  ██████████     957            │   │
│              └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### 主机 CMDB + 巡检

```
┌──────────────────────────────────────────────────────────────────────┐
│  主机 CMDB                          [全量巡检] [AI分析] [下载Excel]  │
│ ┌────────────────────────────────────────────────────────────────┐   │
│ │ 主机名         IP           CPU   内存   磁盘   状态   操作    │   │
│ │ node-prod-01  192.168.1.10  23%   61%    45%    正常   SSH     │   │
│ │ node-prod-02  192.168.1.11  78%   85%    92%   ⚠警告   SSH     │   │
│ │ node-prod-03  192.168.1.12  91%   92%    67%   ✗严重   SSH     │   │
│ └────────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  AI 巡检分析（流式输出）                                             │
│  当前集群存在 2 台主机资源告警，node-prod-03 CPU 达 91%...▌          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 技术架构

```
┌──────────────────────────────────────────────────────────┐
│                   前端 Vue 3 + Vite                       │
│  Dashboard │ LogAnalysis │ Metrics │ Alerts │ Report      │
│  HostCMDB (主机列表 + 巡检 + SSH 终端)                    │
│                  Axios + SSE 流式                         │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP / SSE
┌────────────────────────▼─────────────────────────────────┐
│             后端 FastAPI (Python 3.11+)                   │
│  ┌────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ LokiClient │  │  AIAnalyzer  │  │  Reports / CMDB  │  │
│  │  HTTP API  │  │  Provider层  │  │  JSON 文件存储   │  │
│  └─────┬──────┘  └──────┬───────┘  └──────────────────┘  │
│  ┌─────▼──────┐  ┌──────▼───────┐  ┌──────────────────┐  │
│  │ PromClient │  │  asyncssh    │  │  APScheduler     │  │
│  │  HTTP API  │  │  SSH 终端    │  │  定时推送        │  │
│  └─────┬──────┘  └──────────────┘  └──────────────────┘  │
└────────┼─────────────────────────────────────────────────┘
         │
┌────────▼──────────┐  ┌─────────────────────────────────┐
│  Loki Server      │  │  Prometheus Server               │
│  日志存储         │  │  指标采集 (node_exporter)        │
└───────────────────┘  └─────────────────────────────────┘
         │                          │
         └──────────────────────────┘
                      │
              ┌───────▼──────────────────────────┐
              │         AI Provider               │
              │  Anthropic Claude                 │
              │  OpenAI 兼容接口                  │
              │  (Qwen3 / vLLM / Ollama / 等)    │
              └──────────────────────────────────┘
```

---

## 快速开始

### 环境要求

**直接启动**
- Python 3.11+
- Node.js 18+

**Docker 启动**
- Docker 24+ & Docker Compose v2

**外部依赖**
- 可访问的 Loki 服务
- 可访问的 Prometheus 服务（需部署 node_exporter）
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

编辑 `.env`：

```env
# Loki 地址
LOKI_URL=http://your-loki-host:3100

# Prometheus 地址（CMDB 主机发现）
PROMETHEUS_URL=http://your-prometheus-host:9090

# ── 选项 A：Anthropic Claude ──────────────
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
AI_MODEL=claude-opus-4-6

# ── 选项 B：本地 / 第三方 OpenAI 兼容接口 ──
AI_PROVIDER=openai
AI_BASE_URL=http://192.168.x.x:8000/v1   # vLLM / Ollama / LM Studio
AI_API_KEY=                               # 本地模型可留空
AI_MODEL=Qwen3-32B

# ── 通知推送（选填）──────────────────────
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
FEISHU_KEYWORD=运维
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
DINGTALK_KEYWORD=运维
APP_URL=http://192.168.1.100:5173

# ── 定时推送（选填）──────────────────────
SCHEDULE_CRON=0 9 * * *          # 每天 09:00
SCHEDULE_CHANNELS=feishu,dingtalk
```

### 3. 启动服务

#### 方式一：Linux 直接启动（开发 / 测试）

```bash
# 一键启动前后端
chmod +x start.sh
./start.sh
```

或分别启动：

```bash
# 后端（:8000）
cd backend
pip install -r requirements.txt
python3 main.py

# 前端（:5173，新开终端）
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173

#### 方式二：Docker Compose（推荐生产）

```bash
# 构建并启动（前端 :80，后端 :8000）
docker compose up -d --build

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

访问 http://localhost

---

## 通知推送

在 `.env` 中填写 Webhook 地址，在报告页点击按钮一键推送到飞书或钉钉。

| 平台 | 配置项 |
|------|--------|
| 飞书 | `FEISHU_WEBHOOK` + `FEISHU_KEYWORD` |
| 钉钉 | `DINGTALK_WEBHOOK` + `DINGTALK_KEYWORD` |

---

## 定时推送

后端内置 APScheduler，启动后自动按 cron 表达式生成日报并推送，无需外部 cron 服务。

| cron 表达式 | 含义 |
|-------------|------|
| `0 9 * * *` | 每天 09:00 |
| `0 18 * * *` | 每天 18:00 |
| `30 8 * * 1-5` | 工作日 08:30 |
| `0 9,18 * * *` | 每天 09:00 和 18:00 |

---

## AI Provider 支持

| Provider | 配置方式 | 适用场景 |
|----------|---------|---------|
| **Anthropic Claude** | `AI_PROVIDER=anthropic` + API Key | 云端，推理能力强 |
| **Qwen3-32B (vLLM)** | `AI_PROVIDER=openai` + `AI_BASE_URL` | 本地部署，数据不出内网 |
| **Ollama** | `AI_PROVIDER=openai` + `http://host:11434/v1` | 本地一键部署 |
| **DeepSeek** | `AI_PROVIDER=openai` + DeepSeek API URL | 低成本云端 |
| **OpenRouter** | `AI_PROVIDER=openai` + OpenRouter URL | 多模型聚合 |

> 任何支持 OpenAI Chat Completions API 格式的服务均可接入。

---

## Drain3 日志模板聚类

**Drain** 是一种基于固定深度前缀树的在线日志聚类算法，无需预定义正则表达式，自动将格式相似的日志归纳为统一模板。

```
原始日志：
  "Connection timeout to 10.0.1.5 after 30002ms"
  "Connection timeout to 10.0.2.3 after 15443ms"

Drain 输出：
  "Connection timeout to <*> after <*>"
```

在「日志分析」页切换到「模板聚类」标签，可快速掌握系统中最频繁出现的日志模式。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `drain_sim_th` | `0.4` | 相似度阈值，越低越宽松 |
| `drain_depth` | `4` | 前缀树深度，越深越精细 |
| `drain_max_clusters` | `500` | 最多保留的模板数量 |

---

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（Loki + Prometheus + AI 状态） |
| GET | `/api/services` | 服务列表及错误数 |
| GET | `/api/logs` | 查询日志（服务/时间/级别过滤） |
| GET | `/api/logs/errors` | 全量错误日志 |
| GET | `/api/logs/templates` | Drain3 日志模板聚类 |
| GET | `/api/metrics/errors` | 各服务错误数统计 |
| GET | `/api/analyze/stream` | **流式** AI 日志分析（SSE） |
| POST | `/api/report/generate` | **流式** 生成运维日报（SSE） |
| GET | `/api/report/list` | 历史报告列表 |
| GET | `/api/report/{id}` | 报告详情 |
| POST | `/api/report/{id}/notify` | 推送报告到飞书 / 钉钉 |
| GET | `/api/hosts` | 主机列表（Prometheus 发现 + CMDB + 实时指标） |
| PUT | `/api/hosts/{instance}` | 更新主机 CMDB 信息 |
| GET | `/api/hosts/inspect` | 全量主机巡检 |
| GET | `/api/hosts/{instance}/inspect` | 单台主机巡检 |
| POST | `/api/hosts/inspect/ai` | **流式** AI 巡检分析（SSE） |
| POST | `/api/hosts/inspect/excel` | 导出巡检报告 Excel |
| POST | `/api/ssh/connect` | 建立 SSH 连接 |
| GET | `/api/ssh/credentials` | 凭证列表 |
| POST | `/api/ssh/credentials` | 添加凭证（AES 加密存储） |

---

## 项目结构

```
AI-logging-analyse/
├── backend/
│   ├── main.py              # FastAPI 主应用 + APScheduler 定时任务
│   ├── loki_client.py       # Loki HTTP API v1 客户端
│   ├── prom_client.py       # Prometheus HTTP API 客户端
│   ├── ai_analyzer.py       # AI 分析器（Provider 抽象层）
│   ├── log_clusterer.py     # Drain3 日志模板聚类
│   ├── notifier.py          # 飞书 / 钉钉 Webhook 推送
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example         # 配置模板
│   ├── cmdb_hosts.json      # CMDB 手动字段存储（不提交）
│   └── reports/             # 历史报告（不提交）
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── Dashboard.vue        # 仪表盘
│   │   │   ├── LogAnalysis.vue      # 日志分析 + AI 分析 + 模板聚类
│   │   │   ├── MetricsMonitor.vue   # 指标监控
│   │   │   ├── AlertHistory.vue     # 告警历史
│   │   │   ├── AnalysisReport.vue   # 运维日报
│   │   │   └── HostCMDB.vue         # 主机 CMDB + 巡检 + SSH 终端
│   │   ├── components/
│   │   │   └── Sidebar.vue          # 侧边导航（含 AI/服务状态指示）
│   │   └── api/index.js             # HTTP + SSE 封装
│   ├── nginx.conf           # Docker 生产环境 Nginx 配置
│   └── Dockerfile
├── docker-compose.yml       # Docker Compose 一键部署
├── start.sh                 # Linux 直接启动脚本
└── README.md
```

---

## License

MIT
