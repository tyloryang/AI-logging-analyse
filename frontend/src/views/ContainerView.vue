<template>
  <div class="container-view">
    <div class="page-header">
      <div class="header-left">
        <h1>容器管理</h1>
        <span class="subtitle">多集群 Kubernetes 资源总览与 kubeconfig 管理</span>
      </div>
      <div class="header-right">
        <select v-model="activeNs" class="ns-select" :disabled="!activeClusterId || loading" @change="fetchAll">
          <option value="">全部命名空间</option>
          <option v-for="ns in namespaces" :key="ns.name" :value="ns.name">{{ ns.name }}</option>
        </select>
        <button v-if="canManageClusters" class="btn-ghost" :disabled="!activeCluster" @click="openEditCluster">编辑</button>
        <button v-if="canManageClusters" class="btn-ghost" :disabled="!activeCluster" @click="testActiveCluster">测试</button>
        <button v-if="canManageClusters" class="btn-ghost danger" :disabled="!activeCluster" @click="removeCluster">删除</button>
        <button class="btn-refresh" @click="fetchAll" :disabled="loading || !activeClusterId">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <polyline points="23 4 23 10 17 10" />
            <polyline points="1 20 1 14 7 14" />
            <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
          </svg>
          刷新
        </button>
      </div>
    </div>

    <div v-if="clusterTestMsg" class="cluster-banner" :class="clusterTestResult ? 'ok' : 'err'">
      {{ clusterTestMsg }}
    </div>

    <div v-if="!clusters.length" class="empty-state">
      <div class="empty-card">
        <div class="empty-title">还没有 Kubernetes 集群</div>
        <div class="empty-subtitle">现在支持多个 kubeconfig 分别接入不同集群，并设置默认集群作为默认访问目标。</div>
        <button v-if="canManageClusters" class="btn-primary-lg" @click="openAddCluster">+ 添加第一个集群</button>
      </div>
    </div>

    <div v-else class="workspace-body">
      <aside class="cluster-sidebar">
        <div class="sidebar-head">
          <div>
            <div class="sidebar-title">集群列表</div>
            <div class="sidebar-subtitle">{{ sortedClusters.length }} 个集群</div>
          </div>
          <button v-if="canManageClusters" class="btn-ghost compact" @click="openAddCluster">+ 新建</button>
        </div>

        <div class="cluster-card-list">
          <div
            v-for="cluster in sortedClusters"
            :key="cluster.id"
            class="cluster-card"
            :class="{ active: activeClusterId === cluster.id, default: cluster.is_default }"
            @click="selectCluster(cluster.id)"
          >
            <div class="cluster-card-top">
              <div class="cluster-title-row">
                <div class="cluster-card-name">{{ cluster.name }}</div>
                <span v-if="cluster.is_default" class="default-badge">默认</span>
              </div>
              <button
                v-if="canManageClusters && !cluster.is_default"
                class="cluster-link"
                @click.stop="setDefaultCluster(cluster)"
              >
                设为默认
              </button>
            </div>
            <div class="cluster-card-context">{{ cluster.context || '默认 context' }}</div>
            <div class="cluster-card-desc">{{ cluster.description || '未填写描述' }}</div>
            <div class="cluster-card-path mono">{{ cluster.kubeconfig }}</div>
          </div>
        </div>
      </aside>

      <section class="content-area">
        <div class="cluster-meta">
          <div class="meta-card">
            <div class="meta-label">当前集群</div>
            <div class="meta-value">{{ activeCluster?.name || '未选择' }}</div>
            <div class="meta-sub">{{ activeCluster?.context || '默认 context' }}</div>
          </div>
          <div class="meta-card">
            <div class="meta-label">默认访问</div>
            <div class="meta-value">{{ activeCluster?.is_default ? '是' : '否' }}</div>
            <div class="meta-sub">{{ activeCluster?.is_default ? '未指定 cluster_id 时默认使用该集群' : '可在左侧卡片中设为默认集群' }}</div>
          </div>
          <div class="meta-card wide">
            <div class="meta-label">kubeconfig</div>
            <div class="meta-value mono">{{ activeCluster?.kubeconfig || '未配置' }}</div>
            <div class="meta-sub">{{ activeCluster?.description || '可使用不同 kubeconfig 路径分别管理多个集群' }}</div>
          </div>
        </div>

        <div v-if="error" class="error-banner">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          {{ error }}
        </div>

        <div class="summary-row" v-if="summary">
          <div class="stat-card" :class="{ warn: summary.nodes.ready < summary.nodes.total }">
            <div class="stat-icon node">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <rect x="2" y="3" width="20" height="14" rx="2" />
                <line x1="8" y1="21" x2="16" y2="21" />
                <line x1="12" y1="17" x2="12" y2="21" />
              </svg>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ summary.nodes.ready }}<span class="stat-total">/{{ summary.nodes.total }}</span></div>
              <div class="stat-label">节点 Ready</div>
            </div>
          </div>
          <div class="stat-card" :class="{ warn: summary.pods.running < summary.pods.total }">
            <div class="stat-icon pod">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" />
              </svg>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ summary.pods.running }}<span class="stat-total">/{{ summary.pods.total }}</span></div>
              <div class="stat-label">Pod Running</div>
            </div>
          </div>
          <div class="stat-card" :class="{ warn: summary.deployments.ready < summary.deployments.total }">
            <div class="stat-icon deploy">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <polyline points="16 18 22 12 16 6" />
                <polyline points="8 6 2 12 8 18" />
              </svg>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ summary.deployments.ready }}<span class="stat-total">/{{ summary.deployments.total }}</span></div>
              <div class="stat-label">Deployment Ready</div>
            </div>
          </div>
          <div class="stat-card" :class="{ warn: summary.daemonSets?.ready < summary.daemonSets?.total }">
            <div class="stat-icon daemon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
              </svg>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ summary.daemonSets?.ready || 0 }}<span class="stat-total">/{{ summary.daemonSets?.total || 0 }}</span></div>
              <div class="stat-label">DaemonSet Ready</div>
            </div>
          </div>
          <div class="stat-card" :class="{ warn: summary.statefulSets?.ready < summary.statefulSets?.total }">
            <div class="stat-icon stateful">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <rect x="4" y="4" width="16" height="5" rx="1.5" />
                <rect x="4" y="10" width="16" height="5" rx="1.5" />
                <rect x="4" y="16" width="16" height="4" rx="1.5" />
              </svg>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ summary.statefulSets?.ready || 0 }}<span class="stat-total">/{{ summary.statefulSets?.total || 0 }}</span></div>
              <div class="stat-label">StatefulSet Ready</div>
            </div>
          </div>
          <div class="stat-card" :class="{ warn: summary.jobs?.complete < summary.jobs?.total }">
            <div class="stat-icon job">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <path d="M8 6h13M8 12h13M8 18h13" />
                <path d="M3 6l1 1 2-2M3 12l1 1 2-2M3 18l1 1 2-2" />
              </svg>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ summary.jobs?.complete || 0 }}<span class="stat-total">/{{ summary.jobs?.total || 0 }}</span></div>
              <div class="stat-label">Job Complete</div>
            </div>
          </div>
          <div class="stat-card" :class="{ warn: (summary.cronJobs?.suspended || 0) > 0 }">
            <div class="stat-icon cron">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <circle cx="12" cy="12" r="8" />
                <path d="M12 8v5l3 2" />
              </svg>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ summary.cronJobs?.total || 0 }}</div>
              <div class="stat-label">CronJob 总数 / 活跃 {{ summary.cronJobs?.active || 0 }}</div>
            </div>
          </div>
        </div>

        <div class="tab-row">
          <button
            v-for="tab in TABS"
            :key="tab.id"
            class="tab-btn"
            :class="{ active: activeTab === tab.id }"
            @click="activeTab = tab.id"
          >
            {{ tab.label }}
            <span class="tab-count">{{ tabCount(tab.id) }}</span>
          </button>
        </div>

        <div v-if="loading" class="loading-row">
          <span class="spinner"></span>
          正在加载 {{ activeCluster?.name }} ...
        </div>

        <div v-else-if="activeTab === 'pods'" class="table-wrap">
          <table class="k8s-table">
            <thead>
              <tr>
                <th>名称</th><th>命名空间</th><th>状态</th><th>节点</th><th>容器</th><th>重启</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!pods.length"><td colspan="8" class="empty">暂无数据</td></tr>
              <tr v-for="pod in pods" :key="pod.namespace + '/' + pod.name">
                <td class="name-cell">{{ pod.name }}</td>
                <td><span class="ns-tag">{{ pod.namespace }}</span></td>
                <td><span class="status-dot" :class="pod.statusClass"></span>{{ pod.status }}</td>
                <td class="mono small">{{ pod.node || '-' }}</td>
                <td>
                  <span
                    v-for="container in pod.containers"
                    :key="container.name"
                    class="container-tag"
                    :class="{ ready: container.ready }"
                  >
                    {{ container.name }}
                  </span>
                </td>
                <td :class="{ 'col-warn': pod.restarts > 0 }">{{ pod.restarts }}</td>
                <td class="muted">{{ pod.age }}</td>
                <td class="action-cell">
                  <div class="action-group">
                    <button class="action-btn" @click="openResourceDetail('pod', pod)">详情</button>
                    <button class="action-btn" @click="openResourceLogs('pod', pod)">日志</button>
                    <button
                      class="action-btn exec-btn"
                      :disabled="pod.status !== 'Running'"
                      :title="pod.status !== 'Running' ? 'Pod 未 Running，无法进入终端' : '进入容器终端'"
                      @click="openExecModal(pod)"
                    >终端</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="activeTab === 'deployments'" class="table-wrap">
          <table class="k8s-table">
            <thead>
              <tr>
                <th>名称</th><th>命名空间</th><th>状态</th><th>Ready</th><th>镜像</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!deployments.length"><td colspan="7" class="empty">暂无数据</td></tr>
              <tr v-for="deployment in deployments" :key="deployment.namespace + '/' + deployment.name">
                <td class="name-cell">{{ deployment.name }}</td>
                <td><span class="ns-tag">{{ deployment.namespace }}</span></td>
                <td><span class="status-dot" :class="deployment.statusClass"></span>{{ deployment.status }}</td>
                <td>{{ deployment.ready }}/{{ deployment.desired }}</td>
                <td class="mono small">{{ deployment.images.join(', ') }}</td>
                <td class="muted">{{ deployment.age }}</td>
                <td class="action-cell">
                  <div class="action-group">
                    <button class="action-btn" @click="openResourceDetail('deployment', deployment)">详情</button>
                    <button class="action-btn" @click="openResourceLogs('deployment', deployment)">日志</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="activeTab === 'daemonSets'" class="table-wrap">
          <table class="k8s-table">
            <thead>
              <tr>
                <th>名称</th><th>命名空间</th><th>状态</th><th>Ready</th><th>当前</th><th>可用</th><th>镜像</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!daemonSets.length"><td colspan="9" class="empty">暂无数据</td></tr>
              <tr v-for="daemonSet in daemonSets" :key="daemonSet.namespace + '/' + daemonSet.name">
                <td class="name-cell">{{ daemonSet.name }}</td>
                <td><span class="ns-tag">{{ daemonSet.namespace }}</span></td>
                <td><span class="status-dot" :class="daemonSet.statusClass"></span>{{ daemonSet.status }}</td>
                <td>{{ daemonSet.ready }}/{{ daemonSet.desired }}</td>
                <td>{{ daemonSet.current }}/{{ daemonSet.updated }}</td>
                <td>{{ daemonSet.available }}</td>
                <td class="mono small">{{ daemonSet.images.join(', ') }}</td>
                <td class="muted">{{ daemonSet.age }}</td>
                <td class="action-cell">
                  <div class="action-group">
                    <button class="action-btn" @click="openResourceDetail('daemonset', daemonSet)">详情</button>
                    <button class="action-btn" @click="openResourceLogs('daemonset', daemonSet)">日志</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="activeTab === 'statefulSets'" class="table-wrap">
          <table class="k8s-table">
            <thead>
              <tr>
                <th>名称</th><th>命名空间</th><th>状态</th><th>Ready</th><th>当前</th><th>更新</th><th>镜像</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!statefulSets.length"><td colspan="9" class="empty">暂无数据</td></tr>
              <tr v-for="statefulSet in statefulSets" :key="statefulSet.namespace + '/' + statefulSet.name">
                <td class="name-cell">{{ statefulSet.name }}</td>
                <td><span class="ns-tag">{{ statefulSet.namespace }}</span></td>
                <td><span class="status-dot" :class="statefulSet.statusClass"></span>{{ statefulSet.status }}</td>
                <td>{{ statefulSet.ready }}/{{ statefulSet.desired }}</td>
                <td>{{ statefulSet.current }}</td>
                <td>{{ statefulSet.updated }}</td>
                <td class="mono small">{{ statefulSet.images.join(', ') }}</td>
                <td class="muted">{{ statefulSet.age }}</td>
                <td class="action-cell">
                  <div class="action-group">
                    <button class="action-btn" @click="openResourceDetail('statefulset', statefulSet)">详情</button>
                    <button class="action-btn" @click="openResourceLogs('statefulset', statefulSet)">日志</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="activeTab === 'jobs'" class="table-wrap">
          <table class="k8s-table">
            <thead>
              <tr>
                <th>名称</th><th>命名空间</th><th>状态</th><th>完成</th><th>并发</th><th>运行</th><th>失败</th><th>镜像</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!jobs.length"><td colspan="10" class="empty">暂无数据</td></tr>
              <tr v-for="job in jobs" :key="job.namespace + '/' + job.name">
                <td class="name-cell">{{ job.name }}</td>
                <td><span class="ns-tag">{{ job.namespace }}</span></td>
                <td><span class="status-dot" :class="job.statusClass"></span>{{ job.status }}</td>
                <td>{{ job.succeeded }}/{{ job.completions }}</td>
                <td>{{ job.parallelism }}</td>
                <td>{{ job.active }}</td>
                <td :class="{ 'col-warn': job.failed > 0 }">{{ job.failed }}</td>
                <td class="mono small">{{ job.images.join(', ') }}</td>
                <td class="muted">{{ job.age }}</td>
                <td class="action-cell">
                  <div class="action-group">
                    <button class="action-btn" @click="openResourceDetail('job', job)">详情</button>
                    <button class="action-btn" @click="openResourceLogs('job', job)">日志</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="activeTab === 'cronJobs'" class="table-wrap">
          <table class="k8s-table">
            <thead>
              <tr>
                <th>名称</th><th>命名空间</th><th>状态</th><th>调度</th><th>挂起</th><th>活跃 Job</th><th>最近调度</th><th>最近成功</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!cronJobs.length"><td colspan="10" class="empty">暂无数据</td></tr>
              <tr v-for="cronJob in cronJobs" :key="cronJob.namespace + '/' + cronJob.name">
                <td class="name-cell">{{ cronJob.name }}</td>
                <td><span class="ns-tag">{{ cronJob.namespace }}</span></td>
                <td><span class="status-dot" :class="cronJob.statusClass"></span>{{ cronJob.status }}</td>
                <td class="mono small">{{ cronJob.schedule }}</td>
                <td>{{ cronJob.suspend ? '是' : '否' }}</td>
                <td class="mono small">{{ cronJob.activeJobs.length ? cronJob.activeJobs.join(', ') : cronJob.active }}</td>
                <td class="muted">{{ cronJob.lastScheduleTime || '-' }}</td>
                <td class="muted">{{ cronJob.lastSuccessfulTime || '-' }}</td>
                <td class="muted">{{ cronJob.age }}</td>
                <td class="action-cell">
                  <div class="action-group">
                    <button class="action-btn" @click="openResourceDetail('cronjob', cronJob)">详情</button>
                    <button class="action-btn" @click="openResourceLogs('cronjob', cronJob)">日志</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="activeTab === 'services'" class="table-wrap">
          <table class="k8s-table">
            <thead>
              <tr>
                <th>名称</th><th>命名空间</th><th>类型</th><th>ClusterIP</th><th>端口</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!services.length"><td colspan="7" class="empty">暂无数据</td></tr>
              <tr v-for="service in services" :key="service.namespace + '/' + service.name">
                <td class="name-cell">{{ service.name }}</td>
                <td><span class="ns-tag">{{ service.namespace }}</span></td>
                <td><span class="svc-type" :class="service.type.toLowerCase()">{{ service.type }}</span></td>
                <td class="mono small">{{ service.clusterIP }}</td>
                <td class="mono small">{{ service.ports.join(', ') }}</td>
                <td class="muted">{{ service.age }}</td>
                <td class="action-cell">
                  <div class="action-group">
                    <button class="action-btn" @click="openResourceDetail('service', service)">详情</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-else-if="activeTab === 'nodes'" class="table-wrap">
          <table class="k8s-table">
            <thead>
              <tr>
                <th>名称</th><th>状态</th><th>角色</th><th>版本</th><th>OS</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!nodes.length"><td colspan="7" class="empty">暂无数据</td></tr>
              <tr v-for="node in nodes" :key="node.name">
                <td class="name-cell">{{ node.name }}</td>
                <td><span class="status-dot" :class="node.statusClass"></span>{{ node.status }}</td>
                <td><span class="role-tag">{{ node.roles }}</span></td>
                <td class="mono small">{{ node.version }}</td>
                <td class="small muted">{{ node.os }}</td>
                <td class="muted">{{ node.age }}</td>
                <td class="action-cell">
                  <div class="action-group">
                    <button class="action-btn" @click="openResourceDetail('node', node)">详情</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <div v-if="showClusterModal" class="modal-mask" @click.self="closeClusterModal">
      <div class="modal-card">
        <div class="modal-title">{{ editingClusterId ? '编辑集群' : '添加集群' }}</div>
        <div class="modal-body">
          <label class="field">
            <span>集群名称</span>
            <input v-model="clusterForm.name" class="form-input" placeholder="生产-k8s-01" />
          </label>
          <label class="field">
            <span>kubeconfig 路径</span>
            <input v-model="clusterForm.kubeconfig" class="form-input" placeholder="backend/data/kubeconfig/prod 或 ~/.kube/config" />
          </label>
          <label class="field">
            <span>context（可选）</span>
            <input v-model="clusterForm.context" class="form-input" placeholder="prod-context" />
          </label>
          <label class="field">
            <span>说明（可选）</span>
            <textarea v-model="clusterForm.description" class="form-textarea" rows="3" placeholder="例如：生产集群 / 华东机房"></textarea>
          </label>
          <div class="modal-tip">
            kubeconfig 按文件路径读取，不限制后缀；支持相对路径、Windows 路径和 Linux 路径，相对路径会优先按项目根目录解析。
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="closeClusterModal">取消</button>
          <button class="btn-primary-lg" @click="saveCluster">{{ editingClusterId ? '保存修改' : '确认添加' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showDetailModal" class="modal-mask" @click.self="closeDetailModal">
      <div class="modal-card detail-modal-card">
        <div class="modal-title">{{ detailModalTitle }}</div>
        <div class="modal-body">
          <div class="resource-head">
            <span class="resource-kind">{{ kindLabel(detailMeta.kind) }}</span>
            <span class="mono">{{ detailMeta.name }}</span>
            <span v-if="detailMeta.namespace" class="ns-tag">{{ detailMeta.namespace }}</span>
          </div>
          <div v-if="detailError" class="modal-tip modal-tip-error">{{ detailError }}</div>
          <div v-else class="code-panel">
            <div v-if="detailLoading" class="loading-row compact">
              <span class="spinner"></span>
              正在加载详情...
            </div>
            <pre v-else class="json-view">{{ detailText }}</pre>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="closeDetailModal">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="showLogModal" class="modal-mask" @click.self="closeLogModal">
      <div class="modal-card log-modal-card">
        <div class="modal-title">{{ logModalTitle }}</div>
        <div class="modal-body">
          <div class="resource-head">
            <span class="resource-kind">{{ kindLabel(logMeta.kind) }}</span>
            <span class="mono">{{ logMeta.name }}</span>
            <span v-if="logMeta.namespace" class="ns-tag">{{ logMeta.namespace }}</span>
          </div>
          <div class="log-toolbar">
            <label class="field toolbar-field">
              <span>Pod</span>
              <select
                v-model="selectedLogPod"
                class="form-input"
                :disabled="!logPods.length || logLoading"
                @change="handleLogPodChange"
              >
                <option v-for="pod in logPods" :key="pod.name" :value="pod.name">{{ pod.name }}</option>
              </select>
            </label>
            <label class="field toolbar-field">
              <span>容器</span>
              <select
                v-model="selectedLogContainer"
                class="form-input"
                :disabled="!selectedLogContainers.length || logLoading"
                @change="handleLogContainerChange"
              >
                <option v-for="container in selectedLogContainers" :key="container.name" :value="container.name">{{ container.name }}</option>
              </select>
            </label>
            <label class="field toolbar-field tail-field">
              <span>行数</span>
              <input
                v-model.number="logTailLines"
                type="number"
                min="20"
                max="2000"
                class="form-input"
                @change="loadSelectedPodLogs"
              />
            </label>
            <button class="btn-ghost refresh-log-btn" :disabled="!selectedLogPod || logLoading" @click="loadSelectedPodLogs">
              刷新日志
            </button>
          </div>
          <div v-if="logError" class="modal-tip modal-tip-error">{{ logError }}</div>
          <div class="code-panel">
            <div v-if="logLoading" class="loading-row compact">
              <span class="spinner"></span>
              正在加载日志...
            </div>
            <pre v-else class="log-view">{{ logText || '暂无日志输出' }}</pre>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="closeLogModal">关闭</button>
        </div>
      </div>
    </div>
    <!-- Container Exec 终端弹窗 -->
    <div v-if="showExecModal" class="exec-modal-mask" @click.self="closeExecModal">
      <div class="exec-modal-card">
        <div class="exec-modal-header">
          <div class="exec-modal-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
            容器终端
            <span class="exec-meta">{{ execMeta.pod }}</span>
            <span v-if="execMeta.container" class="exec-meta dim">/ {{ execMeta.container }}</span>
          </div>
          <div class="exec-controls">
            <select v-model="execContainer" class="exec-select" @change="restartExec" :disabled="execConnected">
              <option v-for="c in execMeta.containers" :key="c.name" :value="c.name">{{ c.name }}</option>
            </select>
            <select v-model="execShell" class="exec-select" :disabled="execConnected">
              <option value="/bin/sh">sh</option>
              <option value="/bin/bash">bash</option>
            </select>
            <button class="exec-btn-sm" @click="restartExec" :disabled="execConnecting">
              {{ execConnecting ? '连接中...' : execConnected ? '重连' : '连接' }}
            </button>
            <button class="exec-btn-sm close" @click="closeExecModal">✕</button>
          </div>
        </div>
        <div class="exec-term-wrap" ref="execTermEl"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, reactive, ref, nextTick, watch } from 'vue'
import { api } from '../api/index.js'
import { useAuthStore } from '../stores/auth.js'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'

const authStore = useAuthStore()

const TABS = [
  { id: 'pods', label: 'Pods' },
  { id: 'deployments', label: 'Deployments' },
  { id: 'daemonSets', label: 'DaemonSets' },
  { id: 'statefulSets', label: 'StatefulSets' },
  { id: 'jobs', label: 'Jobs' },
  { id: 'cronJobs', label: 'CronJobs' },
  { id: 'services', label: 'Services' },
  { id: 'nodes', label: 'Nodes' },
]
const KIND_LABELS = {
  pod: 'Pod',
  deployment: 'Deployment',
  daemonset: 'DaemonSet',
  statefulset: 'StatefulSet',
  job: 'Job',
  cronjob: 'CronJob',
  service: 'Service',
  node: 'Node',
}
const LOGGABLE_KINDS = new Set(['pod', 'deployment', 'daemonset', 'statefulset', 'job', 'cronjob'])

const activeTab = ref('pods')
const activeClusterId = ref('')
const activeNs = ref('')
const loading = ref(false)
const error = ref('')

const clusters = ref([])
const summary = ref(null)
const namespaces = ref([])
const pods = ref([])
const deployments = ref([])
const daemonSets = ref([])
const statefulSets = ref([])
const jobs = ref([])
const cronJobs = ref([])
const services = ref([])
const nodes = ref([])
const showDetailModal = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detailData = ref(null)
const detailMeta = reactive({
  kind: '',
  name: '',
  namespace: '',
})
const showLogModal = ref(false)
const logLoading = ref(false)
const logError = ref('')
const logText = ref('')
const logTailLines = ref(200)
const logPods = ref([])
const selectedLogPod = ref('')
const selectedLogContainer = ref('')
const logMeta = reactive({
  kind: '',
  name: '',
  namespace: '',
})

const showClusterModal = ref(false)
const editingClusterId = ref('')
const clusterTestResult = ref(null)
const clusterTestMsg = ref('')
const clusterForm = reactive({
  name: '',
  kubeconfig: '',
  context: '',
  description: '',
})

const activeCluster = computed(() => clusters.value.find(item => item.id === activeClusterId.value) || null)
const sortedClusters = computed(() => (
  [...clusters.value].sort((left, right) => {
    if (left.is_default === right.is_default) return left.name.localeCompare(right.name, 'zh-CN')
    return left.is_default ? -1 : 1
  })
))
const detailText = computed(() => (detailData.value ? JSON.stringify(detailData.value, null, 2) : ''))
const detailModalTitle = computed(() => `${kindLabel(detailMeta.kind)} 详情`)
const logModalTitle = computed(() => `${kindLabel(logMeta.kind)} 日志`)
const selectedLogPodData = computed(() => logPods.value.find(item => item.name === selectedLogPod.value) || null)
const selectedLogContainers = computed(() => selectedLogPodData.value?.containers || [])
const canManageClusters = computed(() => authStore.isAdmin)

function normalizeKind(kind) {
  const value = String(kind || '').trim().toLowerCase().replace(/[-_]/g, '')
  const aliases = {
    pods: 'pod',
    deployments: 'deployment',
    daemonsets: 'daemonset',
    statefulsets: 'statefulset',
    jobs: 'job',
    cronjobs: 'cronjob',
    services: 'service',
    nodes: 'node',
  }
  return aliases[value] || value
}

function kindLabel(kind) {
  return KIND_LABELS[normalizeKind(kind)] || String(kind || '')
}

function canViewLogs(kind) {
  return LOGGABLE_KINDS.has(normalizeKind(kind))
}

function clampTailLines(value) {
  const number = Number(value) || 200
  return Math.max(20, Math.min(2000, Math.round(number)))
}

function pickDefaultContainer(pod) {
  return pod?.containers?.[0]?.name || ''
}

function resetDetailState() {
  detailLoading.value = false
  detailError.value = ''
  detailData.value = null
  Object.assign(detailMeta, { kind: '', name: '', namespace: '' })
}

function closeDetailModal() {
  showDetailModal.value = false
  resetDetailState()
}

function resetLogState() {
  logLoading.value = false
  logError.value = ''
  logText.value = ''
  logTailLines.value = 200
  logPods.value = []
  selectedLogPod.value = ''
  selectedLogContainer.value = ''
  Object.assign(logMeta, { kind: '', name: '', namespace: '' })
}

function closeLogModal() {
  showLogModal.value = false
  resetLogState()
}

function resetData() {
  summary.value = null
  namespaces.value = []
  pods.value = []
  deployments.value = []
  daemonSets.value = []
  statefulSets.value = []
  jobs.value = []
  cronJobs.value = []
  services.value = []
  nodes.value = []
  closeDetailModal()
  closeLogModal()
}

function resetNotice() {
  clusterTestResult.value = null
  clusterTestMsg.value = ''
}

function tabCount(id) {
  const mapping = {
    pods: pods.value.length,
    deployments: deployments.value.length,
    daemonSets: daemonSets.value.length,
    statefulSets: statefulSets.value.length,
    jobs: jobs.value.length,
    cronJobs: cronJobs.value.length,
    services: services.value.length,
    nodes: nodes.value.length,
  }
  return mapping[id] ?? 0
}

async function loadClusters() {
  try {
    clusters.value = await api.k8sClusters()
    if (!clusters.value.length) {
      activeClusterId.value = ''
      resetData()
      return
    }
    if (!clusters.value.some(item => item.id === activeClusterId.value)) {
      activeClusterId.value = clusters.value.find(item => item.is_default)?.id || clusters.value[0].id
    }
  } catch (e) {
    clusters.value = []
    activeClusterId.value = ''
    error.value = `加载集群失败: ${e}`
  }
}

async function fetchAll() {
  if (!activeClusterId.value) {
    resetData()
    return
  }
  loading.value = true
  error.value = ''
  try {
    const ns = activeNs.value || undefined
    const clusterId = activeClusterId.value
    const [sum, nsList, podList, depList, daemonSetList, statefulSetList, jobList, cronJobList, svcList, nodeList] = await Promise.all([
      api.k8sSummary(clusterId).catch(() => null),
      api.k8sNamespaces(clusterId).catch(() => []),
      api.k8sPods(clusterId, ns).catch(() => []),
      api.k8sDeployments(clusterId, ns).catch(() => []),
      api.k8sDaemonSets(clusterId, ns).catch(() => []),
      api.k8sStatefulSets(clusterId, ns).catch(() => []),
      api.k8sJobs(clusterId, ns).catch(() => []),
      api.k8sCronJobs(clusterId, ns).catch(() => []),
      api.k8sServices(clusterId, ns).catch(() => []),
      api.k8sNodes(clusterId).catch(() => []),
    ])
    summary.value = sum
    namespaces.value = nsList
    pods.value = podList
    deployments.value = depList
    daemonSets.value = daemonSetList
    statefulSets.value = statefulSetList
    jobs.value = jobList
    cronJobs.value = cronJobList
    services.value = svcList
    nodes.value = nodeList
  } catch (e) {
    error.value = `加载失败: ${e}`
  } finally {
    loading.value = false
  }
}

async function selectCluster(clusterId) {
  if (!clusterId || clusterId === activeClusterId.value) return
  activeClusterId.value = clusterId
  activeNs.value = ''
  resetNotice()
  await fetchAll()
}

function openAddCluster() {
  editingClusterId.value = ''
  Object.assign(clusterForm, { name: '', kubeconfig: '', context: '', description: '' })
  showClusterModal.value = true
}

function openEditCluster() {
  if (!activeCluster.value) return
  editingClusterId.value = activeCluster.value.id
  Object.assign(clusterForm, {
    name: activeCluster.value.name || '',
    kubeconfig: activeCluster.value.kubeconfig || '',
    context: activeCluster.value.context || '',
    description: activeCluster.value.description || '',
  })
  showClusterModal.value = true
}

function closeClusterModal() {
  showClusterModal.value = false
}

async function openResourceDetail(kind, row) {
  if (!activeClusterId.value) return
  resetDetailState()
  Object.assign(detailMeta, {
    kind: normalizeKind(kind),
    name: row?.name || '',
    namespace: row?.namespace || '',
  })
  showDetailModal.value = true
  detailLoading.value = true
  try {
    const result = await api.k8sResourceDetail(activeClusterId.value, detailMeta.kind, detailMeta.name, detailMeta.namespace)
    detailData.value = result?.data ?? result
  } catch (e) {
    detailError.value = `加载详情失败：${e}`
  } finally {
    detailLoading.value = false
  }
}

async function loadSelectedPodLogs() {
  if (!activeClusterId.value || !selectedLogPod.value || !logMeta.namespace) return
  logTailLines.value = clampTailLines(logTailLines.value)
  logLoading.value = true
  logError.value = ''
  try {
    const result = await api.k8sPodLogs(
      activeClusterId.value,
      logMeta.namespace,
      selectedLogPod.value,
      selectedLogContainer.value,
      logTailLines.value,
    )
    logTailLines.value = result?.tailLines || logTailLines.value
    logText.value = result?.logs || ''
  } catch (e) {
    logText.value = ''
    logError.value = `加载日志失败：${e}`
  } finally {
    logLoading.value = false
  }
}

async function handleLogPodChange() {
  selectedLogContainer.value = pickDefaultContainer(selectedLogPodData.value)
  await loadSelectedPodLogs()
}

async function handleLogContainerChange() {
  await loadSelectedPodLogs()
}

async function openResourceLogs(kind, row) {
  if (!activeClusterId.value || !canViewLogs(kind)) return
  resetLogState()
  Object.assign(logMeta, {
    kind: normalizeKind(kind),
    name: row?.name || '',
    namespace: row?.namespace || '',
  })
  showLogModal.value = true
  logLoading.value = true
  try {
    const result = await api.k8sResourcePods(activeClusterId.value, logMeta.kind, logMeta.name, logMeta.namespace)
    logPods.value = result?.pods || []
    if (!logPods.value.length) {
      logError.value = '未找到可查看日志的 Pod'
      return
    }
    selectedLogPod.value = logPods.value[0].name
    selectedLogContainer.value = pickDefaultContainer(logPods.value[0])
  } catch (e) {
    logError.value = `加载日志目标失败：${e}`
    return
  } finally {
    logLoading.value = false
  }
  await loadSelectedPodLogs()
}

async function saveCluster() {
  const payload = {
    name: clusterForm.name.trim(),
    kubeconfig: clusterForm.kubeconfig.trim(),
    context: clusterForm.context.trim(),
    description: clusterForm.description.trim(),
  }
  if (!payload.name || !payload.kubeconfig) {
    clusterTestResult.value = false
    clusterTestMsg.value = '集群名称和 kubeconfig 路径不能为空'
    return
  }
  const successMsg = editingClusterId.value ? '集群配置已更新' : `已添加集群：${payload.name}`
  let saved
  try {
    if (editingClusterId.value) {
      saved = await api.k8sUpdateCluster(editingClusterId.value, payload)
    } else {
      saved = await api.k8sAddCluster(payload)
    }
  } catch (e) {
    clusterTestResult.value = false
    clusterTestMsg.value = `保存集群失败：${e}`
    return
  }
  try {
    await loadClusters()
    activeClusterId.value = saved.id
    activeNs.value = ''
    closeClusterModal()
    await fetchAll()
    clusterTestResult.value = true
    clusterTestMsg.value = successMsg
  } catch (e) {
    clusterTestResult.value = false
    clusterTestMsg.value = `${successMsg}，但资源加载失败：${e}`
  }
}

async function setDefaultCluster(cluster) {
  let saved
  try {
    saved = await api.k8sSetDefaultCluster(cluster.id)
  } catch (e) {
    clusterTestResult.value = false
    clusterTestMsg.value = `设置默认集群失败：${e}`
    return
  }
  try {
    await loadClusters()
    activeClusterId.value = saved.id
    activeNs.value = ''
    await fetchAll()
    clusterTestResult.value = true
    clusterTestMsg.value = `默认集群已切换为：${saved.name}`
  } catch (e) {
    clusterTestResult.value = false
    clusterTestMsg.value = `默认集群已切换为：${saved.name}，但资源加载失败：${e}`
  }
}

async function removeCluster() {
  if (!activeCluster.value) return
  if (!confirm(`确认删除集群「${activeCluster.value.name}」？`)) return
  try {
    await api.k8sDeleteCluster(activeCluster.value.id)
    resetNotice()
  } catch (e) {
    clusterTestResult.value = false
    clusterTestMsg.value = `删除集群失败：${e}`
    return
  }
  try {
    await loadClusters()
    activeNs.value = ''
    await fetchAll()
    clusterTestResult.value = true
    clusterTestMsg.value = '集群已删除'
  } catch (e) {
    clusterTestResult.value = false
    clusterTestMsg.value = `集群已删除，但资源刷新失败：${e}`
  }
}

async function testActiveCluster() {
  if (!activeCluster.value) return
  try {
    const result = await api.k8sTestCluster(activeCluster.value.id)
    clusterTestResult.value = result.ok
    clusterTestMsg.value = result.ok
      ? `连接成功，共 ${result.node_count} 个节点：${(result.nodes || []).join(', ')}（使用 ${result.resolved_kubeconfig || result.kubeconfig}）`
      : `连接失败：${result.error}${result.resolved_kubeconfig ? `（解析后路径：${result.resolved_kubeconfig}）` : ''}`
  } catch (e) {
    clusterTestResult.value = false
    clusterTestMsg.value = `测试失败：${e}`
  }
}

onMounted(async () => {
  await loadClusters()
  await fetchAll()
})

// ── Container Exec ────────────────────────────────────────────────────────────
const showExecModal  = ref(false)
const execConnected  = ref(false)
const execConnecting = ref(false)
const execContainer  = ref('')
const execShell      = ref('/bin/sh')
const execTermEl     = ref(null)
const execMeta       = reactive({ pod: '', namespace: '', container: '', containers: [] })

let _execTerm    = null
let _execFitAddon = null
let _execWs      = null
let _execResizeOb = null

function _destroyExec() {
  _execWs?.close()
  _execWs = null
  _execResizeOb?.disconnect()
  _execResizeOb = null
  if (_execTerm) { _execTerm.dispose(); _execTerm = null }
  _execFitAddon = null
  execConnected.value  = false
  execConnecting.value = false
}

async function openExecModal(pod) {
  execMeta.pod       = pod.name
  execMeta.namespace = pod.namespace
  execMeta.containers = pod.containers || []
  execMeta.container = pod.containers?.[0]?.name || ''
  execContainer.value = execMeta.container
  showExecModal.value = true
  await nextTick()
  await _startExec()
}

function closeExecModal() {
  _destroyExec()
  showExecModal.value = false
}

async function restartExec() {
  _destroyExec()
  await nextTick()
  await _startExec()
}

async function _startExec() {
  if (!execTermEl.value) return
  execConnecting.value = true

  _execTerm = new Terminal({
    theme: { background: '#0d1117', foreground: '#c9d1d9', cursor: '#58a6ff' },
    fontFamily: "'Cascadia Code', 'Consolas', 'Fira Code', monospace",
    fontSize: 13, lineHeight: 1.4, cursorBlink: true,
    scrollback: 3000,
  })
  _execFitAddon = new FitAddon()
  _execTerm.loadAddon(_execFitAddon)
  _execTerm.open(execTermEl.value)
  await nextTick()
  _execFitAddon.fit()

  _execResizeOb = new ResizeObserver(() => {
    requestAnimationFrame(() => {
      _execFitAddon?.fit()
      const d = _execFitAddon?.proposeDimensions?.()
      if (d && _execWs?.readyState === WebSocket.OPEN)
        _execWs.send(`\x1b[RESIZE:${d.cols},${d.rows}]`)
    })
  })
  _execResizeOb.observe(execTermEl.value)

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const cont  = execContainer.value || execMeta.container
  const qs    = new URLSearchParams({
    cluster_id: activeClusterId.value || '',
    namespace:  execMeta.namespace,
    pod:        execMeta.pod,
    container:  cont,
    shell:      execShell.value,
  })
  _execWs = new WebSocket(`${proto}://${location.host}/api/k8s/exec?${qs}`)

  _execWs.onopen = () => {
    execConnected.value  = true
    execConnecting.value = false
    const d = _execFitAddon?.proposeDimensions?.()
    if (d) _execWs.send(`\x1b[RESIZE:${d.cols},${d.rows}]`)
  }
  _execWs.onmessage = (e) => _execTerm?.write(e.data)
  _execWs.onclose   = () => {
    execConnected.value  = false
    execConnecting.value = false
    _execTerm?.writeln('\r\n\x1b[90m连接已断开\x1b[0m')
  }
  _execWs.onerror   = () => {
    execConnected.value  = false
    execConnecting.value = false
    _execTerm?.writeln('\r\n\x1b[31mWebSocket 连接错误\x1b[0m')
  }
  _execTerm.onData((data) => {
    if (_execWs?.readyState === WebSocket.OPEN) _execWs.send(data)
  })
  _execTerm.onResize(({ cols, rows }) => {
    if (_execWs?.readyState === WebSocket.OPEN)
      _execWs.send(`\x1b[RESIZE:${cols},${rows}]`)
  })
}

onBeforeUnmount(() => { _destroyExec() })
</script>

<style scoped>
.container-view { display: flex; flex-direction: column; height: 100vh; overflow: hidden; background: var(--bg-base); color: var(--text-primary); }

.page-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px 12px; border-bottom: 1px solid var(--border-light); flex-shrink: 0; gap: 16px; }
.header-left h1 { font-size: 16px; font-weight: 600; margin: 0 0 2px; }
.subtitle { font-size: 12px; color: var(--text-muted); }
.header-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }

.ns-select,
.form-input,
.form-textarea {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 12px;
}

.ns-select { padding: 6px 10px; cursor: pointer; min-width: 180px; }

.btn-refresh,
.btn-ghost,
.btn-primary-lg,
.cluster-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all .15s;
}

.btn-refresh {
  background: var(--accent-dim);
  border: 1px solid var(--border-accent);
  color: var(--accent);
  padding: 6px 12px;
}

.btn-ghost {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 6px 10px;
}

.btn-ghost.compact { padding: 5px 8px; }
.btn-ghost.danger { color: var(--error); border-color: rgba(207,34,46,0.22); }
.btn-refresh:hover,
.btn-ghost:hover,
.btn-primary-lg:hover,
.cluster-link:hover { filter: brightness(0.97); }
.btn-refresh:disabled,
.btn-ghost:disabled { opacity: .5; cursor: not-allowed; }

.btn-primary-lg {
  background: var(--accent);
  border: 1px solid var(--accent);
  color: #fff;
  padding: 8px 16px;
}

.cluster-banner,
.error-banner {
  margin: 12px 20px 0;
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 12px;
}

.cluster-banner.ok { background: rgba(26,127,55,0.08); border: 1px solid rgba(26,127,55,0.22); color: var(--success); }
.cluster-banner.err,
.error-banner { background: rgba(207,34,46,0.07); border: 1px solid rgba(207,34,46,0.25); color: var(--error); }
.error-banner { display: flex; align-items: center; gap: 7px; }

.empty-state { flex: 1; display: flex; align-items: center; justify-content: center; padding: 24px; }
.empty-card {
  width: min(520px, 100%);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 28px;
  text-align: center;
  box-shadow: var(--shadow-sm);
}
.empty-title { font-size: 18px; font-weight: 600; margin-bottom: 8px; }
.empty-subtitle { color: var(--text-muted); font-size: 13px; line-height: 1.7; margin-bottom: 18px; }

.workspace-body { flex: 1; min-height: 0; display: flex; gap: 16px; padding: 12px 20px 20px; }

.cluster-sidebar {
  width: 300px;
  min-width: 300px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.sidebar-head {
  padding: 14px 14px 10px;
  border-bottom: 1px solid var(--border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.sidebar-title { font-size: 14px; font-weight: 600; }
.sidebar-subtitle { font-size: 11px; color: var(--text-muted); margin-top: 3px; }

.cluster-card-list {
  padding: 12px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.cluster-card {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px;
  background: var(--bg-base);
  cursor: pointer;
  transition: all .15s ease;
}

.cluster-card:hover { border-color: var(--border-accent); box-shadow: var(--shadow-sm); }
.cluster-card.active { border-color: var(--accent); background: linear-gradient(180deg, var(--accent-dim), rgba(255,255,255,0)); box-shadow: var(--shadow-sm); }
.cluster-card.default { box-shadow: inset 0 0 0 1px rgba(59,130,246,0.12); }

.cluster-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.cluster-title-row { display: flex; align-items: center; gap: 8px; min-width: 0; }
.cluster-card-name { font-size: 13px; font-weight: 600; color: var(--text-primary); word-break: break-all; }
.default-badge {
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 10px;
  color: var(--accent);
  background: var(--accent-dim);
  border: 1px solid var(--border-accent);
  white-space: nowrap;
}

.cluster-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--accent);
  font-size: 11px;
  white-space: nowrap;
}

.cluster-card-context { margin-top: 8px; font-size: 11px; color: var(--text-secondary); }
.cluster-card-desc { margin-top: 6px; font-size: 12px; color: var(--text-muted); line-height: 1.6; min-height: 38px; }
.cluster-card-path {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border-light);
  font-size: 10.5px;
  color: var(--text-secondary);
  word-break: break-all;
}

.content-area { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; }

.cluster-meta { display: grid; grid-template-columns: 220px 220px 1fr; gap: 12px; flex-shrink: 0; }
.meta-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  min-width: 0;
}
.meta-card.wide { min-width: 0; }
.meta-label { font-size: 11px; color: var(--text-muted); margin-bottom: 6px; }
.meta-value { font-size: 14px; font-weight: 600; color: var(--text-primary); word-break: break-all; }
.meta-sub { margin-top: 4px; font-size: 11px; color: var(--text-secondary); line-height: 1.6; }

.summary-row { display: flex; flex-wrap: wrap; gap: 12px; padding-top: 12px; flex-shrink: 0; }
.stat-card { flex: 1 1 180px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; display: flex; align-items: center; gap: 12px; }
.stat-card.warn { border-color: rgba(154,103,0,0.3); background: rgba(154,103,0,0.05); }
.stat-icon { width: 38px; height: 38px; border-radius: 8px; display: flex; align-items: center; justify-content: center; }
.stat-icon.node { background: var(--accent-dim); color: var(--accent); }
.stat-icon.pod { background: rgba(26,127,55,0.12); color: var(--success); }
.stat-icon.deploy { background: rgba(154,103,0,0.12); color: var(--warning); }
.stat-icon.daemon { background: rgba(99,102,241,0.12); color: #4f46e5; }
.stat-icon.stateful { background: rgba(14,165,233,0.12); color: #0284c7; }
.stat-icon.job { background: rgba(20,184,166,0.12); color: #0f766e; }
.stat-icon.cron { background: rgba(217,119,6,0.12); color: #b45309; }
.stat-value { font-size: 22px; font-weight: 700; line-height: 1; }
.stat-total { font-size: 14px; color: var(--text-muted); font-weight: 400; }
.stat-label { font-size: 11px; color: var(--text-muted); margin-top: 3px; }

.tab-row { display: flex; gap: 4px; padding-top: 10px; flex-shrink: 0; }
.tab-btn { padding: 6px 14px; border-radius: 6px; border: 1px solid transparent; background: none; color: var(--text-secondary); font-size: 13px; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: all .15s; }
.tab-btn:hover { color: var(--text-primary); background: var(--bg-hover); }
.tab-btn.active { background: var(--accent-dim); border-color: var(--border-accent); color: var(--accent); font-weight: 500; }
.tab-count { font-size: 10px; background: var(--bg-surface); border: 1px solid var(--border); padding: 1px 5px; border-radius: 8px; color: var(--text-secondary); }

.loading-row { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 40px; color: var(--text-muted); }
.spinner { width: 16px; height: 16px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.table-wrap { flex: 1; overflow: auto; padding-top: 10px; }
.k8s-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.k8s-table th { text-align: left; padding: 8px 10px; color: var(--text-muted); font-weight: 500; border-bottom: 1px solid var(--border); white-space: nowrap; position: sticky; top: 0; background: var(--bg-base); }
.k8s-table td { padding: 7px 10px; border-bottom: 1px solid var(--border-light); vertical-align: middle; }
.k8s-table tr:hover td { background: var(--bg-hover); }
.empty { text-align: center; color: var(--text-muted); padding: 40px !important; }

.name-cell { font-weight: 500; font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 11.5px; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ns-tag { background: var(--accent-dim); border: 1px solid var(--border-accent); color: var(--accent); padding: 1px 6px; border-radius: 10px; font-size: 10.5px; }
.role-tag { background: rgba(154,103,0,0.1); border: 1px solid rgba(154,103,0,0.2); color: var(--warning); padding: 1px 6px; border-radius: 10px; font-size: 10.5px; }
.svc-type { padding: 1px 6px; border-radius: 10px; font-size: 10.5px; }
.svc-type.clusterip { background: var(--accent-dim); color: var(--accent); border: 1px solid var(--border-accent); }
.svc-type.nodeport { background: rgba(154,103,0,0.1); color: var(--warning); border: 1px solid rgba(154,103,0,0.2); }
.svc-type.loadbalancer { background: rgba(26,127,55,0.1); color: var(--success); border: 1px solid rgba(26,127,55,0.2); }

.status-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; vertical-align: middle; }
.status-dot.ok { background: var(--success); }
.status-dot.warn { background: var(--warning); }
.status-dot.err { background: var(--error); }

.container-tag { display: inline-block; font-size: 10px; padding: 1px 5px; border-radius: 4px; margin-right: 3px; background: var(--bg-surface); color: var(--text-secondary); border: 1px solid var(--border); }
.container-tag.ready { color: var(--success); background: rgba(26,127,55,0.08); border-color: rgba(26,127,55,0.2); }
.action-cell { white-space: nowrap; width: 1%; }
.action-group { display: flex; align-items: center; gap: 6px; }
.action-btn {
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  transition: all .15s;
}
.action-btn:hover { border-color: var(--border-accent); color: var(--accent); background: var(--accent-dim); }

.mono { font-family: 'Cascadia Code', 'Consolas', monospace; }
.small { font-size: 11px; }
.muted { color: var(--text-muted); }
.col-warn { color: var(--warning); font-weight: 500; }

.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.42);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1300;
}
.modal-card {
  width: min(560px, calc(100vw - 32px));
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.22);
}
.detail-modal-card { width: min(920px, calc(100vw - 40px)); }
.log-modal-card { width: min(1180px, calc(100vw - 40px)); }
.modal-title { padding: 18px 20px 0; font-size: 16px; font-weight: 600; }
.modal-body { padding: 16px 20px 6px; display: flex; flex-direction: column; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--text-secondary); }
.form-input { padding: 9px 10px; }
.form-textarea { padding: 9px 10px; resize: vertical; min-height: 84px; }
.modal-tip { font-size: 12px; color: var(--text-muted); line-height: 1.7; background: var(--bg-surface); border: 1px dashed var(--border); border-radius: 8px; padding: 10px 12px; }
.modal-tip-error { color: var(--error); border-style: solid; border-color: rgba(207,34,46,0.18); background: rgba(207,34,46,0.05); }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; padding: 0 20px 20px; }
.resource-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.resource-kind {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--bg-surface);
  color: var(--text-secondary);
  font-size: 11px;
}
.code-panel {
  min-height: 320px;
  max-height: 62vh;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-surface);
  overflow: auto;
}
.json-view,
.log-view {
  margin: 0;
  padding: 14px 16px;
  min-height: 320px;
  color: var(--text-primary);
  font-family: 'Cascadia Code', 'Consolas', monospace;
  font-size: 11.5px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}
.loading-row.compact { padding: 40px 20px; }
.log-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1.4fr) 120px auto;
  gap: 10px;
  align-items: end;
}
.toolbar-field { min-width: 0; }
.toolbar-field .form-input { width: 100%; }
.tail-field { max-width: 120px; }
.refresh-log-btn { height: 38px; }

@media (max-width: 1280px) {
  .cluster-meta { grid-template-columns: 1fr 1fr; }
  .meta-card.wide { grid-column: 1 / -1; }
  .log-toolbar { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .tail-field { max-width: none; }
}

@media (max-width: 1080px) {
  .page-header { flex-direction: column; align-items: flex-start; }
  .header-right { width: 100%; justify-content: flex-start; }
  .workspace-body { flex-direction: column; }
  .cluster-sidebar { width: 100%; min-width: 0; max-height: 260px; }
  .summary-row { flex-direction: column; }
  .action-group { flex-wrap: wrap; }
}

@media (max-width: 760px) {
  .container-view { height: auto; min-height: 100vh; }
  .page-header,
  .workspace-body { padding-left: 12px; padding-right: 12px; }
  .workspace-body { padding-top: 12px; padding-bottom: 12px; }
  .header-right { gap: 6px; }
  .ns-select { min-width: 0; width: 100%; }
  .btn-refresh,
  .btn-ghost { flex: 1; }
  .cluster-meta { grid-template-columns: 1fr; }
  .detail-modal-card,
  .log-modal-card { width: calc(100vw - 24px); }
  .log-toolbar { grid-template-columns: 1fr; }
  .exec-modal-card { width: 100vw; height: 100vh; border-radius: 0; }
}

/* ── Container Exec Terminal ─────────────────────────────────── */
.exec-modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(1, 4, 9, 0.72);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1400;
}
.exec-modal-card {
  width: min(1100px, calc(100vw - 48px));
  height: min(660px, calc(100vh - 80px));
  background: #0d1117;
  border: 1px solid rgba(48, 54, 61, 0.8);
  border-radius: 12px;
  box-shadow: 0 32px 100px rgba(1, 4, 9, 0.5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.exec-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid rgba(48, 54, 61, 0.8);
  background: #161b22;
  flex-shrink: 0;
  gap: 12px;
}
.exec-modal-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #c9d1d9;
}
.exec-meta { color: #58a6ff; font-family: monospace; font-size: 12px; }
.exec-meta.dim { color: #8b949e; }
.exec-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.exec-select {
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid rgba(48, 54, 61, 0.9);
  background: #0d1117;
  color: #c9d1d9;
  font-size: 12px;
  cursor: pointer;
}
.exec-btn-sm {
  padding: 4px 12px;
  border-radius: 6px;
  border: 1px solid rgba(48, 54, 61, 0.9);
  background: #21262d;
  color: #c9d1d9;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: background .15s;
}
.exec-btn-sm:hover:not(:disabled) { background: #30363d; }
.exec-btn-sm:disabled { opacity: 0.4; cursor: not-allowed; }
.exec-btn-sm.close { color: #f85149; border-color: rgba(248, 81, 73, 0.3); }
.exec-btn-sm.close:hover { background: rgba(248, 81, 73, 0.12); }
.exec-term-wrap {
  flex: 1;
  min-height: 0;
  padding: 4px 0 0 4px;
}
.exec-term-wrap :deep(.xterm) { height: 100%; }
.exec-term-wrap :deep(.xterm-viewport) { overflow-y: auto !important; }
.action-btn.exec-btn { color: #58a6ff; }
.action-btn.exec-btn:disabled { opacity: 0.35; cursor: not-allowed; }
</style>
