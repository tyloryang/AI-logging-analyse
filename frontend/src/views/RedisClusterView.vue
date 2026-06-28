<template>
  <div class="redis-view">
    <div class="cluster-bar">
      <div class="cb-logo">
        <span class="cb-logo-icon">R</span>
        Redis Manager
      </div>
      <button
        v-for="cluster in clusters"
        :key="cluster.id"
        class="cluster-tab"
        :class="{ active: activeId === cluster.id }"
        type="button"
        @click="switchCluster(cluster.id)"
      >
        <span class="ct-dot" :class="clusterHealthTone(cluster.id)"></span>
        <span class="ct-name" :style="activeId === cluster.id ? `color:${cluster.color || '#dc2626'}` : ''">
          {{ cluster.name }}
          <span v-if="cluster.env" class="ct-env" :class="`env-${cluster.env}`">{{ cluster.env.toUpperCase() }}</span>
        </span>
        <span class="ct-close" @click.stop="removeCluster(cluster.id)">×</span>
      </button>
      <button class="cb-add" type="button" title="添加 Redis 连接" @click="openClusterModal()">
        +
      </button>
    </div>

    <div class="page-shell">
      <section v-if="!clusters.length || !activeId" class="welcome card">
        <div class="welcome-mark">R</div>
        <h1>Redis 管理</h1>
        <p>统一维护 Redis 单机与 Redis Cluster 连接、连通性、节点状态、槽位覆盖和容量概览。</p>
        <button class="btn btn-primary" type="button" @click="openClusterModal()">添加 Redis 连接</button>
      </section>

      <template v-else>
        <!-- 左侧导航 -->
        <nav class="side-nav">
          <div class="sn-cluster-name">{{ activeCluster?.name }}</div>
          <div class="sn-section">监控</div>
          <button v-for="item in NAV_ITEMS" :key="item.id"
            class="sn-item" :class="{ active: activePage === item.id }"
            type="button" @click="switchPage(item.id)">
            <span class="sn-icon">{{ item.icon }}</span>{{ item.label }}
          </button>
          <div class="sn-section">工具</div>
          <button v-for="item in NAV_TOOLS" :key="item.id"
            class="sn-item" :class="{ active: activePage === item.id }"
            type="button" @click="switchPage(item.id)">
            <span class="sn-icon">{{ item.icon }}</span>{{ item.label }}
          </button>
        </nav>

        <!-- 主内容 -->
        <main class="main-pane">
          <!-- 顶部 Hero -->
          <header class="page-head">
            <div>
              <div class="page-title">{{ currentPageLabel }}</div>
              <div class="page-sub">
                {{ activeCluster?.name }} ·
                <span class="state-pill sm" :class="summaryTone">{{ stateText }}</span>
              </div>
            </div>
            <div class="head-actions">
              <select v-if="activePage === 'keys'" v-model.number="keyDb" class="db-select" @change="scanKeys(true)">
                <option v-for="n in 16" :key="n-1" :value="n-1">DB {{ n-1 }}</option>
              </select>
              <button class="btn btn-outline btn-sm" @click="openClusterModal(activeId)">编辑</button>
              <button class="btn btn-outline btn-sm" :disabled="testing" @click="testActiveCluster">
                {{ testing ? '测试中...' : '测试连接' }}
              </button>
              <button class="btn btn-primary btn-sm" :disabled="loading" @click="refreshPage">
                {{ loading ? '刷新中...' : '↻ 刷新' }}
              </button>
            </div>
          </header>

          <div v-if="testResult" class="alert" :class="testResult.ok ? 'alert-success' : 'alert-error'" style="margin:0 16px 0">
            {{ testResult.ok ? `${testResult.message}，识别为 ${modeLabel(testResult.detected_mode)}` : `连接失败: ${testResult.error || testResult.message}` }}
          </div>

          <!-- KPI 卡片（概览页显示） -->
          <div v-if="activePage === 'overview'" class="kpi-grid">
            <article v-for="item in kpis" :key="item.label" class="kpi card" :class="item.tone">
              <div class="kpi-label">{{ item.label }}</div>
              <div class="kpi-value">{{ item.value }}</div>
              <div class="kpi-hint">{{ item.hint }}</div>
            </article>
          </div>

          <div v-if="loading && activePage === 'overview' && !overview" class="loading-card">
            <div class="spinner"></div><span>加载中...</span>
          </div>

        <div v-if="overview && activePage === 'overview'" class="main-grid">
          <section class="main-grid" style="padding:0;gap:14px">
            <article class="card summary-card">
              <div class="card-head">
                <div>
                  <h3>集群总览</h3>
                  <p>聚合 Redis 单机或集群状态、节点分布与槽位覆盖情况</p>
                </div>
                <span class="card-meta">{{ summary?.known_nodes || 0 }} 节点</span>
              </div>

              <div class="summary-grid">
                <div class="summary-item">
                  <span>模式 / 角色</span>
                  <strong>{{ summary?.mode_label || '-' }}</strong>
                </div>
                <div class="summary-item">
                  <span>Master / Replica</span>
                  <strong>{{ summary?.master_count || 0 }} / {{ summary?.replica_count || 0 }}</strong>
                </div>
                <div class="summary-item">
                  <span>已连接节点</span>
                  <strong>{{ summary?.connected_nodes || 0 }}</strong>
                </div>
                <div class="summary-item">
                  <span>总 QPS</span>
                  <strong>{{ formatCompact(summary?.total_ops_per_sec) }}</strong>
                </div>
                <div class="summary-item">
                  <span>总内存</span>
                  <strong>{{ summary?.total_memory_human || '0 B' }}</strong>
                </div>
                <div class="summary-item">
                  <span>总连接数</span>
                  <strong>{{ formatCompact(summary?.total_clients) }}</strong>
                </div>
                <div class="summary-item">
                  <span>Redis 版本</span>
                  <strong>{{ versionsText }}</strong>
                </div>
              </div>

              <div v-if="summary?.mode === 'cluster'" class="slot-panel">
                <div class="slot-head">
                  <span>槽位覆盖</span>
                  <strong>{{ summary?.coverage_pct || 0 }}%</strong>
                </div>
                <div class="slot-bar">
                  <span class="slot-ok" :style="{ width: `${slotOkPct}%` }"></span>
                  <span class="slot-pfail" :style="{ width: `${slotPfailPct}%` }"></span>
                  <span class="slot-fail" :style="{ width: `${slotFailPct}%` }"></span>
                </div>
                <div class="slot-legend">
                  <span>OK {{ summary?.slots_ok || 0 }}</span>
                  <span>PFAIL {{ summary?.slots_pfail || 0 }}</span>
                  <span>FAIL {{ summary?.slots_fail || 0 }}</span>
                </div>
              </div>
            </article>

            <article class="card shard-card">
              <div class="card-head">
                <div>
                  <h3>{{ summary?.mode === 'cluster' ? '分片拓扑' : '实例视图' }}</h3>
                  <p>{{ summary?.mode === 'cluster' ? '每个 shard 的槽位范围和主从成员' : '单机模式下展示当前实例角色与基本信息' }}</p>
                </div>
                <span class="card-meta">{{ shards.length }} {{ summary?.mode === 'cluster' ? 'Shards' : 'Instances' }}</span>
              </div>

              <div v-if="shards.length" class="shard-list">
                <div v-for="shard in shards" :key="shard.id" class="shard-item">
                  <div class="shard-top">
                    <strong>{{ shard.id }}</strong>
                    <span>{{ shard.slot_count }} slots</span>
                  </div>
                  <div class="shard-ranges">{{ shard.slot_ranges.join(', ') || '未识别槽位' }}</div>
                  <div class="shard-members">
                    <span
                      v-for="node in shard.nodes"
                      :key="`${shard.id}-${node.id}-${node.role}`"
                      class="shard-member"
                      :class="node.role === 'master' ? 'master' : 'replica'"
                    >
                      {{ node.role === 'master' ? 'M' : 'R' }} {{ node.host }}:{{ node.port }}
                    </span>
                  </div>
                </div>
              </div>

              <div v-else class="empty-block">
                暂无 shard 信息
              </div>
            </article>
          </section>

          <section class="card table-card">
            <div class="card-head">
              <div>
                <h3>节点列表</h3>
                <p>按角色和风险优先级排序，优先暴露异常节点</p>
              </div>
              <div class="table-tools">
                <button
                  class="filter-pill"
                  :class="{ active: roleFilter === '' }"
                  type="button"
                  @click="roleFilter = ''"
                >
                  全部
                </button>
                <button
                  class="filter-pill"
                  :class="{ active: roleFilter === 'master' }"
                  type="button"
                  @click="roleFilter = 'master'"
                >
                  Master
                </button>
                <button
                  class="filter-pill"
                  :class="{ active: roleFilter === 'replica' }"
                  type="button"
                  @click="roleFilter = 'replica'"
                >
                  Replica
                </button>
              </div>
            </div>

            <div class="table-wrap">
              <table class="table">
                <thead>
                  <tr>
                    <th>角色</th>
                    <th>节点</th>
                    <th>状态</th>
                    <th>槽位</th>
                    <th>连接数</th>
                    <th>QPS</th>
                    <th>内存</th>
                    <th>命中率</th>
                    <th>版本</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="!filteredNodes.length">
                    <td colspan="9" class="empty-cell">当前筛选条件下没有节点</td>
                  </tr>
                  <tr v-for="node in filteredNodes" :key="node.id" :class="node.status">
                    <td>
                      <span class="role-tag" :class="node.role">{{ node.role_text }}</span>
                    </td>
                    <td class="mono">
                      <div>{{ node.host }}:{{ node.port }}</div>
                      <small class="muted">{{ node.master_id ? `master=${node.master_id.slice(0, 8)}` : node.flags_text }}</small>
                    </td>
                    <td>
                      <span class="status-badge" :class="nodeStatusTone(node)">
                        {{ nodeStatusText(node) }}
                      </span>
                    </td>
                    <td>{{ node.slot_count || '-' }}</td>
                    <td>{{ formatCompact(node.connected_clients) }}</td>
                    <td>{{ formatCompact(node.ops_per_sec) }}</td>
                    <td>{{ node.used_memory_human || '-' }}</td>
                    <td>{{ node.keyspace_hit_rate == null ? '-' : `${node.keyspace_hit_rate}%` }}</td>
                    <td>{{ node.redis_version || '-' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div><!-- /overview -->

        <!-- ══ Key 浏览 ══ -->
        <div v-if="activePage === 'keys'" class="keys-pane">
          <div class="keys-toolbar">
            <input v-model="keyPattern" class="keys-search" placeholder="Pattern: * 或 user:*" @keyup.enter="scanKeys(true)" />
            <button class="btn btn-primary btn-sm" @click="scanKeys(true)" :disabled="keysLoading">{{ keysLoading ? '扫描中...' : '扫描' }}</button>
            <span class="keys-hint">{{ keyList.length }} 个 Key{{ keyCursor ? '（还有更多）' : '' }}</span>
          </div>
          <div class="keys-body">
            <!-- Key 列表 -->
            <div class="key-list-wrap">
              <div v-if="keysLoading" class="loading-row"><div class="spinner"></div></div>
              <div v-else-if="!keyList.length" class="empty-state">暂无 Key</div>
              <div v-else>
                <div v-for="item in keyList" :key="item.key"
                  class="key-row" :class="{ active: selectedKey === item.key }"
                  @click="selectKey(item)">
                  <span class="key-type-badge" :class="'ktype-' + item.type">{{ item.type }}</span>
                  <span class="key-name">{{ item.key }}</span>
                  <span class="key-ttl" :class="item.ttl === -1 ? 'ttl-perm' : item.ttl < 60 ? 'ttl-soon' : ''">
                    {{ item.ttl === -1 ? '永久' : item.ttl === -2 ? '已过期' : item.ttl + 's' }}
                  </span>
                </div>
                <button v-if="keyCursor" class="btn btn-outline btn-sm" style="width:100%;margin-top:6px" @click="scanKeys(false)">
                  加载更多
                </button>
              </div>
            </div>
            <!-- Key 详情 -->
            <div class="key-detail-wrap">
              <div v-if="!selectedKey" class="empty-state">← 选择 Key 查看详情</div>
              <template v-else>
                <div class="kd-header">
                  <span class="key-type-badge" :class="'ktype-' + (keyDetail?.type || '')">{{ keyDetail?.type }}</span>
                  <span class="kd-name">{{ selectedKey }}</span>
                  <span class="kd-ttl">TTL: {{ keyDetail?.ttl === -1 ? '永久' : (keyDetail?.ttl ?? '-') + 's' }}</span>
                  <div style="margin-left:auto;display:flex;gap:6px">
                    <input v-model.number="newTTL" type="number" class="ttl-input" placeholder="设置 TTL(s)" min="-1" />
                    <button class="btn btn-outline btn-sm" @click="setTTL">设置 TTL</button>
                    <button class="btn btn-danger btn-sm" @click="deleteSelectedKey">删除</button>
                  </div>
                </div>
                <div v-if="keyDetailLoading" class="loading-row"><div class="spinner"></div></div>
                <div v-else-if="keyDetail" class="kd-body">
                  <div class="kd-meta">长度: {{ keyDetail.length ?? '-' }} · 编码: {{ keyDetail.encoding || '-' }}</div>
                  <!-- String -->
                  <pre v-if="keyDetail.type === 'string'" class="kd-value">{{ keyDetail.value }}</pre>
                  <!-- Hash -->
                  <table v-else-if="keyDetail.type === 'hash'" class="kd-table">
                    <thead><tr><th>Field</th><th>Value</th></tr></thead>
                    <tbody>
                      <tr v-for="(v, k) in keyDetail.value" :key="k">
                        <td class="mono kd-field">{{ k }}</td>
                        <td class="kd-val">{{ v }}</td>
                      </tr>
                    </tbody>
                  </table>
                  <!-- List -->
                  <table v-else-if="keyDetail.type === 'list'" class="kd-table">
                    <thead><tr><th>#</th><th>Value</th></tr></thead>
                    <tbody>
                      <tr v-for="(v, i) in keyDetail.value" :key="i">
                        <td class="mono">{{ i }}</td><td>{{ v }}</td>
                      </tr>
                    </tbody>
                  </table>
                  <!-- Set -->
                  <div v-else-if="keyDetail.type === 'set'" class="kd-set">
                    <span v-for="m in keyDetail.value" :key="m" class="set-member">{{ m }}</span>
                  </div>
                  <!-- ZSet -->
                  <table v-else-if="keyDetail.type === 'zset'" class="kd-table">
                    <thead><tr><th>Member</th><th>Score</th></tr></thead>
                    <tbody>
                      <tr v-for="item in keyDetail.value" :key="item.member">
                        <td>{{ item.member }}</td><td class="mono">{{ item.score }}</td>
                      </tr>
                    </tbody>
                  </table>
                  <!-- Stream -->
                  <div v-else-if="keyDetail.type === 'stream'" class="kd-stream">
                    <div v-for="entry in keyDetail.value" :key="entry.id" class="stream-entry">
                      <span class="stream-id mono">{{ entry.id }}</span>
                      <span v-for="(v, k) in entry.fields" :key="k" class="stream-field">
                        <em>{{ k }}</em>: {{ v }}
                      </span>
                    </div>
                  </div>
                  <pre v-else class="kd-value">{{ JSON.stringify(keyDetail.value, null, 2) }}</pre>
                </div>
              </template>
            </div>
          </div>
        </div>

        <!-- ══ 监控 ══ -->
        <div v-if="activePage === 'monitor'" class="monitor-pane">
          <div v-if="infoLoading" class="loading-row"><div class="spinner"></div><span>加载 INFO...</span></div>
          <template v-else-if="redisInfo">
            <!-- 核心指标 -->
            <div class="info-kpi-row">
              <div class="info-kpi">
                <span>Redis 版本</span><strong>{{ redisInfo.server?.redis_version || '-' }}</strong>
              </div>
              <div class="info-kpi">
                <span>运行天数</span><strong>{{ redisInfo.server?.uptime_in_days ?? '-' }} 天</strong>
              </div>
              <div class="info-kpi">
                <span>连接数</span><strong>{{ redisInfo.clients?.connected_clients ?? '-' }}</strong>
              </div>
              <div class="info-kpi">
                <span>内存使用</span><strong>{{ redisInfo.memory?.used_memory_human || '-' }}</strong>
              </div>
              <div class="info-kpi">
                <span>峰值内存</span><strong>{{ redisInfo.memory?.used_memory_peak_human || '-' }}</strong>
              </div>
              <div class="info-kpi">
                <span>内存策略</span><strong>{{ redisInfo.memory?.maxmemory_policy || '-' }}</strong>
              </div>
              <div class="info-kpi">
                <span>QPS</span><strong>{{ redisInfo.stats?.instantaneous_ops_per_sec ?? '-' }}</strong>
              </div>
              <div class="info-kpi" :class="(redisInfo.stats?.hit_rate ?? 0) < 80 ? 'tone-warn' : ''">
                <span>命中率</span>
                <strong>{{ redisInfo.stats?.hit_rate != null ? redisInfo.stats.hit_rate + '%' : '-' }}</strong>
              </div>
              <div class="info-kpi">
                <span>过期 Key</span><strong>{{ redisInfo.stats?.expired_keys ?? '-' }}</strong>
              </div>
              <div class="info-kpi">
                <span>淘汰 Key</span><strong>{{ redisInfo.stats?.evicted_keys ?? '-' }}</strong>
              </div>
            </div>
            <!-- Keyspace 分布 -->
            <div class="info-section">
              <div class="info-sec-title">Keyspace</div>
              <div v-if="!Object.keys(redisInfo.keyspace || {}).length" class="empty-state sm">无数据（空实例）</div>
              <table v-else class="info-table">
                <thead><tr><th>DB</th><th>Keys</th><th>Expires</th><th>Avg TTL</th></tr></thead>
                <tbody>
                  <tr v-for="(v, k) in redisInfo.keyspace" :key="k">
                    <td>{{ k }}</td>
                    <td>{{ parseKsField(v, 'keys') }}</td>
                    <td>{{ parseKsField(v, 'expires') }}</td>
                    <td>{{ parseKsField(v, 'avg_ttl') }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <!-- 主从复制 -->
            <div class="info-section">
              <div class="info-sec-title">主从复制</div>
              <div class="info-kv-grid">
                <template v-for="(v, k) in redisInfo.replication" :key="k">
                  <span class="info-k">{{ k }}</span><span class="info-v">{{ v }}</span>
                </template>
              </div>
            </div>
            <!-- 慢查询 -->
            <div class="info-section">
              <div class="info-sec-title">
                慢查询日志
                <button class="btn btn-outline btn-sm" style="margin-left:8px" @click="loadSlowlog">刷新</button>
              </div>
              <div v-if="!slowlog.length" class="empty-state sm">暂无慢查询</div>
              <table v-else class="info-table">
                <thead><tr><th>耗时(μs)</th><th>命令</th><th>时间</th><th>客户端</th></tr></thead>
                <tbody>
                  <tr v-for="s in slowlog" :key="s.id">
                    <td :class="s.duration_us > 10000 ? 'val-err' : 'val-warn'">{{ s.duration_us }}</td>
                    <td class="mono">{{ s.command }}</td>
                    <td>{{ formatSlowTs(s.timestamp) }}</td>
                    <td class="mono">{{ s.client_addr }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>

        <!-- ══ 命令台 ══ -->
        <div v-if="activePage === 'console'" class="console-pane">
          <!-- 顶栏 -->
          <div class="con-topbar">
            <div class="con-db-row">
              <span class="con-label">DB</span>
              <select v-model.number="consoleDb" class="con-db-sel">
                <option v-for="n in 16" :key="n-1" :value="n-1">{{ n-1 }}</option>
              </select>
              <span class="con-cluster-info">{{ activeCluster?.name }}</span>
            </div>
            <div class="con-preset-groups">
              <div v-for="grp in CONSOLE_PRESET_GROUPS" :key="grp.label" class="preset-group">
                <span class="preset-group-label">{{ grp.label }}</span>
                <button v-for="p in grp.cmds" :key="p" class="preset-chip"
                  @click="fillConsoleCmdAndFocus(p)">{{ p }}</button>
              </div>
            </div>
          </div>

          <!-- 终端输出区（命令 + 结果按时序展示） -->
          <div class="con-output" ref="conOutputRef">
            <div v-if="!consoleSession.length" class="con-welcome">
              <div class="con-welcome-title">Redis CLI</div>
              <div class="con-welcome-sub">Connected to {{ activeCluster?.name }} · DB {{ consoleDb }}</div>
              <div class="con-welcome-hint">输入命令后按 Enter 执行 · ↑↓ 键切换历史</div>
            </div>
            <div v-for="(item, i) in consoleSession" :key="i" class="con-entry">
              <!-- 命令行 -->
              <div class="con-cmd-line">
                <span class="con-prompt">{{ item.db !== undefined ? `[db${item.db}]` : '' }} &gt;</span>
                <span class="con-cmd-text">{{ item.cmd }}</span>
                <span class="con-copy-btn" title="复制命令" @click="copyText(item.cmd)">⎘</span>
              </div>
              <!-- 结果 -->
              <div class="con-result-block" :class="item.ok === false ? 'res-err' : 'res-ok'">
                <div class="con-result-meta">
                  <span class="con-type-badge" :class="'rtype-' + item.rtype">{{ item.rtype }}</span>
                  <span class="con-dur">{{ item.ms }}ms</span>
                  <span class="con-copy-btn" title="复制结果" @click="copyText(item.resultText)">⎘</span>
                </div>
                <pre class="con-result-pre" v-html="item.resultHtml"></pre>
              </div>
            </div>
            <div v-if="consoleRunning" class="con-running">
              <div class="spinner" style="width:12px;height:12px;border-width:2px"></div>
              <span>执行中...</span>
            </div>
          </div>

          <!-- AI 翻译条（dbx 风格：自然语言 → Redis 命令） -->
          <div class="ai-translate-bar">
            <span class="ai-spark">✨</span>
            <input
              v-model="aiQuery"
              class="ai-translate-input"
              placeholder="用自然语言描述意图，AI 生成 Redis 命令。例：『查所有 session: 开头的 key 总数』"
              @keydown.enter.prevent="aiTranslate"
            />
            <button class="con-btn-run" :disabled="aiTranslating || !aiQuery.trim()" @click="aiTranslate">
              <span v-if="aiTranslating" class="spinner-mini"></span>{{ aiTranslating ? '生成中' : 'AI 生成' }}
            </button>
          </div>
          <div v-if="aiResult" class="ai-result" :class="'risk-' + (aiResult.risk || 'low')">
            <div class="ai-result-cmd">
              <span class="ai-result-label">建议命令：</span>
              <code>{{ aiResult.command }}</code>
              <button class="con-btn-clear" title="填入命令行" @click="consoleCmd = aiResult.command; aiResult = null">→ 填入</button>
            </div>
            <div class="ai-result-explain">{{ aiResult.explain }}</div>
            <div v-if="aiResult.risk_reason" class="ai-result-risk">⚠ {{ aiResult.risk_reason }}</div>
          </div>

          <!-- 输入区 -->
          <div class="con-input-wrap">
            <span class="con-prompt-static">[db{{ consoleDb }}]&gt;</span>
            <input
              ref="conInputRef"
              v-model="consoleCmd"
              class="con-input"
              placeholder="输入 Redis 命令，Enter 执行，↑↓ 切换历史..."
              spellcheck="false"
              autocomplete="off"
              :disabled="consoleRunning"
              @keydown.enter.prevent="runConsoleCmd"
              @keydown.up.prevent="historyUp"
              @keydown.down.prevent="historyDown"
              @keydown.ctrl.l.prevent="clearConsoleSession"
            />
            <div class="con-input-actions">
              <button class="con-btn-run" :disabled="consoleRunning || !consoleCmd.trim()"
                @click="runConsoleCmd" title="执行 (Enter)">▶</button>
              <button class="con-btn-clear" @click="clearConsoleSession" title="清空 (Ctrl+L)">✕</button>
            </div>
          </div>
        </div>

        </main><!-- /main-pane -->
      </template>
    </div><!-- /page-shell -->

    <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
      <div class="modal">
        <div class="modal-title">{{ editingId ? '编辑 Redis 连接' : '添加 Redis 连接' }}</div>
        <div class="form-row">
          <div class="form-group grow">
            <label class="form-label">连接名称 *</label>
            <input v-model.trim="form.name" class="form-input" placeholder="生产 Redis / Redis Cluster" />
          </div>
          <div class="form-group narrow">
            <label class="form-label">环境</label>
            <select v-model="form.env" class="form-input">
              <option value="">无</option>
              <option value="prod">PROD</option>
              <option value="uat">UAT</option>
              <option value="sit">SIT</option>
              <option value="dev">DEV</option>
            </select>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group grow">
            <label class="form-label">连接模式</label>
            <select v-model="form.mode" class="form-input">
              <option value="auto">自动识别</option>
              <option value="standalone">单机</option>
              <option value="cluster">集群</option>
            </select>
          </div>
          <div class="form-group grow">
            <label class="form-label">节点说明</label>
            <div class="form-readonly">
              {{ form.mode === 'cluster' ? '至少填写 1 个集群节点，系统按 Cluster 方式连接' : form.mode === 'standalone' ? '填写任意一个单机节点地址，系统按单机方式连接' : '默认先探测 cluster_enabled，再自动选择单机或集群连接方式' }}
            </div>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">{{ form.mode === 'standalone' ? '节点地址 *' : '启动节点 *' }}</label>
          <textarea
            v-model="form.startup_nodes_text"
            class="form-textarea"
            rows="4"
            placeholder="10.0.0.11:6379&#10;10.0.0.12:6379&#10;10.0.0.13:6379"
          ></textarea>
          <div class="form-hint">支持换行、逗号分隔，也支持 `redis://host:port`。单机模式下填 1 个即可。</div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">用户名</label>
            <input v-model.trim="form.username" class="form-input" placeholder="默认可留空" />
          </div>
          <div class="form-group">
            <label class="form-label">密码</label>
            <input v-model="form.password" class="form-input" type="password" :placeholder="editingId ? '留空表示不修改' : '可留空'" />
          </div>
        </div>
        <div class="form-row">
          <div class="form-group narrow">
            <label class="form-label">TLS</label>
            <select v-model="form.tls" class="form-input">
              <option :value="false">关闭</option>
              <option :value="true">开启</option>
            </select>
          </div>
          <div class="form-group grow">
            <label class="form-label">标识颜色</label>
            <input v-model.trim="form.color" class="form-input mono" placeholder="#dc2626" />
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">备注</label>
          <input v-model.trim="form.note" class="form-input" placeholder="如：订单缓存集群、核心链路" />
        </div>

        <div v-if="modalTestResult" class="alert" :class="modalTestResult.ok ? 'alert-success' : 'alert-error'">
          {{ modalTestResult.ok ? `${modalTestResult.message}，识别为 ${modeLabel(modalTestResult.detected_mode)}${modalTestResult.cluster_state ? `，状态 ${modalTestResult.cluster_state}` : ''}` : `连接失败: ${modalTestResult.error || modalTestResult.message}` }}
        </div>

        <div class="modal-footer">
          <button class="btn btn-outline" type="button" :disabled="saving || testingConfig" @click="testFormConfig">
            {{ testingConfig ? '测试中...' : '测试配置' }}
          </button>
          <div class="footer-actions">
            <button class="btn btn-outline" type="button" @click="closeModal">取消</button>
            <button class="btn btn-primary" type="button" :disabled="saving" @click="submitCluster">
              {{ saving ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { api } from '../api/index.js'

// ── 导航 ──────────────────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id: 'overview', icon: '◈', label: '集群概览' },
  { id: 'monitor',  icon: '📊', label: '监控统计' },
]
const NAV_TOOLS = [
  { id: 'keys',    icon: '🔑', label: 'Key 浏览器' },
  { id: 'console', icon: '⌨', label: '命令台' },
]
const activePage = ref('overview')
const currentPageLabel = computed(() =>
  [...NAV_ITEMS, ...NAV_TOOLS].find(i => i.id === activePage.value)?.label || '概览'
)

const clusters = ref([])
const overviewCache = ref({})
const activeId = ref('')
const loading = ref(false)
const testing = ref(false)
const testResult = ref(null)
const roleFilter = ref('')

const showModal = ref(false)
const editingId = ref('')
const saving = ref(false)
const testingConfig = ref(false)
const modalTestResult = ref(null)
const form = ref(makeEmptyForm())

const activeCluster = computed(() => clusters.value.find((item) => item.id === activeId.value) || null)
const overview = computed(() => overviewCache.value[activeId.value] || null)
const summary = computed(() => overview.value?.summary || null)
const nodes = computed(() => overview.value?.nodes || [])
const shards = computed(() => overview.value?.shards || [])
const versionsText = computed(() => {
  const versions = summary.value?.versions || []
  return versions.length ? versions.join(' / ') : '-'
})

const summaryTone = computed(() => summary.value?.state_tone || 'warn')
const stateText = computed(() => {
  const mode = summary.value?.mode
  const state = summary.value?.cluster_state || 'unknown'
  if (mode === 'standalone') {
    return state === 'ok' ? 'Standalone OK' : state.toUpperCase()
  }
  return state === 'ok' ? 'Cluster OK' : state
})
const slotOkPct = computed(() => ratioPct(summary.value?.slots_ok))
const slotPfailPct = computed(() => ratioPct(summary.value?.slots_pfail))
const slotFailPct = computed(() => ratioPct(summary.value?.slots_fail))

const kpis = computed(() => [
  {
    label: 'Shards',
    value: summary.value?.shard_count ?? 0,
    hint: `Master ${summary.value?.master_count ?? 0} / Replica ${summary.value?.replica_count ?? 0}`,
    tone: 'info',
  },
  {
    label: '节点健康',
    value: `${summary.value?.connected_nodes ?? 0}/${summary.value?.known_nodes ?? 0}`,
    hint: summary.value?.unhealthy_nodes ? `${summary.value.unhealthy_nodes} 个节点需关注` : '当前未发现离线节点',
    tone: summary.value?.unhealthy_nodes ? 'warn' : 'ok',
  },
  {
    label: '槽位覆盖',
    value: `${summary.value?.coverage_pct ?? 0}%`,
    hint: `OK ${summary.value?.slots_ok ?? 0} / FAIL ${summary.value?.slots_fail ?? 0}`,
    tone: (summary.value?.slots_fail ?? 0) > 0 ? 'danger' : (summary.value?.slots_pfail ?? 0) > 0 ? 'warn' : 'ok',
  },
  {
    label: '总吞吐',
    value: formatCompact(summary.value?.total_ops_per_sec),
    hint: `连接 ${formatCompact(summary.value?.total_clients)} / 内存 ${summary.value?.total_memory_human || '0 B'}`,
    tone: 'info',
  },
])

const filteredNodes = computed(() => {
  const list = roleFilter.value
    ? nodes.value.filter((node) => node.role === roleFilter.value)
    : nodes.value

  return [...list].sort((left, right) => {
    const toneRank = toneWeight(nodeStatusTone(left)) - toneWeight(nodeStatusTone(right))
    if (toneRank !== 0) return toneRank
    if (left.role !== right.role) return left.role === 'master' ? -1 : 1
    return `${left.host}:${left.port}`.localeCompare(`${right.host}:${right.port}`)
  })
})

function makeEmptyForm() {
  return {
    name: '',
    startup_nodes_text: '',
    mode: 'auto',
    username: '',
    password: '',
    tls: false,
    env: '',
    note: '',
    color: '#dc2626',
  }
}

function normalizeNodesInput(text) {
  return String(text || '')
    .replace(/\r/g, '\n')
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function buildPayload() {
  return {
    name: form.value.name.trim(),
    startup_nodes: normalizeNodesInput(form.value.startup_nodes_text),
    mode: form.value.mode || 'auto',
    username: form.value.username.trim(),
    password: form.value.password,
    tls: Boolean(form.value.tls),
    env: form.value.env,
    note: form.value.note.trim(),
    color: form.value.color.trim() || '#dc2626',
  }
}

function ratioPct(value) {
  const total = 16384
  const amount = Number(value || 0)
  return total > 0 ? Math.round((amount / total) * 1000) / 10 : 0
}

function modeLabel(mode) {
  return {
    auto: '自动识别',
    standalone: '单机',
    cluster: '集群',
  }[mode] || mode || '-'
}

function formatCompact(value) {
  const num = Number(value || 0)
  if (!Number.isFinite(num)) return '-'
  if (Math.abs(num) >= 1e9) return `${(num / 1e9).toFixed(1)}G`
  if (Math.abs(num) >= 1e6) return `${(num / 1e6).toFixed(1)}M`
  if (Math.abs(num) >= 1e3) return `${(num / 1e3).toFixed(1)}K`
  return `${Math.round(num)}`
}

function toneWeight(tone) {
  return { danger: 0, warn: 1, ok: 2, info: 3 }[tone] ?? 9
}

function nodeStatusTone(node) {
  if (!node.connected) return 'danger'
  if (node.probe_error || node.status === 'warn') return 'warn'
  if (node.master_link_status && node.master_link_status !== 'up') return 'warn'
  return 'ok'
}

function nodeStatusText(node) {
  if (!node.connected) return 'OFFLINE'
  if (node.probe_error) return 'DEGRADED'
  if (node.master_link_status && node.master_link_status !== 'up') return 'REPL-SYNC'
  return 'ONLINE'
}

function clusterHealthTone(clusterId) {
  const item = overviewCache.value[clusterId]?.summary
  return item?.state_tone || 'warn'
}

async function loadClusters({ preserveActive = true } = {}) {
  const result = await api.redisClusters().catch(() => [])
  clusters.value = Array.isArray(result) ? result : []
  if (!clusters.value.length) {
    activeId.value = ''
    return
  }
  const existing = preserveActive ? clusters.value.find((item) => item.id === activeId.value) : null
  activeId.value = existing?.id || clusters.value[0].id
}

async function loadOverview(clusterId, { force = false } = {}) {
  if (!clusterId) return
  if (!force && overviewCache.value[clusterId]) return overviewCache.value[clusterId]
  loading.value = true
  try {
    const result = await api.redisOverview(clusterId)
    overviewCache.value = { ...overviewCache.value, [clusterId]: result }
    return result
  } finally {
    loading.value = false
  }
}

async function switchCluster(clusterId) {
  activeId.value = clusterId
  roleFilter.value = ''
  testResult.value = null
  await loadOverview(clusterId)
}

async function testActiveCluster() {
  if (!activeId.value) return
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await api.redisTestCluster(activeId.value)
  } finally {
    testing.value = false
  }
}

function openClusterModal(clusterId = '') {
  editingId.value = clusterId
  modalTestResult.value = null
  if (clusterId) {
    const cluster = clusters.value.find((item) => item.id === clusterId)
    form.value = {
      name: cluster?.name || '',
      startup_nodes_text: (cluster?.startup_nodes || []).join('\n'),
      mode: cluster?.mode || 'auto',
      username: cluster?.username || '',
      password: '',
      tls: Boolean(cluster?.tls),
      env: cluster?.env || '',
      note: cluster?.note || '',
      color: cluster?.color || '#dc2626',
    }
  } else {
    form.value = makeEmptyForm()
  }
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  editingId.value = ''
  modalTestResult.value = null
}

async function testFormConfig() {
  const payload = buildPayload()
  if (!payload.name || !payload.startup_nodes.length) return
  testingConfig.value = true
  modalTestResult.value = null
  try {
    modalTestResult.value = await api.redisTestConfig({
      ...payload,
      cluster_id: editingId.value || '',
    })
  } finally {
    testingConfig.value = false
  }
}

async function submitCluster() {
  const payload = buildPayload()
  if (!payload.name || !payload.startup_nodes.length) return
  saving.value = true
  try {
    if (editingId.value) {
      await api.redisUpdateCluster(editingId.value, payload)
    } else {
      const created = await api.redisAddCluster(payload)
      activeId.value = created.id
    }
    overviewCache.value = {}
    await loadClusters()
    if (activeId.value) await loadOverview(activeId.value, { force: true })
    closeModal()
  } finally {
    saving.value = false
  }
}

async function removeCluster(clusterId) {
  if (!window.confirm('确认删除该 Redis 集群配置？')) return
  await api.redisDeleteCluster(clusterId)
  delete overviewCache.value[clusterId]
  await loadClusters({ preserveActive: false })
  if (activeId.value) await loadOverview(activeId.value, { force: true })
}

// ── 页面切换 ──────────────────────────────────────────────────────────────────
async function switchPage(id) {
  activePage.value = id
  if (id === 'monitor') { await loadRedisInfo(); await loadSlowlog() }
  if (id === 'keys')    { await scanKeys(true) }
}

function refreshPage() {
  if (activePage.value === 'overview') loadOverview(activeId.value, { force: true })
  else if (activePage.value === 'monitor') { loadRedisInfo(); loadSlowlog() }
  else if (activePage.value === 'keys') scanKeys(true)
}

// ── Key 浏览 ──────────────────────────────────────────────────────────────────
const keyDb       = ref(0)
const keyPattern  = ref('*')
const keyList     = ref([])
const keyCursor   = ref(0)
const keysLoading = ref(false)
const selectedKey = ref('')
const keyDetail   = ref(null)
const keyDetailLoading = ref(false)
const newTTL      = ref(null)

async function scanKeys(reset = false) {
  if (!activeId.value) return
  keysLoading.value = true
  if (reset) { keyList.value = []; keyCursor.value = 0; selectedKey.value = ''; keyDetail.value = null }
  try {
    const r = await api.redisScanKeys(activeId.value, {
      pattern: keyPattern.value || '*',
      cursor:  reset ? 0 : keyCursor.value,
      count:   200,
      db:      keyDb.value,
    })
    keyList.value   = reset ? (r.keys || []) : [...keyList.value, ...(r.keys || [])]
    keyCursor.value = r.cursor || 0
  } catch (e) { keyList.value = [] }
  finally { keysLoading.value = false }
}

async function selectKey(item) {
  selectedKey.value = item.key
  keyDetail.value = null
  keyDetailLoading.value = true
  try {
    keyDetail.value = await api.redisGetKey(activeId.value, { key: item.key, db: keyDb.value })
  } catch {}
  finally { keyDetailLoading.value = false }
}

async function deleteSelectedKey() {
  if (!selectedKey.value || !confirm(`确认删除 Key: ${selectedKey.value}？`)) return
  await api.redisDeleteKey(activeId.value, selectedKey.value, keyDb.value)
  keyList.value = keyList.value.filter(k => k.key !== selectedKey.value)
  selectedKey.value = ''
  keyDetail.value = null
}

async function setTTL() {
  if (!selectedKey.value || newTTL.value == null) return
  await api.redisSetKeyTTL(activeId.value, selectedKey.value, newTTL.value, keyDb.value)
  // 刷新详情
  await selectKey({ key: selectedKey.value })
}

// ── 监控 ──────────────────────────────────────────────────────────────────────
const redisInfo  = ref(null)
const slowlog    = ref([])
const infoLoading = ref(false)

async function loadRedisInfo() {
  if (!activeId.value) return
  infoLoading.value = true
  try { redisInfo.value = await api.redisInfo(activeId.value, 0) }
  catch { redisInfo.value = null }
  finally { infoLoading.value = false }
}

async function loadSlowlog() {
  if (!activeId.value) return
  try {
    const r = await api.redisSlowlog(activeId.value, 25, 0)
    slowlog.value = r.entries || []
  } catch { slowlog.value = [] }
}

function parseKsField(ks, field) {
  // redis-py 把 keyspace 解析为对象 {keys, expires, avg_ttl}；
  // 兼容原始字符串 "keys=16,expires=14,avg_ttl=0" 两种格式
  if (ks == null) return '-'
  if (typeof ks === 'object') {
    const v = ks[field]
    return v == null ? '-' : String(v)
  }
  const m = String(ks).match(new RegExp(`${field}=(\\d+)`))
  return m ? m[1] : '-'
}

function formatSlowTs(ts) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString()
}

// ── 命令台 ────────────────────────────────────────────────────────────────────
// ── 命令台（完整重写）────────────────────────────────────────────────────────
const consoleDb      = ref(0)
const consoleCmd     = ref('')

// ── AI 翻译（dbx 风格）─────────────────────────────────
const aiQuery = ref('')
const aiTranslating = ref(false)
const aiResult = ref(null)
async function aiTranslate() {
  if (!aiQuery.value.trim()) return
  aiTranslating.value = true
  aiResult.value = null
  try {
    const r = await fetch('/api/ai/translate', {
      method: 'POST', credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scene: 'redis', query: aiQuery.value,
        context: { db: consoleDb.value, current_keys_pattern: keyPattern.value || '*' },
      }),
    })
    if (!r.ok) throw new Error('translate failed: ' + r.status)
    aiResult.value = await r.json()
  } catch (e) {
    aiResult.value = { command: '', explain: '', risk: 'medium', risk_reason: 'AI 调用失败：' + e }
  } finally {
    aiTranslating.value = false
  }
}
const consoleRunning = ref(false)
const consoleSession = ref([])    // 当前会话的命令+结果序列
const cmdHistoryAll  = ref([])    // 历史命令列表（仅命令，用于↑↓导航）
const historyIdx     = ref(-1)    // 当前历史游标
const conOutputRef   = ref(null)
const conInputRef    = ref(null)

const CONSOLE_PRESET_GROUPS = [
  {
    label: '服务器',
    cmds: ['INFO server', 'INFO clients', 'INFO memory', 'INFO stats', 'INFO replication', 'INFO all'],
  },
  {
    label: '数据',
    cmds: ['DBSIZE', 'KEYS *', 'RANDOMKEY', 'SCAN 0 COUNT 20', 'TYPE key', 'TTL key', 'PERSIST key'],
  },
  {
    label: '字符串',
    cmds: ['GET key', 'MGET k1 k2', 'STRLEN key', 'INCR key'],
  },
  {
    label: '哈希',
    cmds: ['HGETALL key', 'HKEYS key', 'HVALS key', 'HLEN key'],
  },
  {
    label: '列表',
    cmds: ['LLEN key', 'LRANGE key 0 -1', 'LINDEX key 0'],
  },
  {
    label: '集合',
    cmds: ['SMEMBERS key', 'SCARD key', 'SRANDMEMBER key'],
  },
  {
    label: '有序集',
    cmds: ['ZRANGE key 0 -1 WITHSCORES', 'ZCARD key', 'ZSCORE key member'],
  },
  {
    label: '管理',
    cmds: ['CLIENT LIST', 'CLIENT INFO', 'CONFIG GET maxmemory', 'CONFIG GET save', 'SLOWLOG GET 10', 'LATENCY LATEST'],
  },
]

// 判断结果类型，用于着色
function detectResultType(v) {
  if (v === null || v === undefined) return 'nil'
  if (typeof v === 'number' || (typeof v === 'string' && /^-?\d+$/.test(v.trim()))) return 'integer'
  if (typeof v === 'string') return 'string'
  if (Array.isArray(v)) return 'array'
  if (typeof v === 'object') return 'object'
  return 'string'
}

// 结果 → 带语法着色的 HTML
function colorizeResult(v, rtype) {
  if (v === null || v === undefined) return '<span class="r-nil">(nil)</span>'

  if (rtype === 'integer')
    return `<span class="r-num">(integer) ${v}</span>`

  if (rtype === 'string') {
    const escaped = String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    return `<span class="r-str">"${escaped}"</span>`
  }

  if (rtype === 'array') {
    const arr = Array.isArray(v) ? v : [v]
    if (!arr.length) return '<span class="r-nil">(empty array)</span>'
    const lines = arr.map((item, i) => {
      const idx = `<span class="r-idx">${i + 1})</span>`
      if (item === null) return `${idx} <span class="r-nil">(nil)</span>`
      const safe = String(item).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      return `${idx} <span class="r-str">"${safe}"</span>`
    })
    return lines.join('\n')
  }

  if (rtype === 'object') {
    try {
      const json = JSON.stringify(v, null, 2)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
        .replace(/"([^"]+)":/g, '<span class="r-key">"$1"</span>:')
        .replace(/: "([^"]*)"/g, ': <span class="r-str">"$1"</span>')
        .replace(/: (-?\d+)/g, ': <span class="r-num">$1</span>')
        .replace(/: (true|false)/g, ': <span class="r-bool">$1</span>')
        .replace(/: (null)/g, ': <span class="r-nil">$1</span>')
      return json
    } catch {
      return String(v)
    }
  }

  return String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

function resultToText(v) {
  if (v === null || v === undefined) return '(nil)'
  if (typeof v === 'object') return JSON.stringify(v, null, 2)
  return String(v)
}

async function runConsoleCmd() {
  const cmd = consoleCmd.value.trim()
  if (!cmd || consoleRunning.value || !activeId.value) return

  consoleRunning.value = true
  const t0 = Date.now()

  // 保存到历史（去重，最新在末尾）
  const existIdx = cmdHistoryAll.value.indexOf(cmd)
  if (existIdx >= 0) cmdHistoryAll.value.splice(existIdx, 1)
  cmdHistoryAll.value.push(cmd)
  if (cmdHistoryAll.value.length > 200) cmdHistoryAll.value.shift()
  historyIdx.value = -1
  consoleCmd.value = ''

  let entry = null
  try {
    const r = await api.redisCommand(activeId.value, { command: cmd, db: consoleDb.value })
    const ms = Date.now() - t0
    const ok = r.ok !== false
    const rtype = ok ? detectResultType(r.result) : 'error'
    const resultText = ok ? resultToText(r.result) : (r.error || '未知错误')
    const dbUsed = r.db_used ?? consoleDb.value
    entry = {
      cmd,
      db: dbUsed,
      ok, ms, rtype,
      resultText,
      resultHtml: ok
        ? colorizeResult(r.result, rtype)
        : `<span class="r-err">(error) ${esc(r.error || '未知错误')}</span>`,
    }
  } catch (e) {
    // axios 拦截器会把错误信息作为字符串 reject
    const errMsg = typeof e === 'string' ? e : (e?.message || String(e))
    const isNotFound = errMsg.toLowerCase().includes('not found') || errMsg === '404'
    entry = {
      cmd, db: consoleDb.value, ok: false,
      ms: Date.now() - t0, rtype: 'error',
      resultText: errMsg,
      resultHtml: isNotFound
        ? `<span class="r-err">(error) 接口未找到，请重启后端服务后重试</span>`
        : `<span class="r-err">(error) ${esc(errMsg)}</span>`,
    }
  } finally {
    consoleRunning.value = false
    if (entry) consoleSession.value.push(entry)
    await nextTick()
    scrollConToBottom()
    conInputRef.value?.focus()
  }
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

function scrollConToBottom() {
  if (conOutputRef.value) {
    conOutputRef.value.scrollTop = conOutputRef.value.scrollHeight
  }
}

function historyUp() {
  const len = cmdHistoryAll.value.length
  if (!len) return
  if (historyIdx.value < len - 1) historyIdx.value++
  consoleCmd.value = cmdHistoryAll.value[len - 1 - historyIdx.value] || ''
}

function historyDown() {
  if (historyIdx.value <= 0) {
    historyIdx.value = -1
    consoleCmd.value = ''
    return
  }
  historyIdx.value--
  const len = cmdHistoryAll.value.length
  consoleCmd.value = cmdHistoryAll.value[len - 1 - historyIdx.value] || ''
}

function clearConsoleSession() {
  consoleSession.value = []
  consoleCmd.value = ''
  historyIdx.value = -1
  conInputRef.value?.focus()
}

function fillConsoleCmdAndFocus(cmd) {
  consoleCmd.value = cmd
  nextTick(() => conInputRef.value?.focus())
}

async function copyText(text) {
  try { await navigator.clipboard.writeText(text || '') } catch {}
}

onMounted(async () => {
  await loadClusters()
  if (activeId.value) await loadOverview(activeId.value, { force: true })
})
</script>

<style scoped>
.redis-view {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  background:
    radial-gradient(circle at top right, rgba(220, 38, 38, 0.07), transparent 30%),
    radial-gradient(circle at top left, rgba(251, 146, 60, 0.08), transparent 22%),
    var(--bg-base);
}

.cluster-bar {
  height: 46px;
  display: flex;
  align-items: stretch;
  border-bottom: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.92);
  overflow-x: auto;
}

.cb-logo {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
  border-right: 1px solid var(--border);
  font-weight: 700;
  color: var(--text-primary);
  white-space: nowrap;
}

.cb-logo-icon {
  width: 24px;
  height: 24px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #ef4444, #f97316);
  color: #fff;
  font-size: 13px;
}

.cluster-tab,
.cb-add {
  border: none;
  background: transparent;
  cursor: pointer;
}

.cluster-tab {
  min-width: 156px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  border-right: 1px solid var(--border);
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
}

.cluster-tab.active {
  background: rgba(255, 255, 255, 0.84);
  border-bottom-color: #dc2626;
  color: var(--text-primary);
}

.ct-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ct-dot.ok {
  background: var(--success);
}

.ct-dot.warn {
  background: #f59e0b;
}

.ct-dot.danger {
  background: var(--error);
}

.ct-name {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
  gap: 6px;
}

.ct-env {
  font-size: 9px;
  padding: 1px 4px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.14);
}

.env-prod {
  color: var(--error);
}

.env-uat {
  color: #b45309;
}

.env-sit {
  color: var(--accent);
}

.env-dev {
  color: #7c3aed;
}

.ct-close {
  opacity: 0;
  color: var(--text-muted);
}

.cluster-tab:hover .ct-close {
  opacity: 1;
}

.cb-add {
  padding: 0 16px;
  font-size: 22px;
  color: var(--text-muted);
}

.cb-add:hover {
  color: #dc2626;
}

.page-shell {
  flex: 1; display: flex; overflow: hidden; min-height: 0;
}

/* 左侧导航 */
.side-nav {
  width: 160px; flex-shrink: 0; overflow-y: auto;
  background: var(--bg-card); border-right: 1px solid var(--border);
  display: flex; flex-direction: column; padding: 8px 0;
}
.sn-cluster-name {
  font-size: 12px; font-weight: 600; color: var(--text-primary);
  padding: 8px 14px 6px; border-bottom: 1px solid var(--border);
  margin-bottom: 6px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sn-section {
  font-size: 10px; font-weight: 600; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: .05em;
  padding: 8px 14px 3px;
}
.sn-item {
  display: flex; align-items: center; gap: 7px;
  padding: 7px 14px; cursor: pointer; font-size: 12.5px;
  color: var(--text-secondary); border: none; background: transparent;
  text-align: left; border-left: 2px solid transparent; transition: .1s;
}
.sn-item:hover { background: var(--bg-hover); color: var(--text-primary); }
.sn-item.active { background: var(--accent-dim); color: var(--accent); border-left-color: var(--accent); font-weight: 500; }
.sn-icon { width: 16px; text-align: center; font-size: 13px; }

/* 主内容区 */
.main-pane {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
}
.page-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0;
  background: var(--bg-card);
}
.page-title { font-size: 14px; font-weight: 600; }
.page-sub   { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.head-actions { display: flex; align-items: center; gap: 7px; }
.db-select { padding: 4px 8px; font-size: 12px; border-radius: 5px; border: 1px solid var(--border); background: var(--bg-input); color: var(--text-primary); }

/* Key 浏览 */
.keys-pane  { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.keys-toolbar { display: flex; align-items: center; gap: 8px; padding: 8px 14px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.keys-search { flex: 1; padding: 5px 10px; font-size: 12px; border-radius: 5px; border: 1px solid var(--border); background: var(--bg-input); color: var(--text-primary); font-family: monospace; }
.keys-hint   { font-size: 11px; color: var(--text-muted); white-space: nowrap; }
.keys-body   { flex: 1; display: flex; overflow: hidden; min-height: 0; }
.key-list-wrap   { width: 280px; flex-shrink: 0; overflow-y: auto; border-right: 1px solid var(--border); }
.key-detail-wrap { flex: 1; overflow-y: auto; padding: 12px 14px; }
.key-row  { display: flex; align-items: center; gap: 7px; padding: 7px 12px; cursor: pointer; border-bottom: 1px solid rgba(0,0,0,.04); font-size: 12px; }
.key-row:hover  { background: var(--bg-hover); }
.key-row.active { background: var(--accent-dim); }
.key-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: monospace; }
.key-ttl  { font-size: 10px; color: var(--text-muted); flex-shrink: 0; }
.ttl-perm { color: var(--success, #22c55e); }
.ttl-soon { color: var(--error); font-weight: 600; }
.key-type-badge { font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 3px; flex-shrink: 0; }
.ktype-string { background: rgba(59,130,246,.12); color: var(--accent); }
.ktype-hash   { background: rgba(168,85,247,.12); color: #a855f7; }
.ktype-list   { background: rgba(34,197,94,.12);  color: #22c55e; }
.ktype-set    { background: rgba(249,115,22,.12); color: #f97316; }
.ktype-zset   { background: rgba(234,179,8,.12);  color: #eab308; }
.ktype-stream { background: rgba(6,182,212,.12);  color: #06b6d4; }
.kd-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.kd-name   { font-family: monospace; font-size: 13px; font-weight: 600; flex: 1; overflow-wrap: break-word; }
.kd-ttl    { font-size: 11px; color: var(--text-muted); }
.kd-meta   { font-size: 11px; color: var(--text-muted); margin-bottom: 8px; }
.ttl-input { width: 100px; padding: 4px 7px; font-size: 12px; border-radius: 5px; border: 1px solid var(--border); background: var(--bg-input); color: var(--text-primary); }
.kd-value { background: var(--bg-input); padding: 10px; border-radius: 7px; font-size: 12px; overflow-wrap: break-word; white-space: pre-wrap; max-height: 400px; overflow-y: auto; }
.kd-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.kd-table th { padding: 5px 8px; border-bottom: 1px solid var(--border); color: var(--text-muted); text-align: left; }
.kd-table td { padding: 5px 8px; border-bottom: 1px solid rgba(0,0,0,.04); }
.kd-field { color: var(--accent); }
.kd-set   { display: flex; flex-wrap: wrap; gap: 6px; }
.set-member { padding: 2px 8px; background: var(--bg-input); border-radius: 4px; font-size: 12px; font-family: monospace; }
.kd-stream { display: flex; flex-direction: column; gap: 8px; }
.stream-entry { background: var(--bg-input); border-radius: 6px; padding: 7px 10px; font-size: 12px; }
.stream-id    { font-family: monospace; color: var(--accent); margin-right: 8px; }
.stream-field { margin-right: 12px; }
.stream-field em { color: var(--text-muted); font-style: normal; }

/* 监控 */
.monitor-pane  { flex: 1; overflow-y: auto; padding: 14px 16px; display: flex; flex-direction: column; gap: 14px; }
.info-kpi-row  { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }
.info-kpi      { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
.info-kpi span { display: block; font-size: 11px; color: var(--text-muted); margin-bottom: 3px; }
.info-kpi strong { font-size: 14px; font-weight: 700; }
.info-kpi.tone-warn strong { color: var(--warning); }
.info-section  { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }
.info-sec-title { font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 10px; display: flex; align-items: center; }
.info-kv-grid  { display: grid; grid-template-columns: 200px 1fr; gap: 4px 12px; font-size: 12px; }
.info-k { color: var(--text-muted); }
.info-v { font-family: monospace; }
.info-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.info-table th { padding: 5px 8px; border-bottom: 1px solid var(--border); color: var(--text-muted); text-align: left; font-weight: 500; }
.info-table td { padding: 5px 8px; border-bottom: 1px solid rgba(0,0,0,.04); }
.val-err  { color: var(--error); font-weight: 600; }
.val-warn { color: var(--warning); }
.empty-state.sm { font-size: 12px; padding: 8px 0; }

/* ══ 命令台 ══ */
.console-pane { flex: 1; display: flex; flex-direction: column; overflow: hidden; background: #0d1117; color: #c9d1d9; }

/* 顶部工具栏 */
.con-topbar { flex-shrink: 0; background: #161b22; border-bottom: 1px solid #30363d; padding: 8px 12px; display: flex; flex-direction: column; gap: 6px; }
.con-db-row { display: flex; align-items: center; gap: 8px; }
.con-label  { font-size: 11px; color: #8b949e; }
.con-db-sel { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; border-radius: 4px; padding: 2px 6px; font-size: 12px; cursor: pointer; }
.con-cluster-info { font-size: 11px; color: #58a6ff; margin-left: 6px; }

/* 预设命令分组 */
.con-preset-groups { display: flex; flex-wrap: wrap; gap: 8px; }
.preset-group { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.preset-group-label { font-size: 10px; color: #8b949e; font-weight: 600; text-transform: uppercase; letter-spacing: .05em; white-space: nowrap; padding: 2px 4px; }
.preset-chip { padding: 2px 8px; font-size: 11px; border-radius: 4px; border: 1px solid #30363d; background: #21262d; color: #8b949e; cursor: pointer; font-family: monospace; transition: .1s; white-space: nowrap; }
.preset-chip:hover { border-color: #58a6ff; color: #58a6ff; }

/* 终端输出区 */
.con-output { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 12px; }
.con-output::-webkit-scrollbar { width: 6px; }
.con-output::-webkit-scrollbar-track { background: #0d1117; }
.con-output::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }

/* 欢迎屏 */
.con-welcome { text-align: center; padding: 40px 0; }
.con-welcome-title { font-size: 18px; font-weight: 700; color: #58a6ff; margin-bottom: 6px; }
.con-welcome-sub   { font-size: 13px; color: #8b949e; margin-bottom: 4px; }
.con-welcome-hint  { font-size: 11px; color: #484f58; }

/* 每条命令+结果 */
.con-entry { display: flex; flex-direction: column; gap: 4px; }
.con-cmd-line { display: flex; align-items: center; gap: 6px; }
.con-prompt   { color: #3fb950; font-size: 12px; font-family: monospace; flex-shrink: 0; }
.con-cmd-text { color: #e6edf3; font-family: monospace; font-size: 13px; flex: 1; word-break: break-all; }
.con-copy-btn { opacity: 0; color: #484f58; font-size: 12px; cursor: pointer; padding: 1px 4px; border-radius: 3px; flex-shrink: 0; transition: .1s; }
.con-entry:hover .con-copy-btn { opacity: 1; }
.con-copy-btn:hover { background: #30363d; color: #c9d1d9; }

/* 结果块 */
.con-result-block { background: #161b22; border-radius: 6px; border-left: 3px solid; padding: 7px 10px; }
.con-result-block.res-ok  { border-left-color: #3fb950; }
.con-result-block.res-err { border-left-color: #f85149; }
.con-result-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.con-type-badge { font-size: 10px; font-weight: 700; padding: 1px 5px; border-radius: 3px; }
.rtype-nil     { background: rgba(139,148,158,.15); color: #8b949e; }
.rtype-integer { background: rgba(249,196,74,.12);  color: #e3b341; }
.rtype-string  { background: rgba(63,185,80,.12);   color: #3fb950; }
.rtype-array   { background: rgba(88,166,255,.12);  color: #58a6ff; }
.rtype-object  { background: rgba(188,121,247,.12); color: #bc8cff; }
.rtype-error   { background: rgba(248,81,73,.12);   color: #f85149; }
.con-dur { font-size: 10px; color: #484f58; }
.con-result-pre { font-family: 'Consolas','Monaco','Courier New',monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all; line-height: 1.6; margin: 0; color: #c9d1d9; }

/* 结果着色 token */
.con-result-pre :deep(.r-nil)  { color: #8b949e; }
.con-result-pre :deep(.r-num)  { color: #e3b341; }
.con-result-pre :deep(.r-str)  { color: #3fb950; }
.con-result-pre :deep(.r-err)  { color: #f85149; }
.con-result-pre :deep(.r-key)  { color: #58a6ff; }
.con-result-pre :deep(.r-bool) { color: #79c0ff; }
.con-result-pre :deep(.r-idx)  { color: #484f58; min-width: 28px; display: inline-block; text-align: right; margin-right: 6px; }

/* 执行中指示 */
.con-running { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #8b949e; padding: 6px 0; }

/* 输入区 */
.con-input-wrap { flex-shrink: 0; display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-top: 1px solid #30363d; background: #161b22; }

/* AI 翻译条 */
.ai-translate-bar {
  flex-shrink: 0; display: flex; align-items: center; gap: 8px;
  padding: 10px 14px; border-top: 1px solid #30363d;
  background: rgba(217,119,87,.06);
}
.ai-spark { color: var(--accent); font-size: 14px; }
.ai-translate-input {
  flex: 1; background: rgba(0,0,0,.18); border: 1px solid rgba(217,119,87,.28);
  border-radius: 8px; padding: 6px 12px;
  font-size: 12.5px; color: inherit; outline: none;
}
.ai-translate-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(217,119,87,.18); }
.ai-result {
  margin: 0 14px 6px; padding: 10px 12px;
  border-radius: 8px; background: var(--bg-card); border: 1px solid var(--border);
  font-size: 12.5px; display: flex; flex-direction: column; gap: 5px;
}
.ai-result.risk-medium { border-color: rgba(197,138,70,.5); background: rgba(197,138,70,.06); }
.ai-result.risk-high { border-color: rgba(189,86,79,.5); background: rgba(189,86,79,.08); }
.ai-result-cmd { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ai-result-label { font-size: 11px; color: var(--text-muted); }
.ai-result-cmd code {
  flex: 1; min-width: 0; padding: 4px 8px; border-radius: 6px;
  background: rgba(0,0,0,.18); font-family: var(--font-mono); font-size: 12px;
  color: var(--text-primary); word-break: break-all; white-space: pre-wrap;
}
.ai-result-explain { color: var(--text-secondary); font-size: 12px; line-height: 1.55; }
.ai-result-risk { color: var(--error); font-size: 11.5px; }
.spinner-mini { display: inline-block; width: 10px; height: 10px; margin-right: 4px;
  border: 1.5px solid rgba(255,255,255,.4); border-top-color: #fff;
  border-radius: 50%; animation: spin .7s linear infinite; vertical-align: -1px; }
.con-prompt-static { color: #3fb950; font-family: monospace; font-size: 13px; flex-shrink: 0; }
.con-input { flex: 1; background: transparent; border: none; outline: none; color: #e6edf3; font-family: 'Consolas','Monaco',monospace; font-size: 13px; caret-color: #58a6ff; }
.con-input::placeholder { color: #484f58; }
.con-input-actions { display: flex; gap: 5px; flex-shrink: 0; }
.con-btn-run { padding: 4px 10px; font-size: 12px; border-radius: 5px; border: 1px solid #238636; background: rgba(35,134,54,.15); color: #3fb950; cursor: pointer; transition: .1s; }
.con-btn-run:hover:not(:disabled) { background: rgba(35,134,54,.3); }
.con-btn-run:disabled { opacity: .4; cursor: not-allowed; }
.con-btn-clear { padding: 4px 9px; font-size: 12px; border-radius: 5px; border: 1px solid #30363d; background: transparent; color: #8b949e; cursor: pointer; }
.con-btn-clear:hover { border-color: #8b949e; color: #c9d1d9; }

.loading-row { display: flex; align-items: center; gap: 8px; padding: 20px; font-size: 12px; color: var(--text-muted); }

/* 概览页的 KPI/grid 改为内嵌 main-pane */
.kpi-grid  { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; padding: 14px 16px; flex-shrink: 0; }
.main-grid { padding: 14px 16px; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; flex: 1; }

.card {
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 20px;
  box-shadow: 0 18px 38px rgba(15, 23, 42, 0.05);
}

.welcome {
  min-height: 420px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  text-align: center;
}

.welcome-mark {
  width: 72px;
  height: 72px;
  border-radius: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  font-weight: 800;
  background: linear-gradient(135deg, #ef4444, #f97316);
  color: #fff;
  box-shadow: 0 20px 38px rgba(239, 68, 68, 0.2);
}

.welcome h1 {
  font-size: 28px;
  color: var(--text-primary);
}

.welcome p {
  max-width: 560px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 22px;
  background:
    linear-gradient(135deg, rgba(254, 242, 242, 0.95), rgba(255, 255, 255, 0.98)),
    #fff;
}

.hero-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(220, 38, 38, 0.08);
  color: #b91c1c;
  font-size: 12px;
  font-weight: 700;
}

.hero-badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ef4444;
}

.hero-title-row {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.hero-title-row h1 {
  font-size: 30px;
  color: var(--text-primary);
}

.hero-subtitle {
  margin-top: 10px;
  max-width: 760px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.state-pill,
.card-meta,
.filter-pill,
.role-tag,
.status-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.state-pill {
  height: 30px;
  padding: 0 12px;
}

.state-pill.ok,
.status-badge.ok,
.kpi.ok {
  background: rgba(34, 197, 94, 0.12);
  color: var(--success);
}

.state-pill.warn,
.status-badge.warn,
.kpi.warn {
  background: rgba(245, 158, 11, 0.12);
  color: #b45309;
}

.state-pill.danger,
.status-badge.danger,
.kpi.danger {
  background: rgba(239, 68, 68, 0.12);
  color: var(--error);
}

.kpi.info {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.98));
  color: inherit;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.kpi {
  padding: 18px;
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.9);
}

.kpi-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.kpi-value {
  margin-top: 8px;
  font-size: 30px;
  line-height: 1.1;
  font-weight: 800;
  color: var(--text-primary);
}

.kpi-hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.alert {
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 13px;
  font-weight: 600;
}

.alert-success {
  background: rgba(34, 197, 94, 0.08);
  border: 1px solid rgba(34, 197, 94, 0.2);
  color: var(--success);
}

.alert-error {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.2);
  color: var(--error);
}

.loading-card {
  min-height: 220px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(148, 163, 184, 0.3);
  border-top-color: #ef4444;
  border-radius: 50%;
  animation: spin .7s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
  gap: 16px;
}

.summary-card,
.shard-card,
.table-card {
  padding: 18px;
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.card-head h3 {
  font-size: 16px;
  color: var(--text-primary);
}

.card-head p {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 13px;
}

.card-meta {
  height: 28px;
  padding: 0 10px;
  background: rgba(148, 163, 184, 0.12);
  color: var(--text-secondary);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.summary-item {
  padding: 14px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(255, 255, 255, 0.98));
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.9);
}

.summary-item span {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
}

.summary-item strong {
  display: block;
  margin-top: 8px;
  font-size: 22px;
  color: var(--text-primary);
}

.slot-panel {
  margin-top: 18px;
  padding: 16px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 247, 237, 0.96), rgba(255, 255, 255, 0.98));
  box-shadow: inset 0 0 0 1px rgba(253, 186, 116, 0.2);
}

.slot-head,
.slot-legend,
.shard-top,
.table-tools,
.modal-footer,
.footer-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.slot-head strong {
  font-size: 22px;
  color: var(--text-primary);
}

.slot-bar {
  margin-top: 12px;
  height: 12px;
  border-radius: 999px;
  overflow: hidden;
  display: flex;
  background: rgba(226, 232, 240, 0.9);
}

.slot-bar span {
  height: 100%;
}

.slot-ok {
  background: linear-gradient(90deg, #ef4444, #f97316);
}

.slot-pfail {
  background: #f59e0b;
}

.slot-fail {
  background: #b91c1c;
}

.slot-legend {
  margin-top: 10px;
  color: var(--text-secondary);
  font-size: 12px;
}

.shard-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.shard-item {
  padding: 14px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(255, 255, 255, 0.98));
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.9);
}

.shard-top strong {
  color: var(--text-primary);
}

.shard-top span,
.shard-ranges {
  color: var(--text-secondary);
  font-size: 12px;
}

.shard-ranges {
  margin-top: 6px;
  line-height: 1.6;
}

.shard-members {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.shard-member {
  display: inline-flex;
  align-items: center;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.shard-member.master,
.role-tag.master {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.shard-member.replica,
.role-tag.replica {
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
}

.table-tools {
  flex-wrap: wrap;
}

.filter-pill {
  height: 30px;
  padding: 0 12px;
  border: none;
  background: rgba(226, 232, 240, 0.7);
  color: var(--text-secondary);
  cursor: pointer;
}

.filter-pill.active {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.table-wrap {
  overflow: auto;
}

.table {
  width: 100%;
  border-collapse: collapse;
}

.table th,
.table td {
  padding: 12px 10px;
  border-bottom: 1px solid var(--border-light);
  vertical-align: middle;
}

.table th {
  text-align: left;
  color: var(--text-secondary);
  font-size: 12px;
}

.table tbody tr:hover td {
  background: rgba(148, 163, 184, 0.04);
}

.table tbody tr.warn td {
  background: rgba(245, 158, 11, 0.04);
}

.table tbody tr.fail td {
  background: rgba(239, 68, 68, 0.05);
}

.empty-cell,
.empty-block {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary);
}

.status-badge {
  height: 26px;
  padding: 0 10px;
}

.mono {
  font-family: 'Cascadia Code', 'Consolas', monospace;
}

.muted {
  color: var(--text-secondary);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 40px;
  padding: 0 16px;
  border-radius: 12px;
  border: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
}

.btn-primary {
  background: linear-gradient(135deg, #ef4444, #f97316);
  color: #fff;
  box-shadow: 0 12px 28px rgba(239, 68, 68, 0.18);
}

.btn-outline {
  background: rgba(255, 255, 255, 0.85);
  color: var(--text-primary);
  box-shadow: inset 0 0 0 1px rgba(226, 232, 240, 0.9);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  z-index: 1000;
}

.modal {
  width: 560px;
  max-width: 100%;
  max-height: 90vh;
  overflow: auto;
  padding: 22px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 28px 60px rgba(15, 23, 42, 0.18);
}

.modal-title {
  font-size: 18px;
  font-weight: 800;
  color: var(--text-primary);
  margin-bottom: 16px;
}

.form-row {
  display: flex;
  gap: 12px;
}

.form-group {
  margin-bottom: 14px;
}

.form-group.grow {
  flex: 1;
}

.form-group.narrow {
  width: 120px;
}

.form-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
}

.form-input,
.form-textarea {
  width: 100%;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.9);
  color: var(--text-primary);
  font-size: 13px;
  padding: 10px 12px;
  outline: none;
}

.form-textarea {
  resize: vertical;
  min-height: 110px;
}

.form-input:focus,
.form-textarea:focus {
  border-color: rgba(239, 68, 68, 0.45);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.08);
}

.form-readonly {
  min-height: 44px;
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(226, 232, 240, 0.9);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.6;
}

.form-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

@media (max-width: 1180px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .main-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 860px) {
  .page-shell {
    padding: 12px;
  }

  .hero {
    flex-direction: column;
  }

  .hero-actions,
  .summary-grid,
  .form-row,
  .kpi-grid {
    grid-template-columns: 1fr;
  }

  .hero-actions,
  .form-row {
    display: flex;
    flex-direction: column;
  }

  .form-group.narrow {
    width: auto;
  }
}
</style>
