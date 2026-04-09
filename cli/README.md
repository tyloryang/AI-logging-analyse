# AI 运维智能体 CLI

Claude Code 风格的终端智能体界面，基于 Ink 构建。

## 安装

```bash
cd cli
npm install
npm run build
```

## 运行

```bash
# 默认对话模式
node dist/index.mjs

# 指定模式
node dist/index.mjs chat      # 自由对话
node dist/index.mjs rca       # 根因分析
node dist/index.mjs inspect   # 系统巡检
node dist/index.mjs guided    # 引导排障

# 指定后端地址
AIOPS_URL=http://192.168.9.221:30800 node dist/index.mjs
```

## 快捷键

| 按键 | 功能 |
|------|------|
| `Enter` | 发送消息 |
| `Tab` | 切换模式 |
| `Ctrl+R` | 重置对话（新 session） |
| `Ctrl+L` | 清屏（保留对话上下文） |
| `Ctrl+C` | 退出 |
| `Esc` | 关闭错误提示 |
