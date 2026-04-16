# Elasticsearch 8.19.3 on Kubernetes
重新扫码
本仓库新增了一个基于 ECK（Elastic Cloud on Kubernetes）的 Elasticsearch 8.19.3 三节点集群清单：

- 集群名：`aiops-es`
- 命名空间：`aiops`
- 账号：`elastic`
- 密码：`Password!`
- 镜像：`192.168.9.221:5000/elasticsearch:8.19.3`
- 对外访问：`https://<NodeIP>:30920`

## 1. 安装 ECK Operator

如果集群里还没有 ECK，请先安装：

```powershell
kubectl create -f https://download.elastic.co/downloads/eck/3.3.1/crds.yaml
kubectl apply -f https://download.elastic.co/downloads/eck/3.3.1/operator.yaml
kubectl -n elastic-system rollout status sts/elastic-operator
```

## 2. 部署命名空间和 ES 集群

```powershell
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/elasticsearch-eck.yaml
kubectl -n aiops get elasticsearch
kubectl -n aiops get pods -l elasticsearch.k8s.elastic.co/cluster-name=aiops-es -w
```

## 3. 验证访问

### 方式 A：NodePort

```powershell
curl.exe -k -u elastic:Password! https://<NodeIP>:30920
```

### 方式 B：端口转发

```powershell
kubectl -n aiops port-forward service/aiops-es-es-http 9200:9200
curl.exe -k -u elastic:Password! https://127.0.0.1:9200
```

## 4. 常用排查

```powershell
kubectl -n aiops describe elasticsearch aiops-es
kubectl -n aiops get pvc
kubectl -n aiops logs -l control-plane=elastic-operator -c manager --tail=200
kubectl -n aiops get svc
```

## 5. 说明

- `k8s/elasticsearch-eck.yaml` 依赖 ECK CRD，不能在未安装 ECK 的集群直接生效。
- ECK 默认启用 HTTPS，因此示例里用的是 `https://`。
- 示例验证命令使用 `-k` 跳过证书校验，正式接入建议改为导出 CA 证书后校验。
- 存储类沿用了仓库现有的 `nfs-csi`。
