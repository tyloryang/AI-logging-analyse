# AIOPS Code — AI 运维智能体 CLI

Claude Code 风格的终端智能体界面，基于 Ink 构建。与平台 Web 端共享同一套
LangGraph Agent / 认证体系 / 会话历史。

## 安装

```bash
cd cli
npm install
npm run build
```

## 运行

```bash
# 交互模式（首次会弹出登录向导，凭据缓存在 ~/.aiops-code.json）
node dist/index.mjs

# 指定模式启动
node dist/index.mjs chat      # 自由对话
node dist/index.mjs rca       # 根因分析
node dist/index.mjs inspect   # 系统巡检
node dist/index.mjs guided    # 引导排障

# print 模式（无 TTY 也可用，适合脚本 / CI / 飞书 Bot 集成）
node dist/index.mjs -p "现在哪个服务错误最多？"
node dist/index.mjs -p "请输出根因分析报告" rca

# 指定后端地址（默认 http://127.0.0.1:8000）
AIOPS_URL=http://192.168.9.221:30800 node dist/index.mjs

# 免交互登录（适合脚本）
AIOPS_USER=admin AIOPS_PASS=xxx node dist/index.mjs -p "巡检一下"
```

## 认证

- 后端所有 Agent 接口都需要登录。CLI 首次启动显示登录向导，登录成功后
  session 缓存到 `~/.aiops-code.json`，后续启动免登录。
- 会话过期会自动回到登录向导；print 模式下提示设置 `AIOPS_USER` / `AIOPS_PASS`。

## 会话互通

交互模式下每轮对话自动保存到服务端（标题前缀 `[CLI]`），
可在 Web 端「AI 智能助手」的历史会话列表中查看和续聊。

## Slash 命令

| 命令 | 功能 |
|------|------|
| `/help` | 显示命令帮助 |
| `/mode <m>` | 切换模式（chat/rca/inspect/guided） |
| `/status` | 查看后端健康状态（Loki/Prometheus/AI） |
| `/reset` | 开启新会话（清空上下文） |
| `/clear` | 清屏（保留上下文） |
| `/logout` | 退出登录并清除本地凭据 |
| `/exit` | 退出 CLI |

## 快捷键

| 按键 | 功能 |
|------|------|
| `Enter` | 发送消息 |
| `Tab` | 切换模式 |
| `Ctrl+R` | 重置对话（新 session） |
| `Ctrl+L` | 清屏（保留对话上下文） |
| `Ctrl+C` | 退出 |
| `Esc` | 关闭错误提示 |
