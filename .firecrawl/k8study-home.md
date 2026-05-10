[**K8S可视化学习平台**](https://k8study.cn/ "返回首页")

[首页](https://k8study.cn/)

概念原理

### 入门导读 4

- [容器与镜像基础\\
\\
先理解容器、镜像、Registry 与镜像拉取链路](https://k8study.cn/knowledge/container-image-basics)
- [Kubernetes 入门导读](https://k8study.cn/knowledge/kubernetes-intro)
- [YAML 基础\\
\\
开始接触资源清单时，再补 YAML 结构与校验方法](https://k8study.cn/knowledge/yaml-basics)
- [命令行观察基础\\
\\
建立 kubectl 的基础观察路径，而不是一上来就排障](https://k8study.cn/knowledge/cli-troubleshooting-basics)

### 核心概念 9

- [Pod](https://k8study.cn/knowledge/concept-pod)
- [Pod 生命周期与调试](https://k8study.cn/knowledge/pod-lifecycle-debug)
- [Node](https://k8study.cn/knowledge/concept-node)
- [Service](https://k8study.cn/knowledge/concept-service)
- [工作负载控制器](https://k8study.cn/knowledge/concept-workloads)
- [Scheduling](https://k8study.cn/knowledge/concept-scheduling)
- [API与控制器模式](https://k8study.cn/knowledge/api-controller-pattern)
- [API  PRO](https://k8study.cn/knowledge/api-deep-dive)
- [容器运行时 (Runtime)](https://k8study.cn/knowledge/container-runtime)

### 组织与选择 3

- [Namespace\\
\\
资源隔离](https://k8study.cn/knowledge/concept-namespace)
- [Label & Selector\\
\\
标签选择器](https://k8study.cn/knowledge/concept-label)
- [Quota\\
\\
资源配额](https://k8study.cn/knowledge/concept-quota)

### 网络与安全模型 2

- [Networking\\
\\
网络模型](https://k8study.cn/knowledge/concept-networking)
- [Security PRO \\
\\
安全机制](https://k8study.cn/knowledge/concept-security)

### 可观测性模型 1

- [Observability\\
\\
监控日志](https://k8study.cn/knowledge/concept-observability)

架构部署

### 架构拆解 8

- [整体架构\\
\\
全景概览](https://k8study.cn/knowledge/architecture-overview)
- [控制平面\\
\\
Control Plane](https://k8study.cn/knowledge/control-plane)
- [工作节点\\
\\
Worker Node](https://k8study.cn/knowledge/worker-node)
- [集群维护 PRO \\
\\
Cluster Maintenance](https://k8study.cn/knowledge/cluster-maintenance)
- [节点性能优化 PRO \\
\\
Node Performance](https://k8study.cn/knowledge/node-performance)
- [GPU 与异构计算 PRO \\
\\
GPU & Device Plugin](https://k8study.cn/knowledge/gpu-heterogeneous)
- [Runtime Isolation PRO \\
\\
RuntimeClass / Kata / gVisor](https://k8study.cn/knowledge/runtime-isolation)
- [APIServer 流控 PRO \\
\\
FlowControl](https://k8study.cn/knowledge/apiserver-flowcontrol)

### 架构形态 5

- [单 Master\\
\\
开发测试环境](https://k8study.cn/knowledge/single-master)
- [高可用集群\\
\\
生产环境架构](https://k8study.cn/knowledge/ha-cluster)
- [多云架构 PRO \\
\\
Multi Cloud K8s](https://k8study.cn/knowledge/multi-cloud-architecture)
- [多集群管理 PRO \\
\\
Multi Cluster](https://k8study.cn/knowledge/multi-cluster)
- [控制平面扩展 PRO \\
\\
Control Plane Scaling](https://k8study.cn/knowledge/control-plane-scaling)

### 部署与练习 6

- [Kubeadm 部署\\
\\
标准工具部署](https://k8study.cn/knowledge/kubeadm-deployment)
- [二进制部署\\
\\
硬核部署方式](https://k8study.cn/knowledge/binary-deployment)
- [Kubectl 模拟器\\
\\
在线命令行](https://k8study.cn/knowledge/terminal-practice)
- [命令速查表\\
\\
常用命令集合](https://k8study.cn/knowledge/cheatsheet)
- [备份恢复 PRO \\
\\
Backup Restore](https://k8study.cn/knowledge/backup-restore)
- [平台基线 PRO \\
\\
Platform Baseline](https://k8study.cn/knowledge/platform-baseline)

应用编排

### 基础对象 4

- [Pod\\
\\
Pod 核心概念](https://k8study.cn/knowledge/resource-pod)
- [Node\\
\\
节点管理](https://k8study.cn/knowledge/resource-node)
- [Namespace\\
\\
命名空间](https://k8study.cn/knowledge/resource-namespace)
- [Label & Selector\\
\\
标签管理](https://k8study.cn/knowledge/resource-label)

### 配置与密钥 2

- [ConfigMap\\
\\
配置管理](https://k8study.cn/knowledge/resource-configmap)
- [Secret\\
\\
敏感信息](https://k8study.cn/knowledge/resource-secret)

### 工作负载 7

- [Deployment\\
\\
无状态应用](https://k8study.cn/knowledge/resource-deployment)
- [StatefulSet\\
\\
有状态应用](https://k8study.cn/knowledge/resource-statefulset)
- [DaemonSet\\
\\
守护进程](https://k8study.cn/knowledge/resource-daemonset)
- [Job / CronJob\\
\\
批处理任务](https://k8study.cn/knowledge/resource-job-cronjob)
- [ReplicaSet\\
\\
副本控制器](https://k8study.cn/knowledge/resource-replicaset)
- [CronJob\\
\\
定时任务](https://k8study.cn/knowledge/resource-job-cronjob)
- [有状态工作负载\\
\\
Stateful Workloads](https://k8study.cn/knowledge/stateful-workloads)

### 服务与入口 2

- [Service\\
\\
服务暴露](https://k8study.cn/knowledge/resource-service)
- [Ingress PRO \\
\\
HTTP路由](https://k8study.cn/knowledge/resource-ingress)

### 调度与配额 5

- [Scheduling PRO \\
\\
高级调度](https://k8study.cn/knowledge/resource-scheduling)
- [Quota\\
\\
资源配额](https://k8study.cn/knowledge/resource-quota)
- [LimitRange\\
\\
资源限制范围](https://k8study.cn/knowledge/resource-limitrange)
- [调度框架 PRO \\
\\
Scheduler Framework](https://k8study.cn/knowledge/scheduler-framework)
- [Kueue / Volcano PRO](https://k8study.cn/knowledge/kueue-volcano)

网络与存储

### 网络 5

- [NetworkPolicy PRO \\
\\
网络策略](https://k8study.cn/knowledge/resource-networkpolicy)
- [Gateway API PRO \\
\\
新一代网关](https://k8study.cn/knowledge/resource-gateway-api)
- [CNI & eBPF PRO \\
\\
CNI & eBPF](https://k8study.cn/knowledge/cni-ebpf)
- [Cluster DNS PRO \\
\\
DNS](https://k8study.cn/knowledge/cluster-dns)
- [出口流量治理 PRO \\
\\
Egress Governance](https://k8study.cn/knowledge/egress-governance)

### 存储 8

- [PV / PVC\\
\\
持久化存储](https://k8study.cn/knowledge/resource-pv-pvc)
- [StorageClass PRO \\
\\
存储类](https://k8study.cn/knowledge/resource-storageclass)
- [VolumeSnapshot PRO \\
\\
快照备份](https://k8study.cn/knowledge/resource-volumesnapshot)
- [Volume\\
\\
存储卷](https://k8study.cn/knowledge/resource-volume)
- [CSI 存储架构 PRO](https://k8study.cn/knowledge/resource-csi)
- [数据一致性 PRO \\
\\
Data Consistency](https://k8study.cn/knowledge/data-consistency)
- [数据迁移 PRO \\
\\
Data Migration](https://k8study.cn/knowledge/data-migration)
- [Local PV / Topology Aware Routing PRO](https://k8study.cn/knowledge/local-pv-topology-routing)

安全与治理

### 安全 10

- [RBAC](https://k8study.cn/knowledge/concept-rbac)
- [ServiceAccount](https://k8study.cn/knowledge/resource-serviceaccount)
- [镜像安全 PRO](https://k8study.cn/knowledge/image-security)
- [密钥管理进阶 PRO](https://k8study.cn/knowledge/secret-management-advanced)
- [认证与授权 PRO](https://k8study.cn/knowledge/authentication-authorization)
- [供应链安全 PRO](https://k8study.cn/knowledge/supply-chain-security)
- [密钥轮转 PRO](https://k8study.cn/knowledge/secret-rotation)
- [OIDC 与 SSO PRO](https://k8study.cn/knowledge/oidc-sso)
- [零信任网络 PRO](https://k8study.cn/knowledge/zero-trust)
- [运行时安全 PRO](https://k8study.cn/knowledge/runtime-security)

### 治理 7

- [Governance PRO \\
\\
策略治理](https://k8study.cn/knowledge/resource-governance)
- [策略引擎 PRO \\
\\
Policy Engine](https://k8study.cn/knowledge/policy-engine)
- [策略测试 PRO \\
\\
Policy Testing](https://k8study.cn/knowledge/policy-testing)
- [全链路限流 PRO \\
\\
End-to-End RateLimiting](https://k8study.cn/knowledge/rate-limiting)
- [依赖治理 PRO \\
\\
Dependency Gov](https://k8study.cn/knowledge/dependency-governance)
- [持续合规 PRO \\
\\
Compliance](https://k8study.cn/knowledge/continuous-compliance)
- [多租户隔离 PRO \\
\\
Multi Tenancy](https://k8study.cn/knowledge/multi-tenancy)

运维生态

### 可观测性 4

- [Observability\\
\\
全链路监控](https://k8study.cn/knowledge/concept-observability)
- [Prometheus & Grafana PRO \\
\\
监控](https://k8study.cn/knowledge/observability-prometheus)
- [日志架构 (EFK/Loki) PRO \\
\\
日志采集与存储架构](https://k8study.cn/knowledge/logging-architecture)
- [链路追踪 PRO \\
\\
Tracing](https://k8study.cn/knowledge/observability-tracing)

### 弹性与容量 7

- [HPA PRO \\
\\
水平伸缩](https://k8study.cn/knowledge/resource-hpa)
- [VPA PRO \\
\\
垂直伸缩](https://k8study.cn/knowledge/resource-vpa)
- [PDB PRO \\
\\
Pod中断预算](https://k8study.cn/knowledge/resource-pdb)
- [Karpenter PRO](https://k8study.cn/knowledge/karpenter)
- [容量规划 PRO \\
\\
Capacity Planning](https://k8study.cn/knowledge/capacity-planning)
- [FinOps 成本优化 PRO \\
\\
FinOps](https://k8study.cn/knowledge/finops-cost)
- [容量预测 PRO \\
\\
Capacity Forecasting](https://k8study.cn/knowledge/capacity-forecasting)

### 排障 4

- [Troubleshooting PRO \\
\\
故障排查](https://k8study.cn/knowledge/resource-troubleshooting)
- [FAQ\\
\\
常见问题解答](https://k8study.cn/faq)
- [混沌工程 PRO \\
\\
Chaos Engineering](https://k8study.cn/knowledge/chaos-engineering)
- [OnCall 响应 PRO \\
\\
OnCall](https://k8study.cn/knowledge/oncall-response)

### 生态扩展 9

- [Helm PRO](https://k8study.cn/knowledge/resource-helm)
- [CRD & Operator PRO](https://k8study.cn/knowledge/resource-crd)
- [GitOps (ArgoCD) PRO](https://k8study.cn/knowledge/gitops-argocd)
- [Kustomize PRO](https://k8study.cn/knowledge/resource-kustomize)
- [Service Mesh PRO](https://k8study.cn/knowledge/resource-servicemesh)
- [CI/CD 流水线 PRO](https://k8study.cn/knowledge/cicd-pipeline)
- [渐进式交付 PRO](https://k8study.cn/knowledge/progressive-delivery)
- [多集群应用分发 PRO](https://k8study.cn/knowledge/multicluster-distribution)
- [Service Mesh 生产 PRO](https://k8study.cn/knowledge/service-mesh-production)

### 全景视图 1

- [资源关系图谱\\
\\
可视化拓扑](https://k8study.cn/resource-relations)

[学习地图 · 0/103 · 0%](https://k8study.cn/knowledge/topic-map "学习地图 · 0/103 · 0%")[登录](https://k8study.cn/login) [注册](https://k8study.cn/register)

关注我\|欢迎大家关注公众号：香菜爱Linux，学习更多运维知识！

## 轻松理解Kubernetes核心原理

基于2D可视化动画，直观展示 K8s 核心概念、架构原理和资源调度流程，让初学者快速掌握 K8s 核心知识。

[开始学习](https://k8study.cn/knowledge/kubernetes-intro) [先补容器基础](https://k8study.cn/knowledge/container-image-basics) [架构解析](https://k8study.cn/knowledge/architecture-overview)

### 2D可视化

直观展示组件交互

### 实操模拟

在线执行kubectl

### 响应式

多端适配学习

k8s-cluster-view

Running

User

kubectl

Control Plane

etcd

API Server

sched

c-m

Node-1

Pod

kubelet

proxy

Node-2

Pod

kubelet

proxy

等待调度指令...

动画展示 K8S 核心组件交互流程

开始调度

0.5x

### 每日测验

K8S 知识点  换一批

判断

#### 判断题：只要做过漏洞扫描，就完全不需要再校验镜像来源。

提交答案

上一题 1 / 20 下一题

### 推荐学习路径

循序渐进的学习路线，助你从零开始掌握 Kubernetes

1

#### 入门导读

先理解 Kubernetes 为什么出现、解决什么问题、学习路径怎么展开。

[开始](https://k8study.cn/knowledge/kubernetes-intro)

2

#### 架构原理

控制平面与工作节点组件交互及集群机制。

[开始](https://k8study.cn/knowledge/architecture-overview)

3

#### 核心概念

Pod、Node、Service 等基础对象与 Kubernetes 的设计哲学。

[开始](https://k8study.cn/knowledge/concept-pod)

4

#### 清单与命令

开始接触 YAML 清单结构，以及 kubectl 的基础观察方式。

[开始](https://k8study.cn/knowledge/yaml-basics)

5

#### 基础资源

Deployment、ConfigMap 等资源配置与应用部署。

[开始](https://k8study.cn/knowledge/resource-deployment)

6

#### 进阶与生态

安全治理、平台工程、Service Mesh 等生产级专题。

[开始](https://k8study.cn/knowledge/concept-security)

## 为不同阶段的学习者量身定制

无论你是刚接触容器技术的新手，还是寻求进阶的资深工程师，我们都有适合你的学习路径。

### 入门阶段

从零开始，了解容器化技术基础，掌握 Docker 基本操作，理解 Kubernetes 的核心概念（Pod, Node, Service）和架构设计。

- 容器技术基础
- K8s 核心组件
- 声明式配置入门

[开始入门学习](https://k8study.cn/knowledge/concept-pod)

### 进阶实战

深入学习资源编排，掌握 Deployment, StatefulSet 等高级控制器，学习存储、网络配置以及常用的应用部署模式。

- 工作负载管理
- 服务发现与负载均衡
- 持久化存储配置

[进入进阶课程](https://k8study.cn/knowledge/resource-deployment)

### 高阶精通

探索 Kubernetes 高可用架构，学习集群安全、高级调度、CRD 开发、Operator 模式以及 Service Mesh 等云原生生态技术。

- 安全策略与 RBAC
- 弹性伸缩与调度
- 云原生生态扩展

[挑战高阶内容](https://k8study.cn/knowledge/resource-servicemesh)

© 2026 K8S Learn. 香菜爱Linux

[京ICP备2021027351号-1](https://beian.miit.gov.cn/)

回到顶部