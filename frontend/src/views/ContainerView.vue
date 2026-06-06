<template>
  <div class="container-view">
    <div class="page-header">
      <div class="header-left">
        <h1>容器管理</h1>
        <span class="subtitle">多集群 Kubernetes 资源总览与 kubeconfig 管理</span>
      </div>
      <div class="header-right">
        <input
          v-model="searchKeyword"
          class="search-input"
          type="text"
          placeholder="关键字搜索"
          :disabled="!activeClusterId || loading"
        />
        <select v-model="activeNs" class="ns-select" :disabled="!activeClusterId || loading" @change="fetchAll()">
          <option value="">全部命名空间</option>
          <option v-for="ns in namespaces" :key="ns.name" :value="ns.name">{{ ns.name }}</option>
        </select>
        <span v-if="lastFetchedAt" class="cache-stamp" :title="`数据缓存时间 ${new Date(lastFetchedAt).toLocaleString()}`">
          ⏱ {{ lastFetchedText }}
        </span>
        <select v-model="autoRefreshInterval" class="ns-select auto-refresh-select" :disabled="!activeClusterId" title="自动刷新">
          <option v-for="opt in AUTO_REFRESH_OPTIONS" :key="opt.value" :value="opt.value">
            {{ opt.value === 'off' ? '自动刷新：关' : `自动 ${opt.label}` }}
          </option>
        </select>
        <button v-if="canManageClusters" class="btn-ghost" :disabled="!activeCluster" @click="openEditCluster">编辑</button>
        <button v-if="canManageClusters" class="btn-ghost" :disabled="!activeCluster" @click="testActiveCluster">测试</button>
        <button v-if="canManageClusters" class="btn-ghost danger" :disabled="!activeCluster" @click="removeCluster">删除</button>
        <button class="btn-refresh" @click="refreshAll" :disabled="loading || !activeClusterId" title="跳过缓存强制重拉">
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
          </div>
        </div>
      </aside>

      <section class="content-area">
        <div class="cluster-meta">
          <div class="meta-card compact">
            <div class="meta-label">当前集群</div>
            <div class="meta-value">{{ activeCluster?.name || '未选择' }}</div>
            <div class="meta-sub">{{ activeCluster?.context || '默认 context' }}</div>
          </div>
          <div class="meta-card compact">
            <div class="meta-label">默认访问</div>
            <div class="meta-value">{{ activeCluster?.is_default ? '是' : '否' }}</div>
            <div class="meta-sub">{{ activeCluster?.is_default ? '未指定 cluster_id 时默认使用该集群' : '可在左侧卡片中设为默认集群' }}</div>
          </div>
          <div class="meta-card wide compact">
            <div class="meta-label">kubeconfig</div>
            <div class="meta-value mono">{{ activeCluster?.kubeconfig || '未配置' }}</div>
            <div class="meta-sub">{{ activeCluster?.description || '可使用不同 kubeconfig 路径分别管理多个集群' }}</div>
          </div>
        </div>

        <!-- 资源关键字搜索（取代原"kubeconfig 认证检测"卡片）-->
        <div class="inspect-card">
          <div class="inspect-title">🔍 资源关键字搜索</div>
          <div class="inspect-row">
            <input v-model="searchKeyword" class="form-input inspect-input"
              placeholder="搜索当前集群所有资源 (Pod / Deployment / Service / Node ...) 的名称、镜像、命名空间..."
              :disabled="!activeClusterId" />
            <button v-if="searchKeyword" class="btn-ghost inspect-btn" @click="searchKeyword = ''">清空</button>
          </div>
          <div v-if="searchKeyword" class="inspect-result">
            <div class="search-stats">
              <button
                v-for="item in searchMatchSummary"
                :key="item.tab"
                class="search-stat-chip"
                :class="{ active: activeTab === item.tab, zero: item.count === 0 }"
                @click="activeTab = item.tab"
              >
                <span class="search-stat-name">{{ item.label }}</span>
                <span class="search-stat-count">{{ item.count }}</span>
              </button>
            </div>
            <div v-if="searchTotalCount === 0" class="search-empty">
              未在当前集群任何资源中匹配到 <em>{{ searchKeyword }}</em>
            </div>
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
              <div class="stat-label">Pods</div>
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
              <div class="stat-label">Deployments</div>
            </div>
          </div>
          <div class="stat-card compact" :class="{ warn: summary.daemonSets?.ready < summary.daemonSets?.total }">
            <div class="stat-icon daemon">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1" />
              </svg>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ summary.daemonSets?.ready || 0 }}<span class="stat-total">/{{ summary.daemonSets?.total || 0 }}</span></div>
              <div class="stat-label">DaemonSets</div>
            </div>
          </div>
          <div class="stat-card compact" :class="{ warn: summary.statefulSets?.ready < summary.statefulSets?.total }">
            <div class="stat-icon stateful">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <rect x="4" y="4" width="16" height="5" rx="1.5" />
                <rect x="4" y="10" width="16" height="5" rx="1.5" />
                <rect x="4" y="16" width="16" height="4" rx="1.5" />
              </svg>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ summary.statefulSets?.ready || 0 }}<span class="stat-total">/{{ summary.statefulSets?.total || 0 }}</span></div>
              <div class="stat-label">StatefulSets</div>
            </div>
          </div>
          <div class="stat-card compact" :class="{ warn: summary.jobs?.complete < summary.jobs?.total }">
            <div class="stat-icon job">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <path d="M8 6h13M8 12h13M8 18h13" />
                <path d="M3 6l1 1 2-2M3 12l1 1 2-2M3 18l1 1 2-2" />
              </svg>
            </div>
            <div class="stat-body">
              <div class="stat-value">{{ summary.jobs?.complete || 0 }}<span class="stat-total">/{{ summary.jobs?.total || 0 }}</span></div>
              <div class="stat-label">Jobs</div>
            </div>
          </div>
          <div class="stat-card compact" :class="{ warn: (summary.cronJobs?.suspended || 0) > 0 }">
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
          <!-- Pod 重启统计：点击 → 跳到 Pods tab 并按重启降序排 -->
          <div
            class="stat-card restart-card"
            :class="{ warn: podRestartStats.frequent > 0, danger: podRestartStats.maxRestart >= 10 }"
            :title="podRestartStats.maxPod ? `重启最多的 Pod: ${podRestartStats.maxPod.namespace}/${podRestartStats.maxPod.name} (${podRestartStats.maxRestart} 次)` : ''"
            @click="activeTab = 'pods'; podRestartSortOrder = 'desc'"
            style="cursor: pointer"
          >
            <div class="stat-icon restart">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
                <polyline points="23 4 23 10 17 10" />
                <polyline points="1 20 1 14 7 14" />
                <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
              </svg>
            </div>
            <div class="stat-body">
              <div class="stat-value">
                {{ podRestartStats.totalRestarts }}
                <span class="stat-total">/ {{ podRestartStats.withRestart }} 个 Pod</span>
              </div>
              <div class="stat-label">
                Pod 重启总次数
                <span v-if="podRestartStats.frequent > 0" class="stat-warn-tag">
                  · 频繁 {{ podRestartStats.frequent }}
                </span>
              </div>
              <div v-if="podRestartStats.topReasons.length" class="restart-reason-row">
                <span
                  v-for="r in podRestartStats.topReasons"
                  :key="r.reason"
                  class="restart-reason mini"
                  :class="restartReasonClass(r.reason)"
                  :title="`${r.reason}: ${r.count} 个 Pod`"
                >
                  {{ r.reason }} <em>{{ r.count }}</em>
                </span>
              </div>
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
                <th class="select-col">
                  <input type="checkbox"
                    :checked="allCurrentSelected"
                    @change="toggleAllCurrent"
                    :disabled="!sortedFilteredPods.length"
                    title="全选 / 取消全选" />
                </th>
                <th>名称</th><th>命名空间</th><th>状态</th><th>节点</th><th>容器</th>
                <th class="sortable-th" @click="togglePodRestartSort" :title="`点击切换排序 (当前: ${ {desc:'降序',asc:'升序',null:'默认'}[podRestartSortOrder] || '默认' })`">
                  重启
                  <span class="sort-indicator">{{ podRestartSortOrder === 'desc' ? '↓' : podRestartSortOrder === 'asc' ? '↑' : '⇅' }}</span>
                </th>
                <th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!sortedFilteredPods.length"><td colspan="9" class="empty">暂无数据</td></tr>
              <tr v-for="pod in sortedFilteredPods" :key="pod.namespace + '/' + pod.name"
                  :class="{ 'row-selected': isRowSelected('pod', pod) }">
                <td class="select-col">
                  <input type="checkbox"
                    :checked="isRowSelected('pod', pod)"
                    @change="toggleRowSelected('pod', pod)" />
                </td>
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
                <td>
                  <span class="restart-badge" :class="restartClass(pod.restarts)">{{ pod.restarts }}</span>
                  <span
                    v-if="pod.last_restart_reason"
                    class="restart-reason"
                    :class="restartReasonClass(pod.last_restart_reason)"
                    :title="restartReasonTitle(pod)"
                  >
                    {{ pod.last_restart_reason }}
                  </span>
                </td>
                <td class="muted mono small" :title="formatRelative(pod.age)">{{ formatDateTime(pod.age) }}</td>
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
                <th class="select-col">
                  <input type="checkbox" :checked="allCurrentSelected" @change="toggleAllCurrent"
                    :disabled="!filteredDeployments.length" title="全选 / 取消全选" />
                </th>
                <th>名称</th><th>命名空间</th><th>状态</th><th>Ready</th><th>镜像</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredDeployments.length"><td colspan="8" class="empty">暂无数据</td></tr>
              <tr v-for="deployment in filteredDeployments" :key="deployment.namespace + '/' + deployment.name"
                  :class="{ 'row-selected': isRowSelected('deployment', deployment) }">
                <td class="select-col">
                  <input type="checkbox" :checked="isRowSelected('deployment', deployment)"
                    @change="toggleRowSelected('deployment', deployment)" />
                </td>
                <td class="name-cell">{{ deployment.name }}</td>
                <td><span class="ns-tag">{{ deployment.namespace }}</span></td>
                <td><span class="status-dot" :class="deployment.statusClass"></span>{{ deployment.status }}</td>
                <td>
                  <span class="ready-frac">{{ deployment.ready }}/{{ deployment.desired }}</span>
                  <span class="scale-ctrl">
                    <button class="scale-btn" :disabled="scalingKey === scaleKey('deployment', deployment) || (deployment.desired || 0) <= 0" @click="scaleResource('deployment', deployment, -1)" title="副本数 -1">−</button>
                    <button class="scale-btn" :disabled="scalingKey === scaleKey('deployment', deployment)" @click="scaleResource('deployment', deployment, +1)" title="副本数 +1">+</button>
                    <span v-if="scalingKey === scaleKey('deployment', deployment)" class="scale-spinner spinner"></span>
                  </span>
                </td>
                <td class="mono small image-cell" @click="openImageEdit('deployment', deployment)" title="点击编辑镜像">
                  {{ deployment.images.join(', ') }}
                  <span class="image-edit-hint">✎</span>
                </td>
                <td class="muted mono small" :title="formatRelative(deployment.age)">{{ formatDateTime(deployment.age) }}</td>
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
                <th class="select-col">
                  <input type="checkbox" :checked="allCurrentSelected" @change="toggleAllCurrent"
                    :disabled="!filteredDaemonSets.length" title="全选 / 取消全选" />
                </th>
                <th>名称</th><th>命名空间</th><th>状态</th><th>Ready</th><th>当前</th><th>可用</th><th>镜像</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredDaemonSets.length"><td colspan="10" class="empty">暂无数据</td></tr>
              <tr v-for="daemonSet in filteredDaemonSets" :key="daemonSet.namespace + '/' + daemonSet.name"
                  :class="{ 'row-selected': isRowSelected('daemonset', daemonSet) }">
                <td class="select-col">
                  <input type="checkbox" :checked="isRowSelected('daemonset', daemonSet)"
                    @change="toggleRowSelected('daemonset', daemonSet)" />
                </td>
                <td class="name-cell">{{ daemonSet.name }}</td>
                <td><span class="ns-tag">{{ daemonSet.namespace }}</span></td>
                <td><span class="status-dot" :class="daemonSet.statusClass"></span>{{ daemonSet.status }}</td>
                <td>{{ daemonSet.ready }}/{{ daemonSet.desired }}</td>
                <td>{{ daemonSet.current }}/{{ daemonSet.updated }}</td>
                <td>{{ daemonSet.available }}</td>
                <td class="mono small image-cell" @click="openImageEdit('daemonset', daemonSet)" title="点击编辑镜像">
                  {{ daemonSet.images.join(', ') }}
                  <span class="image-edit-hint">✎</span>
                </td>
                <td class="muted mono small" :title="formatRelative(daemonSet.age)">{{ formatDateTime(daemonSet.age) }}</td>
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
                <th class="select-col">
                  <input type="checkbox" :checked="allCurrentSelected" @change="toggleAllCurrent"
                    :disabled="!filteredStatefulSets.length" title="全选 / 取消全选" />
                </th>
                <th>名称</th><th>命名空间</th><th>状态</th><th>Ready</th><th>当前</th><th>更新</th><th>镜像</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredStatefulSets.length"><td colspan="10" class="empty">暂无数据</td></tr>
              <tr v-for="statefulSet in filteredStatefulSets" :key="statefulSet.namespace + '/' + statefulSet.name"
                  :class="{ 'row-selected': isRowSelected('statefulset', statefulSet) }">
                <td class="select-col">
                  <input type="checkbox" :checked="isRowSelected('statefulset', statefulSet)"
                    @change="toggleRowSelected('statefulset', statefulSet)" />
                </td>
                <td class="name-cell">{{ statefulSet.name }}</td>
                <td><span class="ns-tag">{{ statefulSet.namespace }}</span></td>
                <td><span class="status-dot" :class="statefulSet.statusClass"></span>{{ statefulSet.status }}</td>
                <td>
                  <span class="ready-frac">{{ statefulSet.ready }}/{{ statefulSet.desired }}</span>
                  <span class="scale-ctrl">
                    <button class="scale-btn" :disabled="scalingKey === scaleKey('statefulset', statefulSet) || (statefulSet.desired || 0) <= 0" @click="scaleResource('statefulset', statefulSet, -1)" title="副本数 -1">−</button>
                    <button class="scale-btn" :disabled="scalingKey === scaleKey('statefulset', statefulSet)" @click="scaleResource('statefulset', statefulSet, +1)" title="副本数 +1">+</button>
                    <span v-if="scalingKey === scaleKey('statefulset', statefulSet)" class="scale-spinner spinner"></span>
                  </span>
                </td>
                <td>{{ statefulSet.current }}</td>
                <td>{{ statefulSet.updated }}</td>
                <td class="mono small image-cell" @click="openImageEdit('statefulset', statefulSet)" title="点击编辑镜像">
                  {{ statefulSet.images.join(', ') }}
                  <span class="image-edit-hint">✎</span>
                </td>
                <td class="muted mono small" :title="formatRelative(statefulSet.age)">{{ formatDateTime(statefulSet.age) }}</td>
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
                <th class="select-col">
                  <input type="checkbox" :checked="allCurrentSelected" @change="toggleAllCurrent"
                    :disabled="!filteredJobs.length" title="全选 / 取消全选" />
                </th>
                <th>名称</th><th>命名空间</th><th>状态</th><th>完成</th><th>并发</th><th>运行</th><th>失败</th><th>镜像</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredJobs.length"><td colspan="11" class="empty">暂无数据</td></tr>
              <tr v-for="job in filteredJobs" :key="job.namespace + '/' + job.name"
                  :class="{ 'row-selected': isRowSelected('job', job) }">
                <td class="select-col">
                  <input type="checkbox" :checked="isRowSelected('job', job)"
                    @change="toggleRowSelected('job', job)" />
                </td>
                <td class="name-cell">{{ job.name }}</td>
                <td><span class="ns-tag">{{ job.namespace }}</span></td>
                <td><span class="status-dot" :class="job.statusClass"></span>{{ job.status }}</td>
                <td>{{ job.succeeded }}/{{ job.completions }}</td>
                <td>{{ job.parallelism }}</td>
                <td>{{ job.active }}</td>
                <td :class="{ 'col-warn': job.failed > 0 }">{{ job.failed }}</td>
                <td class="mono small">{{ job.images.join(', ') }}</td>
                <td class="muted mono small" :title="formatRelative(job.age)">{{ formatDateTime(job.age) }}</td>
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
                <th class="select-col">
                  <input type="checkbox" :checked="allCurrentSelected" @change="toggleAllCurrent"
                    :disabled="!filteredCronJobs.length" title="全选 / 取消全选" />
                </th>
                <th>名称</th><th>命名空间</th><th>状态</th><th>调度</th><th>挂起</th><th>活跃 Job</th><th>最近调度</th><th>最近成功</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredCronJobs.length"><td colspan="11" class="empty">暂无数据</td></tr>
              <tr v-for="cronJob in filteredCronJobs" :key="cronJob.namespace + '/' + cronJob.name"
                  :class="{ 'row-selected': isRowSelected('cronjob', cronJob) }">
                <td class="select-col">
                  <input type="checkbox" :checked="isRowSelected('cronjob', cronJob)"
                    @change="toggleRowSelected('cronjob', cronJob)" />
                </td>
                <td class="name-cell">{{ cronJob.name }}</td>
                <td><span class="ns-tag">{{ cronJob.namespace }}</span></td>
                <td><span class="status-dot" :class="cronJob.statusClass"></span>{{ cronJob.status }}</td>
                <td class="mono small">{{ cronJob.schedule }}</td>
                <td>{{ cronJob.suspend ? '是' : '否' }}</td>
                <td class="mono small">{{ cronJob.activeJobs.length ? cronJob.activeJobs.join(', ') : cronJob.active }}</td>
                <td class="muted mono small" :title="formatRelative(cronJob.lastScheduleTime)">{{ formatDateTime(cronJob.lastScheduleTime) }}</td>
                <td class="muted mono small" :title="formatRelative(cronJob.lastSuccessfulTime)">{{ formatDateTime(cronJob.lastSuccessfulTime) }}</td>
                <td class="muted mono small" :title="formatRelative(cronJob.age)">{{ formatDateTime(cronJob.age) }}</td>
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
                <th class="select-col">
                  <input type="checkbox" :checked="allCurrentSelected" @change="toggleAllCurrent"
                    :disabled="!filteredServices.length" title="全选 / 取消全选" />
                </th>
                <th>名称</th><th>命名空间</th><th>类型</th><th>ClusterIP</th><th>端口</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredServices.length"><td colspan="8" class="empty">暂无数据</td></tr>
              <tr v-for="service in filteredServices" :key="service.namespace + '/' + service.name"
                  :class="{ 'row-selected': isRowSelected('service', service) }">
                <td class="select-col">
                  <input type="checkbox" :checked="isRowSelected('service', service)"
                    @change="toggleRowSelected('service', service)" />
                </td>
                <td class="name-cell">{{ service.name }}</td>
                <td><span class="ns-tag">{{ service.namespace }}</span></td>
                <td><span class="svc-type" :class="service.type.toLowerCase()">{{ service.type }}</span></td>
                <td class="mono small">{{ service.clusterIP }}</td>
                <td class="mono small">{{ service.ports.join(', ') }}</td>
                <td class="muted mono small" :title="formatRelative(service.age)">{{ formatDateTime(service.age) }}</td>
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
              <tr v-if="!filteredNodes.length"><td colspan="7" class="empty">暂无数据</td></tr>
              <tr v-for="node in filteredNodes" :key="node.name">
                <td class="name-cell">{{ node.name }}</td>
                <td><span class="status-dot" :class="node.statusClass"></span>{{ node.status }}</td>
                <td><span class="role-tag">{{ node.roles }}</span></td>
                <td class="mono small">{{ node.version }}</td>
                <td class="small muted">{{ node.os }}</td>
                <td class="muted mono small" :title="formatRelative(node.age)">{{ formatDateTime(node.age) }}</td>
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

          <!-- 集群名称 -->
          <label class="field">
            <span>集群名称</span>
            <input v-model="clusterForm.name" class="form-input" placeholder="生产-k8s-01" />
          </label>

          <!-- 粘贴 kubeconfig 文本（自动识别 *-data base64 内嵌格式） -->
          <div class="field">
            <div class="paste-header" @click="pasteOpen = !pasteOpen">
              <span class="paste-toggle">{{ pasteOpen ? '▼' : '▶' }}</span>
              <span>或粘贴 kubeconfig 文本（自动识别 apiVersion / clusters / users / contexts）</span>
            </div>
            <div v-if="pasteOpen" class="paste-body">
              <textarea
                v-model="pasteContent"
                class="form-textarea"
                rows="8"
                placeholder="apiVersion: v1&#10;clusters:&#10;- cluster:&#10;    certificate-authority-data: ...&#10;    server: https://x.x.x.x:6443&#10;..."
              />
              <div class="paste-actions">
                <button
                  class="btn-detect"
                  :class="{ loading: pasteLoading }"
                  type="button"
                  :disabled="pasteLoading || !clusterForm.name.trim() || !pasteContent.trim()"
                  @click="savePastedKubeconfig"
                >
                  {{ pasteLoading ? '保存中...' : '保存并自动识别' }}
                </button>
                <span v-if="pasteResult" class="paste-success">
                  ✓ 已保存到 {{ pasteResult.relative }}
                  <em v-if="pasteResult.server">· server={{ pasteResult.server }}</em>
                  <em v-if="pasteResult.current_context">· context={{ pasteResult.current_context }}</em>
                </span>
                <span v-if="pasteError" class="paste-error">{{ pasteError }}</span>
              </div>
            </div>
          </div>

          <!-- kubeconfig 路径 + 自动识别（支持直接粘贴 yaml 文本：含 apiVersion: 自动落盘） -->
          <div class="field">
            <span>kubeconfig 路径 <small style="color:var(--text-muted);font-weight:400">（可直接粘贴 yaml 文本）</small></span>
            <div class="detect-row">
              <input v-model="clusterForm.kubeconfig" class="form-input detect-input"
                placeholder="路径 (~/.kube/config) 或粘贴 yaml 文本（含 apiVersion:）"
                @paste="onPathInputPaste"
                @keyup.enter="autoDetect" />
              <button class="btn-detect" :class="{ loading: detectLoading || pasteLoading }"
                @click="autoDetect" type="button" :disabled="detectLoading || pasteLoading || !clusterForm.kubeconfig.trim()">
                {{ pasteLoading ? '解析文本...' : detectLoading ? '识别中...' : '自动识别' }}
              </button>
            </div>
            <div v-if="pasteError" class="paste-error" style="margin-top:6px">{{ pasteError }}</div>
          </div>

          <!-- 识别结果徽章 -->
          <div v-if="detectResult" class="detect-result" :class="'detect-' + (detectResult.auth?.type || 'unknown')">
            <span class="detect-icon">{{ { certificate:'🔐', token:'🎫', exec:'⚙️', basic:'👤', unknown:'❓' }[detectResult.auth?.type] || '❓' }}</span>
            <div class="detect-info">
              <span class="detect-type">
                {{ { certificate:'证书认证', token:'Token 认证', exec:'Exec 插件', basic:'用户名密码', unknown:'未知类型' }[detectResult.auth?.type] }}
                <span v-if="detectResult.auth?.cert_embedded" class="detect-tag-embedded" title="证书已通过 *-data base64 内嵌在 kubeconfig 中，无需外部文件">
                  ✓ 内嵌证书
                </span>
              </span>
              <span class="detect-server">{{ detectResult.server }}</span>
              <span v-if="detectResult.auth?.cert_detail?.subject" class="detect-sub">{{ detectResult.auth.cert_detail.subject }}</span>
              <span v-if="detectResult.auth?.cert_detail?.not_after" class="detect-sub"
                :class="{ 'detect-expired': new Date(detectResult.auth.cert_detail.not_after) < new Date() }">
                过期：{{ detectResult.auth.cert_detail.not_after }}
              </span>
            </div>
            <button class="detect-clear" @click="detectResult = null; authMode = 'kubeconfig'" type="button">✕</button>
          </div>
          <div v-if="detectError" class="detect-error">{{ detectError }}</div>

          <!-- 认证模式（自动识别后高亮，也可手动切换） -->
          <div class="field">
            <span>认证方式</span>
            <div class="auth-mode-tabs">
              <button :class="['auth-tab', { active: authMode === 'kubeconfig' }]" @click="authMode = 'kubeconfig'" type="button">kubeconfig 路径</button>
              <button :class="['auth-tab', { active: authMode === 'cert' }]"       @click="authMode = 'cert'"       type="button">证书认证</button>
              <button :class="['auth-tab', { active: authMode === 'token' }]"      @click="authMode = 'token'"      type="button">Token 认证</button>
            </div>
          </div>

          <!-- 证书/Token 模式：路径从自动识别填入，也可手动编辑 -->
          <template v-if="authMode === 'cert' || authMode === 'token'">
            <label class="field">
              <span>API Server 地址</span>
              <input v-model="certForm.server" class="form-input" placeholder="https://192.168.9.221:6443" />
            </label>
            <label class="field field-inline">
              <input type="checkbox" v-model="certForm.insecureSkipTLS" style="margin-right:6px" />
              <span>跳过 TLS 验证（insecure-skip-tls-verify）</span>
            </label>
            <div class="field" v-if="!certForm.insecureSkipTLS">
              <span>CA 证书路径</span>
              <div class="cert-path-row">
                <input v-model="certForm.caPath" class="form-input" placeholder="backend/data/test/ca.crt 或 /opt/kubernetes/ssl/ca.pem" />
                <label class="cert-upload-btn" title="上传新文件到 data/ca/">
                  {{ certForm.caUploading ? '...' : '上传' }}
                  <input type="file" accept=".pem,.crt,.cer,.ca" style="display:none"
                    @change="e => handleCertUpload(e, 'ca')" />
                </label>
              </div>
            </div>
          </template>

          <template v-if="authMode === 'cert'">
            <div class="field">
              <span>客户端证书路径</span>
              <div class="cert-path-row">
                <input v-model="certForm.clientCertPath" class="form-input" placeholder="backend/data/test/user.crt" />
                <label class="cert-upload-btn" title="上传新文件到 data/ca/">
                  {{ certForm.clientCertUploading ? '...' : '上传' }}
                  <input type="file" accept=".pem,.crt,.cer" style="display:none"
                    @change="e => handleCertUpload(e, 'client-cert')" />
                </label>
              </div>
            </div>
            <div class="field">
              <span>客户端私钥路径</span>
              <div class="cert-path-row">
                <input v-model="certForm.clientKeyPath" class="form-input" placeholder="backend/data/test/user.key" />
                <label class="cert-upload-btn" title="上传新文件到 data/ca/">
                  {{ certForm.clientKeyUploading ? '...' : '上传' }}
                  <input type="file" accept=".pem,.key" style="display:none"
                    @change="e => handleCertUpload(e, 'client-key')" />
                </label>
              </div>
            </div>
          </template>

          <template v-if="authMode === 'token'">
            <label class="field">
              <span>Bearer Token</span>
              <textarea v-model="certForm.token" class="form-textarea" rows="3" placeholder="eyJhbGciOiJSUzI1NiIsInR5..." />
            </label>
          </template>

          <!-- 通用字段 -->
          <label class="field">
            <span>context（可选）</span>
            <input v-model="clusterForm.context" class="form-input" placeholder="default" />
          </label>
          <label class="field">
            <span>说明（可选）</span>
            <textarea v-model="clusterForm.description" class="form-textarea" rows="2" placeholder="例如：生产集群 / 华东机房"></textarea>
          </label>
        </div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="closeClusterModal">取消</button>
          <button class="btn-primary-lg" @click="saveCluster">{{ editingClusterId ? '保存修改' : '确认添加' }}</button>
        </div>
      </div>
    </div>

    <div v-if="showDetailModal" class="modal-mask" @click.self="closeDetailModal">
      <div class="modal-card detail-modal-card">
        <div class="modal-title">
          {{ detailModalTitle }}
          <div class="detail-view-tabs">
            <button :class="['detail-tab', { active: detailView === 'json' }]" @click="switchDetailView('json')" type="button">JSON</button>
            <button :class="['detail-tab', { active: detailView === 'yaml' }]" @click="switchDetailView('yaml')" type="button">YAML</button>
            <button :class="['detail-tab', { active: detailView === 'events' }]" @click="switchDetailView('events')" type="button">
              Events <span v-if="detailEvents.length" class="event-tab-count">{{ detailEvents.length }}</span>
            </button>
          </div>
        </div>
        <div class="modal-body">
          <div class="resource-head">
            <span class="resource-kind">{{ kindLabel(detailMeta.kind) }}</span>
            <span class="mono">{{ detailMeta.name }}</span>
            <span v-if="detailMeta.namespace" class="ns-tag">{{ detailMeta.namespace }}</span>
            <span v-if="detailView === 'yaml' && yamlEditing" class="yaml-edit-badge">编辑模式</span>
            <span v-if="yamlApplyError" class="yaml-apply-error" :title="yamlApplyError">⚠ 应用失败</span>
            <span v-if="yamlApplySuccess" class="yaml-apply-success">✓ 已应用</span>
          </div>
          <div v-if="detailError" class="modal-tip modal-tip-error">{{ detailError }}</div>
          <div v-else class="code-panel">
            <div v-if="detailLoading" class="loading-row compact">
              <span class="spinner"></span>
              正在加载详情...
            </div>
            <pre v-else-if="detailView === 'json'" class="json-view">{{ detailText }}</pre>
            <textarea
              v-else-if="detailView === 'yaml'"
              v-model="yamlBuffer"
              class="yaml-editor"
              :readonly="!yamlEditing"
              spellcheck="false"
              @input="onYamlInput"
            ></textarea>
            <!-- Events tab -->
            <div v-else class="events-panel">
              <div v-if="eventsLoading" class="loading-row compact">
                <span class="spinner"></span>正在加载 events...
              </div>
              <div v-else-if="!detailEvents.length" class="events-empty">
                此资源近期无 K8s events
              </div>
              <div v-else class="events-list">
                <div v-for="(ev, i) in detailEvents" :key="i" class="event-row" :class="'event-' + ev.type.toLowerCase()">
                  <div class="event-meta">
                    <span class="event-type-badge" :class="'event-type-' + ev.type.toLowerCase()">{{ ev.type }}</span>
                    <span class="event-reason">{{ ev.reason }}</span>
                    <span v-if="ev.count > 1" class="event-count">×{{ ev.count }}</span>
                    <span class="event-source">{{ ev.source }}</span>
                    <span class="event-ts" :title="ev.first_ts ? `首次: ${ev.first_ts}` : ''">{{ formatRelative(ev.last_ts) || ev.last_ts }}</span>
                  </div>
                  <div class="event-message">{{ ev.message }}</div>
                </div>
              </div>
            </div>
          </div>
          <div v-if="yamlApplyError" class="modal-tip modal-tip-error" style="margin-top:8px;white-space:pre-wrap">{{ yamlApplyError }}</div>
        </div>
        <div class="modal-actions">
          <template v-if="detailView === 'yaml'">
            <button v-if="!yamlEditing" class="btn-ghost" @click="startYamlEdit" :disabled="!detailData">✏️ 编辑</button>
            <template v-else>
              <button class="btn-ghost" @click="cancelYamlEdit">撤销</button>
              <button class="btn-primary-sm" @click="applyYamlEdit" :disabled="yamlApplying || !yamlDirty">
                {{ yamlApplying ? '应用中...' : '✓ 应用' }}
              </button>
            </template>
          </template>
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
        <div class="exec-term-wrap" ref="execTermEl"
          @mousedown="_execTerm?.focus()"
          @click="_execTerm?.focus()">
        </div>
      </div>
    </div>

    <!-- 底部浮动批量操作条（借鉴 jay-codemine/k8s_operation）-->
    <transition name="batch-bar-slide">
      <div v-if="currentSelectedKeys.length" class="batch-bar">
        <div class="batch-bar-left">
          <span class="batch-bar-count">已选 <strong>{{ currentSelectedKeys.length }}</strong> 个 {{ currentKind || '资源' }}</span>
          <button class="btn-ghost btn-xs" @click="clearSelection">清空选择</button>
        </div>
        <div class="batch-bar-right">
          <button v-if="canBatchRestart" class="batch-action-btn"
            :disabled="batchRunning" @click="runBatchAction('restart')">
            🔄 批量重启
          </button>
          <button v-if="canBatchDelete" class="batch-action-btn danger"
            :disabled="batchRunning" @click="runBatchAction('delete')">
            🗑 批量删除
          </button>
          <span v-if="!canBatchDelete && !canBatchRestart" class="batch-no-action">
            该资源类型无可用批量操作
          </span>
          <span v-if="batchRunning" class="spinner" style="width:14px;height:14px"></span>
        </div>
      </div>
    </transition>

    <!-- 镜像编辑模态 -->
    <div v-if="imageEditModal.open" class="modal-mask" @click.self="closeImageEdit">
      <div class="modal-card image-edit-card">
        <div class="modal-title">
          ✎ 编辑镜像
          <span class="image-edit-target">{{ imageEditModal.kind }} · {{ imageEditModal.namespace }}/{{ imageEditModal.name }}</span>
        </div>
        <div class="modal-body">
          <div class="image-edit-list">
            <div v-for="c in imageEditModal.containers" :key="c.name" class="image-edit-row">
              <span class="image-edit-cname">{{ c.name }}</span>
              <input v-model="c.image" class="form-input image-edit-input" placeholder="nginx:1.25-alpine" />
              <button v-if="c.image !== c.original" class="btn-xs btn-ghost" @click="c.image = c.original" title="还原">↻</button>
            </div>
          </div>
          <div v-if="imageEditModal.error" class="modal-tip modal-tip-error" style="margin-top:12px;white-space:pre-wrap">{{ imageEditModal.error }}</div>
          <div v-if="imageEditModal.success" class="modal-tip" style="margin-top:12px;color:#3fb950">✓ 已 patch, 触发 rolling update, 稍后刷新</div>
        </div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="closeImageEdit">取消</button>
          <button class="btn-primary-sm" @click="applyImageEdit" :disabled="!imageEditDirty || imageEditModal.applying">
            {{ imageEditModal.applying ? '应用中...' : '✓ 应用并 rolling update' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 批量操作结果模态 -->
    <div v-if="batchResult" class="modal-mask" @click.self="batchResult = null">
      <div class="modal-card batch-result-card">
        <div class="modal-title">
          批量{{ batchResult.action === 'delete' ? '删除' : '重启' }}结果
          <span class="batch-result-summary">
            <span class="batch-stat success">✓ {{ batchResult.success }}</span>
            <span v-if="batchResult.failed" class="batch-stat failed">✗ {{ batchResult.failed }}</span>
            <span class="batch-stat total">共 {{ batchResult.total }}</span>
          </span>
        </div>
        <div class="modal-body">
          <div class="batch-result-list">
            <div v-for="(r, i) in batchResult.results" :key="i"
              class="batch-result-row" :class="r.ok ? 'ok' : 'err'">
              <span class="batch-result-icon">{{ r.ok ? '✓' : '✗' }}</span>
              <span class="batch-result-name">
                <span class="ns-tag">{{ r.namespace }}</span>
                <span class="mono">{{ r.name }}</span>
              </span>
              <span v-if="r.error" class="batch-result-err" :title="r.error">{{ r.error.split('\n')[0].slice(0, 120) }}</span>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="batchResult = null">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onBeforeUnmount, onActivated, onDeactivated, reactive, ref, nextTick, watch } from 'vue'

defineOptions({ name: 'Containers' })

// ── 模块级缓存（跨组件实例存活；keep-alive 失效或首次实例化都能复用）
// key: `${clusterId}|${namespace}`  value: { summary, namespaces, pods, ..., lastFetchedAt }
const _resourceCache = new Map()
const CACHE_TTL_MS = 30_000   // 30 秒内 hit cache 直接返回，超过自动 miss
const AUTO_REFRESH_OPTIONS = [
  { value: 'off', label: '关闭', sec: 0 },
  { value: '30',  label: '30 秒', sec: 30 },
  { value: '60',  label: '1 分钟', sec: 60 },
  { value: '300', label: '5 分钟', sec: 300 },
]
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
// 缓存元数据 & 自动刷新
const lastFetchedAt = ref(0)              // 当前展示数据的 fetch 时间（ms）
const autoRefreshInterval = ref('off')    // 自动刷新档位：'off' / '30' / '60' / '300'
const _nowTick = ref(Date.now())          // 触发"X 秒前"相对时间重新计算
let _autoRefreshTimer = null              // 自动刷新 setInterval handle
let _nowTickTimer = null                  // _nowTick 每秒更新的 setInterval handle
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
const searchKeyword = ref('')
const showDetailModal = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detailData = ref(null)
// 详情视图 + YAML 编辑状态
const detailView = ref('json')        // 'json' | 'yaml' | 'events'
const yamlBuffer = ref('')            // textarea 双向绑定
const yamlOriginal = ref('')          // 加载后的原始 yaml（撤销用）
const yamlEditing = ref(false)
const yamlApplying = ref(false)
const yamlApplyError = ref('')
const yamlApplySuccess = ref(false)
// Events tab
const detailEvents = ref([])
const eventsLoading = ref(false)
// 镜像编辑弹窗
const imageEditModal = reactive({
  open: false, kind: '', name: '', namespace: '',
  containers: [],   // [{ name, image, original }]
  applying: false, error: '', success: false,
})
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
// 认证模式：kubeconfig | cert | token
const authMode     = ref('kubeconfig')
const detectLoading = ref(false)
const detectResult  = ref(null)   // 识别出的单个 file 对象
const detectError   = ref('')
// 粘贴文本入口
const pasteOpen     = ref(false)
const pasteContent  = ref('')
const pasteLoading  = ref(false)
const pasteResult   = ref(null)
const pasteError    = ref('')

const certForm = reactive({
  server: '',
  insecureSkipTLS: false,
  // CA
  caPath: '', caUploading: false,
  // 客户端证书
  clientCertPath: '', clientCertUploading: false,
  // 客户端私钥
  clientKeyPath: '', clientKeyUploading: false,
  // Token
  token: '',
})

// 上传证书文件到 data/ca/，上传完把路径回填到对应字段
async function handleCertUpload(e, certType) {
  const file = e.target.files[0]
  if (!file) return
  const uploadingKey = { ca: 'caUploading', 'client-cert': 'clientCertUploading', 'client-key': 'clientKeyUploading' }[certType]
  const pathKey      = { ca: 'caPath',      'client-cert': 'clientCertPath',      'client-key': 'clientKeyPath'      }[certType]
  certForm[uploadingKey] = true
  try {
    const r = await api.k8sUploadCert(file, certType)
    certForm[pathKey] = r.relative   // 回填相对路径
  } catch (err) {
    clusterTestMsg.value = '上传失败: ' + err
  } finally {
    certForm[uploadingKey] = false
  }
}

// 自动识别：调用 inspect-kubeconfig，解析认证类型并回填表单
async function autoDetect() {
  const path = clusterForm.kubeconfig.trim()
  if (!path) return
  detectLoading.value = true
  detectResult.value  = null
  detectError.value   = ''
  try {
    const res = await api.k8sInspectKubeconfig(path)
    if (res.error) { detectError.value = res.error; return }

    const firstFile = (res.files || [])[0]
    if (!firstFile) { detectError.value = '未解析到 kubeconfig 内容'; return }
    if (firstFile.error) { detectError.value = firstFile.error; return }

    detectResult.value = firstFile
    const auth = firstFile.auth || {}

    // 自动填充 server
    if (firstFile.server) certForm.server = firstFile.server

    // 自动填充 context
    if (firstFile.current_context) clusterForm.context = firstFile.current_context

    // 自动切换模式并填充字段
    if (auth.type === 'certificate') {
      authMode.value = 'cert'
      // 内嵌证书时显式标注"(已内嵌)"，让用户知道认证 OK，无需手动填路径
      const isEmbedded = auth.cert_embedded === true
      certForm.caPath = firstFile.ca && firstFile.ca !== '(none)' && firstFile.ca !== '(embedded)'
        ? firstFile.ca
        : (isEmbedded ? '(已内嵌在 kubeconfig 中，无需路径)' : '')
      certForm.clientCertPath = auth.client_certificate && auth.client_certificate !== '(embedded)'
        ? auth.client_certificate
        : (isEmbedded ? '(已内嵌在 kubeconfig 中，无需路径)' : '')
      certForm.clientKeyPath = auth.client_key && auth.client_key !== '(embedded)'
        ? auth.client_key
        : (isEmbedded ? '(已内嵌在 kubeconfig 中，无需路径)' : '')
    } else if (auth.type === 'token') {
      authMode.value = 'token'
      certForm.caPath = firstFile.ca && firstFile.ca !== '(none)' && firstFile.ca !== '(embedded)' ? firstFile.ca : ''
      certForm.token  = auth.token_preview || ''
    } else {
      // exec / basic / unknown → 保持 kubeconfig 路径模式
      authMode.value = 'kubeconfig'
    }
  } catch (e) {
    detectError.value = '识别失败: ' + e
  } finally {
    detectLoading.value = false
  }
}

// 用户在「kubeconfig 路径」框 paste 时：检测粘贴内容是不是 yaml 文本
//   - 是 yaml (含 apiVersion: + clusters: 等关键字) → 自动 upload-text 落盘 → 路径回填 → autoDetect
//   - 是普通路径 → 让浏览器默认 paste 进入输入框
async function onPathInputPaste(event) {
  const clipboard = event.clipboardData || window.clipboardData
  if (!clipboard) return
  const text = clipboard.getData('text') || ''
  if (!text) return

  // 关键字识别：必须同时含 apiVersion: 和 clusters: / kind: Config 至少一个 → 视为 kubeconfig yaml
  const lower = text.toLowerCase()
  const looksLikeYaml = lower.includes('apiversion:') &&
                        (lower.includes('clusters:') || lower.includes('kind: config') || lower.includes('kind:config'))
  if (!looksLikeYaml) return   // 当成普通路径处理

  // 拦截默认 paste，走自动落盘流程
  event.preventDefault()
  pasteContent.value = text
  pasteError.value   = ''

  // 集群名兜底：用户没填 → 生成临时名 (后续保存集群时仍用 form.name 真名)
  const fallbackName = (clusterForm.name || '').trim() ||
                       `pasted-${new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)}`

  pasteLoading.value = true
  pasteResult.value  = null
  try {
    const r = await api.k8sUploadKubeconfigText(fallbackName, text)
    pasteResult.value = r
    // 把后端返回的 relative 路径填进输入框, 替换原始粘贴文本
    clusterForm.kubeconfig = r.relative
    if (r.current_context) clusterForm.context = r.current_context
    await autoDetect()   // 自动触发证书/Token 识别
  } catch (e) {
    pasteError.value = '落盘失败: ' + (e?.response?.data?.detail || e?.message || e)
    // 失败也把文本填进输入框，让用户能手动改
    clusterForm.kubeconfig = text.split('\n')[0].slice(0, 80) + '...'
  } finally {
    pasteLoading.value = false
  }
}

// 把粘贴的 kubeconfig 文本提交后端落盘，再触发 autoDetect 走原流程
async function savePastedKubeconfig() {
  const name = clusterForm.name.trim()
  const content = pasteContent.value.trim()
  if (!name) { pasteError.value = '请先填写集群名称'; return }
  if (!content) { pasteError.value = 'kubeconfig 文本不能为空'; return }

  pasteLoading.value = true
  pasteResult.value  = null
  pasteError.value   = ''
  try {
    const r = await api.k8sUploadKubeconfigText(name, content)
    pasteResult.value = r
    // 回填路径，触发已有 autoDetect 流程
    clusterForm.kubeconfig = r.relative
    if (r.current_context) clusterForm.context = r.current_context
    await autoDetect()
  } catch (e) {
    pasteError.value = '保存失败: ' + (e?.response?.data?.detail || e?.message || e)
  } finally {
    pasteLoading.value = false
  }
}

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
const normalizedSearchKeyword = computed(() => searchKeyword.value.trim().toLowerCase())

function matchesSearch(parts) {
  const keyword = normalizedSearchKeyword.value
  if (!keyword) return true
  return parts.some((part) => String(part ?? '').toLowerCase().includes(keyword))
}

const filteredPods = computed(() =>
  pods.value.filter((pod) => matchesSearch([
    pod.name, pod.namespace, pod.status, pod.node, pod.restarts,
    ...(pod.containers || []).map((container) => container.name),
  ]))
)
const filteredDeployments = computed(() =>
  deployments.value.filter((item) => matchesSearch([
    item.name, item.namespace, item.status, item.ready, item.desired,
    ...(item.images || []),
  ]))
)
const filteredDaemonSets = computed(() =>
  daemonSets.value.filter((item) => matchesSearch([
    item.name, item.namespace, item.status, item.ready, item.desired,
    item.current, item.updated, item.available, ...(item.images || []),
  ]))
)
const filteredStatefulSets = computed(() =>
  statefulSets.value.filter((item) => matchesSearch([
    item.name, item.namespace, item.status, item.ready, item.desired,
    item.current, item.updated, ...(item.images || []),
  ]))
)
const filteredJobs = computed(() =>
  jobs.value.filter((item) => matchesSearch([
    item.name, item.namespace, item.status, item.succeeded, item.completions,
    item.parallelism, item.active, item.failed, ...(item.images || []),
  ]))
)
const filteredCronJobs = computed(() =>
  cronJobs.value.filter((item) => matchesSearch([
    item.name, item.namespace, item.status, item.schedule, item.active,
    item.lastScheduleTime, item.lastSuccessfulTime, ...(item.activeJobs || []),
  ]))
)
const filteredServices = computed(() =>
  services.value.filter((item) => matchesSearch([
    item.name, item.namespace, item.type, item.clusterIP, ...(item.ports || []),
  ]))
)
const filteredNodes = computed(() =>
  nodes.value.filter((item) => matchesSearch([
    item.name, item.status, item.roles, item.version, item.os,
  ]))
)

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
  detailView.value = 'json'
  yamlBuffer.value = ''
  yamlOriginal.value = ''
  yamlEditing.value = false
  yamlApplying.value = false
  yamlApplyError.value = ''
  yamlApplySuccess.value = false
  detailEvents.value = []
  eventsLoading.value = false
  Object.assign(detailMeta, { kind: '', name: '', namespace: '' })
}

function closeDetailModal() {
  showDetailModal.value = false
  resetDetailState()
}

// ── YAML 编辑 ────────────────────────────────────────────────────────────────
const yamlDirty = computed(() => yamlBuffer.value !== yamlOriginal.value)

function switchDetailView(view) {
  // 切走 yaml 视图时, 若有未保存编辑给个确认
  if (detailView.value === 'yaml' && yamlEditing.value && yamlDirty.value && view !== 'yaml') {
    if (!confirm('有未应用的 YAML 修改, 切走将丢弃, 是否继续?')) return
    cancelYamlEdit()
  }
  detailView.value = view
  yamlApplySuccess.value = false
  if (view === 'events' && !detailEvents.value.length && !eventsLoading.value) {
    loadDetailEvents()
  }
}

async function loadDetailEvents() {
  if (!detailMeta.kind || !detailMeta.name) return
  eventsLoading.value = true
  try {
    const r = await api.k8sResourceEvents(activeClusterId.value, detailMeta.kind, detailMeta.name, detailMeta.namespace)
    detailEvents.value = r?.items || []
  } catch (e) {
    detailEvents.value = []
  } finally {
    eventsLoading.value = false
  }
}

// ── 镜像点击编辑 ─────────────────────────────────────────────────────────────
const imageEditableKinds = new Set(['deployment', 'statefulset', 'daemonset', 'cronjob'])

function openImageEdit(kind, row) {
  const normalized = (kind || '').toLowerCase()
  if (!imageEditableKinds.has(normalized)) return
  const images = Array.isArray(row?.images) ? row.images : []
  const containerNames = Array.isArray(row?.container_names) ? row.container_names : []
  // 拼装 containers: 若后端没返回 container_names, 用 image 前缀 / images 数组兜底
  const containers = images.map((img, i) => ({
    name: containerNames[i] || `c${i + 1}`,
    image: img,
    original: img,
  }))
  if (!containers.length) {
    alert('未识别到容器列表, 请用 YAML 编辑')
    return
  }
  Object.assign(imageEditModal, {
    open: true, kind: normalized, name: row?.name || '', namespace: row?.namespace || '',
    containers, applying: false, error: '', success: false,
  })
}

function closeImageEdit() {
  imageEditModal.open = false
  imageEditModal.containers = []
  imageEditModal.error = ''
  imageEditModal.success = false
}

const imageEditDirty = computed(() =>
  imageEditModal.containers.some(c => c.image !== c.original)
)

async function applyImageEdit() {
  if (!imageEditDirty.value) return
  const changed = imageEditModal.containers.filter(c => c.image !== c.original)
  if (!confirm(`更新 ${imageEditModal.kind}/${imageEditModal.name} 的 ${changed.length} 个镜像? 将触发 rolling update.`)) return
  imageEditModal.applying = true
  imageEditModal.error = ''
  try {
    await api.k8sUpdateResourceImage(
      activeClusterId.value, imageEditModal.kind, imageEditModal.name, imageEditModal.namespace,
      imageEditModal.containers.map(c => ({ name: c.name, image: c.image })),
    )
    imageEditModal.success = true
    // 清缓存 + 静默刷新
    for (const key of Array.from(_resourceCache.keys())) {
      if (key.startsWith(`${activeClusterId.value}|`)) _resourceCache.delete(key)
    }
    setTimeout(() => { refreshAll(); closeImageEdit() }, 800)
  } catch (e) {
    imageEditModal.error = e?.response?.data?.detail || e?.message || String(e)
  } finally {
    imageEditModal.applying = false
  }
}

function startYamlEdit() {
  yamlEditing.value = true
  yamlApplyError.value = ''
  yamlApplySuccess.value = false
}

function cancelYamlEdit() {
  yamlBuffer.value = yamlOriginal.value
  yamlEditing.value = false
  yamlApplyError.value = ''
}

function onYamlInput() {
  yamlApplySuccess.value = false
}

// ── 批量选择 + 操作 (借鉴 jay-codemine/k8s_operation 浮动操作条) ─────────────
// 各 tab 独立的选中集合: key 形如 "deployment:default/nginx"
const selectedRows = ref(new Set())
const batchRunning = ref(false)
const batchResult  = ref(null)   // { action, total, success, failed, results: [] }

function rowKey(kind, row) {
  return `${kind}:${row?.namespace || ''}/${row?.name || ''}`
}

// 当前 tab 资源类型 → singular kind (用于 batch 请求)
const TAB_TO_KIND = {
  pods: 'pod',
  deployments: 'deployment',
  daemonSets: 'daemonset',
  statefulSets: 'statefulset',
  jobs: 'job',
  cronJobs: 'cronjob',
  services: 'service',
  nodes: 'node',
}
// 当前 tab 对应过滤后的列表 (用于全选)
const TAB_TO_LIST = {
  pods: () => sortedFilteredPods.value,
  deployments: () => filteredDeployments.value,
  daemonSets: () => filteredDaemonSets.value,
  statefulSets: () => filteredStatefulSets.value,
  jobs: () => filteredJobs.value,
  cronJobs: () => filteredCronJobs.value,
  services: () => filteredServices.value,
  nodes: () => filteredNodes.value,
}

const currentKind = computed(() => TAB_TO_KIND[activeTab.value] || '')
const currentList = computed(() => (TAB_TO_LIST[activeTab.value]?.() || []))
const currentSelectedKeys = computed(() => {
  const prefix = `${currentKind.value}:`
  return Array.from(selectedRows.value).filter(k => k.startsWith(prefix))
})
const allCurrentSelected = computed(() =>
  currentList.value.length > 0 &&
  currentList.value.every(row => selectedRows.value.has(rowKey(currentKind.value, row)))
)

function isRowSelected(kind, row) {
  return selectedRows.value.has(rowKey(kind, row))
}

function toggleRowSelected(kind, row) {
  const k = rowKey(kind, row)
  const next = new Set(selectedRows.value)
  next.has(k) ? next.delete(k) : next.add(k)
  selectedRows.value = next
}

function toggleAllCurrent() {
  const next = new Set(selectedRows.value)
  if (allCurrentSelected.value) {
    for (const row of currentList.value) next.delete(rowKey(currentKind.value, row))
  } else {
    for (const row of currentList.value) next.add(rowKey(currentKind.value, row))
  }
  selectedRows.value = next
}

function clearSelection() {
  selectedRows.value = new Set()
}

// 切换 tab 时清掉非当前 tab 的选中, 防止跨 tab 混淆
watch(activeTab, () => {
  const prefix = `${currentKind.value}:`
  const next = new Set()
  for (const k of selectedRows.value) {
    if (k.startsWith(prefix)) next.add(k)
  }
  selectedRows.value = next
})

const restartableKinds = new Set(['pod', 'deployment', 'statefulset', 'daemonset'])
const canBatchRestart = computed(() => restartableKinds.has(currentKind.value))
const deletableKinds  = new Set(['pod', 'deployment', 'daemonset', 'statefulset', 'job', 'cronjob', 'service'])
const canBatchDelete  = computed(() => deletableKinds.has(currentKind.value))

async function runBatchAction(action) {
  const keys = currentSelectedKeys.value
  if (!keys.length) return
  const items = keys.map(k => {
    const [, rest] = k.split(':', 2)   // 'deployment:default/nginx' → ['deployment','default/nginx']
    const [ns, name] = rest.split('/', 2)
    return { kind: currentKind.value, namespace: ns, name }
  })
  const verb = action === 'delete' ? '删除' : '重启'
  if (!confirm(`确认 ${verb} 已选 ${items.length} 个 ${currentKind.value}? 不可撤销.`)) return

  batchRunning.value = true
  batchResult.value  = null
  try {
    const r = await api.k8sBatchOperate(activeClusterId.value, action, items)
    batchResult.value = r
    // 清缓存 + 静默刷新
    for (const key of Array.from(_resourceCache.keys())) {
      if (key.startsWith(`${activeClusterId.value}|`)) _resourceCache.delete(key)
    }
    setTimeout(() => refreshAll(), 800)
    // 删除全部成功 → 清掉对应选中
    if (action === 'delete') {
      const next = new Set(selectedRows.value)
      for (const item of r.results || []) {
        if (item.ok) next.delete(rowKey(currentKind.value, item))
      }
      selectedRows.value = next
    }
  } catch (e) {
    alert(`批量${verb}失败: ` + (e?.response?.data?.detail || e?.message || e))
  } finally {
    batchRunning.value = false
  }
}

// ── 行内副本数 ± 控制 (Deployment / StatefulSet) ───────────────────────────
const scalingKey = ref('')   // 正在 scale 的资源唯一 key, 用于禁用按钮 + 显示 spinner

function scaleKey(kind, row) {
  return `${kind}:${row?.namespace || ''}/${row?.name || ''}`
}

async function scaleResource(kind, row, delta) {
  if (!row?.name || !row?.namespace) return
  const current = Number(row.desired) || 0
  const next = current + delta
  if (next < 0) return
  if (next > 1000) { alert('副本数不能超过 1000'); return }
  if (delta < 0 && next === 0) {
    if (!confirm(`将 ${kind} ${row.namespace}/${row.name} 缩到 0 副本 (停止服务)?`)) return
  }
  const key = scaleKey(kind, row)
  scalingKey.value = key
  try {
    await api.k8sScaleResource(activeClusterId.value, kind, row.name, row.namespace, next)
    // 乐观更新 UI: 立即改 row 的 desired (ready 等下次刷新真实数据)
    row.desired = next
    // 清缓存让下次 fetchAll 拿真实数据
    for (const cacheKey of Array.from(_resourceCache.keys())) {
      if (cacheKey.startsWith(`${activeClusterId.value}|`)) _resourceCache.delete(cacheKey)
    }
    // 静默后台刷新 (不显示 loading)
    setTimeout(() => refreshAll(), 1200)
  } catch (e) {
    const detail = e?.response?.data?.detail || e?.message || String(e)
    alert(`扩缩容失败: ${detail}`)
  } finally {
    scalingKey.value = ''
  }
}

async function applyYamlEdit() {
  if (!yamlDirty.value) return
  if (!confirm(`确认应用对 ${detailMeta.kind}/${detailMeta.name} 的 YAML 修改? 这将直接 replace 到集群.`)) return
  yamlApplying.value = true
  yamlApplyError.value = ''
  yamlApplySuccess.value = false
  try {
    const r = await api.k8sUpdateResourceYaml(
      activeClusterId.value, detailMeta.kind, detailMeta.name, detailMeta.namespace, yamlBuffer.value,
    )
    detailData.value = r?.data ?? r
    // 后端返回最新对象, 重新生成 yaml (前端简化: 重置 original = buffer, 让 dirty=false)
    // 同时再调一次 detail 拿规范化 yaml (resourceVersion 等会变)
    try {
      const fresh = await api.k8sResourceDetail(activeClusterId.value, detailMeta.kind, detailMeta.name, detailMeta.namespace)
      detailData.value = fresh?.data ?? fresh
      yamlOriginal.value = fresh?.yaml || yamlBuffer.value
      yamlBuffer.value = yamlOriginal.value
    } catch {
      yamlOriginal.value = yamlBuffer.value
    }
    yamlEditing.value = false
    yamlApplySuccess.value = true
    // 清掉对应集群缓存（让用户切回列表立即看到新状态）
    for (const key of Array.from(_resourceCache.keys())) {
      if (key.startsWith(`${activeClusterId.value}|`)) _resourceCache.delete(key)
    }
  } catch (e) {
    yamlApplyError.value = e?.response?.data?.detail || e?.message || String(e)
  } finally {
    yamlApplying.value = false
  }
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

const lastFetchedText = computed(() => {
  if (!lastFetchedAt.value) return '尚未加载'
  const diff = Math.max(0, _nowTick.value - lastFetchedAt.value)
  const sec = Math.floor(diff / 1000)
  if (sec < 5)    return '刚刚'
  if (sec < 60)   return `${sec} 秒前`
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`
  return new Date(lastFetchedAt.value).toLocaleTimeString()
})

function tabCount(id) {
  const mapping = {
    pods: filteredPods.value.length,
    deployments: filteredDeployments.value.length,
    daemonSets: filteredDaemonSets.value.length,
    statefulSets: filteredStatefulSets.value.length,
    jobs: filteredJobs.value.length,
    cronJobs: filteredCronJobs.value.length,
    services: filteredServices.value.length,
    nodes: filteredNodes.value.length,
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

function _applyCachedPayload(payload) {
  summary.value      = payload.summary
  namespaces.value   = payload.namespaces
  pods.value         = payload.pods
  deployments.value  = payload.deployments
  daemonSets.value   = payload.daemonSets
  statefulSets.value = payload.statefulSets
  jobs.value         = payload.jobs
  cronJobs.value     = payload.cronJobs
  services.value     = payload.services
  nodes.value        = payload.nodes
  lastFetchedAt.value = payload.lastFetchedAt
}

// fetchAll(opts)
//   opts.force = true  → 跳过缓存强制重拉（手动「刷新」按钮 / 自动 timer）
//   默认走缓存：命中 TTL 内的缓存就直接渲染，否则才发请求
//   兼容旧调用：参数若为 Event（select.change 等），按非 force 处理
async function fetchAll(opts) {
  const force = (opts && opts.force === true) === true
  if (!activeClusterId.value) {
    resetData()
    return
  }
  const clusterId = activeClusterId.value
  const ns = activeNs.value || ''
  const key = `${clusterId}|${ns}`

  if (!force) {
    const cached = _resourceCache.get(key)
    if (cached && Date.now() - cached.lastFetchedAt < CACHE_TTL_MS) {
      _applyCachedPayload(cached)
      return
    }
  }

  loading.value = true
  error.value = ''
  try {
    const nsArg = ns || undefined
    const [sum, nsList, podList, depList, daemonSetList, statefulSetList, jobList, cronJobList, svcList, nodeList] = await Promise.all([
      api.k8sSummary(clusterId).catch(() => null),
      api.k8sNamespaces(clusterId).catch(() => []),
      api.k8sPods(clusterId, nsArg).catch(() => []),
      api.k8sDeployments(clusterId, nsArg).catch(() => []),
      api.k8sDaemonSets(clusterId, nsArg).catch(() => []),
      api.k8sStatefulSets(clusterId, nsArg).catch(() => []),
      api.k8sJobs(clusterId, nsArg).catch(() => []),
      api.k8sCronJobs(clusterId, nsArg).catch(() => []),
      api.k8sServices(clusterId, nsArg).catch(() => []),
      api.k8sNodes(clusterId).catch(() => []),
    ])
    const payload = {
      summary: sum,
      namespaces: nsList,
      pods: podList,
      deployments: depList,
      daemonSets: daemonSetList,
      statefulSets: statefulSetList,
      jobs: jobList,
      cronJobs: cronJobList,
      services: svcList,
      nodes: nodeList,
      lastFetchedAt: Date.now(),
    }
    _resourceCache.set(key, payload)
    _applyCachedPayload(payload)
  } catch (e) {
    error.value = `加载失败: ${e}`
  } finally {
    loading.value = false
  }
}

// 用户主动刷新（按钮 / timer）：跳过缓存
function refreshAll() {
  return fetchAll({ force: true })
}

async function selectCluster(clusterId) {
  if (!clusterId || clusterId === activeClusterId.value) return
  activeClusterId.value = clusterId
  activeNs.value = ''
  resetNotice()
  await fetchAll()   // 走缓存：切回老集群时秒回
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
  // 重置检测状态和 certForm
  authMode.value      = 'kubeconfig'
  detectResult.value  = null
  detectError.value   = ''
  pasteOpen.value     = false
  pasteContent.value  = ''
  pasteResult.value   = null
  pasteError.value    = ''
  pasteLoading.value  = false
  Object.assign(certForm, {
    server: '', insecureSkipTLS: false, caPath: '', caUploading: false,
    clientCertPath: '', clientCertUploading: false,
    clientKeyPath: '',  clientKeyUploading: false,
    token: '',
  })
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
    yamlOriginal.value = result?.yaml || ''
    yamlBuffer.value = yamlOriginal.value
  } catch (e) {
    detailError.value = `加载详情失败：${e}`
  } finally {
    detailLoading.value = false
  }
}

// 将 K8s 日志中的 UTC 时间戳（2026-05-10T05:37:26.564872329Z）转为东八区（2026-05-10 13:37:26 +08）
function toCST(raw) {
  if (!raw) return raw
  return raw.replace(
    /(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?(Z)/gm,
    (_, dt) => {
      const d = new Date(dt + 'Z')
      // UTC+8 偏移
      d.setTime(d.getTime() + 8 * 3600 * 1000)
      const pad = n => String(n).padStart(2, '0')
      return `${d.getUTCFullYear()}-${pad(d.getUTCMonth()+1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} +08`
    }
  )
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
    logText.value = toCST(result?.logs || '')
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
  const name = clusterForm.name.trim()
  if (!name) {
    clusterTestResult.value = false
    clusterTestMsg.value = '集群名称不能为空'
    return
  }

  // 多行输入 → 用系统路径分隔符拼接（Linux: ":" / Windows: ";"）
  const pathSep = navigator.platform.startsWith('Win') ? ';' : ':'
  let kubeconfigPath = clusterForm.kubeconfig
    .split('\n')
    .map(l => l.trim())
    .filter(Boolean)
    .join(pathSep)

  // 证书 / token 模式：先上传证书再生成 kubeconfig
  if (authMode.value !== 'kubeconfig') {
    if (!certForm.server.trim()) {
      clusterTestResult.value = false
      clusterTestMsg.value = 'API Server 地址不能为空'
      return
    }
    if (!certForm.insecureSkipTLS && !certForm.caPath.trim()) {
      clusterTestResult.value = false
      clusterTestMsg.value = '请填写 CA 证书路径（或勾选跳过 TLS 验证）'
      return
    }

    const caRelative = certForm.caPath.trim()

    let clientCertRel = '', clientKeyRel = ''
    if (authMode.value === 'cert') {
      if (!certForm.clientCertPath.trim()) {
        clusterTestResult.value = false; clusterTestMsg.value = '请填写客户端证书路径'; return
      }
      if (!certForm.clientKeyPath.trim()) {
        clusterTestResult.value = false; clusterTestMsg.value = '请填写客户端私钥路径'; return
      }
      clientCertRel = certForm.clientCertPath.trim()
      clientKeyRel  = certForm.clientKeyPath.trim()
    }

    clusterTestMsg.value = '生成 kubeconfig...'
    try {
      const r = await api.k8sGenerateKubeconfig({
        name,
        server:                   certForm.server.trim(),
        ca_cert:                  caRelative,
        client_cert:              clientCertRel,
        client_key:               clientKeyRel,
        token:                    authMode.value === 'token' ? certForm.token.trim() : '',
        insecure_skip_tls_verify: certForm.insecureSkipTLS,
        context:     clusterForm.context.trim() || 'default',
        description: clusterForm.description.trim(),
      })
      kubeconfigPath = r.relative
    } catch (e) {
      clusterTestResult.value = false
      clusterTestMsg.value = '生成 kubeconfig 失败: ' + e
      return
    }
  }

  if (!kubeconfigPath) {
    clusterTestResult.value = false
    clusterTestMsg.value = 'kubeconfig 路径不能为空'
    return
  }

  const payload = {
    name,
    kubeconfig:  kubeconfigPath,
    context:     clusterForm.context.trim(),
    description: clusterForm.description.trim(),
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
    // 集群配置可能变了，清掉这个集群相关的缓存
    for (const key of Array.from(_resourceCache.keys())) {
      if (key.startsWith(`${saved.id}|`)) _resourceCache.delete(key)
    }
    await loadClusters()
    activeClusterId.value = saved.id
    activeNs.value = ''
    closeClusterModal()
    await fetchAll({ force: true })
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
  const deletedId = activeCluster.value.id
  try {
    await api.k8sDeleteCluster(deletedId)
    resetNotice()
    // 清掉这个集群在缓存里的所有 ns 条目
    for (const key of Array.from(_resourceCache.keys())) {
      if (key.startsWith(`${deletedId}|`)) _resourceCache.delete(key)
    }
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

function _formatAuthInfo(authInfo) {
  if (!authInfo?.files?.length) return ''
  return authInfo.files.map(f => {
    if (f.error) return `  ⚠ ${f.path}: ${f.error}`
    const auth = f.auth || {}
    const typeLabel = { certificate: '证书认证', token: 'Token认证', exec: 'Exec插件', basic: '用户名密码', unknown: '未知' }[auth.type] || auth.type
    let detail = `  认证: ${typeLabel}`
    if (auth.type === 'certificate') {
      const cd = auth.cert_detail || {}
      if (cd.subject) detail += ` | 用户: ${cd.subject}`
      if (cd.not_after) detail += ` | 过期: ${cd.not_after}`
    } else if (auth.type === 'token') {
      detail += ` | ${auth.token_file ? '文件: ' + auth.token_file : 'Token: ' + auth.token_preview}`
    } else if (auth.type === 'exec') {
      detail += ` | 命令: ${auth.command} ${(auth.args || []).join(' ')}`
    }
    return `  Server: ${f.server}\n${detail}\n  CA: ${f.ca}`
  }).join('\n')
}

async function testActiveCluster() {
  if (!activeCluster.value) return
  try {
    const result = await api.k8sTestCluster(activeCluster.value.id)
    const authStr = _formatAuthInfo(result.auth_info)
    clusterTestResult.value = result.ok
    clusterTestMsg.value = result.ok
      ? `连接成功，共 ${result.node_count} 个节点：${(result.nodes || []).join(', ')}\nkubeconfig：${result.resolved_kubeconfig || result.kubeconfig}${authStr ? '\n' + authStr : ''}${result.kubectl_command ? '\nkubectl：' + result.kubectl_command : ''}`
      : `连接失败：${result.error}${result.resolved_kubeconfig ? '\n路径：' + result.resolved_kubeconfig : ''}${authStr ? '\n' + authStr : ''}`
  } catch (e) {
    clusterTestResult.value = false
    clusterTestMsg.value = `测试失败：${e}`
  }
}

// ── Pod 重启次数统计 ─────────────────────────────────────────────────────────
const FREQUENT_RESTART_THRESHOLD = 5
// 重启原因严重度分级：danger (内存/被杀) / warn (退出错误) / info (正常完成/拉镜像中)
const RESTART_REASON_LEVEL = {
  OOMKilled:           'danger',
  Error:               'danger',
  ContainerCannotRun:  'danger',
  CrashLoopBackOff:    'danger',
  DeadlineExceeded:    'danger',
  Evicted:             'danger',
  Killed:              'warn',
  ContainerStatusUnknown: 'warn',
  ImagePullBackOff:    'warn',
  ErrImagePull:        'warn',
  CreateContainerError:'warn',
  CreateContainerConfigError: 'warn',
  Completed:           'info',
  ContainerCreating:   'info',
  PodInitializing:     'info',
}

const podRestartStats = computed(() => {
  let total = 0, withRestart = 0, frequent = 0, maxRestart = 0, maxPod = null
  const reasonCounts = {}
  for (const p of pods.value) {
    const r = Number(p.restarts) || 0
    total += r
    if (r > 0) withRestart++
    if (r >= FREQUENT_RESTART_THRESHOLD) frequent++
    if (r > maxRestart) { maxRestart = r; maxPod = p }
    if (r > 0 && p.last_restart_reason) {
      reasonCounts[p.last_restart_reason] = (reasonCounts[p.last_restart_reason] || 0) + 1
    }
  }
  // 取出现最多的 top 3 原因
  const topReasons = Object.entries(reasonCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([reason, count]) => ({ reason, count }))
  return {
    totalRestarts: total,
    withRestart,
    frequent,
    maxRestart,
    maxPod,
    podTotal: pods.value.length,
    topReasons,
  }
})

function restartClass(n) {
  const v = Number(n) || 0
  if (v >= FREQUENT_RESTART_THRESHOLD) return 'restart-high'
  if (v > 0) return 'restart-mid'
  return 'restart-zero'
}

function restartReasonClass(reason) {
  return 'reason-' + (RESTART_REASON_LEVEL[reason] || 'neutral')
}

// 把后端返回的 ISO 时间戳格式化为本地时区 YYYY-MM-DD HH:MM:SS（精确到秒）
function formatDateTime(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return String(iso)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// 相对时间（"3 天前 / 5 小时前 / 12 分钟前 / 35 秒前"），用于 hover title
function formatRelative(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  const diff = Date.now() - d.getTime()
  if (diff < 0) return '未来'
  const sec = Math.floor(diff / 1000)
  if (sec < 60)   return `${sec} 秒前`
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`
  if (sec < 86400) {
    const h = Math.floor(sec / 3600)
    const m = Math.floor((sec % 3600) / 60)
    return m ? `${h} 小时 ${m} 分前` : `${h} 小时前`
  }
  const days = Math.floor(sec / 86400)
  const hours = Math.floor((sec % 86400) / 3600)
  return hours ? `${days} 天 ${hours} 小时前` : `${days} 天前`
}

function restartReasonTitle(pod) {
  const parts = [`原因: ${pod.last_restart_reason}`]
  if (pod.last_restart_container) parts.push(`容器: ${pod.last_restart_container}`)
  if (pod.last_restart_exit_code !== null && pod.last_restart_exit_code !== undefined) {
    parts.push(`退出码: ${pod.last_restart_exit_code}`)
  }
  if (pod.last_restart_time) {
    parts.push(`时间: ${new Date(pod.last_restart_time).toLocaleString()}`)
  }
  return parts.join('\n')
}

// Pods 表格按重启次数排序：null=默认时间序 / 'desc' / 'asc'
const podRestartSortOrder = ref(null)
function togglePodRestartSort() {
  podRestartSortOrder.value =
    podRestartSortOrder.value === null  ? 'desc' :
    podRestartSortOrder.value === 'desc' ? 'asc'  : null
}
const sortedFilteredPods = computed(() => {
  const list = filteredPods.value
  if (!podRestartSortOrder.value) return list
  const dir = podRestartSortOrder.value === 'desc' ? -1 : 1
  return [...list].sort((a, b) => dir * ((Number(a.restarts) || 0) - (Number(b.restarts) || 0)))
})

// ── 资源关键字搜索统计（替代原 kubeconfig 认证检测）──────────────────────────
// 按 tab 顺序汇总每类资源在 searchKeyword 下的匹配数；点击 chip 可直接跳到对应 tab
const searchMatchSummary = computed(() => [
  { tab: 'pods',         label: 'Pods',         count: filteredPods.value.length },
  { tab: 'deployments',  label: 'Deployments',  count: filteredDeployments.value.length },
  { tab: 'daemonSets',   label: 'DaemonSets',   count: filteredDaemonSets.value.length },
  { tab: 'statefulSets', label: 'StatefulSets', count: filteredStatefulSets.value.length },
  { tab: 'jobs',         label: 'Jobs',         count: filteredJobs.value.length },
  { tab: 'cronJobs',     label: 'CronJobs',     count: filteredCronJobs.value.length },
  { tab: 'services',     label: 'Services',     count: filteredServices.value.length },
  { tab: 'nodes',        label: 'Nodes',        count: filteredNodes.value.length },
])
const searchTotalCount = computed(() =>
  searchMatchSummary.value.reduce((s, i) => s + i.count, 0)
)

function _stopAutoRefresh() {
  if (_autoRefreshTimer) { clearInterval(_autoRefreshTimer); _autoRefreshTimer = null }
}

function _startAutoRefresh() {
  _stopAutoRefresh()
  const opt = AUTO_REFRESH_OPTIONS.find(o => o.value === autoRefreshInterval.value)
  if (!opt || opt.sec <= 0) return
  _autoRefreshTimer = setInterval(() => {
    // 仅当没在加载、且页面可见时触发
    if (loading.value) return
    if (typeof document !== 'undefined' && document.hidden) return
    refreshAll()
  }, opt.sec * 1000)
}

function _startNowTick() {
  if (_nowTickTimer) return
  _nowTickTimer = setInterval(() => { _nowTick.value = Date.now() }, 1000)
}
function _stopNowTick() {
  if (_nowTickTimer) { clearInterval(_nowTickTimer); _nowTickTimer = null }
}

// 用户改自动刷新档位 → 立即应用
watch(autoRefreshInterval, () => _startAutoRefresh())

onMounted(async () => {
  _startNowTick()
  await loadClusters()
  // 首次进入：走缓存逻辑；若是冷启动 cache miss 会拉一次
  await fetchAll()
  _startAutoRefresh()
})

// keep-alive 复活：只重启 timer，不重拉数据（让用户决定）
onActivated(() => {
  _startNowTick()
  _startAutoRefresh()
})

// keep-alive 离开：暂停 timer，避免无谓请求
onDeactivated(() => {
  _stopAutoRefresh()
  _stopNowTick()
})

onBeforeUnmount(() => {
  _stopAutoRefresh()
  _stopNowTick()
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
  _execTerm.focus()   // ← 必须：让终端获取键盘焦点，否则无法输入

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
    _execTerm?.focus()   // ← WS 建立后再次 focus，确保可以立即输入
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

.page-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px 10px; border-bottom: 1px solid var(--border-light); flex-shrink: 0; gap: 12px; }
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

.search-input { padding: 6px 10px; min-width: 160px; width: 200px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-input); color: var(--text-primary); outline: none; }
.search-input:focus { border-color: var(--accent); }
.ns-select { padding: 6px 10px; cursor: pointer; min-width: 180px; }
.auto-refresh-select { min-width: 130px; }
.cache-stamp {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 5px 10px; border-radius: 6px;
  background: var(--bg-input); border: 1px solid var(--border);
  font-size: 11px; color: var(--text-muted); white-space: nowrap;
  user-select: none;
}

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
/* 资源关键字搜索卡片（原 kubeconfig 检测卡片改造） */
.inspect-card  { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; }
.inspect-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; }
.inspect-row   { display: flex; gap: 8px; align-items: center; }
.inspect-input { flex: 1; font-family: inherit; font-size: 13px; }
.inspect-btn   { flex-shrink: 0; white-space: nowrap; }
.inspect-result { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }

/* 资源匹配统计 chip 群 */
.search-stats {
  display: flex; flex-wrap: wrap; gap: 6px;
}
.search-stat-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: 9999px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 11px; cursor: pointer;
  transition: all .12s;
}
.search-stat-chip:hover {
  border-color: var(--accent);
  color: var(--text-primary);
}
.search-stat-chip.active {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
  font-weight: 600;
}
.search-stat-chip.zero {
  opacity: .45;
}
.search-stat-name  { font-weight: 500; }
.search-stat-count {
  background: var(--bg-card);
  padding: 1px 6px; border-radius: 9999px;
  font-weight: 700; font-size: 10px;
}
.search-stat-chip.active .search-stat-count {
  background: var(--accent);
  color: var(--bg-card);
}
.search-empty {
  font-size: 12px; color: var(--text-muted); padding: 6px 2px;
}
.search-empty em { color: var(--text-primary); font-style: normal; font-family: monospace; }

.error-banner {
  margin: 12px 20px 0;
  border-radius: 8px;
  padding: 9px 12px;
  font-size: 12px;
}

.cluster-banner.ok { background: rgba(26,127,55,0.08); border: 1px solid rgba(26,127,55,0.22); color: var(--success); }
.cluster-banner.err,
.error-banner { background: rgba(207,34,46,0.07); border: 1px solid rgba(207,34,46,0.25); color: var(--error); }
.cluster-banner { white-space: pre-line; word-break: break-all; }
.error-banner { display: flex; align-items: center; gap: 7px; }

.empty-state { flex: 1; display: flex; align-items: center; justify-content: center; padding: 24px; }
.empty-card {
  width: min(460px, 100%);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 22px;
  text-align: center;
  box-shadow: var(--shadow-sm);
}
.empty-title { font-size: 17px; font-weight: 600; margin-bottom: 8px; }
.empty-subtitle { color: var(--text-muted); font-size: 13px; line-height: 1.6; margin-bottom: 16px; }

.workspace-body { flex: 1; min-height: 0; display: flex; gap: 12px; padding: 10px 16px 16px; }

.cluster-sidebar {
  width: 270px;
  min-width: 270px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.sidebar-head {
  padding: 12px 12px 8px;
  border-bottom: 1px solid var(--border-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.sidebar-title { font-size: 14px; font-weight: 600; }
.sidebar-subtitle { display: none; }

.cluster-card-list {
  padding: 10px;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cluster-card {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px;
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
.cluster-card-desc { display: none; }
.cluster-card-path { display: none; }

.content-area { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; }

.cluster-meta { display: grid; grid-template-columns: 200px 200px 1fr; gap: 10px; flex-shrink: 0; }
.meta-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  min-width: 0;
}
.meta-card.wide { min-width: 0; }
.meta-label { font-size: 11px; color: var(--text-muted); margin-bottom: 6px; }
.meta-value { font-size: 14px; font-weight: 600; color: var(--text-primary); word-break: break-all; }
.meta-sub { display: none; }
.meta-card.compact { padding: 10px 12px; }

.summary-row { display: flex; flex-wrap: wrap; gap: 10px; padding-top: 10px; flex-shrink: 0; }
.stat-card { flex: 1 1 180px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; display: flex; align-items: center; gap: 10px; }
.stat-card.compact { display: none; }
.stat-card.warn { border-color: rgba(154,103,0,0.3); background: rgba(154,103,0,0.05); }
.stat-icon { width: 34px; height: 34px; border-radius: 8px; display: flex; align-items: center; justify-content: center; }
.stat-icon.node { background: var(--accent-dim); color: var(--accent); }
.stat-icon.pod { background: rgba(26,127,55,0.12); color: var(--success); }
.stat-icon.deploy { background: rgba(154,103,0,0.12); color: var(--warning); }
.stat-icon.daemon { background: rgba(99,102,241,0.12); color: #4f46e5; }
.stat-icon.stateful { background: rgba(14,165,233,0.12); color: #0284c7; }
.stat-icon.job { background: rgba(20,184,166,0.12); color: #0f766e; }
.stat-icon.cron { background: rgba(217,119,6,0.12); color: #b45309; }
.stat-icon.restart { background: rgba(248,81,73,.12); color: var(--error, #f85149); }
.restart-card { transition: border-color .15s, transform .12s; }
.restart-card:hover { transform: translateY(-1px); border-color: var(--accent); }
.restart-card.danger { border-color: rgba(248,81,73,.5) !important; background: rgba(248,81,73,.05) !important; }
.stat-warn-tag { color: var(--warning); font-weight: 600; margin-left: 4px; }
.stat-value { font-size: 20px; font-weight: 700; line-height: 1; }
.stat-total { font-size: 13px; color: var(--text-muted); font-weight: 400; }
.stat-label { font-size: 11px; color: var(--text-muted); margin-top: 3px; }

.tab-row { display: flex; gap: 4px; padding-top: 8px; flex-shrink: 0; }
.tab-btn { padding: 5px 12px; border-radius: 6px; border: 1px solid transparent; background: none; color: var(--text-secondary); font-size: 12px; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: all .15s; }
.tab-btn:hover { color: var(--text-primary); background: var(--bg-hover); }
.tab-btn.active { background: var(--accent-dim); border-color: var(--border-accent); color: var(--accent); font-weight: 500; }
.tab-count { font-size: 10px; background: var(--bg-surface); border: 1px solid var(--border); padding: 1px 5px; border-radius: 8px; color: var(--text-secondary); }

.loading-row { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 28px; color: var(--text-muted); }
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

/* Pod 重启次数徽章：0=灰 1-4=黄 ≥5=红 */
.restart-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 26px; padding: 1px 8px;
  border-radius: 9999px;
  font-size: 11px; font-weight: 700;
  font-family: monospace;
}
.restart-badge.restart-zero { background: var(--bg-input); color: var(--text-muted); }
.restart-badge.restart-mid  { background: rgba(210,153,34,.18); color: var(--warning); }
.restart-badge.restart-high { background: rgba(248,81,73,.18); color: var(--error, #f85149); }

/* 可排序表头 */
.sortable-th { cursor: pointer; user-select: none; }
.sortable-th:hover { color: var(--text-primary); }
.sort-indicator { font-size: 10px; margin-left: 4px; opacity: .7; }

/* 重启原因标签：danger=红、warn=黄、info=蓝、neutral=灰 */
.restart-reason {
  display: inline-flex; align-items: center;
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 10px; font-weight: 600;
  font-family: monospace;
  cursor: help;
  white-space: nowrap;
  border: 1px solid transparent;
}
.restart-reason.reason-danger  { background: rgba(248,81,73,.12); color: var(--error, #f85149); border-color: rgba(248,81,73,.3); }
.restart-reason.reason-warn    { background: rgba(210,153,34,.15); color: var(--warning); border-color: rgba(210,153,34,.3); }
.restart-reason.reason-info    { background: rgba(56,139,253,.12); color: var(--accent); border-color: rgba(56,139,253,.3); }
.restart-reason.reason-neutral { background: var(--bg-input); color: var(--text-muted); border-color: var(--border); }
.restart-reason.mini { font-size: 9px; padding: 0 5px; }
.restart-reason em { font-style: normal; opacity: .75; margin-left: 3px; }

/* 汇总卡片底部 reason 行 */
.restart-reason-row {
  display: flex; flex-wrap: wrap; gap: 4px;
  margin-top: 4px;
}
.restart-reason-row .restart-reason { margin-left: 0; }

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

/* 自动识别行 */
.detect-row { display: flex; gap: 8px; align-items: center; }
.detect-input { flex: 1; font-family: monospace; font-size: 12px; }
.btn-detect {
  padding: 5px 14px; font-size: 12px; border-radius: 5px; cursor: pointer; white-space: nowrap;
  border: 1px solid var(--accent); color: var(--accent); background: rgba(56,139,253,.08);
  transition: all .1s; flex-shrink: 0;
}
.btn-detect:hover:not(:disabled) { background: rgba(56,139,253,.18); }
.btn-detect:disabled { opacity: .5; cursor: not-allowed; }
.btn-detect.loading { opacity: .7; }

/* 粘贴 kubeconfig 文本 */
.paste-header {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 0; cursor: pointer;
  color: var(--text-muted); font-size: 12px;
  user-select: none;
}
.paste-header:hover { color: var(--text-primary); }
.paste-toggle { display: inline-block; width: 10px; font-size: 9px; }
.paste-body {
  margin-top: 6px;
  display: flex; flex-direction: column; gap: 8px;
}
.paste-actions {
  display: flex; align-items: center; gap: 10px;
  flex-wrap: wrap;
}
.paste-success {
  color: var(--success, #3fb950);
  font-size: 12px;
}
.paste-success em {
  font-style: normal;
  color: var(--text-muted);
  font-family: monospace;
  margin-left: 4px;
}
.paste-error {
  color: var(--error, #f85149);
  font-size: 12px;
}
.detect-tag-embedded {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 7px;
  border-radius: 9999px;
  background: rgba(63,185,80,.18);
  color: #3fb950;
  border: 1px solid rgba(63,185,80,.4);
  font-size: 10px;
  font-weight: 700;
  vertical-align: middle;
}

/* 识别结果卡片 */
.detect-result {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 8px 12px; border-radius: 7px; border: 1px solid;
  font-size: 12px; position: relative;
}
.detect-certificate { background: rgba(56,139,253,.08);  border-color: rgba(56,139,253,.3); }
.detect-token       { background: rgba(63,185,80,.08);   border-color: rgba(63,185,80,.3); }
.detect-exec        { background: rgba(163,113,247,.08); border-color: rgba(163,113,247,.3); }
.detect-unknown     { background: var(--bg-input);       border-color: var(--border); }
.detect-icon  { font-size: 18px; flex-shrink: 0; }
.detect-info  { display: flex; flex-direction: column; gap: 2px; flex: 1; }
.detect-type  { font-weight: 700; color: var(--text-primary); }
.detect-server{ font-family: monospace; font-size: 11px; color: var(--text-muted); }
.detect-sub   { font-size: 11px; color: var(--text-muted); }
.detect-expired { color: var(--error) !important; font-weight: 600; }
.detect-clear { position: absolute; top: 6px; right: 8px; background: none; border: none; cursor: pointer; color: var(--text-muted); font-size: 13px; }
.detect-error { font-size: 12px; color: var(--error); padding: 4px 0; }

/* 证书路径输入行 */
.cert-path-row { display: flex; gap: 6px; align-items: center; }
.cert-path-row .form-input { flex: 1; font-family: monospace; font-size: 12px; }

/* 认证模式 */
.auth-mode-tabs { display: flex; gap: 4px; }
.auth-tab {
  padding: 4px 12px; font-size: 12px; border-radius: 5px; cursor: pointer;
  border: 1px solid var(--border); background: transparent; color: var(--text-secondary);
  transition: all .1s;
}
.auth-tab:hover { background: var(--sidebar-hover); }
.auth-tab.active { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }

/* 证书上传行 */
.cert-upload-field { display: flex; flex-direction: column; gap: 4px; }
.cert-upload-row { display: flex; align-items: center; gap: 8px; }
.cert-name { flex: 1; font-size: 12px; color: var(--text-muted); font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cert-upload-btn {
  padding: 4px 12px; font-size: 12px; border-radius: 4px; cursor: pointer;
  border: 1px solid var(--border); background: var(--bg-input); color: var(--text-secondary);
  white-space: nowrap; flex-shrink: 0;
}
.cert-upload-btn:hover { border-color: var(--accent); color: var(--accent); }
.required { color: var(--error); font-style: normal; }
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
.log-view,
.yaml-editor {
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

/* YAML 编辑器: 复用 code-panel 样式, 编辑模式有蓝边强调 */
.yaml-editor {
  width: 100%;
  min-height: 50vh;
  max-height: 62vh;
  background: transparent;
  border: none;
  outline: none;
  resize: vertical;
  tab-size: 2;
}
.yaml-editor:not([readonly]) {
  background: rgba(56,139,253,.04);
  box-shadow: inset 0 0 0 2px rgba(56,139,253,.4);
  border-radius: 8px;
}

/* 详情视图切换 tabs: 模态标题右侧 */
.modal-title {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.detail-view-tabs {
  display: inline-flex; gap: 2px;
  padding: 3px; background: var(--bg-input);
  border-radius: 6px;
  font-weight: 500;
}
.detail-tab {
  padding: 4px 12px;
  background: none; border: none;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  border-radius: 4px;
  transition: all .12s;
}
.detail-tab:hover { color: var(--text-primary); }
.detail-tab.active {
  background: var(--bg-card);
  color: var(--accent);
  box-shadow: 0 1px 3px rgba(0,0,0,.15);
}

/* 状态徽章 */
.yaml-edit-badge {
  padding: 2px 8px; border-radius: 4px;
  background: rgba(56,139,253,.15); color: var(--accent);
  border: 1px solid rgba(56,139,253,.3);
  font-size: 10px; font-weight: 700;
}
.yaml-apply-error {
  padding: 2px 8px; border-radius: 4px;
  background: rgba(248,81,73,.15); color: var(--error, #f85149);
  font-size: 10px; font-weight: 700;
  cursor: help;
}
.yaml-apply-success {
  padding: 2px 8px; border-radius: 4px;
  background: rgba(63,185,80,.15); color: #3fb950;
  font-size: 10px; font-weight: 700;
}

.btn-primary-sm {
  padding: 6px 14px; border-radius: 6px;
  background: var(--accent); color: white;
  border: 1px solid var(--accent);
  font-size: 12px; cursor: pointer;
  transition: all .12s;
}
.btn-primary-sm:hover:not(:disabled) { filter: brightness(1.1); }
.btn-primary-sm:disabled { opacity: .5; cursor: not-allowed; }

/* 行内 scale ± 控件 */
.ready-frac { display: inline-block; min-width: 40px; }
.scale-ctrl {
  display: inline-flex; align-items: center; gap: 2px;
  margin-left: 6px;
  vertical-align: middle;
}
.scale-btn {
  width: 22px; height: 22px;
  padding: 0; line-height: 1;
  border: 1px solid var(--border);
  background: var(--bg-input);
  color: var(--text-secondary);
  border-radius: 4px;
  font-size: 14px; font-weight: 700;
  cursor: pointer;
  transition: all .12s;
}
.scale-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
  background: var(--accent-dim);
}
.scale-btn:disabled { opacity: .35; cursor: not-allowed; }
.scale-spinner {
  width: 11px; height: 11px;
  border-width: 1.5px;
  margin-left: 3px;
}

/* 表格 select 列 */
.k8s-table th.select-col,
.k8s-table td.select-col {
  width: 36px;
  text-align: center;
  padding-left: 8px; padding-right: 4px;
}
.k8s-table tr.row-selected {
  background: rgba(56,139,253,.06);
}
.k8s-table tr.row-selected td:not(.select-col) {
  font-weight: 500;
}

/* 底部浮动批量操作条 */
.batch-bar {
  position: fixed;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  z-index: 90;
  display: flex; align-items: center; gap: 18px;
  padding: 10px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border-accent);
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(0,0,0,.4),
              0 0 0 3px rgba(56,139,253,.15);
  min-width: 360px;
  max-width: 90vw;
}
.batch-bar-left { display: flex; align-items: center; gap: 12px; }
.batch-bar-right { display: flex; align-items: center; gap: 8px; }
.batch-bar-count { font-size: 13px; color: var(--text-primary); }
.batch-bar-count strong { color: var(--accent); font-size: 14px; margin: 0 2px; }
.btn-xs { padding: 3px 10px; font-size: 11px; border-radius: 5px; }
.batch-action-btn {
  padding: 7px 14px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 12px; font-weight: 500;
  cursor: pointer;
  transition: all .12s;
}
.batch-action-btn:hover:not(:disabled) {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
}
.batch-action-btn.danger {
  border-color: rgba(248,81,73,.4);
  color: var(--error, #f85149);
}
.batch-action-btn.danger:hover:not(:disabled) {
  background: rgba(248,81,73,.12);
  border-color: var(--error, #f85149);
}
.batch-action-btn:disabled { opacity: .5; cursor: not-allowed; }
.batch-no-action { font-size: 12px; color: var(--text-muted); font-style: italic; }

.batch-bar-slide-enter-active, .batch-bar-slide-leave-active {
  transition: transform .25s cubic-bezier(.22,1.61,.36,1), opacity .2s;
}
.batch-bar-slide-enter-from, .batch-bar-slide-leave-to {
  transform: translateX(-50%) translateY(80px);
  opacity: 0;
}

/* 批量结果模态 */
.batch-result-card { width: min(640px, calc(100vw - 40px)); }
.batch-result-summary {
  display: inline-flex; gap: 6px;
  font-size: 12px; font-weight: 500;
}
.batch-stat {
  padding: 2px 8px; border-radius: 4px;
  background: var(--bg-input);
}
.batch-stat.success { background: rgba(63,185,80,.15); color: #3fb950; }
.batch-stat.failed  { background: rgba(248,81,73,.15); color: var(--error, #f85149); }
.batch-stat.total   { color: var(--text-muted); }
.batch-result-list {
  display: flex; flex-direction: column; gap: 4px;
  max-height: 50vh; overflow-y: auto;
}
.batch-result-row {
  display: grid;
  grid-template-columns: 22px minmax(160px, 1fr) minmax(0, 2fr);
  gap: 10px; align-items: center;
  padding: 6px 10px;
  border-radius: 5px;
  border: 1px solid var(--border);
  font-size: 12px;
}
.batch-result-row.ok  { background: rgba(63,185,80,.05); border-color: rgba(63,185,80,.2); }
.batch-result-row.err { background: rgba(248,81,73,.05); border-color: rgba(248,81,73,.25); }
.batch-result-icon { font-weight: 700; }
.batch-result-row.ok  .batch-result-icon { color: #3fb950; }
.batch-result-row.err .batch-result-icon { color: var(--error, #f85149); }
.batch-result-name { display: flex; gap: 8px; align-items: center; }
.batch-result-err {
  color: var(--error, #f85149);
  font-family: monospace; font-size: 11px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  cursor: help;
}

/* Events tab */
.events-panel { padding: 12px 16px; min-height: 280px; }
.events-empty { color: var(--text-muted); font-size: 12px; padding: 32px 0; text-align: center; }
.events-list { display: flex; flex-direction: column; gap: 8px; }
.event-row {
  padding: 10px 12px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 7px;
  font-size: 12px;
  border-left: 3px solid var(--border);
}
.event-row.event-warning { border-left-color: var(--warning, #d29922); background: rgba(210,153,34,.04); }
.event-row.event-normal  { border-left-color: rgba(63,185,80,.3); }
.event-meta {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-bottom: 4px;
  font-size: 11px;
}
.event-type-badge {
  padding: 1px 6px; border-radius: 3px; font-weight: 700;
  text-transform: uppercase; font-size: 10px;
}
.event-type-normal  { background: rgba(63,185,80,.18); color: #3fb950; }
.event-type-warning { background: rgba(210,153,34,.18); color: var(--warning, #d29922); }
.event-reason { font-weight: 600; color: var(--text-primary); }
.event-count {
  padding: 1px 5px; background: var(--bg-input);
  border-radius: 4px; color: var(--text-muted);
}
.event-source { color: var(--text-muted); }
.event-ts { margin-left: auto; color: var(--text-muted); font-family: monospace; }
.event-message {
  font-family: monospace; color: var(--text-secondary);
  white-space: pre-wrap; word-break: break-word;
}
.event-tab-count {
  margin-left: 4px; padding: 0 5px;
  background: rgba(56,139,253,.15); color: var(--accent);
  border-radius: 8px; font-size: 10px; font-weight: 700;
}

/* 镜像编辑列 */
.image-cell {
  cursor: pointer;
  position: relative;
  transition: background .12s;
}
.image-cell:hover {
  background: rgba(56,139,253,.06);
}
.image-cell:hover .image-edit-hint { opacity: 1; }
.image-edit-hint {
  margin-left: 6px;
  color: var(--accent);
  opacity: 0;
  transition: opacity .12s;
  font-size: 11px;
}

.image-edit-card { width: min(680px, calc(100vw - 40px)); }
.image-edit-target {
  font-family: monospace; font-size: 12px;
  color: var(--text-muted); font-weight: 400; margin-left: 6px;
}
.image-edit-list { display: flex; flex-direction: column; gap: 10px; }
.image-edit-row {
  display: grid;
  grid-template-columns: 140px 1fr 32px;
  gap: 10px; align-items: center;
}
.image-edit-cname {
  font-family: monospace; font-size: 12px;
  color: var(--accent); font-weight: 600;
  overflow: hidden; text-overflow: ellipsis;
}
.image-edit-input { font-family: monospace; font-size: 12px; }
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
  cursor: text;
}
.exec-term-wrap :deep(.xterm) { height: 100%; }
.exec-term-wrap :deep(.xterm-viewport) { overflow-y: auto !important; }
/* 确保 xterm 的 textarea（实际输入元素）不被遮挡，可以接收键盘事件 */
.exec-term-wrap :deep(.xterm-helper-textarea) {
  position: absolute !important;
  opacity: 0 !important;
  left: 0 !important;
  top: 0 !important;
  z-index: 10 !important;
  pointer-events: auto !important;
}
.exec-term-wrap :deep(.xterm-screen) { cursor: text; }
.action-btn.exec-btn { color: #58a6ff; }
.action-btn.exec-btn:disabled { opacity: 0.35; cursor: not-allowed; }
</style>
