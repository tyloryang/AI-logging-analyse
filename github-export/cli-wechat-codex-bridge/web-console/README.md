# Codex × 微信网页控制台

这个目录提供一个最小可用的网页管理台，让用户在浏览器里完成：

- 生成微信扫码二维码
- 轮询扫码状态并保存凭据
- 启动 / 停止 `Codex + CLI-WeChat-Bridge`
- 查看 bridge / companion / codex 合并日志

> 说明：  
> 这不是一个浏览器聊天界面。  
> 它负责**完成接入和管理**，聊天本身仍发生在微信里。

## 本地启动

在 `CLI-WeChat-Bridge` 根目录执行：

```bash
node web-console/server.mjs
```

默认监听：

```text
http://127.0.0.1:8080
```

## Docker 构建

在 `CLI-WeChat-Bridge` 根目录执行：

```bash
docker build -f web-console/Dockerfile -t codex-wechat-web .
```

## Docker Compose

在 `web-console` 目录执行：

```bash
cp .env.example .env
docker compose up -d --build
```

如果 Codex 走三方中转，可以直接复制中转模板：

```bash
cp .env.relay.example .env
docker compose up -d --build
```

默认访问地址：

```text
http://127.0.0.1:8080
```

如果你要改端口、工作目录或 Codex 凭据挂载，编辑 `web-console/.env`：

```dotenv
HOST_PORT=8080
HOST_WORKSPACE_DIR=./workspace
HOST_CODEX_HOME_DIR=./codex-home
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=
OPENAI_ORGANIZATION=
OPENAI_PROJECT=
CODEX_RELAY_BASE_URL=
CODEX_RELAY_MODEL=gpt-5.4
CODEX_RELAY_WIRE_API=responses
```

说明：
- `OPENAI_API_KEY` 与 `HOST_CODEX_HOME_DIR` 二选一即可，两个都提供也可以
- `HOST_CODEX_HOME_DIR` 目录会挂载到容器内的 `/root/.codex`
- `HOST_WORKSPACE_DIR` 会挂载到容器内的 `/workspace`
- 微信登录态与运行日志默认保存在 `web-console/data`

## 三方中转 / API 网关

如果你的 Codex 不走 OpenAI 官方直连，而是走 **OpenAI-compatible 三方中转**，建议使用下面两种方式之一：

可以先复制模板：

```bash
cp .env.relay.example .env
```

### 方式 1：Responses 兼容中转

适合中转已经兼容 `/v1/responses` 的场景。

```dotenv
OPENAI_API_KEY=your_relay_key
CODEX_RELAY_BASE_URL=https://your-relay.example.com/v1
CODEX_RELAY_MODEL=gpt-5.4
CODEX_RELAY_WIRE_API=responses
```

### 方式 2：仅 Chat Completions 兼容中转

如果中转只支持 `/v1/chat/completions`，把协议切到 `chat`：

```dotenv
OPENAI_API_KEY=your_relay_key
CODEX_RELAY_BASE_URL=https://your-relay.example.com/v1
CODEX_RELAY_MODEL=gpt-5.4
CODEX_RELAY_WIRE_API=chat
```

说明：
- `CODEX_RELAY_MODEL` 要填写成你中转后台实际支持的模型名或别名
- 自动部署脚本会在 `HOST_CODEX_HOME_DIR` 下生成 `config.toml`
- 如果你已经有自己的 `codex-home/config.toml`，脚本默认不会覆盖，除非显式设置 `FORCE_REWRITE_CODEX_CONFIG=1`
- 某些中转会要求完整 `.../v1` 结尾，请按中转文档填写 `CODEX_RELAY_BASE_URL`

## Docker 运行

最小示例：

```bash
docker run -d \
  --name codex-wechat-web \
  -p 8080:8080 \
  -e OPENAI_API_KEY=your_openai_api_key \
  -v codex-wechat-data:/data \
  -v /your/workspace:/workspace \
  codex-wechat-web
```

如果你已经在宿主机登录过 Codex，也可以改为挂载容器内 `~/.codex`：

```bash
docker run -d \
  --name codex-wechat-web \
  -p 8080:8080 \
  -v codex-wechat-data:/data \
  -v /your/workspace:/workspace \
  -v /your/codex-home:/root/.codex \
  codex-wechat-web
```

## 关键环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `8080` | Web 控制台监听端口 |
| `CODEX_WORKSPACE` | `/workspace` | 默认项目目录 |
| `CLAUDE_WECHAT_CHANNEL_DATA_DIR` | `/data/wechat` | 微信桥接凭据与状态文件目录 |
| `OPENAI_BASE_URL` | 空 | OpenAI 官方兼容网关地址，官方直连可留空 |
| `OPENAI_ORGANIZATION` | 空 | 可选，OpenAI 组织 ID |
| `OPENAI_PROJECT` | 空 | 可选，OpenAI Project ID |
| `WECHAT_ILINK_BASE_URL` | `https://ilinkai.weixin.qq.com` | 微信登录服务地址 |
| `MAX_LOG_LINES` | `500` | 页面内保留的日志行数 |

## 页面 API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/config` | 当前凭据与会话状态 |
| `POST` | `/api/qrcode` | 生成新的微信扫码二维码 |
| `GET` | `/api/qrcode/:id/status` | 轮询二维码状态 |
| `POST` | `/api/session/start` | 启动 Codex 接入 |
| `POST` | `/api/session/stop` | 停止 Codex 接入 |
| `GET` | `/api/session/status` | 查询运行状态 |
| `GET` | `/api/logs` | 查询最近日志 |

## 限制与注意事项

1. 当前版本是**单用户、单会话、单工作目录**控制台
2. 默认**没有内建鉴权**
3. 强烈建议：
   - 放到内网
   - 放到 VPN 后面
   - 或使用 Nginx / Traefik / Cloudflare Access 增加认证
4. 如果容器内 `codex` 需要私有仓库凭据、额外模型网关或自定义证书，请在运行容器时追加环境变量或挂载目录
