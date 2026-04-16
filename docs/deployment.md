# AI Ops 日志分析平台 — 上线部署文档

> 版本：v2.0 | 更新日期：2026-03-24 | 环境：Kubernetes 1.32

---

## 目录

1. [系统架构](#1-系统架构)
2. [前置条件](#2-前置条件)
3. [基础设施准备](#3-基础设施准备)
4. [镜像构建与推送](#4-镜像构建与推送)
5. [K8s 资源部署](#5-k8s-资源部署)
6. [配置说明](#6-配置说明)
7. [验证上线](#7-验证上线)
8. [一键部署脚本](#8-一键部署脚本)
9. [运维操作手册](#9-运维操作手册)
10. [回滚流程](#10-回滚流程)
11. [常见问题排查](#11-常见问题排查)

---

## 1. 系统架构

```
用户浏览器
     │
     ▼ http://192.168.9.221:30090
┌─────────────────────────────────────────────────┐
│              K8s 集群 (namespace: aiops)         │
│                                                  │
│  ┌──────────┐    ┌──────────┐   ┌─────────┐    │
│  │ frontend │    │ backend  │   │  redis  │    │
│  │ (nginx)  │───▶│ (FastAPI)│──▶│ 6379    │    │
│  │ :80      │    │ :8000    │   └─────────┘    │
│  └──────────┘    └────┬─────┘                  │
│  NodePort:30090        │                        │
└───────────────────────┼────────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
     Loki :27478  Prometheus    Milvus :19530
   (日志查询)    :24404(监控)   (向量存储)
                              + Embedding :10009
```

### 组件清单

| 组件 | 镜像 | 资源限制 | 存储 |
|------|------|---------|------|
| frontend | `192.168.9.221:5000/aiops-frontend:latest` | 200m CPU / 256Mi | 无 |
| backend | `192.168.9.221:5000/aiops-backend:latest` | 1000m CPU / 2Gi | data-pvc(5G) + reports-pvc(10G) |
| redis | `redis:7-alpine` | 500m CPU / 512Mi | redis-data-pvc(2G) |

---

## 2. 前置条件

### 2.1 K8s 集群要求

| 项目 | 要求 |
|------|------|
| K8s 版本 | ≥ 1.24 |
| 节点数 | master × 1 + worker × N |
| 动态存储 | StorageClass `nfs-csi` 可用 |
| 节点网络 | 集群内节点互通 |

### 2.2 外部依赖服务

| 服务 | 地址 | 说明 |
|------|------|------|
| Loki | `http://192.168.9.221:27478` | 日志数据源，无认证 |
| Prometheus | `http://192.168.9.221:24404` | 指标数据源 |
| Milvus | `192.168.9.227:19530` | 向量数据库（可选，不可用时自动降级） |
| Embedding | `http://192.168.9.227:10009/v1` | 本地 Qwen3-Embedding-4B 服务 |
| AI 接口 | `https://api.codexzh.com/v1` | GPT-5 / 兼容 OpenAI 格式 |

### 2.3 本地镜像仓库

K8s 节点无外网访问，使用本地私有 Registry（`192.168.9.221:5000`）分发镜像。

**检查 Registry 是否运行：**
```bash
docker ps | grep registry
# 如未运行，启动：
docker run -d --name registry --restart always \
  -p 5000:5000 -v /opt/registry-data:/var/lib/registry registry:2
```

---

## 3. 基础设施准备

### 3.1 配置 Docker insecure registry（所有节点）

每个 K8s 节点（master + worker）的 Docker 都需要信任本地私有 Registry。

**在每个节点执行：**
```bash
# 编辑 /etc/docker/daemon.json，追加 insecure-registries
python3 -c "
import json
path = '/etc/docker/daemon.json'
with open(path) as f:
    d = json.load(f)
d.setdefault('insecure-registries', [])
if '192.168.9.221:5000' not in d['insecure-registries']:
    d['insecure-registries'].append('192.168.9.221:5000')
with open(path, 'w') as f:
    json.dump(d, f, indent=2)
print('done')
"
systemctl restart docker
```

**验证：**
```bash
docker pull 192.168.9.221:5000/aiops-backend:latest
```

### 3.2 确认存储类可用

```bash
kubectl get storageclass nfs-csi
# NAME      PROVISIONER      RECLAIMPOLICY   VOLUMEBINDINGMODE   ALLOWVOLUMEEXPANSION
# nfs-csi   nfs.csi.k8s.io   Delete          Immediate           true
```

---

## 4. 镜像构建与推送

> 在 master 节点（192.168.9.221）或有 Docker 的 CI 机器上执行。

### 4.1 获取代码

```bash
# 首次克隆
git clone https://github.com/tyloryang/AI-logging-analyse.git /opt/aiops

# 或更新
git -C /opt/aiops pull
```

> **注意**：若无法访问 GitHub，通过 SFTP 将代码直接上传至 `/opt/aiops/`。

### 4.2 构建后端镜像

```bash
docker build -t 192.168.9.221:5000/aiops-backend:latest /opt/aiops/backend
docker push 192.168.9.221:5000/aiops-backend:latest
```

**Dockerfile 关键点：**
- 基础镜像：`python:3.12-slim`
- pip 源：阿里云镜像（`mirrors.aliyun.com`）
- 工作目录：`/app`
- 启动命令：`uvicorn main:app --host 0.0.0.0 --port 8000`

### 4.3 构建前端镜像

```bash
docker build -t 192.168.9.221:5000/aiops-frontend:latest /opt/aiops/frontend
docker push 192.168.9.221:5000/aiops-frontend:latest
```

**Dockerfile 关键点：**
- 构建阶段：`node:20-alpine` + `npm run build`
- 运行阶段：`nginx:alpine`，静态文件托管
- Nginx 代理：`/api/*` → `http://backend:8000`

### 4.4 验证镜像已推送

```bash
curl http://192.168.9.221:5000/v2/_catalog
# {"repositories":["aiops-backend","aiops-frontend"]}

curl http://192.168.9.221:5000/v2/aiops-backend/tags/list
# {"name":"aiops-backend","tags":["latest"]}
```

---

## 5. K8s 资源部署

所有 manifest 文件位于 `k8s/` 目录，按以下顺序应用。

### 5.1 创建命名空间

```bash
kubectl apply -f k8s/namespace.yaml
# namespace/aiops created
```

### 5.2 创建 ConfigMap（非敏感配置）

```bash
kubectl apply -f k8s/configmap.yaml
```

### 5.3 创建 Secret（敏感配置）

> **重要**：部署前必须填写真实密钥，否则脚本会拒绝继续。

编辑 `k8s/secret.yaml`：
```yaml
stringData:
  AI_API_KEY: "你的AI接口密钥"          # 替换
  ANTHROPIC_API_KEY: ""                  # 如使用 Anthropic 填写
  EMBEDDING_API_KEY: "123456"            # Embedding 服务密钥
  ADMIN_USERNAME: "admin"
  ADMIN_PASSWORD: "Admin@2026"           # 建议修改
  FEISHU_WEBHOOK: "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"  # 替换
  FEISHU_BOT_APP_ID: "cli_xxxxxxxxxxxxxxxx"       # 飞书事件回调应用 App ID
  FEISHU_BOT_APP_SECRET: "your_feishu_app_secret" # 飞书事件回调应用 Secret
  FEISHU_BOT_ENCRYPT_KEY: ""                      # 可选：飞书事件加密密钥
  FEISHU_BOT_VERIFY_TOKEN: ""                     # 可选：飞书 Verification Token
```

```bash
kubectl apply -f k8s/secret.yaml
```

### 5.4 创建 PVC（持久化存储）

```bash
kubectl apply -f k8s/pvc.yaml
```

| PVC 名称 | 容量 | 挂载路径 | 用途 |
|---------|------|---------|------|
| aiops-data-pvc | 5Gi | `/app/data` | SQLite DB、CMDB |
| aiops-reports-pvc | 10Gi | `/app/reports` | 历史报告 JSON |
| redis-data-pvc | 2Gi | `/data` | Redis 持久化 |

### 5.5 部署 Redis

```bash
kubectl apply -f k8s/redis.yaml
kubectl rollout status deployment/redis -n aiops --timeout=120s
```

### 5.6 部署后端

```bash
kubectl apply -f k8s/backend.yaml
kubectl rollout status deployment/backend -n aiops --timeout=180s
```

### 5.7 部署前端

```bash
kubectl apply -f k8s/frontend.yaml
kubectl rollout status deployment/frontend -n aiops --timeout=60s
```

### 5.8 确认所有资源

```bash
kubectl get all -n aiops
```

预期输出：
```
NAME                            READY   STATUS    RESTARTS   AGE
pod/backend-xxx                 1/1     Running   0          2m
pod/frontend-xxx                1/1     Running   0          1m
pod/redis-xxx                   1/1     Running   0          3m

NAME               TYPE        CLUSTER-IP    PORT(S)
service/backend    ClusterIP   10.x.x.x      8000/TCP
service/frontend   NodePort    10.x.x.x      80:30090/TCP
service/redis      ClusterIP   10.x.x.x      6379/TCP
```

---

## 6. 配置说明

### 6.1 ConfigMap 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOKI_URL` | `http://192.168.9.221:27478` | Loki 地址 |
| `PROMETHEUS_URL` | `http://192.168.9.221:24404` | Prometheus 地址 |
| `AI_PROVIDER` | `openai` | AI 提供商：`openai` 或 `anthropic` |
| `AI_BASE_URL` | `https://api.codexzh.com/v1` | OpenAI 兼容 API 地址 |
| `AI_MODEL` | `gpt-5` | 使用的模型名 |
| `MILVUS_HOST` | `192.168.9.227` | Milvus 向量库地址 |
| `EMBEDDING_BASE_URL` | `http://192.168.9.227:10009/v1` | Embedding 服务地址 |
| `EMBEDDING_DIM` | `2560` | 向量维度（Qwen3-Embedding-4B） |
| `REDIS_URL` | `redis://redis:6379` | Redis 地址（K8s service 名） |
| `SCHEDULE_CRON` | `0 7 * * *` | 自动日报定时（每天07:00） |
| `SCHEDULE_CHANNELS` | `feishu` | 推送渠道：`feishu`/`dingtalk` |
| `SESSION_TTL_SECONDS` | `28800` | 登录 Session 有效期（8小时） |

### 6.2 Secret 变量

| 变量 | 说明 |
|------|------|
| `AI_API_KEY` | AI 接口密钥 |
| `ANTHROPIC_API_KEY` | Anthropic 密钥（可选） |
| `EMBEDDING_API_KEY` | Embedding 服务鉴权 |
| `ADMIN_USERNAME` | 后台管理员账号 |
| `ADMIN_PASSWORD` | 后台管理员密码 |
| `FEISHU_WEBHOOK` | 飞书机器人 Webhook 地址 |
| `FEISHU_BOT_APP_ID` | 飞书事件回调应用 App ID |
| `FEISHU_BOT_APP_SECRET` | 飞书事件回调应用 Secret |
| `FEISHU_BOT_ENCRYPT_KEY` | 飞书事件加密密钥（可选） |
| `FEISHU_BOT_VERIFY_TOKEN` | 飞书 Verification Token（可选） |
| `DINGTALK_WEBHOOK` | 钉钉机器人 Webhook 地址 |

### 6.3 Milvus 不可用的降级行为

Milvus 或 Embedding 服务不可达时，系统**不会崩溃**，降级策略：
- 首次连接失败后标记为 `unavailable`，后续调用直接跳过，不再重试
- 报告仅保存到本地 `reports/` 文件，不写入向量库
- AI 分析、日志查询等核心功能**不受影响**

---

## 7. 验证上线

### 7.1 访问前端

浏览器打开：**http://192.168.9.221:30090**

默认账号：`admin` / `Admin@2026`

### 7.2 检查后端健康

```bash
curl http://192.168.9.221:30090/api/health | python3 -m json.tool
```

预期响应：
```json
{
  "status": "ok",
  "loki_connected": true,
  "prometheus_connected": true,
  "ai_provider": "OpenAI-compatible",
  "ai_ready": true
}
```

### 7.3 功能验证清单

- [ ] 登录页面居中显示，能正常登录
- [ ] 日志分析页：默认展示最近 1 小时日志
- [ ] 日志分析页：能查询指定服务的错误日志
- [ ] AI 分析：流式输出正常（SSE）
- [ ] 主机巡检页：能列出 Prometheus 中的主机
- [ ] 运维日报页：能生成并保存日报
- [ ] AI 智能体：能理解"最近 N 分钟"的时间指令
- [ ] 飞书/钉钉推送：测试 Webhook 可达

---

## 8. 一键部署脚本

```bash
# 在 master 节点执行（已配置好所有前置条件后）
bash /opt/aiops/k8s/deploy.sh
```

脚本执行顺序：
1. 检查 docker / kubectl / git 依赖
2. 启动本地 Registry（如未运行）
3. 配置 Docker insecure registry
4. git clone / pull 代码
5. 构建并推送 backend、frontend 镜像
6. 配置 containerd insecure registry
7. 按序 apply 所有 K8s manifest
8. 等待 rollout 完成
9. 输出访问地址

> **注意**：运行前请确保 `k8s/secret.yaml` 已填写真实密钥，否则脚本在步骤 7 会主动退出。

---

## 9. 运维操作手册

### 9.1 查看日志

```bash
# 后端日志
kubectl logs -n aiops -l app=backend -f --tail=100

# 前端日志（nginx）
kubectl logs -n aiops -l app=frontend -f

# Redis 日志
kubectl logs -n aiops -l app=redis -f
```

### 9.2 重启服务

```bash
# 滚动重启（零停机）
kubectl rollout restart deployment/backend -n aiops
kubectl rollout restart deployment/frontend -n aiops

# 查看重启状态
kubectl rollout status deployment/backend -n aiops
```

### 9.3 更新镜像（发布新版本）

```bash
# 1. 重新构建并推送镜像
docker build -t 192.168.9.221:5000/aiops-backend:latest /opt/aiops/backend
docker push 192.168.9.221:5000/aiops-backend:latest

# 2. 强制重新拉取（imagePullPolicy: Always 已配置）
kubectl rollout restart deployment/backend -n aiops
kubectl rollout status deployment/backend -n aiops --timeout=180s
```

### 9.4 扩缩容

```bash
# 扩容后端到 2 副本
kubectl scale deployment/backend -n aiops --replicas=2

# 查看
kubectl get pods -n aiops
```

### 9.5 查看资源使用

```bash
kubectl top pods -n aiops
kubectl top nodes
```

### 9.6 进入容器调试

```bash
# 进入后端 shell
kubectl exec -it -n aiops deploy/backend -- /bin/bash

# 检查环境变量
kubectl exec -it -n aiops deploy/backend -- env | grep -E "LOKI|AI|MILVUS"
```

---

## 10. 回滚流程

### 10.1 K8s 滚动回滚

```bash
# 查看历史版本
kubectl rollout history deployment/backend -n aiops

# 回滚到上一版本
kubectl rollout undo deployment/backend -n aiops

# 回滚到指定版本
kubectl rollout undo deployment/backend -n aiops --to-revision=2
```

### 10.2 镜像版本管理（推荐）

发布时使用带版本号的 tag，保留历史镜像：

```bash
# 推送时同时打 latest 和版本 tag
docker tag 192.168.9.221:5000/aiops-backend:latest 192.168.9.221:5000/aiops-backend:v2.1
docker push 192.168.9.221:5000/aiops-backend:v2.1

# 回滚时指定版本 tag
kubectl set image deployment/backend backend=192.168.9.221:5000/aiops-backend:v2.0 -n aiops
```

---

## 11. 常见问题排查

### Q1: Pod 状态为 `ImagePullBackOff`

**原因**：节点 Docker 未配置 insecure registry，无法拉取本地镜像。

```bash
# 查看具体错误
kubectl describe pod <pod-name> -n aiops | tail -20

# 修复：在对应 worker 节点上执行
# 编辑 /etc/docker/daemon.json，添加 "insecure-registries": ["192.168.9.221:5000"]
systemctl restart docker

# 删除 Pod 让其重新调度
kubectl delete pod <pod-name> -n aiops
```

### Q2: Pod 状态为 `Pending`

**原因一**：PVC 无法绑定（存储类不可用）
```bash
kubectl describe pvc -n aiops
kubectl get storageclass
```

**原因二**：节点资源不足
```bash
kubectl describe node <node-name> | grep -A5 "Allocated resources"
```

### Q3: NodePort 端口冲突

```bash
# 查看所有 NodePort 使用情况
kubectl get svc -A | grep NodePort

# 修改 frontend.yaml 中的 nodePort 值（30000-32767）
# 然后重新 apply
kubectl delete svc frontend -n aiops
kubectl apply -f k8s/frontend.yaml
```

### Q4: 后端无法连接 Loki / Prometheus

```bash
# 确认服务可达
kubectl exec -it -n aiops deploy/backend -- curl -s http://192.168.9.221:27478/ready

# 检查 ConfigMap
kubectl get configmap aiops-config -n aiops -o yaml
```

### Q5: AI 分析无响应

```bash
# 检查 AI 配置
kubectl exec -it -n aiops deploy/backend -- env | grep AI

# 查看后端日志
kubectl logs -n aiops -l app=backend --tail=50 | grep -i "ai\|error"
```

### Q6: 飞书/钉钉推送失败

```bash
# 验证 Webhook
kubectl exec -it -n aiops deploy/backend -- \
  curl -X POST <FEISHU_WEBHOOK> \
  -H "Content-Type: application/json" \
  -d '{"msg_type":"text","content":{"text":"test"}}'
```

---

## 附录：端口一览

| 服务 | 类型 | 端口 | 说明 |
|------|------|------|------|
| frontend | NodePort | 30090 | 外部访问入口 |
| backend | ClusterIP | 8000 | 仅集群内访问 |
| redis | ClusterIP | 6379 | 仅集群内访问 |
| local registry | HostPort | 5000 | 镜像仓库 |
| Loki | NodePort | 27478 | 外部服务 |
| Prometheus | NodePort | 24404 | 外部服务 |
| Milvus | TCP | 19530 | 外部服务 |
| Embedding | HTTP | 10009 | 外部服务 |
---

## 12. 飞书独立回调服务

如果希望把飞书事件回调从主后端解耦，可以单独启动一个轻量回调服务。

### 12.1 相关环境变量

```env
FEISHU_CALLBACK_HOST=0.0.0.0
FEISHU_CALLBACK_PORT=8001
FEISHU_CALLBACK_PUBLIC_BASE_URL=
```

- `FEISHU_CALLBACK_HOST`：独立回调服务绑定的 Host / IP
- `FEISHU_CALLBACK_PORT`：独立回调服务监听端口
- `FEISHU_CALLBACK_PUBLIC_BASE_URL`：展示给飞书开放平台的公网地址，可为空；为空时前端会自动按“当前访问主机 + 回调端口”拼接

### 12.2 启动方式

在仓库根目录执行：

```bash
python backend/feishu_callback_app.py
```

或先进入 `backend` 目录再执行：

```bash
uvicorn feishu_callback_app:app --host 0.0.0.0 --port 8001
```

### 12.3 健康检查

```bash
curl http://127.0.0.1:8001/healthz
```

### 12.4 飞书开放平台配置

在前端“系统配置 -> 飞书机器人”里配置好：

- `App ID`
- `App Secret`
- `Encrypt Key`（可选）
- `Verify Token`（可选）
- `回调服务 Host / Port`
- `公网 Base URL`（如有域名或反向代理）

随后把页面展示的 `Webhook 回调地址` 填到飞书开放平台的“事件与回调”。
