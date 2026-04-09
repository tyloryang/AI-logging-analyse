# Elasticsearch 8.19.3 集群部署文档

> 基于 ECK（Elastic Cloud on Kubernetes）在 K8s 集群部署 3 节点 ES 8.19.3  
> 部署时间：2026-04-09  
> 部署人员：tyloryang

---

## 1. 环境信息

### K8s 集群节点

| 节点名    | IP              | 角色   | 系统                         | 内核                          | 容器运行时      |
|-----------|-----------------|--------|------------------------------|-------------------------------|-----------------|
| master    | 192.168.9.221   | master | Rocky Linux 8.10             | 5.4.295-1.el8.elrepo.x86_64   | docker://28.0.1 |
| node01    | 192.168.9.222   | worker | Rocky Linux 8.10             | 5.4.295-1.el8.elrepo.x86_64   | docker://28.0.1 |
| node02    | 192.168.9.223   | worker | Rocky Linux 8.10             | 5.4.295-1.el8.elrepo.x86_64   | docker://28.0.1 |
| node03    | 192.168.9.224   | worker | Rocky Linux 8.10             | 5.4.295-1.el8.elrepo.x86_64   | docker://28.0.1 |

- Kubernetes 版本：`v1.32.2`
- StorageClass：`nfs-csi`（NFS 动态供给，ReclaimPolicy=Delete）

### 镜像来源（本地 Registry）

| 组件          | 镜像                                          | 版本    |
|---------------|-----------------------------------------------|---------|
| ECK Operator  | `192.168.9.221:5000/eck/eck-operator`         | 3.3.1   |
| Elasticsearch | `192.168.9.221:5000/elasticsearch`            | 8.19.3  |

---

## 2. 部署架构

```
┌─────────────────────────────────────────────────────────┐
│  Namespace: elastic-system                              │
│  StatefulSet: elastic-operator  (ECK 3.3.1)            │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  Namespace: aiops                                       │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Elasticsearch Cluster: aiops-es                │   │
│  │                                                 │   │
│  │  aiops-es-es-default-0 → master (192.168.9.221) │   │
│  │  aiops-es-es-default-1 → node03 (192.168.9.224) │   │
│  │  aiops-es-es-default-2 → node01 (192.168.9.222) │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  Services:                                              │
│    aiops-es-es-http        ClusterIP   :9200 (内部)     │
│    aiops-es-http-nodeport  NodePort    :30920 (外部)    │
│    aiops-es-es-transport   ClusterIP   :9300 (节点间)   │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 部署步骤

### 3.1 安装 ECK Operator

**下载官方 YAML（需要访问 download.elastic.co）：**

```bash
curl -L -o /tmp/eck-crds.yaml \
  https://download.elastic.co/downloads/eck/3.3.1/crds.yaml

curl -L -o /tmp/eck-operator.yaml \
  https://download.elastic.co/downloads/eck/3.3.1/operator.yaml
```

**替换镜像为本地 Registry（离线环境必须）：**

```bash
sed -i 's|docker.elastic.co/eck/eck-operator:3.3.1|192.168.9.221:5000/eck/eck-operator:3.3.1|g' \
  /tmp/eck-operator.yaml
```

**安装 CRD 和 Operator：**

```bash
kubectl apply --server-side -f /tmp/eck-crds.yaml
kubectl apply -f /tmp/eck-operator.yaml
```

**验证 Operator 就绪：**

```bash
kubectl rollout status statefulset/elastic-operator -n elastic-system --timeout=120s
kubectl get pods -n elastic-system
# NAME                 READY   STATUS    RESTARTS   AGE
# elastic-operator-0   1/1     Running   0          ...
```

### 3.2 部署 Elasticsearch 集群

**应用 YAML（`k8s/elasticsearch-eck.yaml`）：**

```bash
kubectl apply -f k8s/elasticsearch-eck.yaml
```

此文件包含以下资源：
- `Secret/aiops-es-elastic-user`：文件认证用户（elastic/Password!）
- `Secret/aiops-es-elastic-roles`：角色映射（elastic → superuser）
- `Elasticsearch/aiops-es`：3 节点 ES 集群
- `Service/aiops-es-http-nodeport`：NodePort 30920 对外暴露

**等待集群就绪：**

```bash
kubectl get elasticsearch -n aiops -w
# NAME       HEALTH   NODES   VERSION   PHASE   AGE
# aiops-es   green    3       8.19.3    Ready   ...
```

---

## 4. 完整 YAML 清单

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: aiops-es-elastic-user
  namespace: aiops
type: kubernetes.io/basic-auth
stringData:
  username: elastic
  password: Password!
---
apiVersion: v1
kind: Secret
metadata:
  name: aiops-es-elastic-roles
  namespace: aiops
type: Opaque
stringData:
  users_roles: "superuser:elastic\n"
---
apiVersion: elasticsearch.k8s.elastic.co/v1
kind: Elasticsearch
metadata:
  name: aiops-es
  namespace: aiops
spec:
  version: 8.19.3
  image: 192.168.9.221:5000/elasticsearch:8.19.3
  auth:
    fileRealm:
      - secretName: aiops-es-elastic-user
      - secretName: aiops-es-elastic-roles
  nodeSets:
    - name: default
      count: 3
      config:
        node.store.allow_mmap: false
      podTemplate:
        spec:
          containers:
            - name: elasticsearch
              env:
                - name: ES_JAVA_OPTS
                  value: -Xms1g -Xmx1g
              resources:
                requests:
                  cpu: 500m
                  memory: 1Gi
                limits:
                  cpu: "1"
                  memory: 2Gi
      volumeClaimTemplates:
        - metadata:
            name: elasticsearch-data
          spec:
            accessModes:
              - ReadWriteOnce
            storageClassName: nfs-csi
            resources:
              requests:
                storage: 20Gi
---
apiVersion: v1
kind: Service
metadata:
  name: aiops-es-http-nodeport
  namespace: aiops
spec:
  type: NodePort
  selector:
    common.k8s.elastic.co/type: elasticsearch
    elasticsearch.k8s.elastic.co/cluster-name: aiops-es
  ports:
    - name: https
      port: 9200
      targetPort: 9200
      nodePort: 30920
```

---

## 5. 部署结果验证

### 5.1 集群状态

```
NAME       HEALTH   NODES   VERSION   PHASE   AGE
aiops-es   green    3       8.19.3    Ready   ~8m
```

### 5.2 Pod 分布

```
NAME                    READY   STATUS    NODE     IP
aiops-es-es-default-0   1/1     Running   master   10.244.219.86
aiops-es-es-default-1   1/1     Running   node03   10.244.186.200
aiops-es-es-default-2   1/1     Running   node01   10.244.196.157
```

### 5.3 存储（PVC）

```
NAME                                        STATUS   CAPACITY   STORAGECLASS
elasticsearch-data-aiops-es-es-default-0    Bound    20Gi       nfs-csi
elasticsearch-data-aiops-es-es-default-1    Bound    20Gi       nfs-csi
elasticsearch-data-aiops-es-es-default-2    Bound    20Gi       nfs-csi
```

### 5.4 集群健康接口

```bash
curl -sk -u elastic:Password! https://192.168.9.221:30920/_cluster/health?pretty
```

```json
{
  "cluster_name" : "aiops-es",
  "status" : "green",
  "number_of_nodes" : 3,
  "number_of_data_nodes" : 3,
  "active_primary_shards" : 3,
  "active_shards" : 6,
  "relocating_shards" : 0,
  "unassigned_shards" : 0,
  "active_shards_percent_as_number" : 100.0
}
```

### 5.5 节点详情

```
ip             heap%  ram%  cpu  load_1m  node.role    master  name
10.244.186.200    15    71   13     3.43  cdfhilmrstw  -       aiops-es-es-default-1
10.244.219.86     33    82   14     6.61  cdfhilmrstw  *       aiops-es-es-default-0
10.244.196.157    28    70   14     3.72  cdfhilmrstw  -       aiops-es-es-default-2
```

---

## 6. 访问信息

| 访问方式         | 地址                                        | 说明                         |
|------------------|---------------------------------------------|------------------------------|
| 外部 NodePort    | `https://192.168.9.221:30920`               | 从集群外访问                 |
| 集群内 ClusterIP | `https://aiops-es-es-http.aiops:9200`       | Pod 间调用                   |
| 用户名           | `elastic`                                   | 文件认证，superuser 角色     |
| 密码             | `Password!`                                 |                              |
| TLS 证书         | ECK 自签名（使用 `-k` 跳过验证）            |                              |

---

## 7. 常用运维命令

```bash
# 查看集群状态
kubectl get elasticsearch -n aiops

# 查看所有 ES Pod
kubectl get pods -n aiops -l common.k8s.elastic.co/type=elasticsearch

# 查看 Pod 日志
kubectl logs -n aiops aiops-es-es-default-0 -c elasticsearch --tail=50

# 集群健康检查
curl -sk -u elastic:Password! https://192.168.9.221:30920/_cluster/health?pretty

# 查看所有索引
curl -sk -u elastic:Password! https://192.168.9.221:30920/_cat/indices?v

# 查看节点
curl -sk -u elastic:Password! https://192.168.9.221:30920/_cat/nodes?v

# 查看分片
curl -sk -u elastic:Password! https://192.168.9.221:30920/_cat/shards?v

# 查看集群设置
curl -sk -u elastic:Password! https://192.168.9.221:30920/_cluster/settings?pretty

# 缩容（改 count 为 1 后 apply）
kubectl edit elasticsearch aiops-es -n aiops

# 扩容（改 count 为 5 后 apply）
kubectl edit elasticsearch aiops-es -n aiops
```

---

## 8. 注意事项

1. **mmap 关闭**：`node.store.allow_mmap: false`，适用于 NFS 存储（NFS 不支持 mmap）；本地 SSD 可设为 `true` 并配置 `vm.max_map_count=262144`。

2. **TLS 强制开启**：ECK 默认启用 TLS，客户端必须使用 `https` 且携带 `-k`（或导入 CA 证书）。

3. **获取 ECK 自签名 CA 证书**：
   ```bash
   kubectl get secret aiops-es-es-http-certs-public -n aiops \
     -o go-template='{{index .data "ca.crt" | base64decode}}' > es-ca.crt
   curl --cacert es-ca.crt -u elastic:Password! https://192.168.9.221:30920/_cluster/health
   ```

4. **fileRealm 角色映射**：ECK 的 `auth.fileRealm` 通过 `basic-auth` Secret 创建用户时不会自动分配角色，需单独提供 `users_roles` Opaque Secret（见 YAML 中 `aiops-es-elastic-roles`）。

5. **密码修改**：修改 `aiops-es-elastic-user` Secret 后，ECK 会自动热重载，无需重启 Pod。
   ```bash
   kubectl patch secret aiops-es-elastic-user -n aiops \
     -p '{"stringData":{"password":"NewPassword123!"}}'
   ```

6. **存储回收**：StorageClass ReclaimPolicy 为 `Delete`，删除 PVC 后数据会被自动清除，生产环境建议改为 `Retain`。
