# CodeGraph 使用指南

本文档基于本项目 `D:\loki-log-analyse` 的实测结果编写，并结合当前 CodeGraph 官方文档和本机 `codegraph --help` 输出校准。

## 当前状态

本项目已重新初始化 CodeGraph 索引：

- CodeGraph 版本：`1.2.0`
- 项目路径：`D:\loki-log-analyse`
- 索引目录：`.codegraph`
- 文件数：`201`
- 节点数：`6,139`
- 边数：`17,410`
- 语言：`javascript`、`python`、`vue`、`yaml`
- 当前状态：`pendingChanges.added=0`、`modified=0`、`removed=0`
- 旧索引备份：`.codegraph.bak-20260703115711`

`.codegraph/` 是本地索引缓存，不建议提交到 Git。当前 `.codegraph/.gitignore` 已忽略数据库、日志、pid 等临时文件。

## 它解决什么问题

CodeGraph 会把项目源码解析成一个本地代码知识图谱，用来回答结构性问题：

- 某个函数、类、变量在哪里定义
- 谁调用了这个函数
- 这个函数又调用了谁
- 修改某个符号会影响哪些代码
- 修改某个文件后，可能需要跑哪些测试
- 某个功能区域有哪些相关源码和调用路径

它适合做代码理解、影响面分析和改动前摸底；不适合替代 `rg` 查纯文本、日志片段、注释文案或配置字符串。

## 快速开始

在仓库根目录执行：

```powershell
cd D:\loki-log-analyse
codegraph init .
codegraph status
```

`init` 会初始化 `.codegraph/` 并建立完整索引。官方文档也常写作 `codegraph init -i`，当前本机版本 `1.2.0` 中 `codegraph init .` 已会完成初始化和建索引。

日常改代码后同步索引：

```powershell
codegraph sync .
```

如果索引损坏或版本升级后需要完整重建：

```powershell
codegraph index .
```

## 常用命令

查看索引状态：

```powershell
codegraph status
codegraph status --json
```

查看项目文件结构：

```powershell
codegraph files
codegraph files | Select-Object -First 40
```

搜索符号：

```powershell
codegraph query build_graph
codegraph query build_graph --kind function --limit 5 --json
codegraph query get_platform_overview --limit 10 --json
```

查看某个符号的源码和上下游 trail：

```powershell
codegraph node build_graph
codegraph node get_platform_overview
```

查谁调用了它：

```powershell
codegraph callers build_graph
codegraph callers build_graph --json
```

查它调用了谁：

```powershell
codegraph callees build_graph
codegraph callees build_graph --json
```

分析改动影响面：

```powershell
codegraph impact get_platform_overview --depth 3
```

根据文件查可能受影响的测试：

```powershell
codegraph affected backend/agent/graph.py
```

按功能区域探索相关源码：

```powershell
codegraph explore "get_platform_overview platform overview agent tools"
codegraph explore "AI助手 平台信息 工具调用"
```

查看本机支持的全部命令：

```powershell
codegraph --help
codegraph help query
codegraph help impact
```

## 本项目实测示例

### 1. 查 LangGraph 构建入口

```powershell
codegraph node build_graph
```

实测定位到：

- 文件：`backend/agent/graph.py`
- 行号：`490`
- 签名：`(mode: str = "chat", checkpointer=None, runtime_overrides: dict | None = None)`

它的调用方：

```powershell
codegraph callers build_graph --json
```

实测结果包含：

- `backend/aiops_cli.py:_run`
- `backend/routers/agent.py:_stream_graph`
- `backend/routers/feishu_bot.py:_invoke_via_langgraph`
- `backend/routers/agent.py`

它调用的下游：

```powershell
codegraph callees build_graph --json
```

实测结果包含：

- `_load_enabled_mcps`
- `_build_mcp_context`
- `_find_mcp`
- `get_agent_runtime_context`
- `tools_for_runtime`
- `bind_tools`
- `_get_llm`
- `_build_guarded_tools_node`

### 2. 查平台信息工具

```powershell
codegraph node get_platform_overview
```

实测定位到：

- 文件：`backend/agent/tool_modules/platform.py`
- 行号：`173`
- 签名：`(scope: str = "overview", config: RunnableConfig = None) -> str`

它的直接调用方：

```powershell
codegraph callers get_platform_overview --json
```

实测结果：

- `backend/agent/tools.py`

它调用的下游：

```powershell
codegraph callees get_platform_overview --json
```

实测结果包含：

- `_read_json`
- `_capabilities_section`
- `_agent_section`
- `_inventory_section`
- `_mcp_section`
- `_settings_section`

影响面分析：

```powershell
codegraph impact get_platform_overview --depth 3
```

实测影响面较小，主要是：

- `backend/agent/tool_modules/platform.py`
- `backend/agent/tools.py`

### 3. 查文件改动后应关注的测试

```powershell
codegraph affected backend/agent/graph.py
```

实测返回：

- `backend/tests/test_guarded_tools_node.py`

这类命令适合在改核心编排、工具注册、路由入口前先跑一遍，用来决定最小测试范围。

## 推荐工作流

改动前先问结构：

```powershell
codegraph explore "要改的功能 关键函数 关键文件"
```

定位符号：

```powershell
codegraph query <symbol> --json
codegraph node <symbol>
```

看调用关系：

```powershell
codegraph callers <symbol> --json
codegraph callees <symbol> --json
```

评估影响面：

```powershell
codegraph impact <symbol> --depth 3
codegraph affected <changed-file>
```

改完后同步索引：

```powershell
codegraph sync .
codegraph status --json
```

最后再结合单元测试或构建命令验证，不要只依赖 CodeGraph 判断功能正确性。

## 注意事项

### `context` 子命令不可用

部分文档或旧示例可能会提到：

```powershell
codegraph context <symbol>
```

但本机 `codegraph 1.2.0` 实测不支持该命令，会报：

```text
error: unknown command 'context'
```

当前应使用：

```powershell
codegraph node <symbol>
codegraph explore "<query>"
```

### 索引是本地缓存

`.codegraph/` 由本机生成，数据库和日志不应提交。换机器或重新 clone 后，需要重新执行：

```powershell
codegraph init .
```

### 查询结果依赖索引新鲜度

如果刚做了大量改动，先执行：

```powershell
codegraph sync .
```

再跑 `query`、`node`、`impact`。

### 纯文本搜索仍用 rg

查具体字符串、日志片段、注释、配置项时，`rg` 更直接：

```powershell
rg "get_platform_overview"
rg "AI助手"
```

CodeGraph 更适合问“结构关系”，`rg` 更适合问“字面文本”。

## 命令速查

| 目的 | 命令 |
| --- | --- |
| 初始化并建索引 | `codegraph init .` |
| 完整重建索引 | `codegraph index .` |
| 增量同步索引 | `codegraph sync .` |
| 查看状态 | `codegraph status --json` |
| 查看文件树 | `codegraph files` |
| 搜索符号 | `codegraph query <search> --json` |
| 查看符号源码和 trail | `codegraph node <symbol>` |
| 查调用方 | `codegraph callers <symbol> --json` |
| 查被调用方 | `codegraph callees <symbol> --json` |
| 查影响面 | `codegraph impact <symbol> --depth 3` |
| 查受影响测试 | `codegraph affected <file>` |
| 探索功能区域 | `codegraph explore "<query>"` |
| 查看帮助 | `codegraph --help` |
