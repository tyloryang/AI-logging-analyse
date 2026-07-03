# CLI-WeChat-Bridge-Web

一个独立的微信接入 Codex 网页控制台项目。

这个仓库只保留：

- Web 控制台前后端代码
- 启动 Codex 会话所需的最小运行源码
- Docker / Docker Compose / 自动化部署脚本
- 三方中转配置与部署文档

## 目录说明

- `web-console/`：网页控制台与部署文件
- `src/`：Web 控制台启动 Codex 会话所需的运行源码
- `package.json`：Node 依赖与启动脚本

## 本地启动

```bash
npm install
npm run web:console
```

默认访问：

```text
http://127.0.0.1:8080
```

## Docker 启动

```bash
cd web-console
cp .env.example .env
docker compose up -d --build
```

如果走三方中转：

```bash
cd web-console
cp .env.relay.example .env
docker compose up -d --build
```

## 主要文档

- `web-console/README.md`
- `web-console/EMPTY_SERVER_AUTO_DEPLOY.md`
- `web-console/QR_CODE_DISPLAY_FIX.md`

