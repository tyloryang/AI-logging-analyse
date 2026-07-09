<template>
  <div class="container-view">
    <div class="page-header">
      <div class="header-left">
        <h1>容器管理</h1>
        <span class="subtitle">多集群 Kubernetes 资源总览与 kubeconfig 管理</span>
      </div>
      <div class="header-right">
        <div class="filter-group" :title="searchKeyword ? `搜索: ${searchKeyword}` : '资源关键字搜索'">
          <span class="filter-icon">🔍</span>
          <input
            v-model="searchKeyword"
            class="search-input"
            type="text"
            placeholder="搜索..."
            :disabled="!activeClusterId || loading"
          />
        </div>
        <div class="filter-group" title="命名空间过滤">
          <span class="filter-icon">📂</span>
          <select v-model="activeNs" class="ns-select" :disabled="!activeClusterId || loading" @change="fetchAll()">
            <option value="">全部</option>
            <option v-for="ns in namespaces" :key="ns.name" :value="ns.name">{{ ns.name }}</option>
          </select>
        </div>
        <div class="filter-group" title="自动刷新档位">
          <span class="filter-icon">🔄</span>
          <select v-model="autoRefreshInterval" class="ns-select auto-refresh-select" :disabled="!activeClusterId">
            <option v-for="opt in AUTO_REFRESH_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.short }}</option>
          </select>
        </div>
        <span v-if="lastFetchedAt" class="cache-stamp" :title="`当前缓存时间 ${new Date(lastFetchedAt).toLocaleString()}，手动刷新或开启自动刷新可更新`">
          ⏱ {{ lastFetchedText }}
        </span>
        <button v-if="canManageClusters" class="btn-ghost" :disabled="!activeCluster" @click="openEditCluster">编辑</button>
        <button v-if="canManageClusters" class="btn-ghost" :disabled="!activeCluster" @click="testActiveCluster">测试</button>
        <button v-if="canManageClusters" class="btn-ghost danger" :disabled="!activeCluster" @click="removeCluster">删除</button>
        <button v-if="canManageClusters" class="btn-ghost" :disabled="!activeClusterId" @click="openCreateResource" title="从 YAML 创建资源">
          + 新建
        </button>
        <button class="btn-refresh" @click="refreshAll({ clusters: true })" :disabled="loading || !activeClusterId" title="跳过缓存强制重拉">
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

    <!-- AI 自然语言命令栏: 可整体折叠 -->
    <div v-if="activeClusterId" class="ai-cmd-bar" :class="{ open: aiCmd.expanded, 'has-pending': aiCmd.pendingActions.length }">
      <!-- 折叠态: 紧凑头, 显示徽章 + 展开按钮 -->
      <div v-if="!aiCmd.expanded" class="ai-cmd-collapsed" @click="aiCmd.expanded = true">
        <span class="ai-cmd-icon">🤖</span>
        <span class="ai-cmd-collapsed-title">AI 助手</span>
        <span class="ai-cmd-mode-mini">{{ aiCmd.smart ? '🧠 智能' : '⚡ 正则' }}</span>
        <span v-if="aiCmd.pendingActions.length" class="ai-cmd-badge danger">
          ⚠️ {{ aiCmd.pendingActions.length }} 待审批
        </span>
        <span v-if="aiCmd.chatHistory.length" class="ai-cmd-badge">
          💬 {{ aiCmd.chatHistory.length }} 条对话
        </span>
        <span v-if="aiCmd.intent" class="ai-cmd-badge">📝 1 个意图</span>
        <span class="ai-cmd-collapsed-hint">点击展开 ▾</span>
      </div>
      <!-- 展开态: 完整输入栏 -->
      <div v-else class="ai-cmd-input-wrap">
        <span class="ai-cmd-icon" @click="aiCmd.expanded = false" title="点击折叠 AI 命令栏">🤖</span>
        <input v-model="aiCmd.text" class="ai-cmd-input"
          :placeholder="aiCmd.smart ? '智能模式: 自由对话, Claude 自主调用工具...' : aiCmd.examples[aiCmd.exampleIdx]"
          @keyup.enter="aiCmd.smart ? runSmartChat() : parseAICmd()"
          :disabled="aiCmd.parsing || aiCmd.executing || aiCmd.chatting" />
        <button class="ai-mode-toggle" :class="{ active: aiCmd.smart }" @click="aiCmd.smart = !aiCmd.smart"
          :title="aiCmd.smart ? '智能模式 (LLM 工具调用) — 点击切回正则模式' : '正则模式 (确定性指令) — 点击切到智能模式 (LLM)'">
          {{ aiCmd.smart ? '🧠 智能' : '⚡ 正则' }}
        </button>
        <button class="btn-ghost btn-xs" :disabled="!aiCmd.text.trim() || aiCmd.parsing || aiCmd.chatting"
          @click="aiCmd.smart ? runSmartChat() : parseAICmd()">
          {{ aiCmd.smart ? (aiCmd.chatting ? '思考中...' : '提问') : (aiCmd.parsing ? '解析中...' : '解析') }}
        </button>
        <button v-if="aiCmd.intent || aiCmd.chatHistory.length" class="btn-ghost btn-xs" @click="clearAICmd">清空</button>
        <button class="btn-ghost btn-xs" @click="aiCmd.expanded = false" title="折叠">▴</button>
      </div>
      <!-- 智能模式: 写工具待审批卡片 (折叠态也显示, 因为是高危必须看到) -->
      <transition name="ai-intent-fade">
        <div v-if="aiCmd.pendingActions.length && aiCmd.expanded" class="ai-pending-actions">
          <div class="pending-header">
            ⚠️ {{ aiCmd.pendingActions.length }} 个增删改操作待你审批
            <button class="btn-ghost btn-xs" @click="aiCmd.pendingCollapsed = !aiCmd.pendingCollapsed" style="margin-left:auto">
              {{ aiCmd.pendingCollapsed ? '展开 ▾' : '折叠 ▴' }}
            </button>
            <button class="btn-ghost btn-xs" :disabled="aiCmd.pendingApproving" @click="rejectAllPending">全部拒绝</button>
          </div>
          <template v-if="!aiCmd.pendingCollapsed">
          <div v-for="(a, i) in aiCmd.pendingActions" :key="i" class="pending-action-card">
            <div class="pending-tool-row">
              <span class="pending-badge" :class="'pending-' + a.name">{{ pendingActionLabel(a.name) }}</span>
              <span class="pending-tool-name">⚙ {{ a.name }}</span>
            </div>
            <div class="pending-input-block">
              <div v-for="(v, k) in filteredPendingInput(a)" :key="k" class="pending-input-row">
                <span class="pending-k">{{ k }}</span>
                <span class="pending-v mono">{{ formatPendingInputValue(v) }}</span>
              </div>
            </div>
            <!-- ConfigMap 写操作: 高亮 key 级 diff -->
            <div v-if="a.preview && a.preview.type === 'configmap_diff'" class="pending-cm-diff">
              <div class="diff-summary">
                <span v-if="a.preview.added.length" class="diff-tag added">+ 新增 {{ a.preview.added.length }}</span>
                <span v-if="a.preview.changed.length" class="diff-tag changed">~ 修改 {{ a.preview.changed.length }}</span>
                <span v-if="a.preview.removed.length" class="diff-tag removed">− 删除 {{ a.preview.removed.length }}</span>
                <span v-if="!a.preview.added.length && !a.preview.changed.length && !a.preview.removed.length" class="diff-tag noop">无变化</span>
                <span class="diff-merge-mode" :title="a.preview.merge ? '局部更新, 保留其它 key' : '全量替换 (清空其它 key)'">
                  {{ a.preview.merge ? 'merge' : 'replace' }}
                </span>
              </div>
              <div v-for="k in a.preview.added" :key="'add-'+k" class="diff-row added">
                <span class="diff-mark">+</span>
                <span class="diff-key">{{ k }}</span>
                <span class="diff-val mono">{{ truncateDiff(a.preview.after[k]) }}</span>
              </div>
              <div v-for="k in a.preview.changed" :key="'chg-'+k" class="diff-row changed">
                <span class="diff-mark">~</span>
                <span class="diff-key">{{ k }}</span>
                <div class="diff-val-pair">
                  <div class="diff-val mono diff-old">- {{ truncateDiff(a.preview.before[k]) }}</div>
                  <div class="diff-val mono diff-new">+ {{ truncateDiff(a.preview.after[k]) }}</div>
                </div>
              </div>
              <div v-for="k in a.preview.removed" :key="'del-'+k" class="diff-row removed">
                <span class="diff-mark">−</span>
                <span class="diff-key">{{ k }}</span>
                <span class="diff-val mono">{{ truncateDiff(a.preview.before[k]) }}</span>
              </div>
            </div>
            <div class="pending-btn-row">
              <button class="btn-ghost btn-xs" :disabled="aiCmd.pendingApproving" @click="approvePendingAction(a, false)">拒绝</button>
              <button class="btn-primary-sm danger" :disabled="aiCmd.pendingApproving" @click="approvePendingAction(a, true)">
                {{ aiCmd.pendingApproving === a ? '执行中...' : '⚠ 我已审核, 执行' }}
              </button>
            </div>
          </div>
          </template>
        </div>
      </transition>

      <!-- 智能模式: 对话历史 (可折叠) -->
      <transition name="ai-intent-fade">
        <div v-if="aiCmd.smart && aiCmd.chatHistory.length && aiCmd.expanded" class="ai-chat-history-wrap">
          <div class="ai-chat-header">
            <span class="ai-chat-title">💬 对话历史 ({{ aiCmd.chatHistory.length }})</span>
            <button class="btn-ghost btn-xs" @click="aiCmd.chatCollapsed = !aiCmd.chatCollapsed">
              {{ aiCmd.chatCollapsed ? '展开 ▾' : '折叠 ▴' }}
            </button>
            <button class="btn-ghost btn-xs" @click="aiCmd.chatHistory = []">清空</button>
          </div>
          <div v-if="!aiCmd.chatCollapsed" class="ai-chat-history">
          <div v-for="(turn, i) in aiCmd.chatHistory" :key="i" class="ai-turn" :class="'turn-' + turn.role">
            <div v-if="turn.role === 'user'" class="ai-turn-bubble user-bubble">
              <span class="turn-icon">👤</span>{{ turn.content }}
            </div>
            <div v-else-if="turn.role === 'assistant'" class="ai-turn-bubble assistant-bubble">
              <span class="turn-icon">🧠</span>
              <span v-html="renderInspectMd(turn.content)"></span>
            </div>
            <div v-else-if="turn.role === 'tool'" class="ai-tool-step" :class="{ failed: turn.failed }">
              <div class="tool-head">
                <span class="tool-name-badge">⚙ {{ turn.name }}</span>
                <span class="tool-input-preview">{{ JSON.stringify(turn.input) }}</span>
              </div>
              <div class="tool-result">{{ turn.result }}</div>
            </div>
            <div v-else-if="turn.role === 'warn'" class="ai-warn-bubble">
              ⚠ {{ turn.content }}
              <router-link v-if="turn.action" :to="turn.action.route" class="warn-action-link">{{ turn.action.label }} →</router-link>
            </div>
          </div>
          <div v-if="aiCmd.chatting" class="ai-thinking">
            <span class="spinner" style="width:12px;height:12px"></span> Claude 思考中...
          </div>
          </div>
        </div>
      </transition>
      <!-- 意图卡片 -->
      <transition name="ai-intent-fade">
        <div v-if="aiCmd.intent && aiCmd.expanded" class="ai-intent-card" :class="{ danger: aiCmd.intent.danger, unknown: aiCmd.intent.action === 'unknown' }">
          <div class="ai-intent-head">
            <span class="ai-intent-action-badge" :class="'badge-' + aiCmd.intent.action">{{ aiCmd.intent.action }}</span>
            <span class="ai-intent-summary">{{ aiCmd.intent.summary }}</span>
            <span v-if="aiCmd.intent.danger" class="ai-danger-tag">⚠ 高危</span>
          </div>
          <!-- unknown: 给出指令模板示例 -->
          <div v-if="aiCmd.intent.action === 'unknown'" class="ai-intent-body">
            <div v-if="aiCmd.intent.hint" class="ai-unknown-hint">{{ aiCmd.intent.hint }}</div>
            <div class="ai-unknown-examples">
              <div class="ai-unknown-title">支持的指令模板 (点击填入):</div>
              <div class="ai-unknown-chips">
                <button v-for="ex in (aiCmd.intent.examples || [])" :key="ex" class="ai-example-chip"
                  @click="aiCmd.text = ex; aiCmd.intent = null; parseAICmd()">
                  {{ ex }}
                </button>
              </div>
            </div>
          </div>
          <div v-else class="ai-intent-body">
            <div class="ai-intent-row" v-if="aiCmd.intent.kind">
              <span class="ai-field-label">资源</span>
              <span class="mono">{{ aiCmd.intent.kind }} {{ aiCmd.intent.namespace ? aiCmd.intent.namespace + '/' : '' }}{{ aiCmd.intent.name }}</span>
            </div>
            <div class="ai-intent-row" v-if="aiCmd.intent.replicas != null">
              <span class="ai-field-label">副本数</span>
              <input type="number" v-model.number="aiCmd.intent.replicas" min="0" max="1000" class="ai-intent-input" />
            </div>
            <div class="ai-intent-row" v-if="aiCmd.intent.image">
              <span class="ai-field-label">镜像</span>
              <input v-model="aiCmd.intent.image" class="ai-intent-input" />
            </div>
            <div class="ai-intent-row" v-if="!aiCmd.intent.namespace && aiCmd.intent.kind !== 'node'">
              <span class="ai-field-label">命名空间</span>
              <input v-model="aiCmd.intent.namespace" class="ai-intent-input" placeholder="default" />
            </div>
          </div>
          <div class="ai-intent-actions">
            <button class="btn-ghost btn-xs" @click="clearAICmd">取消</button>
            <button v-if="aiCmd.intent.action !== 'unknown'"
              class="btn-primary-sm"
              :class="{ danger: aiCmd.intent.danger }"
              :disabled="aiCmd.executing || !aiCmd.intent.name && aiCmd.intent.action !== 'list'"
              @click="executeAICmd">
              {{ aiCmd.executing ? '执行中...' : (aiCmd.intent.danger ? '⚠ 我已确认, 执行' : '✓ 执行') }}
            </button>
          </div>
          <!-- AlreadyExists: 提供替换选项 -->
          <div v-if="aiCmd.alreadyExists" class="ai-already-exists">
            <div class="ai-already-exists-msg">
              ⚠ <strong>{{ aiCmd.alreadyExists.kind }} {{ aiCmd.alreadyExists.namespace }}/{{ aiCmd.alreadyExists.name }}</strong> 已存在
            </div>
            <div class="ai-already-exists-actions">
              <button class="btn-ghost btn-xs" @click="clearAICmd">取消</button>
              <button class="btn-ghost btn-xs" @click="aiCmd.alreadyExists = null; aiCmd.intent.name = (aiCmd.intent.name || 'nginx') + '-' + Math.random().toString(36).slice(2, 6)">
                改名重试
              </button>
              <button class="btn-primary-sm danger" :disabled="aiCmd.executing" @click="executeAICmd({ force: true })">
                ⚠ 替换 (先删除再创建)
              </button>
            </div>
          </div>
          <div v-if="aiCmd.error" class="modal-tip modal-tip-error" style="margin-top:8px">{{ aiCmd.error }}</div>
          <div v-if="aiCmd.success" class="modal-tip" style="margin-top:8px;color:#3fb950">✓ {{ aiCmd.success }}</div>
          <!-- inspect 巡检报告 -->
          <div v-if="aiCmd.inspectReport" class="ai-inspect-report" v-html="aiCmd.inspectReportHtml"></div>
        </div>
      </transition>
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
          <button
            class="tab-btn abnormal-toggle"
            :class="{ active: onlyAbnormal, 'has-abnormal': abnormalTotal > 0 }"
            @click="onlyAbnormal = !onlyAbnormal"
            :title="onlyAbnormal ? '显示全部资源' : '只显示异常资源（Pod 非 Running/未就绪、副本不满、Job 失败、节点 NotReady）'"
          >
            ⚠ 只看异常
            <span class="tab-count" :class="{ alert: abnormalTotal > 0 }">{{ abnormalTotal }}</span>
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
                <th>名称</th><th>命名空间</th><th>状态</th><th>节点 / IP</th><th>容器</th>
                <th class="sortable-th" @click="togglePodRestartSort" :title="`点击切换排序 (当前: ${ {desc:'降序',asc:'升序',null:'默认'}[podRestartSortOrder] || '默认' })`">
                  重启
                  <span class="sort-indicator">{{ podRestartSortOrder === 'desc' ? '↓' : podRestartSortOrder === 'asc' ? '↑' : '⇅' }}</span>
                </th>
                <th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!sortedFilteredPods.length"><td colspan="9" class="empty">暂无数据</td></tr>
              <tr v-for="pod in limitRows(sortedFilteredPods)" :key="pod.namespace + '/' + pod.name"
                  :class="{ 'row-selected': isRowSelected('pod', pod) }">
                <td class="select-col">
                  <input type="checkbox"
                    :checked="isRowSelected('pod', pod)"
                    @change="toggleRowSelected('pod', pod)" />
                </td>
                <td class="name-cell">{{ pod.name }}</td>
                <td><span class="ns-tag">{{ pod.namespace }}</span></td>
                <td><span class="status-dot" :class="pod.statusClass"></span>{{ pod.status }}</td>
                <td class="mono small">
                  <div>{{ pod.node || '-' }}</div>
                  <div v-if="pod.host_ip" class="node-ip" :title="`节点 IP: ${pod.host_ip}（Pod IP: ${pod.ip || '-'}）`">{{ pod.host_ip }}</div>
                </td>
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
                <th>名称</th><th>命名空间</th><th>状态</th><th>Ready</th><th>节点 IP</th><th>镜像</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredDeployments.length"><td colspan="9" class="empty">暂无数据</td></tr>
              <tr v-for="deployment in limitRows(filteredDeployments)" :key="deployment.namespace + '/' + deployment.name"
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
                <td class="mono small node-list-cell" :title="nodesTitle(deployment)">{{ nodesText(deployment) }}</td>
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
                <th>名称</th><th>命名空间</th><th>状态</th><th>Ready</th><th>当前</th><th>可用</th><th>节点 IP</th><th>镜像</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredDaemonSets.length"><td colspan="11" class="empty">暂无数据</td></tr>
              <tr v-for="daemonSet in limitRows(filteredDaemonSets)" :key="daemonSet.namespace + '/' + daemonSet.name"
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
                <td class="mono small node-list-cell" :title="nodesTitle(daemonSet)">{{ nodesText(daemonSet) }}</td>
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
                <th>名称</th><th>命名空间</th><th>状态</th><th>Ready</th><th>当前</th><th>更新</th><th>节点 IP</th><th>镜像</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredStatefulSets.length"><td colspan="11" class="empty">暂无数据</td></tr>
              <tr v-for="statefulSet in limitRows(filteredStatefulSets)" :key="statefulSet.namespace + '/' + statefulSet.name"
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
                <td class="mono small node-list-cell" :title="nodesTitle(statefulSet)">{{ nodesText(statefulSet) }}</td>
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
                <th>名称</th><th>命名空间</th><th>状态</th><th>完成</th><th>并发</th><th>运行</th><th>失败</th><th>节点 IP</th><th>镜像</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredJobs.length"><td colspan="12" class="empty">暂无数据</td></tr>
              <tr v-for="job in limitRows(filteredJobs)" :key="job.namespace + '/' + job.name"
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
                <td class="mono small node-list-cell" :title="nodesTitle(job)">{{ nodesText(job) }}</td>
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
                <th>名称</th><th>命名空间</th><th>状态</th><th>调度</th><th>挂起</th><th>活跃 Job</th><th>节点 IP</th><th>最近调度</th><th>最近成功</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredCronJobs.length"><td colspan="12" class="empty">暂无数据</td></tr>
              <tr v-for="cronJob in limitRows(filteredCronJobs)" :key="cronJob.namespace + '/' + cronJob.name"
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
                <td class="mono small node-list-cell" :title="nodesTitle(cronJob)">{{ nodesText(cronJob) }}</td>
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
                <th>名称</th><th>命名空间</th><th>类型</th><th>ClusterIP</th><th>端口</th><th>后端节点 IP</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredServices.length"><td colspan="9" class="empty">暂无数据</td></tr>
              <tr v-for="service in limitRows(filteredServices)" :key="service.namespace + '/' + service.name"
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
                <td class="mono small node-list-cell" :title="nodesTitle(service)">{{ nodesText(service) }}</td>
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

        <div v-else-if="activeTab === 'configMaps'" class="table-wrap">
          <table class="k8s-table">
            <thead>
              <tr>
                <th class="select-col">
                  <input type="checkbox" :checked="allCurrentSelected" @change="toggleAllCurrent"
                    :disabled="!filteredConfigMaps.length" title="全选 / 取消全选" />
                </th>
                <th>名称</th><th>命名空间</th><th>Key 数</th><th>大小</th><th>Keys 预览</th><th>引用节点 IP</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredConfigMaps.length"><td colspan="9" class="empty">暂无数据</td></tr>
              <tr v-for="cm in limitRows(filteredConfigMaps)" :key="cm.namespace + '/' + cm.name"
                  :class="{ 'row-selected': isRowSelected('configmap', cm) }">
                <td class="select-col">
                  <input type="checkbox" :checked="isRowSelected('configmap', cm)"
                    @change="toggleRowSelected('configmap', cm)" />
                </td>
                <td class="name-cell">{{ cm.name }}</td>
                <td><span class="ns-tag">{{ cm.namespace }}</span></td>
                <td class="mono small">{{ cm.keyCount }}</td>
                <td class="mono small">{{ formatBytes(cm.size) }}</td>
                <td class="small">
                  <span v-for="k in (cm.keys || []).slice(0, 5)" :key="k" class="cm-key-tag">{{ k }}</span>
                  <span v-if="(cm.keys || []).length > 5" class="muted">+{{ cm.keys.length - 5 }}</span>
                </td>
                <td class="mono small node-list-cell" :title="nodesTitle(cm)">{{ nodesText(cm) }}</td>
                <td class="muted mono small" :title="formatRelative(cm.age)">{{ formatDateTime(cm.age) }}</td>
                <td class="action-cell">
                  <div class="action-group">
                    <button class="action-btn" @click="openResourceDetail('configmap', cm)">详情</button>
                    <button class="action-btn danger" @click="deleteSingleResource('configmap', cm)">删除</button>
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
                <th>名称</th><th>IP 地址</th><th>状态</th><th>角色</th><th>版本</th><th>OS</th><th>创建时间</th><th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredNodes.length"><td colspan="8" class="empty">暂无数据</td></tr>
              <tr v-for="node in limitRows(filteredNodes)" :key="node.name">
                <td class="name-cell">{{ node.name }}</td>
                <td class="mono small node-list-cell">{{ node.internal_ip || '-' }}</td>
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

        <div v-if="!loading && !showAllRows && currentList.length > ROW_LIMIT" class="row-limit-bar">
          为保证流畅仅渲染前 {{ ROW_LIMIT }} 行（共 {{ currentList.length }} 行），可搜索或
          <button @click="showAllRows = true">显示全部</button>
        </div>
        <div v-else-if="!loading && showAllRows && currentList.length > ROW_LIMIT" class="row-limit-bar">
          正在显示全部 {{ currentList.length }} 行
          <button @click="showAllRows = false">恢复折叠</button>
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
            <!-- YAML：编辑态用 textarea；只读态用可折叠视图 -->
            <textarea
              v-else-if="detailView === 'yaml' && yamlEditing"
              v-model="yamlBuffer"
              class="yaml-editor"
              spellcheck="false"
              @input="onYamlInput"
            ></textarea>
            <div v-else-if="detailView === 'yaml'" class="yaml-fold-view">
              <div class="yaml-fold-toolbar">
                <button class="btn-ghost btn-xs" @click="expandAllYaml">展开全部</button>
                <button class="btn-ghost btn-xs" @click="collapseTopLevel">折叠 spec / status</button>
                <span class="yaml-fold-hint">点击 ▶/▼ 折叠对应节点</span>
              </div>
              <div class="yaml-fold-pre" v-html="yamlFoldHtml" @click="onYamlFoldClick"></div>
            </div>
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
            <button class="btn-ghost refresh-log-btn"
              :class="{ 'btn-follow-active': logFollowing }"
              :disabled="!selectedLogPod"
              @click="toggleLogFollow"
              :title="logFollowing ? '停止实时跟随' : '开始实时跟随 (SSE)'">
              {{ logFollowing ? '⏸ 停止' : '▶ 实时' }}
            </button>
          </div>
          <div v-if="logError" class="modal-tip modal-tip-error">{{ logError }}</div>
          <!-- 多关键字过滤栏（支持空格分隔 + 排除模式 -prefix）-->
          <div class="log-filter-bar">
            <input
              v-model="logFilterKeywords"
              class="log-filter-input"
              placeholder="多关键字过滤，空格分隔。前缀 - 表示排除（例：ERROR timeout -DEBUG）"
              spellcheck="false"
              autocapitalize="off"
            />
            <label class="log-filter-toggle" :title="logFilterMode === 'any' ? '任一关键字匹配即显示' : '所有关键字都需匹配才显示'">
              <input type="checkbox" :checked="logFilterMode === 'all'" @change="logFilterMode = ($event.target.checked ? 'all' : 'any')" />
              <span>{{ logFilterMode === 'all' ? '需全部命中' : '任一命中即可' }}</span>
            </label>
            <label class="log-filter-toggle">
              <input type="checkbox" v-model="logFilterCase" />
              <span>区分大小写</span>
            </label>
            <span class="log-filter-stat" v-if="logFilterKeywords.trim()">
              <strong>{{ logFilteredLines.length }}</strong> / {{ logTotalLines }} 行命中
            </span>
            <button v-if="logFilterKeywords" class="btn-ghost log-filter-clear" @click="logFilterKeywords = ''">清空</button>
          </div>
          <div class="code-panel">
            <div v-if="logLoading && !logFollowing" class="loading-row compact">
              <span class="spinner"></span>
              正在加载日志...
            </div>
            <pre v-else-if="!logText" class="log-view">暂无日志输出</pre>
            <pre v-else ref="logViewEl" class="log-view"><template v-for="(seg, i) in logRenderSegments" :key="i"><span v-if="seg.h" :class="'hl hl-' + (seg.idx % 6)">{{ seg.t }}</span><template v-else>{{ seg.t }}</template></template><span v-if="logFollowing" class="log-cursor">▌</span></pre>
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
            <span v-if="execContainer" class="exec-meta dim">/ {{ execContainer }}</span>
          </div>
          <div class="exec-controls" @mousedown.stop @click.stop @keydown.stop>
            <select
              v-model="execContainer"
              class="exec-select"
              :disabled="!execMeta.containers.length"
              @change="handleExecSelectionChange"
            >
              <option v-for="c in execMeta.containers" :key="c.name" :value="c.name">{{ c.name }}</option>
            </select>
            <select v-model="execShell" class="exec-select" @change="handleExecSelectionChange">
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

    <!-- 资源创建模态 (YAML 多文档) -->
    <div v-if="createModal.open" class="modal-mask" @click.self="closeCreateResource">
      <div class="modal-card detail-modal-card">
        <div class="modal-title">+ 从 YAML 创建资源</div>
        <div class="modal-body">
          <p style="font-size:12px;color:var(--text-muted);margin:0 0 10px">
            支持单/多资源 (用 <code>---</code> 分隔多个文档)。kubectl apply 同款行为。
          </p>
          <div class="code-panel" style="min-height:380px">
            <textarea v-model="createModal.yaml" class="yaml-editor"
              spellcheck="false" placeholder="apiVersion: v1
kind: ConfigMap
metadata:
  name: my-config
  namespace: default
data:
  key: value"></textarea>
          </div>
          <div v-if="createModal.error" class="modal-tip modal-tip-error" style="margin-top:12px;white-space:pre-wrap">{{ createModal.error }}</div>
          <div v-if="createModal.result" class="create-result" style="margin-top:12px">
            <div class="batch-result-summary">
              <span class="batch-stat success">✓ {{ createModal.result.created.length }}</span>
              <span v-if="createModal.result.errors.length" class="batch-stat failed">✗ {{ createModal.result.errors.length }}</span>
              <span class="batch-stat total">共 {{ createModal.result.total }}</span>
            </div>
            <div class="batch-result-list" style="margin-top:8px;max-height:160px">
              <div v-for="(r, i) in createModal.result.created" :key="'ok'+i" class="batch-result-row ok">
                <span class="batch-result-icon">✓</span>
                <span class="batch-result-name"><span class="ns-tag">{{ r.namespace || '-' }}</span><span class="mono">{{ r.kind }}/{{ r.name }}</span></span>
                <span></span>
              </div>
              <div v-for="(r, i) in createModal.result.errors" :key="'er'+i" class="batch-result-row err">
                <span class="batch-result-icon">✗</span>
                <span class="batch-result-name"><span class="mono">{{ r.kind }}/{{ r.name }}</span></span>
                <span class="batch-result-err" :title="r.error">{{ r.error.split('\n')[0].slice(0, 120) }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn-ghost" @click="closeCreateResource">关闭</button>
          <button class="btn-primary-sm" :disabled="createModal.applying || !createModal.yaml.trim()" @click="applyCreateResource">
            {{ createModal.applying ? '应用中...' : '✓ 创建' }}
          </button>
        </div>
      </div>
    </div>

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
// 缓存默认常驻；手动刷新、自动刷新、集群/资源变更时才强制重新拉取。
const _resourceCache = new Map()
let _clustersCache = null
let _fetchSeq = 0
let _displayedCacheKey = ''
const _backgroundOverviewLoads = new Set()
const AUTO_REFRESH_OPTIONS = [
  { value: 'off', label: '关闭',  short: '关',  sec: 0 },
  { value: '30',  label: '30 秒', short: '30s', sec: 30 },
  { value: '60',  label: '1 分钟', short: '1m', sec: 60 },
  { value: '300', label: '5 分钟', short: '5m', sec: 300 },
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
  { id: 'configMaps', label: 'ConfigMaps' },
  { id: 'nodes', label: 'Nodes' },
]
const OVERVIEW_SECTIONS = [
  'summary', 'namespaces', 'pods', 'deployments', 'daemonSets',
  'statefulSets', 'jobs', 'cronJobs', 'services', 'configMaps', 'nodes',
]
const FAST_OVERVIEW_SECTIONS = ['namespaces', 'pods', 'nodes']
const TAB_TO_SECTION = {
  pods: 'pods',
  deployments: 'deployments',
  daemonSets: 'daemonSets',
  statefulSets: 'statefulSets',
  jobs: 'jobs',
  cronJobs: 'cronJobs',
  services: 'services',
  configMaps: 'configMaps',
  nodes: 'nodes',
}
const KIND_LABELS = {
  pod: 'Pod',
  deployment: 'Deployment',
  daemonset: 'DaemonSet',
  statefulset: 'StatefulSet',
  job: 'Job',
  cronjob: 'CronJob',
  service: 'Service',
  configmap: 'ConfigMap',
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
const configMaps = ref([])
const nodes = ref([])
const searchKeyword = ref('')
const showDetailModal = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detailData = ref(null)
// 详情视图 + YAML 编辑状态
const detailView = ref('yaml')        // 默认 YAML（更符合运维习惯）| json | events
const collapsedYamlPaths = ref(new Set())   // 折叠的节点路径集合（行号 ID）

function _escHtml(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])) }

// 把 yamlBuffer 解析成可折叠 HTML：扫描每行缩进，给"key:"行注入 ▶/▼ + data-path
const yamlFoldHtml = computed(() => {
  const text = yamlBuffer.value || ''
  if (!text) return '<span class="yaml-empty">（无内容）</span>'
  const lines = text.split('\n')
  const out = []
  // 计算每行缩进等级（2 空格 / 1）
  const indent = (l) => { const m = l.match(/^( *)/); return m ? m[1].length : 0 }
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const ind = indent(line)
    // 判断是否折叠：找最近的"祖先 path id"在 collapsedPaths 里
    let hidden = false
    for (const pid of collapsedYamlPaths.value) {
      // pid 形如 "lineNo:indent"
      const [pLine, pInd] = pid.split(':').map(Number)
      if (i > pLine && ind > pInd) {
        // 仍属于这个折叠块（直到下一个相同或更小缩进的行）
        // 检查中间有没有跳出过
        let still = true
        for (let j = pLine + 1; j < i; j++) {
          if (indent(lines[j]) <= pInd && lines[j].trim()) { still = false; break }
        }
        if (still) { hidden = true; break }
      }
    }
    if (hidden) continue

    // 判断是否是可折叠 key（行尾以 : 结尾或 :{} :{...} 但下一行缩进更深）
    const trimmed = line.trimEnd()
    const nextLine = lines[i + 1] || ''
    const canFold = trimmed.endsWith(':') && nextLine.trim() && indent(nextLine) > ind
    const pathId = `${i}:${ind}`
    const isCollapsed = collapsedYamlPaths.value.has(pathId)
    const folder = canFold
      ? `<span class="yaml-folder" data-pid="${pathId}">${isCollapsed ? '▶' : '▼'}</span>`
      : '<span class="yaml-folder-spacer"></span>'
    const summary = canFold && isCollapsed ? ` <span class="yaml-fold-summary">{ ... }</span>` : ''
    // 给 key 染色
    const colored = _escHtml(line).replace(
      /^(\s*)([A-Za-z0-9_\-]+)(:)(\s.*)?$/,
      (_, sp, k, c, rest) => `${sp}<span class="yk">${k}</span>${c}<span class="yv">${rest || ''}</span>`
    )
    out.push(`<div class="yaml-line">${folder}<span class="yaml-line-text">${colored}${summary}</span></div>`)
  }
  return out.join('')
})

function _toggleYamlFolder(pid) {
  const s = new Set(collapsedYamlPaths.value)
  if (s.has(pid)) s.delete(pid); else s.add(pid)
  collapsedYamlPaths.value = s
}

function expandAllYaml() { collapsedYamlPaths.value = new Set() }
function collapseTopLevel() {
  // 折叠所有缩进=0 的可折叠 key（spec / status / metadata 等顶级节点）
  const lines = (yamlBuffer.value || '').split('\n')
  const s = new Set()
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trimEnd()
    if (!trimmed.endsWith(':')) continue
    const ind = (lines[i].match(/^( *)/) || ['', ''])[1].length
    if (ind !== 0) continue
    const next = lines[i + 1] || ''
    if (next.trim() && (next.match(/^( *)/) || ['', ''])[1].length > 0) {
      s.add(`${i}:0`)
    }
  }
  collapsedYamlPaths.value = s
}

function onYamlFoldClick(e) {
  const t = e.target.closest('.yaml-folder')
  if (!t) return
  const pid = t.getAttribute('data-pid')
  if (pid) _toggleYamlFolder(pid)
}
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
// 资源创建弹窗
const createModal = reactive({
  open: false, yaml: '', applying: false, error: '', result: null,
})
// AI 自然语言命令栏
const aiCmd = reactive({
  open: false, expanded: false, text: '', parsing: false, executing: false,
  chatCollapsed: false, pendingCollapsed: false,   // 各子区域独立折叠
  intent: null, error: '', success: '',
  // 重名替换状态
  alreadyExists: null,   // { kind, name, namespace, message }
  // 巡检报告
  inspectReport: '',
  inspectReportHtml: '',
  // 智能模式 (Phase 1: Claude tool_use)
  smart: false,
  chatting: false,
  chatHistory: [],   // [{ role: 'user'|'assistant'|'tool'|'warn', content?, name?, input?, result?, failed? }]
  pendingActions: [],   // 写工具待审批: [{ name, input, cluster_id, tool_use_id }]
  pendingApproving: null,   // 正在审批的 action (用作 disabled / spinner)
  exampleIdx: 0,
  examples: [
    '部署 deployment nginx',
    '创建 deployment web 镜像 nginx:1.25 3 副本',
    '扩容 nginx 到 5 副本',
    '重启 deployment nginx',
    '删除 pod foo (在 default 命名空间)',
    '更新 deployment web 镜像为 nginx:1.25',
    '列出所有 deployments',
    '🧠 看 pod nginx-xxx 的日志 (智能模式)',
    '🧠 nginx CrashLoopBackOff,帮我查上次崩溃的日志',
    '🧠 看 configmap app-config 里的 database.url',
    '🧠 列出 default 下所有 configmap',
    '🧠 把 app-config 里的 log.level 改成 debug (会让你审批)',
  ],
})
// 占位文字轮播 (每 4s 换一个示例)
let _aiCmdRotateTimer = null
onMounted(() => {
  _aiCmdRotateTimer = setInterval(() => {
    if (!aiCmd.text && !aiCmd.intent) {
      aiCmd.exampleIdx = (aiCmd.exampleIdx + 1) % aiCmd.examples.length
    }
  }, 4000)
})
onBeforeUnmount(() => {
  if (_aiCmdRotateTimer) { clearInterval(_aiCmdRotateTimer); _aiCmdRotateTimer = null }
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

// ── 多关键字过滤 + 高亮（参考 grep -e a -e b -e c）─────────────────────────
const logFilterKeywords = ref('')
const logFilterMode = ref('any')     // any | all
const logFilterCase = ref(false)

// 解析关键字：空格分隔；以 - 开头表示排除；保留引号包裹的整段
function parseLogKeywords(raw) {
  const tokens = []
  const re = /"([^"]+)"|(\S+)/g
  let m
  while ((m = re.exec(raw)) !== null) {
    const t = m[1] || m[2]
    if (!t) continue
    if (t.startsWith('-') && t.length > 1) tokens.push({ neg: true, text: t.slice(1) })
    else tokens.push({ neg: false, text: t })
  }
  return tokens
}

const logKwTokens = computed(() => parseLogKeywords(logFilterKeywords.value.trim()))
const logTotalLines = computed(() => (logText.value ? logText.value.split('\n').length : 0))

function _match(line, kw) {
  return logFilterCase.value ? line.includes(kw) : line.toLowerCase().includes(kw.toLowerCase())
}

// 过滤后命中的行（原始字符串），用于统计 + 渲染
const logFilteredLines = computed(() => {
  if (!logKwTokens.value.length) return []
  const pos = logKwTokens.value.filter(t => !t.neg).map(t => t.text)
  const neg = logKwTokens.value.filter(t => t.neg).map(t => t.text)
  const lines = (logText.value || '').split('\n')
  return lines.filter(line => {
    if (neg.some(k => _match(line, k))) return false
    if (!pos.length) return true
    return logFilterMode.value === 'all'
      ? pos.every(k => _match(line, k))
      : pos.some(k => _match(line, k))
  })
})

// 渲染分段：把 logText 按高亮关键字切片，命中片段标 hl + 颜色 idx；
// 无关键字时整段一个 segment，纯文本输出。
const logRenderSegments = computed(() => {
  const text = logText.value || ''
  if (!text) return []
  const tokens = logKwTokens.value.filter(t => !t.neg).map(t => t.text)
  if (!tokens.length) return [{ t: text, h: false }]
  // 过滤模式：只渲染命中的行（其余隐藏，省去大文本的 DOM 开销）
  let workText = text
  if (tokens.length || logKwTokens.value.length) {
    workText = logFilteredLines.value.join('\n')
    if (!workText) return [{ t: '（无命中行）', h: false }]
  }
  // 构造单一正则同时匹配所有 token，捕获组保留原文，标颜色 idx
  const escape = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`(${tokens.map(escape).join('|')})`, logFilterCase.value ? 'g' : 'gi')
  const out = []
  let last = 0
  for (const m of workText.matchAll(re)) {
    if (m.index > last) out.push({ t: workText.slice(last, m.index), h: false })
    const matched = m[0]
    const idx = tokens.findIndex(k => logFilterCase.value ? k === matched : k.toLowerCase() === matched.toLowerCase())
    out.push({ t: matched, h: true, idx: Math.max(0, idx) })
    last = m.index + matched.length
  }
  if (last < workText.length) out.push({ t: workText.slice(last), h: false })
  return out
})
const logFollowing = ref(false)
const logViewEl = ref(null)
let _logEventSource = null
const MAX_LOG_BUFFER = 100_000  // 防内存爆炸: 单 pod 最多保留 10W 字符
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

// ── 资源所在节点展示 ──────────────────────────────────────────────────────────
function nodesText(item) {
  const list = item.node_list || []
  if (!list.length) return '-'
  const ips = list.map((n) => n.ip || n.name).filter(Boolean)
  return ips.slice(0, 2).join(', ') + (ips.length > 2 ? ` +${ips.length - 2}` : '')
}

function nodesTitle(item) {
  const list = item.node_list || []
  if (!list.length) return '无运行中的 Pod'
  return list.map((n) => `${n.name || '?'} (${n.ip || '-'})`).join('\n')
}

function nodeSearchParts(item) {
  return (item.node_list || []).flatMap((n) => [n.name, n.ip])
}

// ── 「只看异常」过滤 + 大列表渲染上限 ────────────────────────────────────
const onlyAbnormal = ref(false)
const showAllRows = ref(false)
const ROW_LIMIT = 150

const POD_OK_STATUS = new Set(['Running', 'Succeeded', 'Completed'])

function isPodAbnormal(pod) {
  if (!POD_OK_STATUS.has(String(pod.status || ''))) return true
  // Running 但存在未就绪容器
  return (pod.containers || []).some((c) => c.ready === false)
}

function isWorkloadAbnormal(item) {
  const desired = Number(item.desired ?? 0)
  return desired > 0 && Number(item.ready ?? 0) < desired
}

function isJobAbnormal(item) {
  return Number(item.failed || 0) > 0 || String(item.status || '') === 'Failed'
}

function isNodeAbnormal(item) {
  return String(item.status || '') !== 'Ready'
}

function abnormalPass(enabledCheck) {
  // onlyAbnormal 关闭时不过滤；开启时按各资源的异常判定过滤
  return (item) => !onlyAbnormal.value || enabledCheck(item)
}

function limitRows(list) {
  return showAllRows.value ? list : list.slice(0, ROW_LIMIT)
}

const filteredPods = computed(() =>
  pods.value.filter((pod) => matchesSearch([
    pod.name, pod.namespace, pod.status, pod.node, pod.host_ip, pod.ip, pod.restarts,
    ...(pod.containers || []).map((container) => container.name),
  ])).filter(abnormalPass(isPodAbnormal))
)
const filteredDeployments = computed(() =>
  deployments.value.filter((item) => matchesSearch([
    item.name, item.namespace, item.status, item.ready, item.desired,
    ...(item.images || []), ...nodeSearchParts(item),
  ])).filter(abnormalPass(isWorkloadAbnormal))
)
const filteredDaemonSets = computed(() =>
  daemonSets.value.filter((item) => matchesSearch([
    item.name, item.namespace, item.status, item.ready, item.desired,
    item.current, item.updated, item.available, ...(item.images || []), ...nodeSearchParts(item),
  ])).filter(abnormalPass(isWorkloadAbnormal))
)
const filteredStatefulSets = computed(() =>
  statefulSets.value.filter((item) => matchesSearch([
    item.name, item.namespace, item.status, item.ready, item.desired,
    item.current, item.updated, ...(item.images || []), ...nodeSearchParts(item),
  ])).filter(abnormalPass(isWorkloadAbnormal))
)
const filteredJobs = computed(() =>
  jobs.value.filter((item) => matchesSearch([
    item.name, item.namespace, item.status, item.succeeded, item.completions,
    item.parallelism, item.active, item.failed, ...(item.images || []), ...nodeSearchParts(item),
  ])).filter(abnormalPass(isJobAbnormal))
)
const filteredCronJobs = computed(() =>
  cronJobs.value.filter((item) => matchesSearch([
    item.name, item.namespace, item.status, item.schedule, item.active,
    item.lastScheduleTime, item.lastSuccessfulTime, ...(item.activeJobs || []), ...nodeSearchParts(item),
  ]))
)
const filteredServices = computed(() =>
  services.value.filter((item) => matchesSearch([
    item.name, item.namespace, item.type, item.clusterIP, ...(item.ports || []), ...nodeSearchParts(item),
  ]))
)
const filteredConfigMaps = computed(() =>
  configMaps.value.filter((item) => matchesSearch([
    item.name, item.namespace, ...(item.keys || []), ...nodeSearchParts(item),
  ]))
)
const filteredNodes = computed(() =>
  nodes.value.filter((item) => matchesSearch([
    item.name, item.internal_ip, item.status, item.roles, item.version, item.os,
  ])).filter(abnormalPass(isNodeAbnormal))
)

// 全集群异常总数（不受 onlyAbnormal 影响，供开关徽标展示）
const abnormalTotal = computed(() =>
  pods.value.filter(isPodAbnormal).length
  + deployments.value.filter(isWorkloadAbnormal).length
  + daemonSets.value.filter(isWorkloadAbnormal).length
  + statefulSets.value.filter(isWorkloadAbnormal).length
  + jobs.value.filter(isJobAbnormal).length
  + nodes.value.filter(isNodeAbnormal).length
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
  detailView.value = 'yaml'   // 默认 YAML
  collapsedYamlPaths.value = new Set()
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

// ── AI 自然语言命令 (Round 3) ───────────────────────────────────────────────
async function parseAICmd() {
  if (!aiCmd.text.trim()) return
  aiCmd.expanded = true   // 操作时自动展开
  aiCmd.parsing = true
  aiCmd.intent = null
  aiCmd.error = ''
  aiCmd.success = ''
  try {
    const ns = activeNs.value || ''
    const r = await api.k8sAiParse(activeClusterId.value, aiCmd.text, ns)
    aiCmd.intent = r
  } catch (e) {
    aiCmd.error = '解析失败: ' + (e?.response?.data?.detail || e?.message || e)
  } finally {
    aiCmd.parsing = false
  }
}

function clearAICmd() {
  aiCmd.text = ''
  aiCmd.intent = null
  aiCmd.error = ''
  aiCmd.success = ''
  aiCmd.alreadyExists = null
  aiCmd.inspectReport = ''
  aiCmd.inspectReportHtml = ''
  aiCmd.chatHistory = []
  aiCmd.pendingActions = []
  aiCmd.pendingApproving = null
  // 没有任何内容时回到折叠态; 否则保持展开让用户继续看
  if (!aiCmd.text && !aiCmd.intent && !aiCmd.chatHistory.length && !aiCmd.pendingActions.length) {
    aiCmd.expanded = false
  }
}

// 待审批操作的友好标签
const PENDING_LABELS = {
  k8s_scale_workload: '扩缩容',
  k8s_restart_workload: '重启',
  k8s_delete_resource: '⚠ 删除',
  k8s_update_image: '更新镜像',
  k8s_update_configmap: '更新配置',
}
function pendingActionLabel(toolName) {
  return PENDING_LABELS[toolName] || toolName
}

// pending-input-row 展示: 把 update_configmap 的 data 字段隐藏 (diff 已经显示了, 重复又长又乱)
function filteredPendingInput(action) {
  const inp = { ...(action.input || {}) }
  if (action.name === 'k8s_update_configmap') {
    delete inp.data
  }
  return inp
}
function formatPendingInputValue(v) {
  if (v === null || v === undefined) return ''
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
function truncateDiff(s) {
  const v = s === null || s === undefined ? '' : String(s)
  if (v.length <= 200) return v
  return v.slice(0, 200) + '… (+' + (v.length - 200) + ' 字符)'
}

async function approvePendingAction(action, approve) {
  if (approve) {
    const verb = pendingActionLabel(action.name)
    if (!confirm(`【二次审核】${verb}\n\n参数:\n${JSON.stringify(action.input, null, 2)}\n\n确认下发到集群?`)) return
  }
  aiCmd.pendingApproving = action
  try {
    const r = await api.k8sAiChatApprove(action, approve)
    aiCmd.chatHistory.push({
      role: 'tool',
      name: action.name,
      input: action.input,
      result: r.result || (approve ? '执行完成' : '已拒绝'),
      failed: approve && r.ok === false,
    })
    if (approve && r.ok !== false) {
      for (const key of Array.from(_resourceCache.keys())) {
        if (key.startsWith(`${activeClusterId.value}|`)) _resourceCache.delete(key)
      }
      setTimeout(() => refreshAll(), 600)
    }
  } catch (e) {
    aiCmd.chatHistory.push({
      role: 'warn',
      content: `审批端点失败: ${e?.response?.data?.detail || e?.message || e}`,
    })
  } finally {
    // 不论成败都从 pending 列表移除
    aiCmd.pendingActions = aiCmd.pendingActions.filter(a => a !== action)
    aiCmd.pendingApproving = null
  }
}

async function rejectAllPending() {
  if (!confirm(`拒绝全部 ${aiCmd.pendingActions.length} 项待审批操作?`)) return
  const items = [...aiCmd.pendingActions]
  for (const a of items) {
    aiCmd.chatHistory.push({
      role: 'warn',
      content: `用户拒绝: ${pendingActionLabel(a.name)} ${JSON.stringify(a.input)}`,
    })
  }
  aiCmd.pendingActions = []
}

// 智能模式: Claude tool_use
async function runSmartChat() {
  const msg = aiCmd.text.trim()
  if (!msg) return
  aiCmd.expanded = true   // 操作时自动展开
  aiCmd.chatting = true
  aiCmd.chatHistory.push({ role: 'user', content: msg })
  aiCmd.text = ''
  try {
    const r = await api.k8sAiChat(activeClusterId.value, msg, activeNs.value || '')
    // 把后端 history 拆成对话气泡
    for (const item of (r.history || [])) {
      if (item.type === 'assistant_text') {
        aiCmd.chatHistory.push({ role: 'assistant', content: item.content })
      } else if (item.type === 'tool_use') {
        const failed = (item.result || '').startsWith('✗')
        aiCmd.chatHistory.push({ role: 'tool', name: item.name, input: item.input, result: item.result, failed })
      } else if (item.type === 'pending_action') {
        // 写工具占位: 在对话流里也显示一行提示
        aiCmd.chatHistory.push({
          role: 'warn',
          content: `📋 ${pendingActionLabel(item.name)} 已提交待审批 (请看下方卡片)`,
        })
      } else if (item.type === 'warning') {
        aiCmd.chatHistory.push({ role: 'warn', content: item.content })
      }
    }
    // 收集待审批的写操作
    if (r.pending_actions?.length) {
      aiCmd.pendingActions = [...aiCmd.pendingActions, ...r.pending_actions]
    }
    // 只读操作可能没改变集群状态, 但不影响刷新
    for (const key of Array.from(_resourceCache.keys())) {
      if (key.startsWith(`${activeClusterId.value}|`)) _resourceCache.delete(key)
    }
    if (!r.pending_actions?.length) {
      setTimeout(() => refreshAll(), 800)
    }
  } catch (e) {
    const detail = e?.response?.data?.detail || e?.message || String(e)
    // 配置缺失类错误: 引导用户去系统设置页
    const isConfigError = (
      detail.includes('激活模型') || detail.includes('AI_PROVIDER') ||
      detail.includes('AI_MODEL') || detail.includes('API key') ||
      detail.includes('api_key') || detail.includes('base_url') ||
      detail.includes('未配置') || detail.includes('/aiops/config')
    )
    if (isConfigError) {
      aiCmd.chatHistory.push({
        role: 'warn',
        content: `调用失败: ${detail}\n\n➡ 推荐: 到「系统设置 → AIOps → 智能配置」(/aiops/config) 添加并激活模型\n   该页同时管理 AI 分析 / Agent 对话 / 智能模式使用的模型, 一处修改全局生效.`,
        action: { label: '去配置', route: '/aiops/config' },
      })
    } else {
      aiCmd.chatHistory.push({ role: 'warn', content: '调用失败: ' + detail })
    }
  } finally {
    aiCmd.chatting = false
  }
}

// 极简 markdown 渲染 (仅支持 ## 标题 / **粗体** / - 列表 / `代码`)
function renderInspectMd(md) {
  if (!md) return ''
  // 转义 HTML
  let s = md.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // ## 标题
  s = s.replace(/^## (.+)$/gm, '<h3 class="ins-h">$1</h3>')
  // **bold**
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // `code`
  s = s.replace(/`([^`]+?)`/g, '<code class="ins-code">$1</code>')
  // - 缩进列表项
  s = s.replace(/^  - (.+)$/gm, '<div class="ins-li">• $1</div>')
  // 换行 → <br>
  s = s.replace(/\n/g, '<br>')
  return s
}

// 把后端的 K8s 错误 detail 解析成精简文本
function formatAIError(e) {
  const d = e?.response?.data?.detail
  if (!d) return e?.message || String(e)
  if (typeof d === 'string') {
    // 旧版可能仍是字符串, 尝试取关键片段
    if (d.length > 200) return d.slice(0, 200) + ' ...'
    return d
  }
  if (typeof d === 'object') {
    return `${d.reason || 'Error'}: ${d.message || ''}`.trim()
  }
  return String(d)
}

async function executeAICmd(opts = {}) {
  if (!aiCmd.intent) return
  const i = aiCmd.intent
  const force = opts.force === true

  // 'list' 不需要执行, 跳转 tab
  if (i.action === 'list') {
    const tabMap = {
      pod: 'pods', deployment: 'deployments', daemonset: 'daemonSets',
      statefulset: 'statefulSets', job: 'jobs', cronjob: 'cronJobs',
      service: 'services', node: 'nodes',
    }
    activeTab.value = tabMap[i.kind] || activeTab.value
    if (i.namespace) activeNs.value = i.namespace
    clearAICmd()
    return
  }
  // 高危: 二次 confirm (force 模式自带 confirm 提示在按钮处)
  if (i.danger && !force) {
    if (!confirm(`【高危】${i.summary}\n\n确认执行? 操作不可撤销.`)) return
  }
  if (force) {
    if (!confirm(`【替换】将先删除已存在的 ${aiCmd.alreadyExists?.kind}/${aiCmd.alreadyExists?.name}, 再用 AI 生成的 YAML 创建.\n\n确认?`)) return
  }
  aiCmd.executing = true
  aiCmd.error = ''
  aiCmd.alreadyExists = null
  aiCmd.inspectReport = ''
  aiCmd.inspectReportHtml = ''
  try {
    const r = await api.k8sAiExecute(activeClusterId.value, {
      action: i.action, kind: i.kind, name: i.name,
      namespace: i.namespace || 'default',
      replicas: i.replicas, image: i.image,
      force,
    })
    // inspect 返回 markdown 报告, 不刷新列表也不自动关
    if (i.action === 'inspect' && r?.report) {
      aiCmd.inspectReport = r.report
      aiCmd.inspectReportHtml = renderInspectMd(r.report)
      return
    }
    aiCmd.success = `${i.summary} 已下发到集群`
    for (const key of Array.from(_resourceCache.keys())) {
      if (key.startsWith(`${activeClusterId.value}|`)) _resourceCache.delete(key)
    }
    setTimeout(() => { refreshAll(); clearAICmd() }, 1500)
  } catch (e) {
    const detail = e?.response?.data?.detail
    // AlreadyExists 结构化错误 → 提供"替换"按钮
    if (detail && typeof detail === 'object' && detail.reason === 'AlreadyExists' && detail.can_force) {
      aiCmd.alreadyExists = detail
      aiCmd.error = ''
    } else {
      aiCmd.error = formatAIError(e)
    }
  } finally {
    aiCmd.executing = false
  }
}

// ── 资源创建 (YAML) ──────────────────────────────────────────────────────────
function openCreateResource() {
  Object.assign(createModal, {
    open: true,
    yaml: 'apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: example\n  namespace: default\ndata:\n  key: value\n',
    applying: false, error: '', result: null,
  })
}

function closeCreateResource() {
  createModal.open = false
  createModal.result = null
}

async function applyCreateResource() {
  if (!createModal.yaml.trim()) return
  createModal.applying = true
  createModal.error = ''
  createModal.result = null
  try {
    const r = await api.k8sCreateResource(activeClusterId.value, createModal.yaml)
    createModal.result = r
    if (!r.errors?.length) {
      // 全部成功: 清缓存 + 静默刷新 + 1.5s 自动关
      for (const key of Array.from(_resourceCache.keys())) {
        if (key.startsWith(`${activeClusterId.value}|`)) _resourceCache.delete(key)
      }
      setTimeout(() => { refreshAll(); closeCreateResource() }, 1500)
    } else {
      // 有失败: 显示结果但不自动关, 用户决定下一步
      for (const key of Array.from(_resourceCache.keys())) {
        if (key.startsWith(`${activeClusterId.value}|`)) _resourceCache.delete(key)
      }
      setTimeout(() => refreshAll(), 800)
    }
  } catch (e) {
    createModal.error = e?.response?.data?.detail || e?.message || String(e)
  } finally {
    createModal.applying = false
  }
}

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
  configMaps: 'configmap',
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
  configMaps: () => filteredConfigMaps.value,
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
  showAllRows.value = false
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
  stopLogFollow()
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
  configMaps.value = []
  nodes.value = []
  lastFetchedAt.value = 0
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
    configMaps: filteredConfigMaps.value.length,
    nodes: filteredNodes.value.length,
  }
  return mapping[id] ?? 0
}

function formatBytes(n) {
  const x = Number(n) || 0
  if (x < 1024) return x + ' B'
  if (x < 1024 * 1024) return (x / 1024).toFixed(1) + ' KB'
  return (x / (1024 * 1024)).toFixed(2) + ' MB'
}

// 单行删除（复用批量 API, items 长度=1）
async function deleteSingleResource(kind, row) {
  if (!activeClusterId.value) return
  const label = KIND_LABELS[kind] || kind
  if (!confirm(`确认删除 ${label} ${row.namespace}/${row.name}? 不可撤销.`)) return
  try {
    await api.k8sBatchOperate(activeClusterId.value, 'delete', [
      { kind, namespace: row.namespace, name: row.name },
    ])
    // 清缓存 + 刷新
    for (const key of Array.from(_resourceCache.keys())) {
      if (key.startsWith(`${activeClusterId.value}|`)) _resourceCache.delete(key)
    }
    setTimeout(() => refreshAll(), 500)
  } catch (e) {
    alert('删除失败: ' + (e?.response?.data?.detail || e?.message || e))
  }
}

async function loadClusters(force = false) {
  try {
    if (!force && Array.isArray(_clustersCache)) {
      clusters.value = _clustersCache
    } else {
      const data = await api.k8sClusters()
      _clustersCache = Array.isArray(data) ? data : []
      clusters.value = _clustersCache
    }
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

function _sectionSet(payload) {
  const sections = Array.isArray(payload?.sections) && payload.sections.length
    ? payload.sections
    : OVERVIEW_SECTIONS
  return new Set(sections)
}

function _mergeSections(...groups) {
  return Array.from(new Set(groups.flat().filter(Boolean)))
}

function _snapshotPayload(sections = OVERVIEW_SECTIONS) {
  return {
    summary: summary.value,
    namespaces: namespaces.value,
    pods: pods.value,
    deployments: deployments.value,
    daemonSets: daemonSets.value,
    statefulSets: statefulSets.value,
    jobs: jobs.value,
    cronJobs: cronJobs.value,
    services: services.value,
    configMaps: configMaps.value,
    nodes: nodes.value,
    sections: _mergeSections(sections),
    lastFetchedAt: lastFetchedAt.value || Date.now(),
  }
}

function _isFullPayload(payload) {
  const sections = _sectionSet(payload)
  return OVERVIEW_SECTIONS.every(section => sections.has(section))
}

function _applyCachedPayload(payload, { merge = false } = {}) {
  const sections = _sectionSet(payload)
  const shouldApply = section => !merge || sections.has(section)

  if (shouldApply('summary')) summary.value = payload.summary || null
  if (shouldApply('namespaces')) namespaces.value = payload.namespaces || []
  if (shouldApply('pods')) pods.value = payload.pods || []
  if (shouldApply('deployments')) deployments.value = payload.deployments || []
  if (shouldApply('daemonSets')) daemonSets.value = payload.daemonSets || []
  if (shouldApply('statefulSets')) statefulSets.value = payload.statefulSets || []
  if (shouldApply('jobs')) jobs.value = payload.jobs || []
  if (shouldApply('cronJobs')) cronJobs.value = payload.cronJobs || []
  if (shouldApply('services')) services.value = payload.services || []
  if (shouldApply('configMaps')) configMaps.value = payload.configMaps || []
  if (shouldApply('nodes')) nodes.value = payload.nodes || []
  if (payload.lastFetchedAt) lastFetchedAt.value = payload.lastFetchedAt
}

// fetchAll(opts)
//   opts.force = true  → 跳过缓存强制重拉（手动「刷新」按钮 / 自动 timer）
//   默认走缓存：命中当前集群/命名空间缓存就直接渲染，不因时间自动过期
//   兼容旧调用：参数若为 Event（select.change 等），按非 force 处理
async function warmFullOverview({ clusterId, ns, force, seq }) {
  const key = `${clusterId}|${ns}`
  const loadKey = `${key}|${force ? 'force' : 'cache'}`
  if (_backgroundOverviewLoads.has(loadKey)) return
  _backgroundOverviewLoads.add(loadKey)
  try {
    const full = await api.k8sOverview(clusterId, ns || undefined, force, 'all')
    if (seq !== _fetchSeq || clusterId !== activeClusterId.value || ns !== (activeNs.value || '')) return
    full.lastFetchedAt = Date.now()
    const cached = _resourceCache.get(key)
    _applyCachedPayload(full, { merge: true })
    _displayedCacheKey = key
    _resourceCache.set(key, _snapshotPayload(_mergeSections(cached?.sections, full.sections || OVERVIEW_SECTIONS)))
    const errorNames = Object.keys(full?.errors || {})
    if (errorNames.length) error.value = `部分资源加载失败: ${errorNames.join(', ')}`
  } catch (e) {
    if (seq === _fetchSeq && clusterId === activeClusterId.value && ns === (activeNs.value || '')) {
      error.value = `后台补全失败: ${e}`
    }
  } finally {
    _backgroundOverviewLoads.delete(loadKey)
  }
}

async function fetchAll(opts) {
  const force = (opts && opts.force === true) === true
  if (!activeClusterId.value) {
    _fetchSeq += 1
    _displayedCacheKey = ''
    resetData()
    return
  }
  const clusterId = activeClusterId.value
  const ns = activeNs.value || ''
  const key = `${clusterId}|${ns}`
  error.value = ''

  if (!force) {
    const cached = _resourceCache.get(key)
    if (cached) {
      const seq = ++_fetchSeq
      loading.value = false
      _applyCachedPayload(cached, { merge: false })
      _displayedCacheKey = key
      if (!_isFullPayload(cached)) {
        warmFullOverview({ clusterId, ns, force: false, seq })
      }
      return
    }
  }

  loading.value = true
  const seq = ++_fetchSeq
  if (_displayedCacheKey !== key) {
    resetData()
  }
  try {
    const nsArg = ns || undefined
    const overview = await api.k8sOverview(clusterId, nsArg, force, FAST_OVERVIEW_SECTIONS)
    if (seq !== _fetchSeq || clusterId !== activeClusterId.value || ns !== (activeNs.value || '')) return
    overview.lastFetchedAt = Date.now()
    const partialErrors = overview?.errors || {}
    const errorNames = Object.keys(partialErrors)
    const cached = _resourceCache.get(key)
    _applyCachedPayload(overview, { merge: _displayedCacheKey === key })
    _displayedCacheKey = key
    _resourceCache.set(key, _snapshotPayload(_mergeSections(force ? [] : cached?.sections, overview.sections || FAST_OVERVIEW_SECTIONS)))
    loading.value = false
    if (errorNames.length) {
      error.value = `部分资源加载失败: ${errorNames.join(', ')}`
    }
    warmFullOverview({ clusterId, ns, force, seq })
  } catch (e) {
    if (seq !== _fetchSeq) return
    error.value = `加载失败: ${e}`
  } finally {
    if (seq === _fetchSeq) loading.value = false
  }
}

// 用户主动刷新（按钮 / timer）：跳过缓存
async function refreshAll(opts = {}) {
  if (opts?.clusters === true) {
    await loadClusters(true)
  }
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

// ── Pod 日志实时流 (EventSource) ────────────────────────────────────────────
function stopLogFollow() {
  if (_logEventSource) {
    try { _logEventSource.close() } catch {}
    _logEventSource = null
  }
  logFollowing.value = false
}

function startLogFollow() {
  if (!selectedLogPod.value) return
  stopLogFollow()
  const url = api.k8sPodLogsStreamUrl(
    activeClusterId.value, selectedLogPod.value, logMeta.namespace,
    selectedLogContainer.value, logTailLines.value || 100,
  )
  const es = new EventSource(url, { withCredentials: true })
  _logEventSource = es
  logFollowing.value = true
  logError.value = ''
  logText.value = ''   // follow 模式从空开始 (tail_lines 由后端给出)
  es.onmessage = (ev) => {
    if (ev.data === undefined || ev.data === null) return
    // 追加到 logText, 超阈值时丢前面
    let next = logText.value + ev.data + '\n'
    if (next.length > MAX_LOG_BUFFER) {
      next = '... [前面日志已截断] ...\n' + next.slice(next.length - MAX_LOG_BUFFER)
    }
    logText.value = next
    nextTick(() => {
      const el = logViewEl.value
      if (el) el.scrollTop = el.scrollHeight
    })
  }
  es.addEventListener('end', () => {
    stopLogFollow()
  })
  es.onerror = () => {
    // 不显式 close, 让浏览器自动重连
    if (!logText.value) logError.value = 'SSE 连接失败, 请检查 Pod 是否还在 Running'
  }
}

function toggleLogFollow() {
  if (logFollowing.value) stopLogFollow()
  else startLogFollow()
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
  stopLogFollow()
  selectedLogContainer.value = pickDefaultContainer(selectedLogPodData.value)
  await loadSelectedPodLogs()
}

async function handleLogContainerChange() {
  stopLogFollow()
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
    await loadClusters(true)
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
    await loadClusters(true)
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
    await loadClusters(true)
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
  if (podRestartSortOrder.value) {
    const dir = podRestartSortOrder.value === 'desc' ? -1 : 1
    return [...list].sort((a, b) => dir * ((Number(a.restarts) || 0) - (Number(b.restarts) || 0)))
  }
  // 默认：异常 Pod 置顶（稳定排序，正常 Pod 保持原顺序）
  return [...list].sort((a, b) => Number(isPodAbnormal(b)) - Number(isPodAbnormal(a)))
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

function _focusExecTerm() {
  const active = document.activeElement
  if (active?.closest?.('.exec-controls')) return
  _execTerm?.focus()
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

async function handleExecSelectionChange() {
  if (!showExecModal.value) return
  await restartExec()
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
  _focusExecTerm()

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
  const ws = new WebSocket(`${proto}://${location.host}/api/k8s/exec?${qs}`)
  _execWs = ws

  ws.onopen = () => {
    if (_execWs !== ws) return
    execConnected.value  = true
    execConnecting.value = false
    const d = _execFitAddon?.proposeDimensions?.()
    if (d) ws.send(`\x1b[RESIZE:${d.cols},${d.rows}]`)
    _focusExecTerm()
  }
  ws.onmessage = (e) => {
    if (_execWs !== ws) return
    _execTerm?.write(e.data)
  }
  ws.onclose   = () => {
    if (_execWs !== ws) return
    execConnected.value  = false
    execConnecting.value = false
    _execTerm?.writeln('\r\n\x1b[90m连接已断开\x1b[0m')
  }
  ws.onerror   = () => {
    if (_execWs !== ws) return
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

.form-input,
.form-textarea {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 12px;
}

.filter-group {
  display: inline-flex; align-items: center;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg-input);
  overflow: hidden;
  transition: border-color .15s, box-shadow .15s;
}
.filter-group:focus-within { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim, rgba(99, 102, 241, .15)); }
.filter-group:has(input:disabled),
.filter-group:has(select:disabled) { opacity: .55; }
.filter-icon { padding: 0 6px 0 8px; font-size: 12px; color: var(--text-muted); user-select: none; pointer-events: none; }

.search-input {
  padding: 6px 10px 6px 2px;
  width: 140px;
  border: 0; outline: none; background: transparent;
  color: var(--text-primary);
  transition: width .2s ease;
}
.search-input:focus { width: 220px; }
.ns-select {
  padding: 6px 22px 6px 2px;
  cursor: pointer; min-width: 100px; max-width: 160px;
  border: 0; outline: none; background: transparent;
  color: var(--text-primary);
  appearance: none;
  -webkit-appearance: none;
  background-image: linear-gradient(45deg, transparent 50%, var(--text-muted) 50%),
                    linear-gradient(135deg, var(--text-muted) 50%, transparent 50%);
  background-position: calc(100% - 12px) 50%, calc(100% - 7px) 50%;
  background-size: 5px 5px;
  background-repeat: no-repeat;
}
.auto-refresh-select { min-width: 56px; max-width: 72px; }

.cache-stamp {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 5px 8px; border-radius: 6px;
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
.abnormal-toggle { margin-left: auto; }
.abnormal-toggle.has-abnormal { color: var(--warning); }
.abnormal-toggle.active { background: rgba(210, 153, 34, .12); border-color: var(--warning); color: var(--warning); font-weight: 600; }
.tab-count.alert { background: rgba(248, 81, 73, .12); border-color: rgba(248, 81, 73, .3); color: var(--error); }
.row-limit-bar { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 9px; margin-top: 4px; font-size: 12px; color: var(--text-muted); border: 1px dashed var(--border); border-radius: 8px; }
.row-limit-bar button { border: none; background: none; color: var(--accent); cursor: pointer; font-size: 12px; padding: 0; }
.row-limit-bar button:hover { opacity: .8; }

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
.node-ip { color: var(--primary, #3b82f6); font-size: 10.5px; opacity: .85; }
.node-list-cell { color: var(--primary, #3b82f6); white-space: nowrap; cursor: default; }
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

/* ── 日志多关键字过滤栏 ───────────────────────────────────── */
.log-filter-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px; margin: 6px 0 8px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 10px; flex-wrap: wrap;
}
.log-filter-input {
  flex: 1; min-width: 240px;
  background: var(--bg-input); border: 1px solid var(--border);
  border-radius: 8px; padding: 6px 12px;
  font-size: 12.5px; font-family: var(--font-mono);
  color: inherit; outline: none;
}
.log-filter-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(var(--accent-rgb), 0.12); }
.log-filter-toggle {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11.5px; color: var(--text-secondary);
  cursor: pointer; user-select: none; white-space: nowrap;
}
.log-filter-toggle input { width: auto; cursor: pointer; }
.log-filter-stat { font-size: 11.5px; color: var(--text-muted); white-space: nowrap; }
.log-filter-stat strong { color: var(--accent); font-family: var(--font-mono); margin: 0 2px; }
.log-filter-clear { font-size: 11px; padding: 2px 8px; }

/* ── YAML 折叠视图 ──────────────────────────────────────── */
.yaml-fold-view { padding: 8px 0; }
.yaml-fold-toolbar {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 12px 8px; border-bottom: 1px solid var(--border-light);
}
.yaml-fold-toolbar .btn-xs { font-size: 11px; padding: 2px 10px; border-radius: 6px; }
.yaml-fold-hint { font-size: 11.5px; color: var(--text-muted); margin-left: auto; }
.yaml-fold-pre {
  margin: 0; padding: 10px 14px;
  font-family: var(--font-mono); font-size: 12.5px; line-height: 1.55;
  color: var(--text-secondary);
  white-space: pre; overflow-x: auto;
  user-select: text;
}
.yaml-line {
  display: flex; align-items: flex-start; gap: 6px;
  border-radius: 4px; padding: 0 2px;
}
.yaml-line:hover { background: var(--bg-hover); }
.yaml-folder {
  display: inline-block; width: 14px;
  color: var(--accent); cursor: pointer; user-select: none;
  font-size: 10px; line-height: 1.55; flex-shrink: 0;
}
.yaml-folder-spacer { display: inline-block; width: 14px; flex-shrink: 0; }
.yaml-line-text { flex: 1; min-width: 0; }
.yk { color: var(--accent); font-weight: 600; }
.yv { color: var(--text-primary); }
.yaml-fold-summary { color: var(--text-muted); font-style: italic; margin-left: 4px; opacity: .6; }
.yaml-empty { color: var(--text-muted); padding: 14px; }

/* 多关键字 6 色高亮 */
.log-view .hl { padding: 0 2px; border-radius: 3px; font-weight: 600; }
.log-view .hl-0 { background: rgba(217,119,87,.32); color: var(--text-primary); }
.log-view .hl-1 { background: rgba(99,130,91,.32); color: var(--text-primary); }
.log-view .hl-2 { background: rgba(96,165,250,.32); color: var(--text-primary); }
.log-view .hl-3 { background: rgba(197,138,70,.34); color: var(--text-primary); }
.log-view .hl-4 { background: rgba(189,86,79,.30); color: var(--text-primary); }
.log-view .hl-5 { background: rgba(168,85,247,.30); color: var(--text-primary); }
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

/* 日志 follow 按钮 + 光标 */
.btn-follow-active {
  background: rgba(63,185,80,.15) !important;
  border-color: rgba(63,185,80,.4) !important;
  color: #3fb950 !important;
}
.log-cursor {
  display: inline-block;
  animation: log-cursor-blink 1s steps(2) infinite;
  color: #3fb950;
  font-weight: 700;
}
@keyframes log-cursor-blink {
  to { opacity: 0 }
}

.create-result .batch-result-summary { display: flex; gap: 6px; }

/* AI 自然语言命令栏 (Round 3) */
.ai-cmd-bar {
  margin: 8px 20px 0;
  padding: 6px 12px;
  background: linear-gradient(135deg, rgba(99,102,241,.06), rgba(56,139,253,.04));
  border: 1px solid rgba(99,102,241,.18);
  border-radius: 10px;
  transition: all .2s;
}
.ai-cmd-bar.open {
  padding: 10px 12px;
  background: linear-gradient(135deg, rgba(99,102,241,.1), rgba(56,139,253,.08));
  border-color: rgba(99,102,241,.4);
  box-shadow: 0 4px 16px rgba(99,102,241,.1);
}
.ai-cmd-bar.has-pending {
  border-color: rgba(210,153,34,.55);
  box-shadow: 0 2px 8px rgba(210,153,34,.18);
}

/* 折叠态紧凑头 */
.ai-cmd-collapsed {
  display: flex; align-items: center; gap: 10px;
  padding: 4px 0;
  cursor: pointer;
  user-select: none;
}
.ai-cmd-collapsed:hover { opacity: .9; }
.ai-cmd-collapsed-title {
  font-size: 13px; font-weight: 600;
  color: var(--text-primary);
}
.ai-cmd-mode-mini {
  font-size: 11px; font-weight: 600;
  color: var(--text-muted);
  padding: 2px 7px;
  background: var(--bg-input);
  border-radius: 4px;
}
.ai-cmd-badge {
  display: inline-flex; align-items: center;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 11px; font-weight: 600;
  background: rgba(56,139,253,.15);
  color: var(--accent);
}
.ai-cmd-badge.danger {
  background: rgba(210,153,34,.18);
  color: var(--warning, #d29922);
  animation: ai-pending-pulse 1.5s ease-in-out infinite;
}
@keyframes ai-pending-pulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: .6; }
}
.ai-cmd-collapsed-hint {
  margin-left: auto;
  font-size: 11px; color: var(--text-muted);
}

/* 对话历史外壳 (含 header + 折叠) */
.ai-chat-history-wrap {
  margin-top: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.ai-chat-header {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px;
  background: var(--bg-input);
  font-size: 12px;
  border-bottom: 1px solid var(--border);
}
.ai-chat-title { flex: 1; font-weight: 600; color: var(--text-primary); }
.ai-cmd-input-wrap {
  display: flex; align-items: center; gap: 8px;
}
.ai-cmd-icon {
  font-size: 18px; cursor: pointer; user-select: none;
  transition: transform .2s;
}
.ai-cmd-icon:hover { transform: scale(1.15) rotate(-5deg); }
.ai-cmd-input {
  flex: 1;
  padding: 7px 12px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}
.ai-cmd-input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(56,139,253,.15); }
.ai-cmd-input::placeholder { color: var(--text-muted); font-style: italic; }

/* 意图卡片 */
.ai-intent-card {
  margin-top: 10px;
  padding: 12px 14px;
  background: var(--bg-card);
  border: 1px solid var(--accent);
  border-radius: 8px;
  font-size: 12px;
}
.ai-intent-card.danger { border-color: var(--warning, #d29922); background: rgba(210,153,34,.05); }
.ai-intent-card.unknown { border-color: var(--text-muted); background: var(--bg-surface); }
.ai-intent-head {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  margin-bottom: 8px;
}
.ai-intent-action-badge {
  padding: 2px 8px; border-radius: 4px;
  background: var(--accent-dim); color: var(--accent);
  font-weight: 700; font-size: 10px; text-transform: uppercase;
  font-family: monospace;
}
.badge-delete { background: rgba(248,81,73,.18); color: var(--error, #f85149); }
.badge-restart { background: rgba(56,139,253,.18); color: var(--accent); }
.badge-scale { background: rgba(63,185,80,.18); color: #3fb950; }
.badge-update_image { background: rgba(163,113,247,.18); color: #a371f7; }
.badge-create { background: rgba(63,185,80,.22); color: #3fb950; font-weight: 700; }
.badge-list { background: var(--accent-dim); color: var(--accent); }
.badge-unknown { background: var(--bg-input); color: var(--text-muted); }
.ai-intent-summary { font-weight: 500; color: var(--text-primary); flex: 1; }
.ai-danger-tag {
  padding: 2px 8px; border-radius: 4px;
  background: rgba(210,153,34,.18); color: var(--warning, #d29922);
  font-weight: 700; font-size: 10px;
}
.ai-intent-body {
  display: flex; flex-direction: column; gap: 6px;
  padding: 6px 0 10px;
}
.ai-intent-row { display: flex; align-items: center; gap: 10px; }
.ai-field-label { width: 60px; color: var(--text-muted); font-size: 11px; flex-shrink: 0; }
.ai-intent-input {
  flex: 1;
  padding: 4px 8px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 12px;
  font-family: monospace;
  outline: none;
}
.ai-intent-input:focus { border-color: var(--accent); }
.ai-intent-actions { display: flex; justify-content: flex-end; gap: 8px; }
.btn-primary-sm.danger {
  background: var(--warning, #d29922);
  border-color: var(--warning, #d29922);
}

.ai-intent-fade-enter-active, .ai-intent-fade-leave-active {
  transition: opacity .18s, transform .18s;
}
.ai-intent-fade-enter-from, .ai-intent-fade-leave-to {
  opacity: 0; transform: translateY(-6px);
}

/* AlreadyExists 替换提示 */
.ai-already-exists {
  margin-top: 10px;
  padding: 10px 12px;
  background: rgba(210,153,34,.08);
  border: 1px solid rgba(210,153,34,.35);
  border-radius: 6px;
}
.ai-already-exists-msg {
  font-size: 12px;
  color: var(--warning, #d29922);
  margin-bottom: 8px;
}
.ai-already-exists-msg strong {
  font-family: monospace; color: var(--text-primary);
}
.ai-already-exists-actions {
  display: flex; justify-content: flex-end; gap: 8px;
}

/* unknown 提示 + 示例 chip */
.ai-unknown-hint {
  font-size: 12px; color: var(--text-muted);
  padding: 4px 0 8px;
}
.ai-unknown-examples {
  border-top: 1px dashed var(--border);
  padding-top: 8px;
}
.ai-unknown-title {
  font-size: 11px; color: var(--text-muted);
  margin-bottom: 6px;
  font-weight: 600;
}
.ai-unknown-chips {
  display: flex; flex-wrap: wrap; gap: 5px;
}
.ai-example-chip {
  padding: 4px 10px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  transition: all .12s;
}
.ai-example-chip:hover {
  background: var(--accent-dim);
  border-color: var(--accent);
  color: var(--accent);
}

/* 巡检报告 */
.ai-inspect-report {
  margin-top: 12px;
  padding: 12px 14px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-secondary);
}
.ai-inspect-report .ins-h {
  font-size: 14px; font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
}
.ai-inspect-report .ins-li {
  margin-left: 12px;
  color: var(--text-muted);
}
.ai-inspect-report .ins-code {
  padding: 1px 5px;
  background: var(--bg-input);
  border-radius: 3px;
  font-family: monospace; font-size: 11px;
  color: var(--accent);
}
.ai-inspect-report strong {
  color: var(--text-primary);
  font-weight: 600;
}

.badge-inspect { background: rgba(99,102,241,.18); color: #818cf8; }

/* 智能模式 toggle */
.ai-mode-toggle {
  padding: 4px 10px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-muted);
  font-size: 11px; font-weight: 600;
  cursor: pointer; user-select: none;
  transition: all .15s;
  white-space: nowrap;
}
.ai-mode-toggle:hover { color: var(--text-primary); }
.ai-mode-toggle.active {
  background: linear-gradient(135deg, rgba(163,113,247,.18), rgba(99,102,241,.18));
  border-color: rgba(163,113,247,.5);
  color: #a371f7;
}

/* 智能模式对话历史 */
.ai-chat-history {
  margin-top: 12px;
  display: flex; flex-direction: column; gap: 8px;
  max-height: 60vh; overflow-y: auto;
  padding-right: 4px;
}
.ai-turn { display: flex; }
.ai-turn-bubble {
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 12px;
  max-width: 88%;
  line-height: 1.65;
  word-break: break-word;
}
.user-bubble {
  background: var(--accent-dim);
  color: var(--text-primary);
  margin-left: auto;
  border-bottom-right-radius: 3px;
}
.assistant-bubble {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  border-bottom-left-radius: 3px;
}
.turn-icon { margin-right: 6px; }

.ai-tool-step {
  padding: 7px 10px;
  background: rgba(56,139,253,.05);
  border: 1px solid rgba(56,139,253,.25);
  border-left: 3px solid var(--accent);
  border-radius: 6px;
  font-size: 11px;
  margin: 2px 0 2px 28px;
}
.ai-tool-step.failed {
  background: rgba(248,81,73,.05);
  border-color: rgba(248,81,73,.3);
  border-left-color: var(--error, #f85149);
}
.tool-head {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 4px;
}
.tool-name-badge {
  font-family: monospace; font-weight: 700;
  color: var(--accent);
}
.ai-tool-step.failed .tool-name-badge { color: var(--error, #f85149); }
.tool-input-preview {
  font-family: monospace; color: var(--text-muted);
  font-size: 10px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.tool-result {
  font-family: monospace; color: var(--text-secondary);
  white-space: pre-wrap; word-break: break-word;
  background: var(--bg-input);
  padding: 6px 8px; border-radius: 4px;
  max-height: 180px; overflow-y: auto;
}

.ai-warn-bubble {
  padding: 6px 10px;
  background: rgba(210,153,34,.1);
  border: 1px solid rgba(210,153,34,.35);
  color: var(--warning, #d29922);
  border-radius: 6px;
  font-size: 11px;
  white-space: pre-wrap;
  font-family: monospace;
  line-height: 1.6;
}
.warn-action-link {
  display: inline-block;
  margin-left: 8px;
  padding: 2px 10px;
  background: var(--accent);
  color: white !important;
  border-radius: 4px;
  font-family: inherit;
  font-weight: 600;
  text-decoration: none;
  font-size: 11px;
}
.warn-action-link:hover { filter: brightness(1.1); }

.ai-thinking {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px;
  color: var(--text-muted);
  font-size: 11px;
  font-style: italic;
}

/* 写工具二次审批卡片 */
.ai-pending-actions {
  margin-top: 12px;
  padding: 12px;
  background: linear-gradient(135deg, rgba(210,153,34,.08), rgba(248,81,73,.06));
  border: 2px solid rgba(210,153,34,.45);
  border-radius: 10px;
  box-shadow: 0 4px 12px rgba(210,153,34,.12);
}
.pending-header {
  display: flex; align-items: center; gap: 10px;
  font-size: 13px; font-weight: 700;
  color: var(--warning, #d29922);
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(210,153,34,.2);
}
.pending-header .btn-ghost { margin-left: auto; color: var(--text-muted); }
.pending-action-card {
  background: var(--bg-card);
  border: 1px solid rgba(248,81,73,.25);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 8px;
}
.pending-action-card:last-child { margin-bottom: 0; }
.pending-tool-row {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 8px;
}
.pending-badge {
  padding: 3px 9px;
  border-radius: 4px;
  font-size: 11px; font-weight: 700;
  background: rgba(248,81,73,.18);
  color: var(--error, #f85149);
}
.pending-k8s_scale_workload { background: rgba(63,185,80,.18); color: #3fb950; }
.pending-k8s_restart_workload { background: rgba(56,139,253,.18); color: var(--accent); }
.pending-k8s_update_image { background: rgba(163,113,247,.18); color: #a371f7; }
.pending-tool-name {
  font-family: monospace; font-size: 12px;
  color: var(--text-secondary);
}
.pending-input-block {
  background: var(--bg-input);
  border-radius: 5px;
  padding: 6px 10px;
  margin-bottom: 10px;
  font-size: 11px;
}
.pending-input-row {
  display: flex; gap: 10px;
  padding: 2px 0;
}
.pending-k {
  color: var(--text-muted);
  min-width: 80px;
  font-family: monospace;
}
.pending-v {
  color: var(--text-primary);
  word-break: break-all;
}
.pending-btn-row {
  display: flex; justify-content: flex-end; gap: 8px;
}

/* ConfigMap 更新审批: key 级 diff 高亮 */
.pending-cm-diff {
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid var(--border-color);
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 10px;
  font-size: 12px;
  font-family: monospace;
}
[data-theme="light"] .pending-cm-diff {
  background: rgba(0, 0, 0, 0.04);
}
.diff-summary {
  display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
  margin-bottom: 8px; padding-bottom: 6px;
  border-bottom: 1px dashed var(--border-color);
}
.diff-tag {
  font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600;
}
.diff-tag.added   { background: rgba(46, 160,  67, .18); color: #3fb950; }
.diff-tag.changed { background: rgba(210, 153, 34, .18); color: #d29922; }
.diff-tag.removed { background: rgba(248,  81, 73, .18); color: #f85149; }
.diff-tag.noop    { background: rgba(139, 148, 158, .18); color: #8b949e; }
.diff-merge-mode {
  margin-left: auto;
  font-size: 10px; padding: 1px 6px; border-radius: 8px;
  background: rgba(88, 166, 255, .15); color: #58a6ff;
}
.diff-row {
  display: flex; gap: 8px; align-items: flex-start;
  padding: 4px 6px; margin: 2px 0; border-radius: 4px;
}
.diff-row.added   { background: rgba(46, 160,  67, .10); border-left: 3px solid #3fb950; }
.diff-row.changed { background: rgba(210, 153, 34, .10); border-left: 3px solid #d29922; }
.diff-row.removed { background: rgba(248,  81, 73, .10); border-left: 3px solid #f85149; }
.diff-mark {
  font-weight: 700; min-width: 12px; text-align: center;
}
.diff-row.added .diff-mark   { color: #3fb950; }
.diff-row.changed .diff-mark { color: #d29922; }
.diff-row.removed .diff-mark { color: #f85149; }
.diff-key {
  color: var(--text-primary); min-width: 100px;
  font-weight: 600;
}
.diff-val {
  flex: 1; color: var(--text-secondary);
  word-break: break-all; white-space: pre-wrap;
}
.diff-val-pair { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.diff-val.diff-old {
  color: #f85149; text-decoration: line-through;
  opacity: 0.85;
}
.diff-val.diff-new { color: #3fb950; }
.diff-row.removed .diff-val {
  color: #f85149; text-decoration: line-through; opacity: 0.85;
}
.diff-row.added .diff-val { color: #3fb950; }

/* ConfigMap 列表 key 预览 tag */
.cm-key-tag {
  display: inline-block;
  font-size: 10px; padding: 1px 6px; margin: 0 3px 2px 0;
  background: rgba(88, 166, 255, .12); color: #58a6ff;
  border-radius: 3px; font-family: monospace;
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
  .filter-group { flex: 1; min-width: 0; }
  .search-input { width: 100%; }
  .search-input:focus { width: 100%; }
  .ns-select { flex: 1; min-width: 0; max-width: none; }
  .auto-refresh-select { flex: 0 0 auto; max-width: 72px; }
  .cache-stamp { display: none; }
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
  position: relative;
  z-index: 20;
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
  position: relative;
  flex: 1;
  min-height: 0;
  padding: 4px 0 0 4px;
  cursor: text;
  z-index: 1;
}
.exec-term-wrap :deep(.xterm) { height: 100%; }
.exec-term-wrap :deep(.xterm-viewport) { overflow-y: auto !important; }
/* 确保 xterm 的 textarea（实际输入元素）不被遮挡，可以接收键盘事件 */
.exec-term-wrap :deep(.xterm-helper-textarea) {
  position: absolute !important;
  opacity: 0 !important;
  left: 0 !important;
  top: 0 !important;
  z-index: 1 !important;
  pointer-events: auto !important;
}
.exec-term-wrap :deep(.xterm-screen) { cursor: text; }
.action-btn.exec-btn { color: #58a6ff; }
.action-btn.exec-btn:disabled { opacity: 0.35; cursor: not-allowed; }
</style>
