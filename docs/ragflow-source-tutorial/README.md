# loki-log-analyse 源码分析教程

> 说明：目录名 `ragflow-source-tutorial` 来自用户指定的存放位置；本教程分析对象是当前仓库 **loki-log-analyse**，不是开源项目 RAGFlow。

本目录是一套面向开发者和运维研发人员的源码导读。目标不是复述 README，而是建立从入口、调用链、状态边界到排障方法的完整心智模型。

## 分析边界与基线

- 仓库：`D:\loki-log-analyse`
- 当前分支：`master`
- HEAD：`72fb2729a93899a916afe220d6ce1be4bde41864`
- 分析日期：2026-07-12
- 分析对象：当前工作区快照，包含尚未提交的用户改动
- 分析方法：CodeGraph 结构索引、路由清单、部署配置与依赖清单的只读检查
- 修改范围：没有修改任何业务源码；仅重写本教程目录中的 Markdown 文件

由于工作区存在大量未提交改动，文档描述的是“分析时看到的工作区”，不能只用 HEAD 提交还原全部结论。

## 教程目录

1. [系统架构总览](01-architecture-overview.md)
2. [代码模块地图](02-module-map.md)
3. [后端运行时、认证与存储](03-backend-runtime-auth-storage.md)
4. [AI Agent、工具调用与 RCA](04-ai-agent-and-rca.md)
5. [Loki 日志、慢日志与报告链路](05-logs-slowlog-reports.md)
6. [可观测性与基础设施连接器](06-observability-infrastructure.md)
7. [Vue 前端、API 层与 Ink CLI](07-frontend-cli.md)
8. [五级源码阅读路线](08-source-reading-guide.md)

## 一句话心智模型

```text
Loki / Prometheus / SkyWalking / K8s / SSH / ES / Redis / Kafka / Jenkins
                              |
                              v
                   FastAPI 路由与领域服务
                              |
            +-----------------+------------------+
            |                 |                  |
       查询与监控         报告与事件         LangGraph Agent
            |                 |             工具 -> 证据 -> RCA
            +-----------------+------------------+
                              |
                  Vue Web / Ink CLI / 飞书回调
```

## 建议阅读顺序

- 第一次接触：`01 -> 02 -> 03 -> 07`
- 研究 AI Agent：`01 -> 04 -> 06`
- 研究日志分析：`01 -> 05 -> 06`
- 定位线上问题：先读对应专题，再用 `08` 的阅读记录模板追踪真实请求
- 准备参与开发：完整阅读 `01 -> 08`，然后选择一条调用链做源码复述

## 阅读时始终问四个问题

1. 请求从哪个入口进入，走 Web、CLI、Webhook 还是定时任务？
2. 数据从哪个外部系统读取，又写入 SQLite/关系库、Redis、文件、Neo4j 或 Milvus 的哪一处？
3. 返回是普通 JSON、文件下载还是 SSE 流？
4. 失败后能否重试、恢复或审计，权限边界在哪里？

