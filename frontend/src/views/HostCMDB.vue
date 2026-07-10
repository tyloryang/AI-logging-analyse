<template>
  <div class="cmdb-page">
    <!-- 顶部统计 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-val">{{ hosts.length }}</div>
        <div class="stat-label">主机总数</div>
      </div>
      <div class="stat-card ok">
        <div class="stat-val">{{ countByStatus('active') }}</div>
        <div class="stat-label">在线</div>
      </div>
      <div class="stat-card warn">
        <div class="stat-val">{{ countByStatus('maintenance') }}</div>
        <div class="stat-label">维护中</div>
      </div>
      <div class="stat-card error">
        <div class="stat-val">{{ countByStatus('offline') }}</div>
        <div class="stat-label">离线</div>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <div class="tab-group">
          <button class="tab-btn" :class="{ active: tab === 'cmdb' }" @click="tab = 'cmdb'">
            主机 CMDB <span class="tab-count">{{ hosts.length }}</span>
          </button>
          <button class="tab-btn" :class="{ active: tab === 'inspect' }" @click="tab = 'inspect'">
            巡检报告 <span class="tab-count" :class="{ warn: inspectSummary.critical > 0 }">{{ inspectResults.length || inspectSummary.total || 0 }}</span>
          </button>
          <button class="tab-btn" :class="{ active: tab === 'groups' }" @click="tab = 'groups'">
            分组管理 <span class="tab-count">{{ groups.length }}</span>
          </button>
          <button class="tab-btn" :class="{ active: tab === 'credentials' }" @click="tab = 'credentials'">
            凭证管理 <span class="tab-count">{{ credentials.length }}</span>
          </button>
        </div>
      </div>
      <div class="toolbar-right">
        <template v-if="tab === 'cmdb'">
          <div class="filter-group" :title="search ? `搜索: ${search}` : '搜索主机名/IP/负责人'">
            <span class="filter-icon">🔍</span>
            <input v-model="search" class="search-input" placeholder="搜索..." />
          </div>
          <div class="filter-group" title="环境过滤">
            <span class="filter-icon">🏷️</span>
            <select v-model="envFilter" class="filter-select">
              <option value="">全部环境</option>
              <option value="production">生产</option>
              <option value="staging">预发</option>
              <option value="development">开发</option>
              <option value="testing">测试</option>
              <option value="dr">容灾</option>
            </select>
          </div>
          <div class="filter-group" title="分组过滤">
            <span class="filter-icon">📁</span>
            <select v-model="groupFilter" class="filter-select">
              <option value="">全部分组</option>
              <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
            </select>
          </div>
          <button class="btn btn-primary" @click="openAdd">+ 添加主机</button>
          <button class="btn btn-outline" @click="downloadExport" title="导出 Excel">📥 导出</button>
          <button class="btn btn-outline" @click="showImportModal = true" title="从 Excel/CSV 导入">📤 导入</button>
          <button class="btn btn-outline" @click="openBatchCred" title="批量为主机应用 SSH 凭证">🔑 批量应用凭证</button>
          <button class="btn btn-sync" :disabled="syncingAll" @click="runSyncAll" title="SSH 同步所有有凭证的主机">
            <span v-if="syncingAll" class="spinner" style="width:13px;height:13px;border-width:2px"></span>
            <span v-else>⟳</span> 一键同步
          </button>
        </template>
        <button class="btn btn-outline" @click="refreshActiveTab()" :disabled="loading">
          <span v-if="loading" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
          <span v-else>↺</span> 刷新
        </button>
        <!-- CMDB 内联巡检操作 -->
        <template v-if="tab === 'inspect'">
          <div class="filter-group" title="巡检范围">
            <span class="filter-icon">🎯</span>
            <select v-model="inspectGroupId" class="filter-select" :disabled="inspecting">
              <option value="">全部主机</option>
              <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}（{{ g.host_count || 0 }}台）</option>
            </select>
          </div>
          <button class="btn btn-primary" @click="runInspect" :disabled="inspecting || inspectAiStreaming">
            <span v-if="inspecting" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>🔍</span> {{ inspectGroupId ? '巡检此分组' : '执行巡检' }}
          </button>
          <button class="btn btn-ai" :disabled="!inspectResults.length || inspecting || inspectAiStreaming" @click="runInspectAI" title="先执行巡检生成报告后可用">
            <span v-if="inspectAiStreaming" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>🤖</span> AI分析
          </button>
          <button class="btn btn-outline" :disabled="!inspectResults.length || inspecting" @click="openInspectRca" title="先执行巡检生成报告后可用">
            <span>🧠</span> 进入 RCA
          </button>
          <button class="btn btn-outline"
            :disabled="notifyingGroups || !inspectResults.length || inspecting || !inspectGroupId || !groups.length" @click="notifyGroups()" title="选择分组并完成巡检后可推送">
            <span v-if="notifyingGroups" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>📤</span> 推送当前分组
          </button>
          <button class="btn btn-excel" :disabled="!inspectResults.length || inspecting || excelDownloading" @click="downloadInspectExcel" title="先执行巡检生成报告后可用">
            <span v-if="excelDownloading" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>📥</span> 下载 Excel
          </button>
        </template>
      </div>
    </div>

    <div class="content-row">
    <div class="content-main">

    <!-- CMDB 主机表 -->
    <div v-show="tab === 'cmdb'" class="cmdb-tab-wrap">
      <!-- 一键同步进度条 -->
      <div v-if="syncingAll || syncAllResult" class="sync-all-bar">
        <div v-if="syncingAll" class="sync-all-progress">
          <span class="sync-all-label">正在同步 {{ syncAllDone }}/{{ syncAllTotal }} 台...</span>
          <div class="progress-track"><div class="progress-fill" :style="{ width: syncAllTotal ? (syncAllDone/syncAllTotal*100)+'%' : '0%' }"></div></div>
          <span class="sync-all-stat">✅ {{ syncAllSuccess }} 成功 &nbsp; ❌ {{ syncAllFail }} 失败</span>
        </div>
        <div v-else class="sync-all-done" :class="syncAllFail > 0 ? 'warn' : 'ok'">
          {{ syncAllResult }}
          <button class="close-btn" style="margin-left:8px;font-size:12px" @click="syncAllResult=''">✕</button>
        </div>
      </div>
      <div class="table-wrap">
        <div v-if="loading && !hosts.length" class="empty-state">
          <div class="spinner"></div><p>加载主机列表...</p>
        </div>
        <div v-else-if="!hosts.length" class="empty-state">
          <span class="icon">🖥️</span>
          <p>暂无主机<br><small style="color:var(--text-muted)">点击「+ 添加主机」手动录入</small></p>
        </div>
        <table v-else class="host-table">
          <thead>
            <tr>
              <th class="select-col">
                <input type="checkbox" :checked="allVisibleSelected" :indeterminate.prop="someVisibleSelected" @change="toggleSelectAll" title="全选当前列表" />
              </th>
              <th>状态</th>
              <th class="th-sort" @click="setSort('hostname')">主机名<span class="sort-icon">{{ sortKey==='hostname'?(sortAsc?'↑':'↓'):'⇅'}}</span></th>
              <th class="th-sort" @click="setSort('ip')">IP<span class="sort-icon">{{ sortKey==='ip'?(sortAsc?'↑':'↓'):'⇅'}}</span></th>
              <th>平台</th>
              <th>操作系统</th>
              <th>配置</th>
              <th>运行状态</th>
              <th class="th-sort" @click="setSort('env')">环境<span class="sort-icon">{{ sortKey==='env'?(sortAsc?'↑':'↓'):'⇅'}}</span></th>
              <th>用途</th>
              <th>负责人</th>
              <th>机房</th>
              <th>分组</th>
              <th class="th-sort" @click="setSort('last_sync_at')">最新同步<span class="sort-icon">{{ sortKey==='last_sync_at'?(sortAsc?'↑':'↓'):'⇅'}}</span></th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="h in sortedHosts" :key="h.id" :class="{ 'row-selected': selectedHostIds.has(h.id) }" @click="selectHost(h)">
              <td class="select-col" @click.stop>
                <input type="checkbox" :checked="selectedHostIds.has(h.id)" @change="toggleHostSelected(h)" />
              </td>
              <td>
                <div class="status-cell">
                  <span class="status-line"><span class="status-dot" :class="h.status"></span><span class="status-text">{{ statusLabel(h.status) }}</span></span>
                  <span v-if="hostSyncState(h.id)?.statusMsg" class="field-sync" :class="syncStatusClass(h.id)">
                    {{ hostSyncState(h.id)?.statusMsg }}
                  </span>
                </div>
              </td>
              <td class="hostname-cell" :class="{ 'field-updated': isSyncedField(h.id, 'hostname') }">
                <div class="hostname-stack">
                  <span class="hostname-line">
                    <span class="hostname">{{ h.hostname }}</span>
                    <span v-if="h.ssh_saved" class="ssh-badge" title="已配置 SSH 凭证">SSH</span>
                  </span>
                </div>
              </td>
              <td class="mono">{{ h.ip }}</td>
              <td><span class="platform-badge" :class="h.platform?.toLowerCase()">{{ h.platform || '-' }}</span></td>
              <td class="small-text" :class="{ 'field-updated': isSyncedField(h.id, 'os_version') }">
                <div class="field-cell">{{ h.os_version || '-' }}</div>
              </td>
              <td class="small-text" :class="{ 'field-updated': isSyncedField(h.id, ['cpu_cores', 'memory_gb', 'disk_gb']) }">
                <div class="field-cell">
                  <span v-if="h.cpu_cores">{{ h.cpu_cores }}C</span>
                  <span v-if="h.cpu_cores && h.memory_gb"> / </span>
                  <span v-if="h.memory_gb">{{ h.memory_gb }}G</span>
                  <span v-if="!h.cpu_cores && !h.memory_gb">-</span>
                </div>
              </td>
              <td class="small-text" :class="{ 'field-updated': isSyncedField(h.id, runtimeSyncKeys) }">
                <div class="runtime-cell">
                  <span>CPU {{ pctText(h.cpu_usage_pct) }}</span>
                  <span>内存 {{ pctText(h.memory_usage_pct) }}</span>
                  <span>负载 {{ valueText(h.load5) }}</span>
                </div>
              </td>
              <td><span class="env-badge" :class="h.env">{{ envLabel(h.env) }}</span></td>
              <td class="small-text">{{ h.role || '-' }}</td>
              <td class="small-text">{{ h.owner || '-' }}</td>
              <td class="small-text">{{ h.datacenter || '-' }}</td>
              <td><span v-if="h.group && groupMap[h.group]" class="group-badge-inline">{{ groupMap[h.group] }}</span><span v-else>-</span></td>
              <td class="small-text sync-time-cell" :title="h.last_sync_at ? formatEast8DateTime(h.last_sync_at) : '从未同步'">
                <div v-if="h.last_sync_at" class="sync-time-stack">
                  <span :class="syncTimeClass(h.last_sync_at)">{{ formatEast8DateTime(h.last_sync_at) }}</span>
                  <span class="sync-time-relative">{{ relativeTime(h.last_sync_at) }}</span>
                </div>
                <span v-else class="no-sync">—</span>
              </td>
              <td class="action-cell" @click.stop>
                <button class="btn btn-outline btn-xs" @click="openEdit(h)" title="编辑">✏</button>
                <button class="btn btn-outline btn-xs" @click="openSSH(h)" title="SSH 连接">>_</button>
                <button class="btn btn-sync btn-xs" :disabled="syncingId === h.id" @click="syncHost(h)" title="同步系统信息">
                  <span v-if="syncingId === h.id" class="spinner" style="width:11px;height:11px;border-width:1.5px"></span>
                  <span v-else>⟳</span>
                </button>
                <button class="btn btn-danger btn-xs" @click="confirmDelete(h)" title="删除">✕</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 选中浮动操作栏 -->
      <transition name="batch-slide">
        <div v-if="selectedHostIds.size" class="cmdb-batch-bar">
          <span class="cb-count">已选 <strong>{{ selectedHostIds.size }}</strong> 台主机</span>
          <button class="btn-ghost btn-xs" @click="selectedHostIds = new Set(); selectedHostIds = new Set(selectedHostIds)">清空</button>
          <span class="cb-sep"></span>
          <select v-model="batchField.group" class="batch-select" @change="applyBatchField('group', batchField.group)">
            <option value="">改分组…</option>
            <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
          </select>
          <select v-model="batchField.env" class="batch-select" @change="applyBatchField('env', batchField.env)">
            <option value="">改环境…</option>
            <option value="production">生产</option>
            <option value="staging">预发</option>
            <option value="development">开发</option>
            <option value="testing">测试</option>
            <option value="dr">容灾</option>
          </select>
          <select v-model="batchField.status" class="batch-select" @change="applyBatchField('status', batchField.status)">
            <option value="">改状态…</option>
            <option value="active">在线</option>
            <option value="offline">离线</option>
            <option value="maintenance">维护中</option>
          </select>
          <button class="btn btn-outline btn-xs" @click="batchApplyCredential">批量绑定凭据</button>
          <button class="btn btn-outline btn-xs danger" @click="batchDeleteSelected">批量删除</button>
          <span v-if="batchRunning" class="spinner" style="width:13px;height:13px"></span>
          <span v-if="batchResult" class="cb-result">{{ batchResult }}</span>
        </div>
      </transition>
    </div>

    <!-- 巡检报告：与主机 CMDB 合并展示 -->
    <div
      v-show="tab === 'inspect'"
      class="inspect-wrap merged-inspect-wrap"
      :class="{ 'is-empty': !inspectResults.length && !inspecting && !inspectError }"
    >
      <div class="inspect-panel-head">
        <div>
          <div class="inspect-panel-title">巡检报告</div>
          <div class="inspect-panel-sub">基于 CMDB 主机和 Prometheus node_exporter 指标生成；无指标时自动连接服务器兜底获取状态</div>
        </div>
        <div v-if="inspectResults.length" class="inspect-panel-kpis">
          <span>正常 {{ inspectSummary.normal }}</span>
          <span>警告 {{ inspectSummary.warning }}</span>
          <span>严重 {{ inspectSummary.critical }}</span>
          <span>指标 {{ inspectSummary.metrics_updated_count || 0 }}</span>
        </div>
      </div>
      <div v-if="inspecting" class="empty-state"><div class="spinner"></div><p>巡检中，请稍候...</p></div>
      <div v-else-if="inspectError" class="empty-state">
        <span class="icon">⚠️</span><p style="color:var(--error)">{{ inspectError }}</p>
        <button class="btn btn-outline" style="margin-top:10px" @click="runInspect">重试</button>
      </div>
      <div v-else-if="!inspectResults.length" class="empty-state">
        <span class="icon">🔍</span><p>点击「执行巡检」开始<br><small style="color:var(--text-muted)">优先使用 Prometheus，缺失时 SSH/Python 兜底采集</small></p>
      </div>
      <div v-else style="flex:1;display:flex;flex-direction:column;overflow:hidden;min-height:0">
        <div class="inspect-scope-bar">
          <span class="inspect-scope-label">巡检范围：</span>
          <span class="inspect-scope-badge" :class="inspectSummary.group_id ? 'group' : 'all'">
            {{ inspectSummary.group_name || '全部主机' }}
          </span>
          <span class="inspect-scope-stat">共 {{ inspectSummary.total }} 台 · 正常 {{ inspectSummary.normal }} · 警告 {{ inspectSummary.warning }} · 严重 {{ inspectSummary.critical }} · 已更新指标 {{ inspectSummary.metrics_updated_count || 0 }} 台 · 兜底 {{ inspectSummary.metrics_fallback_count || 0 }} 台 · 未获取 {{ inspectSummary.metrics_missing_count || 0 }} 台</span>
        </div>
        <div v-if="inspectNotifyMessage" class="inspect-notify-msg" :class="inspectNotifyStatus">{{ inspectNotifyMessage }}</div>
        <div v-if="inspectAiSummary || inspectAiStreaming" class="inspect-ai-card" :class="{ streaming: inspectAiStreaming }">
          <div class="inspect-ai-header">
            <div>
              <div class="inspect-ai-title">
                <span v-if="inspectAiStreaming" class="ai-thinking-dot"></span>AI 分析总结
              </div>
              <div v-if="inspectAiProvider" class="inspect-ai-provider">模型：{{ inspectAiProvider }}</div>
            </div>
            <div style="display:flex;align-items:center;gap:8px">
              <span class="inspect-ai-badge" :class="{ fallback: inspectAiFallback, streaming: inspectAiStreaming }">
                {{ inspectAiStreaming ? '生成中...' : inspectAiFallback ? '规则兜底' : 'AI生成' }}
              </span>
              <button v-if="!inspectAiStreaming" class="ai-toggle-btn" @click="aiExpanded = !aiExpanded">{{ aiExpanded ? '▲ 收起' : '▼ 展开' }}</button>
            </div>
          </div>
          <div v-show="aiExpanded || inspectAiStreaming" class="inspect-ai-content">
            <span v-if="inspectAiSummary">{{ inspectAiSummary }}</span>
            <span v-else class="ai-placeholder">AI 正在分析...</span>
            <span v-if="inspectAiStreaming" class="ai-cursor"></span>
          </div>
        </div>
        <div class="inspect-table-wrap">
          <table class="inspect-table">
            <thead>
              <tr>
                <th class="th-sort" @click="setInspectSort('status')">状态<span class="sort-icon">{{ inspectSortIcon('status') }}</span></th>
                <th class="th-sort" @click="setInspectSort('hostname')">主机名<span class="sort-icon">{{ inspectSortIcon('hostname') }}</span></th>
                <th class="th-sort" @click="setInspectSort('ip')">IP<span class="sort-icon">{{ inspectSortIcon('ip') }}</span></th>
                <th class="th-sort" @click="setInspectSort('os')">系统<span class="sort-icon">{{ inspectSortIcon('os') }}</span></th>
                <th class="th-sort" @click="setInspectSort('cpu')">CPU 使用率<span class="sort-icon">{{ inspectSortIcon('cpu') }}</span></th>
                <th class="th-sort" @click="setInspectSort('cpu_cores')">CPU 核心<span class="sort-icon">{{ inspectSortIcon('cpu_cores') }}</span></th>
                <th class="th-sort" @click="setInspectSort('memory')">内存使用率<span class="sort-icon">{{ inspectSortIcon('memory') }}</span></th>
                <th class="th-sort" @click="setInspectSort('mem_total')">内存总量<span class="sort-icon">{{ inspectSortIcon('mem_total') }}</span></th>
                <th class="th-sort" @click="setInspectSort('load1')">负载 1m<span class="sort-icon">{{ inspectSortIcon('load1') }}</span></th>
                <th class="th-sort" @click="setInspectSort('load')">负载 5m<span class="sort-icon">{{ inspectSortIcon('load') }}</span></th>
                <th class="th-sort" @click="setInspectSort('load15')">负载 15m<span class="sort-icon">{{ inspectSortIcon('load15') }}</span></th>
                <th class="th-sort" @click="setInspectSort('uptime')">运行时长<span class="sort-icon">{{ inspectSortIcon('uptime') }}</span></th>
                <th class="th-sort" @click="setInspectSort('disk_mount')">磁盘挂载<span class="sort-icon">{{ inspectSortIcon('disk_mount') }}</span></th>
                <th class="th-sort" @click="setInspectSort('disk')">磁盘使用率<span class="sort-icon">{{ inspectSortIcon('disk') }}</span></th>
                <th class="th-sort" @click="setInspectSort('disk_size')">磁盘容量<span class="sort-icon">{{ inspectSortIcon('disk_size') }}</span></th>
                <th class="th-sort" @click="setInspectSort('network_rx')">网络入<span class="sort-icon">{{ inspectSortIcon('network_rx') }}</span></th>
                <th class="th-sort" @click="setInspectSort('network_tx')">网络出<span class="sort-icon">{{ inspectSortIcon('network_tx') }}</span></th>
                <th class="th-sort" @click="setInspectSort('disk_read')">磁盘读<span class="sort-icon">{{ inspectSortIcon('disk_read') }}</span></th>
                <th class="th-sort" @click="setInspectSort('disk_write')">磁盘写<span class="sort-icon">{{ inspectSortIcon('disk_write') }}</span></th>
                <th class="th-sort" @click="setInspectSort('tcp')">TCP 连接<span class="sort-icon">{{ inspectSortIcon('tcp') }}</span></th>
                <th class="th-sort" @click="setInspectSort('tcp_tw')">TIME_WAIT<span class="sort-icon">{{ inspectSortIcon('tcp_tw') }}</span></th>
                <th class="th-sort" @click="setInspectSort('issues')">异常项<span class="sort-icon">{{ inspectSortIcon('issues') }}</span></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in sortedInspectResults" :key="row.instance || row.ip" :class="'irow-'+row.overall">
                <td><span class="inspect-badge" :class="row.overall">{{ inspectStatusLabel(row.overall) }}</span></td>
                <td class="itd-host">
                  <div class="inspect-host-name">{{ row.hostname || row.instance || row.ip || '-' }}</div>
                  <div class="inspect-host-meta">{{ groupMap[row.group] || '未分组' }}</div>
                </td>
                <td class="mono itd-ip">{{ row.ip || '-' }}</td>
                <td class="inspect-plain-cell">{{ row.os || '-' }}</td>
                <td class="inspect-metric-cell compact">
                  <b :class="usageClass(inspectMetric(row, 'cpu_usage'))">{{ pctText(inspectMetric(row, 'cpu_usage')) }}</b>
                </td>
                <td class="inspect-metric-cell compact">
                  <b>{{ valueText(row.cpu_cores) }}</b>
                </td>
                <td class="inspect-metric-cell compact">
                  <b :class="usageClass(inspectMetric(row, 'mem_usage'))">{{ pctText(inspectMetric(row, 'mem_usage')) }}</b>
                </td>
                <td class="inspect-metric-cell compact">
                  <b>{{ gbText(inspectMetric(row, 'mem_total_gb') || row.memory_gb) }}</b>
                </td>
                <td class="inspect-metric-cell compact"><b>{{ valueText(inspectMetric(row, 'load1')) }}</b></td>
                <td class="inspect-metric-cell compact"><b>{{ valueText(inspectMetric(row, 'load5')) }}</b></td>
                <td class="inspect-metric-cell compact"><b>{{ valueText(inspectMetric(row, 'load15')) }}</b></td>
                <td class="inspect-metric-cell compact">
                  <b>{{ inspectUptimeText(row) }}</b>
                </td>
                <td class="inspect-plain-cell">
                  {{ highestDisk(row)?.mountpoint || highestDisk(row)?.mount || '-' }}
                </td>
                <td class="inspect-metric-cell compact">
                  <b :class="usageClass(highestDiskUsage(row))">{{ pctText(highestDiskUsage(row)) }}</b>
                </td>
                <td class="inspect-disk-cell">
                  <div v-if="highestDisk(row)" class="inspect-disk-line single">
                    <span>{{ gbText(highestDisk(row).used_gb) }} / {{ gbText(highestDisk(row).total_gb ?? highestDisk(row).size_gb) }}</span>
                  </div>
                  <span v-else class="check-na">-</span>
                </td>
                <td class="inspect-metric-cell compact"><b>{{ mbpsText(inspectMetric(row, 'net_recv_mbps')) }}</b></td>
                <td class="inspect-metric-cell compact"><b>{{ mbpsText(inspectMetric(row, 'net_send_mbps')) }}</b></td>
                <td class="inspect-metric-cell compact"><b>{{ mbpsText(inspectMetric(row, 'disk_read_mbps')) }}</b></td>
                <td class="inspect-metric-cell compact"><b>{{ mbpsText(inspectMetric(row, 'disk_write_mbps')) }}</b></td>
                <td class="inspect-metric-cell compact"><b>{{ valueText(inspectMetric(row, 'tcp_estab')) }}</b></td>
                <td class="inspect-metric-cell compact"><b>{{ valueText(inspectMetric(row, 'tcp_tw')) }}</b></td>
                <td class="inspect-issues-cell">
                  <template v-if="abnormalChecks(row).length">
                    <span v-for="check in abnormalChecks(row)" :key="check.item" class="check-cell" :class="check.status">
                      {{ check.item }} {{ check.value }}
                    </span>
                  </template>
                  <span v-else class="check-cell normal">全部正常</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 分组管理 -->
    <div v-show="tab === 'groups'" class="groups-wrap">
      <div class="groups-header">
        <button class="btn btn-primary" @click="openAddGroup">+ 新建分组</button>
      </div>
      <div v-if="!groups.length" class="empty-state"><span class="icon">🗂️</span><p>暂无分组，点击「新建分组」创建</p></div>
      <div v-else class="group-cards">
        <div v-for="g in groups" :key="g.id" class="group-card">
          <div class="group-card-header">
            <span class="group-name">{{ g.name }}</span>
            <div class="group-actions">
              <button class="btn btn-outline btn-xs" @click="openEditGroup(g)">编辑</button>
              <button class="btn btn-danger btn-xs" @click="deleteGroup(g)">删除</button>
            </div>
          </div>
          <div class="group-card-meta">
            <span class="group-meta-item">主机数：{{ g.host_count || 0 }}</span>
            <span v-if="g.feishu_webhook" class="group-meta-item ok">飞书 ✓</span>
            <span v-if="g.alert_matchers?.length" class="group-meta-item ok">告警路由 {{ g.alert_matchers.length }} 条</span>
            <span v-if="g.schedule_enabled" class="group-meta-item ok">定时 {{ g.schedule_time }}</span>
          </div>
          <div v-if="g.description" class="group-desc">{{ g.description }}</div>
          <div v-if="g.alert_matchers?.length" class="group-desc">
            告警标签：{{ formatAlertMatcherPreview(g.alert_matchers) }}
          </div>
        </div>
      </div>
    </div>

    <!-- 凭证管理 -->
    <div v-show="tab === 'credentials'" class="credentials-tab-wrap">
      <div class="credential-panel">
        <div class="credential-panel-head">
          <div>
            <div class="credential-panel-title">凭证管理录入</div>
            <div class="credential-panel-sub">维护可复用的 SSH 凭证，主机录入、批量绑定、巡检同步会直接引用凭证库。</div>
          </div>
          <div class="credential-kpis">
            <span>凭证 {{ credentials.length }}</span>
            <span>已绑定主机 {{ credentialBoundHostCount }}</span>
          </div>
        </div>

        <form class="credential-form-card" @submit.prevent="saveCredential">
          <div class="credential-form-title">{{ credentialEditId ? '编辑凭证' : '新增凭证' }}</div>
          <div class="credential-form-grid">
            <div class="form-group required">
              <label>凭证名称</label>
              <input v-model="credentialForm.name" placeholder="生产环境 root" />
            </div>
            <div class="form-group required">
              <label>用户名</label>
              <input v-model="credentialForm.username" placeholder="root" />
            </div>
            <div class="form-group required">
              <label>密码 <span class="form-hint">{{ credentialEditId ? '（留空保持不变）' : '' }}</span></label>
              <input v-model="credentialForm.password" type="password" :placeholder="credentialEditId ? '留空不修改' : '请输入密码'" autocomplete="new-password" />
            </div>
            <div class="form-group credential-port-field">
              <label>端口</label>
              <input v-model.number="credentialForm.port" type="number" min="1" max="65535" />
            </div>
            <div class="credential-form-actions">
              <button type="submit" class="btn btn-primary" :disabled="credentialSaving">
                <span v-if="credentialSaving" class="spinner" style="width:13px;height:13px;border-width:2px"></span>
                {{ credentialEditId ? '保存修改' : '新增凭证' }}
              </button>
              <button v-if="credentialEditId" type="button" class="btn btn-outline" @click="resetCredentialForm()">取消编辑</button>
            </div>
          </div>
          <div v-if="credentialError" class="form-error">{{ credentialError }}</div>
          <div v-if="credentialSuccess" class="import-result ok">{{ credentialSuccess }}</div>
        </form>

        <div class="credential-list-card">
          <div class="credential-list-head">
            <div>
              <div class="credential-list-title">凭证列表</div>
              <div class="credential-list-sub">删除已绑定凭证会同步清除主机上的凭证引用。</div>
            </div>
            <button class="btn btn-outline btn-xs" @click="loadCredentials">刷新凭证</button>
          </div>
          <div v-if="!credentials.length" class="empty-state credential-empty">
            <span class="icon">🔑</span>
            <p>暂无凭证<br><small style="color:var(--text-muted)">在上方录入第一条 SSH 凭证</small></p>
          </div>
          <div v-else class="credential-table-wrap">
            <table class="credential-table">
              <thead>
                <tr>
                  <th>凭证名称</th>
                  <th>用户名</th>
                  <th>端口</th>
                  <th>绑定主机</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="c in credentials" :key="c.id">
                  <td>
                    <div class="credential-name-cell">
                      <span class="credential-name">{{ c.name }}</span>
                      <span class="credential-id">{{ c.id }}</span>
                    </div>
                  </td>
                  <td>{{ c.username || 'root' }}</td>
                  <td>{{ c.port || 22 }}</td>
                  <td>
                    <span class="credential-bind-count" :class="{ empty: credentialUsageCount(c.id) === 0 }">
                      {{ credentialUsageCount(c.id) }} 台
                    </span>
                  </td>
                  <td>
                    <div class="credential-actions">
                      <button class="btn btn-outline btn-xs" @click="editCredential(c)">编辑</button>
                      <button class="btn btn-outline btn-xs" @click="openBatchWithCredential(c)">应用到主机</button>
                      <button class="btn btn-danger btn-xs" @click="deleteCredential(c)">删除</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    </div><!-- /content-main -->

    <!-- 右侧详情面板 -->
    <div v-if="tab === 'cmdb' && selectedHost" class="detail-panel">
      <div class="detail-header">
        <div class="detail-tabs">
          <button class="detail-tab" :class="{ active: detailTab === 'info' }" @click="detailTab='info'">信息</button>
          <button class="detail-tab" :class="{ active: detailTab === 'proc' }" @click="openProcTab">进程</button>
        </div>
        <button class="close-btn" @click="selectedHost = null">✕</button>
      </div>
      <div class="detail-body">

        <!-- ── 进程 Tab ── -->
        <template v-if="detailTab === 'proc'">
          <div v-if="procLoading" class="proc-loading"><div class="spinner"></div><span>正在获取进程...</span></div>
          <div v-else-if="procError" class="proc-error">{{ procError }}</div>
          <template v-else>
            <!-- 检测到的服务徽章 -->
            <div v-if="procServices.length" class="proc-services-row">
              <span class="proc-svc-badge" v-for="svc in procServices" :key="svc" :class="'svc-'+svcColor(svc)">{{ svc }}</span>
            </div>
            <div class="proc-list">
              <div v-for="(p, i) in procList" :key="p.pid" class="proc-item" :class="{ 'proc-service': p.service }">
                <div class="proc-top-row">
                  <span class="proc-rank">{{ i+1 }}</span>
                  <span v-if="p.service" class="proc-svc-tag" :class="'svc-'+p.color">{{ p.service }}</span>
                  <span class="proc-comm">{{ p.comm }}</span>
                  <span class="proc-spacer"></span>
                  <span class="proc-cpu" :class="cpuClass(p.cpu)">CPU {{ p.cpu.toFixed(1) }}%</span>
                  <span class="proc-mem">MEM {{ p.mem.toFixed(1) }}%</span>
                </div>
                <div class="proc-meta-row">
                  <span class="proc-user">{{ p.user }}</span>
                  <span class="proc-pid">PID {{ p.pid }}</span>
                  <span class="proc-rss">{{ p.rss_mb }}MB</span>
                  <span class="proc-stat">{{ p.stat }}</span>
                </div>
                <div v-if="p.service || p.args !== p.comm" class="proc-args" :title="p.args">{{ p.args }}</div>
              </div>
            </div>
            <button class="btn btn-outline btn-xs" style="margin-top:8px;width:100%" @click="loadProcesses(selectedHost)">↺ 刷新进程</button>
          </template>
        </template>

        <!-- ── 信息 Tab ── -->
        <template v-if="detailTab === 'info'">
        <div class="detail-row"><span class="dl">主机名</span><span class="dv">{{ selectedHost.hostname }}</span></div>
        <div class="detail-row"><span class="dl">IP 地址</span><span class="dv mono">{{ selectedHost.ip }}</span></div>
        <div class="detail-row"><span class="dl">平台</span><span class="dv">{{ selectedHost.platform }}</span></div>
        <div class="detail-row"><span class="dl">操作系统</span><span class="dv">{{ selectedHost.os_version || '-' }}</span></div>
        <div class="detail-row"><span class="dl">CPU核心</span><span class="dv">{{ selectedHost.cpu_cores ? selectedHost.cpu_cores + ' 核' : '-' }}</span></div>
        <div class="detail-row"><span class="dl">内存</span><span class="dv">{{ selectedHost.memory_gb ? selectedHost.memory_gb + ' GB' : '-' }}</span></div>
        <div class="detail-row"><span class="dl">磁盘</span><span class="dv">{{ selectedHost.disk_gb ? selectedHost.disk_gb + ' GB' : '-' }}</span></div>
        <div class="detail-section-title">自动状态</div>
        <div class="metric-grid">
          <div class="metric-tile" :class="usageClass(selectedHost.cpu_usage_pct)">
            <span>CPU 使用率</span><b>{{ pctText(selectedHost.cpu_usage_pct) }}</b>
          </div>
          <div class="metric-tile" :class="usageClass(selectedHost.memory_usage_pct)">
            <span>内存使用率</span><b>{{ pctText(selectedHost.memory_usage_pct) }}</b>
          </div>
          <div class="metric-tile">
            <span>5分钟负载</span><b>{{ valueText(selectedHost.load5) }}</b>
          </div>
          <div class="metric-tile">
            <span>运行时长</span><b>{{ uptimeText(selectedHost) }}</b>
          </div>
          <div class="metric-tile">
            <span>磁盘 I/O</span><b>读 {{ rateText(selectedHost.disk_io_read_bps) }} / 写 {{ rateText(selectedHost.disk_io_write_bps) }}</b>
          </div>
          <div class="metric-tile">
            <span>网络带宽</span><b>入 {{ rateText(selectedHost.network_rx_bps) }} / 出 {{ rateText(selectedHost.network_tx_bps) }}</b>
          </div>
          <div class="metric-tile">
            <span>TCP 连接数</span><b>{{ valueText(selectedHost.tcp_connections) }}</b>
          </div>
          <div class="metric-tile" :class="{ warn: Number(selectedHost.tcp_time_wait || 0) > 1000 }">
            <span>TCP TIME_WAIT</span><b>{{ valueText(selectedHost.tcp_time_wait) }}</b>
          </div>
        </div>
        <div v-if="displayDisks(selectedHost).length" class="disk-status-list">
          <div v-for="disk in displayDisks(selectedHost)" :key="disk.mount" class="disk-status-item">
            <div class="disk-status-head">
              <span>磁盘 {{ disk.mount }}</span>
              <b :class="usageClass(disk.used_pct)">{{ pctText(disk.used_pct) }}</b>
            </div>
            <div class="disk-bar"><i :class="usageClass(disk.used_pct)" :style="{ width: clampPct(disk.used_pct) + '%' }"></i></div>
            <div class="disk-status-meta">{{ gbText(disk.used_gb) }} / {{ gbText(disk.size_gb) }}，剩余 {{ gbText(disk.avail_gb) }}</div>
          </div>
        </div>
        <div v-if="selectedHost.metrics_updated_at" class="detail-row"><span class="dl">状态时间</span><span class="dv small-text">{{ formatEast8DateTime(selectedHost.metrics_updated_at) }}</span></div>
        <div class="detail-row"><span class="dl">状态</span><span class="dv">{{ statusLabel(selectedHost.status) }}</span></div>
        <div class="detail-row"><span class="dl">环境</span><span class="dv">{{ envLabel(selectedHost.env) }}</span></div>
        <div class="detail-row"><span class="dl">用途</span><span class="dv">{{ selectedHost.role || '-' }}</span></div>
        <div class="detail-row"><span class="dl">负责人</span><span class="dv">{{ selectedHost.owner || '-' }}</span></div>
        <div class="detail-row"><span class="dl">机房</span><span class="dv">{{ selectedHost.datacenter || '-' }}</span></div>
        <div class="detail-row"><span class="dl">SSH 端口</span><span class="dv">{{ selectedHost.credential_id ? (selectedHost.credential_port || selectedHost.ssh_port || 22) : selectedHost.ssh_port }}</span></div>
        <div class="detail-row"><span class="dl">SSH 用户</span><span class="dv">{{ selectedHost.credential_id ? (selectedHost.credential_username || selectedHost.ssh_user || '-') : (selectedHost.ssh_user || '-') }}</span></div>
        <div class="detail-row"><span class="dl">SSH 凭证</span><span class="dv">{{ credentialDisplay(selectedHost) }}</span></div>
        <div class="detail-row"><span class="dl">备注</span><span class="dv">{{ selectedHost.notes || '-' }}</span></div>
        <div v-if="selectedHost.labels && Object.keys(selectedHost.labels).length" class="detail-row">
          <span class="dl">标签</span>
          <span class="dv">
            <span v-for="(v, k) in selectedHost.labels" :key="k" class="label-chip-detail">{{ k }}={{ v }}</span>
          </span>
        </div>
        <div class="detail-row"><span class="dl">录入时间</span><span class="dv small-text">{{ formatEast8DateTime(selectedHost.created_at) }}</span></div>
        <div class="detail-row"><span class="dl">更新时间</span><span class="dv small-text">{{ formatEast8DateTime(selectedHost.updated_at) }}</span></div>
        <div class="detail-row">
          <span class="dl">最新同步</span>
          <span class="dv small-text" :class="selectedHost.last_sync_at ? '' : 'text-muted'">
            {{ selectedHost.last_sync_at ? formatEast8DateTime(selectedHost.last_sync_at) : '从未同步' }}
          </span>
        </div>
        <div v-if="selectedHostSyncState?.statusMsg" class="sync-msg" :class="selectedHostSyncState?.ok === false ? 'err' : 'ok'">
          <span v-if="selectedHostSyncState?.statusMsg">{{ selectedHostSyncState.statusMsg }}</span>
        </div>
        <div class="detail-actions">
          <button class="btn btn-primary" style="width:100%;margin-bottom:6px" @click="openEdit(selectedHost)">编辑主机</button>
          <button class="btn btn-sync" style="width:100%;margin-bottom:6px" :disabled="syncingId === selectedHost.id" @click="syncHost(selectedHost)">
            <span v-if="syncingId === selectedHost.id" class="spinner" style="width:13px;height:13px;border-width:2px"></span>
            <span v-else>⟳</span> 同步系统信息
          </button>
          <button class="btn btn-outline" style="width:100%" @click="openSSH(selectedHost)">SSH 连接</button>
        </div>
        </template><!-- /info tab -->

      </div>
    </div>
    </div><!-- /content-row -->

    <!-- 添加/编辑主机弹窗 -->
    <div v-if="showHostModal" class="modal-mask" @click.self="showHostModal = false">
      <div class="host-modal">
        <div class="modal-header">
          <span>{{ editingHost ? '编辑主机' : '添加主机' }}</span>
          <button class="close-btn" @click="showHostModal = false">✕</button>
        </div>
        <div class="modal-body">
          <form @submit.prevent="saveHost">
            <div class="form-section-title">基本信息</div>
            <div class="form-row">
              <div class="form-group">
                <label>主机名 <span class="form-hint">（选填，留空自动用 IP）</span></label>
                <input v-model="hostForm.hostname" placeholder="e.g. web-01" />
              </div>
              <div class="form-group required">
                <label>IP 地址</label>
                <input v-model="hostForm.ip" placeholder="e.g. 192.168.1.10" required />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>平台</label>
                <select v-model="hostForm.platform">
                  <option value="Linux">Linux</option>
                  <option value="Windows">Windows</option>
                  <option value="Network">网络设备</option>
                  <option value="Other">其他</option>
                </select>
              </div>
              <div class="form-group">
                <label>操作系统版本</label>
                <input v-model="hostForm.os_version" placeholder="e.g. Ubuntu 22.04.3 LTS" />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>CPU 核心数</label>
                <input v-model="hostForm.cpu_cores" type="text" inputmode="numeric" placeholder="e.g. 8，留空则同步获取" />
              </div>
              <div class="form-group">
                <label>内存 (GB)</label>
                <input v-model="hostForm.memory_gb" type="text" inputmode="decimal" placeholder="e.g. 16，留空则同步获取" />
              </div>
              <div class="form-group">
                <label>磁盘 (GB)</label>
                <input v-model="hostForm.disk_gb" type="text" inputmode="decimal" placeholder="e.g. 500，留空则同步获取" />
              </div>
            </div>

            <div class="form-section-title">运维信息</div>
            <div class="form-row">
              <div class="form-group">
                <label>状态</label>
                <select v-model="hostForm.status">
                  <option value="active">在线</option>
                  <option value="offline">离线</option>
                  <option value="maintenance">维护中</option>
                </select>
              </div>
              <div class="form-group">
                <label>环境</label>
                <select v-model="hostForm.env">
                  <option value="production">生产</option>
                  <option value="staging">预发</option>
                  <option value="development">开发</option>
                  <option value="testing">测试</option>
                  <option value="dr">容灾</option>
                </select>
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>用途/角色</label>
                <input v-model="hostForm.role" placeholder="e.g. Web服务器、数据库主" />
              </div>
              <div class="form-group">
                <label>负责人</label>
                <input v-model="hostForm.owner" placeholder="e.g. 张三" />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>机房/区域</label>
                <input v-model="hostForm.datacenter" placeholder="e.g. 上海机房-A区" />
              </div>
              <div class="form-group">
                <label>所属分组</label>
                <select v-model="hostForm.group">
                  <option value="">无分组</option>
                  <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
                </select>
              </div>
            </div>

            <div class="form-section-title">SSH 配置</div>
            <div class="form-row">
              <div class="form-group">
                <label>SSH 端口</label>
                <input v-model.number="hostForm.ssh_port" type="number" min="1" max="65535" />
              </div>
              <div class="form-group">
                <label>SSH 用户名</label>
                <input v-model="hostForm.ssh_user" placeholder="e.g. root" />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>SSH 密码 <span class="form-hint">{{ hostForm.credential_id ? '（已使用凭证库）' : editingHost ? '（留空保持不变）' : '' }}</span></label>
                <input
                  v-model="hostForm.ssh_password"
                  type="password"
                  :placeholder="hostForm.credential_id ? '已关联凭证库，无需输入密码' : '输入密码加密存储'"
                  :disabled="!!hostForm.credential_id"
                  autocomplete="new-password"
                />
              </div>
              <div class="form-group">
                <label>或关联凭证</label>
                <select v-model="hostForm.credential_id" @change="onCredentialChange">
                  <option value="">不使用凭证库</option>
                  <option v-for="c in credentials" :key="c.id" :value="c.id">{{ credentialOptionLabel(c) }}</option>
                </select>
                <span class="credential-hint">
                  {{ hostForm.credential_id ? '保存后同步系统信息和 SSH 连接会自动使用该凭证。' : '选择凭证后不用再为此主机重复输入密码。' }}
                </span>
              </div>
            </div>

            <div class="form-section-title">其他</div>
            <div class="form-row">
              <div class="form-group full">
                <label>备注</label>
                <textarea v-model="hostForm.notes" rows="2" placeholder="备注信息"></textarea>
              </div>
            </div>
            <div class="form-row">
              <div class="form-group full">
                <label>标签 <span class="form-hint">格式：key=value，每行一条</span></label>
                <textarea v-model="labelsText" rows="3" placeholder="app=nginx&#10;env=prod"></textarea>
              </div>
            </div>
            <div v-if="hostFormError" class="form-error">{{ hostFormError }}</div>
            <div class="form-actions">
              <button type="button" class="btn btn-outline" @click="showHostModal = false">取消</button>
              <button type="submit" class="btn btn-primary" :disabled="saving">
                <span v-if="saving" class="spinner" style="width:13px;height:13px;border-width:2px"></span>
                {{ editingHost ? '保存修改' : '添加主机' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <!-- 导入向导（两步：上传 → 预览 → 确认）-->
    <div v-if="showImportModal" class="modal-mask" @click.self="closeImport">
      <div class="host-modal import-wizard" style="max-width:680px">
        <div class="modal-header">
          <span>批量导入主机 <small class="step-hint">步骤 {{ importPreview ? 2 : 1 }} / 2</small></span>
          <button class="close-btn" @click="closeImport">✕</button>
        </div>

        <!-- 步骤 1：上传 -->
        <div v-if="!importPreview" class="modal-body">
          <div class="wiz-intro">
            <div class="wiz-intro-icon">📋</div>
            <div>
              <p class="wiz-intro-title">从 Excel/CSV 一键导入，分组与凭据自动创建</p>
              <p class="wiz-intro-sub">
                只需 IP 列必填。<b>分组名</b>不存在会自动创建；填了 <b>SSH 用户名+密码</b>会自动加密建凭据；
                任意附加列（如「业务线」「应用名」）会自动进主机标签，不会丢失。
              </p>
            </div>
          </div>

          <div class="wiz-actions-row">
            <a href="/api/hosts/template" class="btn btn-outline" download>
              <span style="margin-right:4px">📥</span>下载导入模板
            </a>
            <span class="wiz-sep">或</span>
            <label class="btn btn-outline wiz-upload-btn">
              <span style="margin-right:4px">📤</span>选择文件上传
              <input type="file" accept=".xlsx,.xls,.csv" @change="onImportFile" hidden />
            </label>
            <span v-if="importFile" class="wiz-file-name">已选：{{ importFile.name }}</span>
          </div>

          <div class="form-group" style="margin-top:14px">
            <label>IP 重复时的策略</label>
            <select v-model="importConflict" class="filter-select" style="width:100%">
              <option value="skip">跳过（保留已有数据）</option>
              <option value="update">覆盖（用文件数据更新）</option>
            </select>
          </div>

          <div class="form-group" style="display:flex;gap:18px;font-size:12.5px">
            <label class="chk">
              <input type="checkbox" v-model="importAutoGroup"/> 分组不存在时自动创建
            </label>
            <label class="chk">
              <input type="checkbox" v-model="importAutoCred"/> 用户名+密码自动建凭据
            </label>
          </div>

          <div v-if="importError" class="form-error">{{ importError }}</div>

          <div class="form-actions">
            <button class="btn btn-outline" @click="closeImport">取消</button>
            <button class="btn btn-primary" @click="doPreview" :disabled="!importFile || importing">
              <span v-if="importing" class="spinner" style="width:13px;height:13px;border-width:2px"></span>
              预览解析结果
            </button>
          </div>
        </div>

        <!-- 步骤 2：预览结果 -->
        <div v-else class="modal-body">
          <div class="wiz-summary">
            <div class="wiz-stat"><span>新增主机</span><strong class="ok">{{ importPreview.added }}</strong></div>
            <div class="wiz-stat"><span>更新主机</span><strong class="warn">{{ importPreview.updated }}</strong></div>
            <div class="wiz-stat"><span>跳过</span><strong class="muted">{{ importPreview.skipped }}</strong></div>
            <div class="wiz-stat"><span>错误</span><strong :class="importPreview.errors ? 'err' : 'muted'">{{ importPreview.errors }}</strong></div>
            <div class="wiz-stat"><span>新建分组</span><strong class="info">{{ importPreview.new_groups.length }}</strong></div>
            <div class="wiz-stat"><span>新建凭据</span><strong class="info">{{ importPreview.new_credentials.length }}</strong></div>
          </div>

          <div v-if="importPreview.new_groups.length || importPreview.new_credentials.length" class="wiz-auto-create">
            <div v-if="importPreview.new_groups.length">
              <b>将自动创建分组：</b>
              <span v-for="g in importPreview.new_groups" :key="g.id" class="wiz-chip">{{ g.name }}</span>
            </div>
            <div v-if="importPreview.new_credentials.length" style="margin-top:6px">
              <b>将自动创建凭据：</b>
              <span v-for="c in importPreview.new_credentials" :key="c.id" class="wiz-chip">{{ c.name }}</span>
            </div>
          </div>

          <div v-if="importPreview.preview_added.length" class="wiz-rows">
            <div class="wiz-rows-title">新增主机预览（前 {{ Math.min(10, importPreview.preview_added.length) }} 条）</div>
            <table class="wiz-table">
              <thead><tr><th>主机名</th><th>IP</th><th>分组</th><th>环境</th></tr></thead>
              <tbody>
                <tr v-for="(h, i) in importPreview.preview_added.slice(0, 10)" :key="i">
                  <td>{{ h.hostname }}</td><td class="mono">{{ h.ip }}</td><td class="mono small">{{ h.group || '-' }}</td><td>{{ h.env }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div v-if="importPreview.error_details?.length" class="wiz-errors">
            <div style="font-weight:600;margin-bottom:6px">⚠ 错误明细</div>
            <div v-for="e in importPreview.error_details.slice(0, 10)" :key="e" class="wiz-err-line">{{ e }}</div>
          </div>

          <div v-if="importResult" class="import-result" :class="importResult.ok ? 'ok' : 'err'">
            <div style="font-weight:600">✓ {{ importResult.message }}</div>
          </div>

          <div v-if="importError" class="form-error">{{ importError }}</div>

          <div class="form-actions">
            <button class="btn btn-outline" @click="resetWizard">返回</button>
            <button class="btn btn-primary" @click="doImport" :disabled="importing || !!importResult">
              <span v-if="importing" class="spinner" style="width:13px;height:13px;border-width:2px"></span>
              确认导入 {{ importPreview.added + importPreview.updated }} 条
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 批量应用凭证弹窗 -->
    <div v-if="showBatchCredModal" class="modal-mask" @click.self="showBatchCredModal = false">
      <div class="host-modal" style="max-width:480px">
        <div class="modal-header">
          <span>批量应用 SSH 凭证</span>
          <button class="close-btn" @click="showBatchCredModal = false">✕</button>
        </div>
        <div class="modal-body">
          <p style="font-size:13px;color:var(--text-muted);margin-bottom:14px">
            为多台主机统一设置 SSH 登录凭证，覆盖原有配置。
          </p>

          <!-- 目标主机 -->
          <div class="form-group">
            <label>应用范围</label>
            <select v-model="batchCredForm.scope" class="filter-select" style="width:100%">
              <option v-if="selectedHostIds.size" value="selected">选中主机（{{ selectedHostIds.size }} 台）</option>
              <option value="all">全部主机（{{ hosts.length }} 台）</option>
              <option value="filtered">当前筛选（{{ filteredHosts.length }} 台）</option>
              <option v-for="g in groups" :key="g.id" :value="'group:' + g.id">
                分组：{{ g.name }}（{{ g.host_count || 0 }} 台）
              </option>
            </select>
          </div>

          <!-- 凭证类型 -->
          <div class="form-group">
            <label>凭证方式</label>
            <select v-model="batchCredForm.mode" class="filter-select" style="width:100%">
              <option value="credential">凭证库</option>
              <option value="password">直接输入密码</option>
            </select>
          </div>

          <!-- 凭证库 -->
          <div v-if="batchCredForm.mode === 'credential'" class="form-group">
            <label>选择凭证</label>
            <select v-model="batchCredForm.credential_id" class="filter-select" style="width:100%">
              <option value="">请选择凭证</option>
              <option v-for="c in credentials" :key="c.id" :value="c.id">{{ credentialOptionLabel(c) }}</option>
            </select>
          </div>

          <!-- 直接密码 -->
          <template v-else>
            <div class="form-row" style="gap:10px">
              <div class="form-group" style="flex:1">
                <label>SSH 用户名</label>
                <input v-model="batchCredForm.ssh_user" placeholder="root" />
              </div>
              <div class="form-group" style="width:90px">
                <label>端口</label>
                <input v-model.number="batchCredForm.ssh_port" type="number" min="1" max="65535" />
              </div>
            </div>
            <div class="form-group">
              <label>SSH 密码</label>
              <input v-model="batchCredForm.ssh_password" type="password" placeholder="加密存储" autocomplete="new-password" />
            </div>
          </template>

          <div v-if="batchCredError" class="form-error">{{ batchCredError }}</div>
          <div v-if="batchCredResult" class="import-result ok">{{ batchCredResult }}</div>

          <div class="form-actions">
            <button class="btn btn-outline" @click="showBatchCredModal = false">取消</button>
            <button class="btn btn-primary" @click="doBatchCred" :disabled="batchCredSaving">
              <span v-if="batchCredSaving" class="spinner" style="width:13px;height:13px;border-width:2px"></span>
              应用凭证
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 删除确认弹窗 -->
    <div v-if="deleteTarget" class="modal-mask" @click.self="deleteTarget = null">
      <div class="confirm-modal">
        <div class="modal-header"><span>确认删除</span><button class="close-btn" @click="deleteTarget = null">✕</button></div>
        <div class="modal-body">
          <p>确定要删除主机 <strong>{{ deleteTarget.hostname }}</strong>（{{ deleteTarget.ip }}）吗？</p>
          <p style="color:var(--text-muted);font-size:12px;margin-top:4px">此操作不可恢复。</p>
          <div class="form-actions">
            <button class="btn btn-outline" @click="deleteTarget = null">取消</button>
            <button class="btn btn-danger" @click="doDelete" :disabled="deleting">
              <span v-if="deleting" class="spinner" style="width:13px;height:13px;border-width:2px"></span>
              确认删除
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 分组弹窗 -->
    <div v-if="showGroupModal" class="modal-mask" @click.self="showGroupModal = false">
      <div class="host-modal" style="max-width:480px">
        <div class="modal-header">
          <span>{{ editingGroup ? '编辑分组' : '新建分组' }}</span>
          <button class="close-btn" @click="showGroupModal = false">✕</button>
        </div>
        <div class="modal-body">
          <form @submit.prevent="saveGroup">
            <div class="form-group required"><label>分组名称</label><input v-model="groupForm.name" required placeholder="e.g. 生产核心" /></div>
            <div class="form-group"><label>描述</label><input v-model="groupForm.description" placeholder="可选描述" /></div>
            <div class="form-section-title">推送配置</div>
            <div class="form-group"><label>飞书 Webhook</label><input v-model="groupForm.feishu_webhook" placeholder="https://open.feishu.cn/..." /></div>
            <div class="form-group"><label>飞书关键字</label><input v-model="groupForm.feishu_keyword" /></div>
            <div class="form-group"><label>钉钉 Webhook</label><input v-model="groupForm.dingtalk_webhook" placeholder="https://oapi.dingtalk.com/..." /></div>
            <div class="form-group"><label>钉钉关键字</label><input v-model="groupForm.dingtalk_keyword" /></div>
            <div class="form-section-title">Alertmanager 告警路由</div>
            <div class="form-group">
              <label>标签匹配规则 <span class="form-hint">每行一条，格式 `label=value`，命中任意一条就推送到当前飞书群</span></label>
              <textarea
                v-model="groupForm.alert_matchers_text"
                rows="4"
                placeholder="例如：&#10;feishu_group=测试A&#10;team=middleware"
              />
            </div>
            <div class="form-section-title">定时巡检</div>
            <div class="form-row">
              <div class="form-group">
                <label>定时时间</label>
                <input v-model="groupForm.schedule_time" type="time" />
              </div>
              <div class="form-group" style="justify-content:flex-end;padding-top:20px">
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
                  <input type="checkbox" v-model="groupForm.schedule_enabled" /> 启用定时巡检
                </label>
              </div>
            </div>
            <div v-if="groupFormError" class="form-error">{{ groupFormError }}</div>
            <div class="form-actions">
              <button type="button" class="btn btn-outline" @click="showGroupModal = false">取消</button>
              <button type="submit" class="btn btn-primary" :disabled="savingGroup">
                <span v-if="savingGroup" class="spinner" style="width:13px;height:13px;border-width:2px"></span>
                {{ editingGroup ? '保存' : '创建' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, nextTick } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { api } from '../api/index.js'

const router = useRouter()

// ── 数据 ─────────────────────────────────────────────────────────────────────
const hosts       = ref([])
const groups      = ref([])
const credentials = ref([])
const loading     = ref(false)
const tab         = ref('cmdb')
const search      = ref('')
const envFilter   = ref('')
const groupFilter = ref('')
const sortKey     = ref('hostname')
const sortAsc     = ref(true)
const selectedHost = ref(null)

const groupMap = computed(() => Object.fromEntries(groups.value.map(g => [g.id, g.name])))
const credentialMap = computed(() => Object.fromEntries(credentials.value.map(c => [c.id, c])))

const countByStatus = (s) => hosts.value.filter(h => h.status === s).length

function setSort(key) {
  if (sortKey.value === key) sortAsc.value = !sortAsc.value
  else { sortKey.value = key; sortAsc.value = true }
}

const filteredHosts = computed(() => {
  let list = hosts.value
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(h =>
      (h.hostname || '').toLowerCase().includes(q) ||
      (h.ip || '').includes(q) ||
      (h.owner || '').toLowerCase().includes(q) ||
      (h.role || '').toLowerCase().includes(q)
    )
  }
  if (envFilter.value) list = list.filter(h => h.env === envFilter.value)
  if (groupFilter.value) list = list.filter(h => h.group === groupFilter.value)
  return list
})

const sortedHosts = computed(() => {
  const list = [...filteredHosts.value]
  list.sort((a, b) => {
    const va = (a[sortKey.value] || '').toString().toLowerCase()
    const vb = (b[sortKey.value] || '').toString().toLowerCase()
    return sortAsc.value ? va.localeCompare(vb) : vb.localeCompare(va)
  })
  return list
})

function refreshSelectedHostFromList() {
  if (!selectedHost.value) return
  const current = selectedHost.value
  const fresh = hosts.value.find(item => item.id === current.id || (current.ip && item.ip === current.ip))
  if (fresh) selectedHost.value = fresh
}

async function loadHosts() {
  loading.value = true
  try {
    const res = await api.getHosts()
    hosts.value = res.data || []
    refreshSelectedHostFromList()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function loadGroups() {
  try {
    const res = await api.listGroups()
    groups.value = res.data || []
  } catch {}
}

async function loadCredentials() {
  try {
    const res = await api.listCredentials()
    credentials.value = Array.isArray(res?.data) ? res.data : (Array.isArray(res) ? res : [])
  } catch {}
}

onMounted(() => {
  // 支持 URL ?tab=xxx 直接进入对应 tab；旧 tab=ssh 映射到凭证管理。
  const q = router.currentRoute.value.query
  const routeTab = String(q.tab || '')
  if (routeTab === 'ssh') tab.value = 'credentials'
  else if (['credentials', 'groups', 'cmdb', 'inspect'].includes(routeTab)) tab.value = routeTab
  if (q.q) search.value = String(q.q)
  if (q.env) envFilter.value = String(q.env)
  if (q.group) groupFilter.value = String(q.group)
  loadHosts(); loadGroups(); loadCredentials()
})

// ── URL query 双向同步：tab/搜索/筛选写进 URL，可分享可后退 ────────────────
function syncQueryToUrl() {
  const q = {}
  if (tab.value && tab.value !== 'cmdb') q.tab = tab.value
  if (search.value) q.q = search.value
  if (envFilter.value) q.env = envFilter.value
  if (groupFilter.value) q.group = groupFilter.value
  router.replace({ query: q }).catch(() => {})
}
watch([tab, search, envFilter, groupFilter], () => syncQueryToUrl(), { flush: 'post' })

// ── 批量选择 + 浮动操作栏 ────────────────────────────────────────────────────
const selectedHostIds = ref(new Set())
const batchField = ref({ group: '', env: '', status: '' })
const batchRunning = ref(false)
const batchResult = ref('')

const visibleHostIds = computed(() => sortedHosts.value.map(h => h.id))
const allVisibleSelected = computed(() => visibleHostIds.value.length > 0 && visibleHostIds.value.every(id => selectedHostIds.value.has(id)))
const someVisibleSelected = computed(() => {
  const total = visibleHostIds.value.filter(id => selectedHostIds.value.has(id)).length
  return total > 0 && total < visibleHostIds.value.length
})

function toggleSelectAll() {
  const next = new Set(selectedHostIds.value)
  if (allVisibleSelected.value) {
    visibleHostIds.value.forEach(id => next.delete(id))
  } else {
    visibleHostIds.value.forEach(id => next.add(id))
  }
  selectedHostIds.value = next
}

function toggleHostSelected(host) {
  const next = new Set(selectedHostIds.value)
  if (next.has(host.id)) next.delete(host.id)
  else next.add(host.id)
  selectedHostIds.value = next
}

async function applyBatchField(field, value) {
  if (!value || !selectedHostIds.value.size) return
  batchRunning.value = true
  batchResult.value = ''
  try {
    const r = await api.batchUpdateHosts({
      host_ids: Array.from(selectedHostIds.value),
      fields: { [field]: value },
    })
    batchResult.value = `已更新 ${r.updated} 台`
    setTimeout(() => batchResult.value = '', 2500)
    await loadHosts()
  } catch (e) {
    batchResult.value = '失败: ' + (typeof e === 'string' ? e : e?.message || '未知')
  } finally {
    batchRunning.value = false
    batchField.value[field] = ''
  }
}

async function batchDeleteSelected() {
  const ids = Array.from(selectedHostIds.value)
  if (!ids.length) return
  if (!confirm(`确认删除选中的 ${ids.length} 台主机？此操作不可恢复！`)) return
  batchRunning.value = true
  let ok = 0
  for (const id of ids) {
    try { await api.deleteHost(id); ok++ } catch { /* 跳过失败 */ }
  }
  batchResult.value = `已删除 ${ok}/${ids.length} 台`
  setTimeout(() => batchResult.value = '', 2500)
  selectedHostIds.value = new Set()
  batchRunning.value = false
  await loadHosts()
}

function batchApplyCredential() {
  // 复用现有的「批量应用 SSH 凭证」弹窗，但传入选中范围
  batchCredForm.scope = 'selected'
  batchCredForm.selectedIds = Array.from(selectedHostIds.value)
  showBatchCredModal.value = true
}

// 主 tab 刷新动作：每个 tab 调对应的加载函数，并联动凭据。
function refreshActiveTab() {
  if (tab.value === 'cmdb') {
    loadHosts()
    loadCredentials()
  } else if (tab.value === 'inspect') {
    loadHosts()
    loadGroups()
  } else if (tab.value === 'groups') {
    loadGroups()
    loadHosts()  // 分组上的「主机数」依赖最新 hosts
  } else if (tab.value === 'credentials') {
    loadHosts()
    loadCredentials()
  }
}

// 主机数据变更时通知其他 tab：CMDB 增删改后自动让 groups 重算主机数
watch(hosts, () => {
  if (groups.value.length) loadGroups()
}, { deep: true, flush: 'post' })

function selectHost(h) { selectedHost.value = h === selectedHost.value ? null : h }

// ── 标签映射 ─────────────────────────────────────────────────────────────────
function statusLabel(s) {
  return { active: '在线', offline: '离线', maintenance: '维护中' }[s] || s
}
function envLabel(e) {
  return { production: '生产', staging: '预发', development: '开发', testing: '测试', dr: '容灾' }[e] || e
}
function inspectStatusLabel(s) {
  return { normal: '正常', warning: '警告', critical: '严重' }[s] || s
}
function valueText(v) {
  if (v === null || v === undefined || v === '') return '-'
  const n = Number(v)
  if (!Number.isFinite(n)) return String(v)
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}
function pctText(v) {
  if (v === null || v === undefined || v === '') return '-'
  const n = Number(v)
  return Number.isFinite(n) ? `${n.toFixed(1)}%` : '-'
}
function gbText(v) {
  if (v === null || v === undefined || v === '') return '-'
  const n = Number(v)
  return Number.isFinite(n) ? `${n.toFixed(1)}GB` : '-'
}
function rateText(v) {
  const n = Number(v || 0)
  if (!Number.isFinite(n) || n <= 0) return '0B/s'
  const units = ['B/s', 'KB/s', 'MB/s', 'GB/s']
  let value = n
  let idx = 0
  while (value >= 1024 && idx < units.length - 1) {
    value /= 1024
    idx += 1
  }
  return `${value >= 10 || idx === 0 ? value.toFixed(0) : value.toFixed(1)}${units[idx]}`
}
function usageClass(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return ''
  if (n >= 90) return 'crit'
  if (n >= 80) return 'warn'
  return 'ok'
}
function clampPct(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(100, n))
}
function uptimeText(host) {
  if (host?.uptime_text) return host.uptime_text
  const seconds = Number(host?.uptime_seconds)
  if (!Number.isFinite(seconds) || seconds < 0) return '-'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return `${days ? `${days}天` : ''}${hours || days ? `${hours}小时` : ''}${minutes}分钟`
}
function displayDisks(host) {
  const disks = Array.isArray(host?.disk_usage) ? [...host.disk_usage] : []
  const priority = ['/', '/boot', '/boot/efi', '/data']
  disks.sort((a, b) => {
    const ai = priority.indexOf(a.mount)
    const bi = priority.indexOf(b.mount)
    if (ai !== -1 || bi !== -1) return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi)
    return String(a.mount || '').localeCompare(String(b.mount || ''))
  })
  return disks
}
function credentialOptionLabel(c) {
  if (!c) return ''
  const username = c.username || 'root'
  const port = c.port || 22
  return `${c.name}（${username}@${port}）`
}
function credentialDisplay(host) {
  if (!host?.credential_id) return host?.ssh_saved ? '已配置主机密码' : '未配置'
  const c = credentialMap.value[host.credential_id]
  if (c) return `凭证库：${credentialOptionLabel(c)}`
  if (host.credential_name) {
    const username = host.credential_username || host.ssh_user || 'root'
    const port = host.credential_port || host.ssh_port || 22
    return `凭证库：${host.credential_name}（${username}@${port}）`
  }
  return `凭证库：${host.credential_id}`
}

// ── 凭证管理 ─────────────────────────────────────────────────────────────────
const credentialEditId = ref('')
const credentialSaving = ref(false)
const credentialError = ref('')
const credentialSuccess = ref('')
const credentialForm = reactive({
  name: '',
  username: 'root',
  password: '',
  port: 22,
})

const credentialBoundHostCount = computed(() => hosts.value.filter(h => h.credential_id || h.ssh_saved).length)

function credentialUsageCount(id) {
  return hosts.value.filter(h => h.credential_id === id).length
}

function resetCredentialForm(clearMessage = true) {
  credentialEditId.value = ''
  Object.assign(credentialForm, { name: '', username: 'root', password: '', port: 22 })
  if (clearMessage) {
    credentialError.value = ''
    credentialSuccess.value = ''
  }
}

function editCredential(c) {
  credentialEditId.value = c.id
  Object.assign(credentialForm, {
    name: c.name || '',
    username: c.username || 'root',
    password: '',
    port: c.port || 22,
  })
  credentialError.value = ''
  credentialSuccess.value = ''
}

function validateCredentialForm() {
  const name = String(credentialForm.name || '').trim()
  const username = String(credentialForm.username || '').trim()
  const password = String(credentialForm.password || '')
  const port = Number(credentialForm.port || 22)
  if (!name) return '请输入凭证名称'
  if (!username) return '请输入用户名'
  if (!Number.isInteger(port) || port < 1 || port > 65535) return '端口必须是 1-65535 的整数'
  if (!credentialEditId.value && !password) return '新增凭证时密码不能为空'
  return ''
}

async function saveCredential() {
  credentialError.value = ''
  credentialSuccess.value = ''
  const invalid = validateCredentialForm()
  if (invalid) {
    credentialError.value = invalid
    return
  }

  credentialSaving.value = true
  try {
    const payload = {
      name: String(credentialForm.name).trim(),
      username: String(credentialForm.username).trim() || 'root',
      password: credentialForm.password || '',
      port: Number(credentialForm.port || 22),
    }
    if (credentialEditId.value) {
      await api.updateCredential(credentialEditId.value, payload)
      credentialSuccess.value = '凭证已更新'
    } else {
      await api.createCredential(payload)
      credentialSuccess.value = '凭证已新增'
    }
    resetCredentialForm(false)
    await loadCredentials()
    await loadHosts()
  } catch (e) {
    credentialError.value = '保存凭证失败：' + (typeof e === 'string' ? e : e?.message || '未知错误')
  } finally {
    credentialSaving.value = false
  }
}

async function deleteCredential(c) {
  credentialError.value = ''
  credentialSuccess.value = ''
  const used = credentialUsageCount(c.id)
  const tip = used ? `该凭证当前绑定 ${used} 台主机，删除后会清除这些主机的凭证引用。` : '该凭证当前未绑定主机。'
  if (!confirm(`${tip}\n确定删除凭证「${c.name}」？`)) return
  try {
    await api.deleteCredential(c.id)
    if (credentialEditId.value === c.id) resetCredentialForm(false)
    credentialSuccess.value = '凭证已删除'
    await loadCredentials()
    await loadHosts()
  } catch (e) {
    credentialError.value = '删除凭证失败：' + (typeof e === 'string' ? e : e?.message || '未知错误')
  }
}

function openBatchWithCredential(c) {
  batchCredError.value = ''
  batchCredResult.value = ''
  batchCredForm.scope = selectedHostIds.value.size ? 'selected' : 'all'
  batchCredForm.mode = 'credential'
  batchCredForm.credential_id = c.id
  batchCredForm.ssh_user = c.username || 'root'
  batchCredForm.ssh_port = c.port || 22
  batchCredForm.ssh_password = ''
  showBatchCredModal.value = true
}

// ── 添加/编辑主机 ─────────────────────────────────────────────────────────────
const showHostModal = ref(false)
const editingHost   = ref(null)
const saving        = ref(false)
const hostFormError = ref('')
const labelsText    = ref('')

const hostForm = reactive({
  hostname: '', ip: '', platform: 'Linux', os_version: '',
  cpu_cores: '', memory_gb: '', disk_gb: '',
  status: 'active', env: 'production', role: '', owner: '',
  datacenter: '', group: '', ssh_port: 22, ssh_user: '',
  ssh_password: '', credential_id: '', notes: '',
})

function parseLabels(text) {
  const result = {}
  for (const line of text.split('\n')) {
    const idx = line.indexOf('=')
    if (idx > 0) {
      const k = line.slice(0, idx).trim()
      const v = line.slice(idx + 1).trim()
      if (k) result[k] = v
    }
  }
  return result
}

function labelsToText(labels) {
  return Object.entries(labels || {}).map(([k, v]) => `${k}=${v}`).join('\n')
}

function numberFieldToInput(value) {
  return value === null || value === undefined || value === '' ? '' : String(value)
}

function parseOptionalInt(value, label, min = 1) {
  const text = String(value ?? '').trim()
  if (!text) return null
  const parsed = Number(text)
  if (!Number.isInteger(parsed) || parsed < min) {
    throw new Error(`${label}必须是大于等于 ${min} 的整数`)
  }
  return parsed
}

function parseOptionalFloat(value, label, min = 0) {
  const text = String(value ?? '').trim()
  if (!text) return null
  const parsed = Number(text)
  if (!Number.isFinite(parsed) || parsed < min) {
    throw new Error(`${label}必须是大于等于 ${min} 的数字`)
  }
  return parsed
}

function openAdd() {
  editingHost.value = null
  hostFormError.value = ''
  labelsText.value = ''
  Object.assign(hostForm, {
    hostname: '', ip: '', platform: 'Linux', os_version: '',
    cpu_cores: '', memory_gb: '', disk_gb: '',
    status: 'active', env: 'production', role: '', owner: '',
    datacenter: '', group: '', ssh_port: 22, ssh_user: '',
    ssh_password: '', credential_id: '', notes: '',
  })
  showHostModal.value = true
}

function openEdit(h) {
  editingHost.value = h
  hostFormError.value = ''
  labelsText.value = labelsToText(h.labels)
  Object.assign(hostForm, {
    hostname: h.hostname, ip: h.ip, platform: h.platform || 'Linux',
    os_version: h.os_version || '', cpu_cores: numberFieldToInput(h.cpu_cores),
    memory_gb: numberFieldToInput(h.memory_gb), disk_gb: numberFieldToInput(h.disk_gb),
    status: h.status || 'active', env: h.env || 'production',
    role: h.role || '', owner: h.owner || '', datacenter: h.datacenter || '',
    group: h.group || '', ssh_port: h.ssh_port || 22,
    ssh_user: h.ssh_user || '', ssh_password: '',
    credential_id: h.credential_id || '', notes: h.notes || '',
  })
  showHostModal.value = true
}

function onCredentialChange() {
  const c = credentialMap.value[hostForm.credential_id]
  if (!c) return
  hostForm.ssh_user = c.username || hostForm.ssh_user || 'root'
  hostForm.ssh_port = c.port || hostForm.ssh_port || 22
  hostForm.ssh_password = ''
}

async function saveHost() {
  hostFormError.value = ''
  if (!hostForm.ip.trim()) { hostFormError.value = 'IP 地址不能为空'; return }
  saving.value = true
  try {
    const payload = {
      ...hostForm,
      cpu_cores: parseOptionalInt(hostForm.cpu_cores, 'CPU 核心数'),
      memory_gb: parseOptionalFloat(hostForm.memory_gb, '内存 (GB)'),
      disk_gb: parseOptionalFloat(hostForm.disk_gb, '磁盘 (GB)'),
      labels: parseLabels(labelsText.value),
    }
    if (payload.credential_id) payload.ssh_password = ''
    else if (editingHost.value && !payload.ssh_password) delete payload.ssh_password
    if (editingHost.value) {
      await api.updateHost(editingHost.value.id, payload)
    } else {
      await api.createHost(payload)
    }
    showHostModal.value = false
    await loadHosts()
    selectedHost.value = null
  } catch (e) {
    hostFormError.value = typeof e === 'string' ? e : e?.message || '保存失败，请重试'
  } finally {
    saving.value = false
  }
}

// ── 导出 / 导入 ───────────────────────────────────────────────────────────────
function downloadExport() {
  const a = document.createElement('a')
  a.href = api.exportHosts()
  a.click()
}

const showImportModal = ref(false)
const importFile      = ref(null)
const importConflict  = ref('skip')
const importAutoGroup = ref(true)
const importAutoCred  = ref(true)
const importing       = ref(false)
const importResult    = ref(null)
const importPreview   = ref(null)
const importError     = ref('')

function onImportFile(e) {
  importFile.value   = e.target.files[0] || null
  importResult.value = null
  importPreview.value = null
  importError.value  = ''
}

function closeImport() {
  showImportModal.value = false
  resetWizard()
  importFile.value = null
}

function resetWizard() {
  importPreview.value = null
  importResult.value  = null
  importError.value   = ''
}

async function doPreview() {
  if (!importFile.value) return
  importing.value = true
  importError.value = ''
  try {
    importPreview.value = await api.previewImportHosts(importFile.value, {
      conflict: importConflict.value,
      auto_create_group: importAutoGroup.value,
      auto_create_credential: importAutoCred.value,
    })
  } catch (e) {
    importError.value = typeof e === 'string' ? e : '预览失败，请检查文件格式'
  } finally {
    importing.value = false
  }
}

async function doImport() {
  if (!importFile.value) return
  importing.value = true
  importError.value = ''
  try {
    const res = await api.importHosts(importFile.value, {
      conflict: importConflict.value,
      auto_create_group: importAutoGroup.value,
      auto_create_credential: importAutoCred.value,
    })
    importResult.value = res
    if (res.ok) {
      await loadHosts()
      // 1.2 秒后自动关闭
      setTimeout(closeImport, 1500)
    }
  } catch (e) {
    importError.value = typeof e === 'string' ? e : '导入失败，请检查文件格式'
  } finally {
    importing.value = false
  }
}

// ── 一键同步所有主机 ──────────────────────────────────────────────────────────
const syncingAll    = ref(false)
const syncAllTotal  = ref(0)
const syncAllDone   = ref(0)
const syncAllSuccess = ref(0)
const syncAllFail   = ref(0)
const syncAllResult  = ref('')

async function runSyncAll() {
  syncingAll.value     = true
  syncAllTotal.value   = 0
  syncAllDone.value    = 0
  syncAllSuccess.value = 0
  syncAllFail.value    = 0
  syncAllResult.value  = ''

  try {
    const resp = await fetch('/api/hosts/sync-all', {
      method: 'POST',
      credentials: 'include',
    })
    if (!resp.ok) {
      const errText = await resp.text()
      throw new Error(`请求失败 (${resp.status}): ${errText}`)
    }

    const reader  = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop()           // 保留未完成的行
      for (const line of lines) {
        if (!line.startsWith('data:')) continue
        const raw = line.slice(5).trim()
        if (!raw) continue
        try {
          const msg = JSON.parse(raw)
          if (msg.type === 'start') {
            syncAllTotal.value = msg.total
          } else if (msg.type === 'progress') {
            syncAllSuccess.value = msg.success
            syncAllFail.value    = msg.fail
            syncAllDone.value    = msg.success + msg.fail
            // 成功时直接更新对应行数据（无需等刷新）
            if (msg.ok && msg.id && msg.updated) {
              const h = hosts.value.find(x => x.id === msg.id)
              if (h) Object.assign(h, msg.updated)
            }
          } else if (msg.type === 'done') {
            syncAllResult.value = msg.message
            // 同步完成后重新拉取列表，确保回填字段显示最新
            await loadHosts()
          }
        } catch { /* JSON 解析错误跳过 */ }
      }
    }
  } catch (e) {
    syncAllResult.value = '同步出错：' + (e?.message || String(e))
    syncAllFail.value   = syncAllTotal.value - syncAllSuccess.value
  } finally {
    syncingAll.value = false
  }
}

// ── 批量应用凭证 ──────────────────────────────────────────────────────────────
const showBatchCredModal = ref(false)
const batchCredSaving    = ref(false)
const batchCredError     = ref('')
const batchCredResult    = ref('')

const batchCredForm = reactive({
  scope:         'all',
  mode:          'credential',
  credential_id: '',
  ssh_user:      'root',
  ssh_port:      22,
  ssh_password:  '',
})

function openBatchCred() {
  batchCredError.value  = ''
  batchCredResult.value = ''
  batchCredForm.scope         = 'all'
  batchCredForm.mode          = credentials.value.length ? 'credential' : 'password'
  batchCredForm.credential_id = credentials.value[0]?.id || ''
  batchCredForm.ssh_user      = 'root'
  batchCredForm.ssh_port      = 22
  batchCredForm.ssh_password  = ''
  showBatchCredModal.value = true
}

async function doBatchCred() {
  batchCredError.value  = ''
  batchCredResult.value = ''

  if (batchCredForm.mode === 'credential' && !batchCredForm.credential_id) {
    batchCredError.value = '请选择凭证'; return
  }
  if (batchCredForm.mode === 'password' && !batchCredForm.ssh_password) {
    batchCredError.value = 'SSH 密码不能为空'; return
  }

  const payload = { mode: batchCredForm.mode }

  // 确定目标范围
  const scope = batchCredForm.scope
  if (scope === 'filtered') {
    payload.host_ids = filteredHosts.value.map(h => h.id)
  } else if (scope === 'selected') {
    payload.host_ids = batchCredForm.selectedIds || Array.from(selectedHostIds.value)
  } else if (scope.startsWith('group:')) {
    payload.group = scope.slice(6)
  }
  // scope === 'all' → 不传 host_ids/group，后端默认全部

  if (batchCredForm.mode === 'credential') {
    payload.credential_id = batchCredForm.credential_id
  } else {
    payload.ssh_user     = batchCredForm.ssh_user || 'root'
    payload.ssh_port     = batchCredForm.ssh_port || 22
    payload.ssh_password = batchCredForm.ssh_password
  }

  batchCredSaving.value = true
  try {
    const res = await fetch('/api/hosts/batch-credential', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '操作失败')
    batchCredResult.value = `已成功更新 ${data.updated} 台主机的凭证`
    await loadHosts()
  } catch (e) {
    batchCredError.value = e?.message || '操作失败'
  } finally {
    batchCredSaving.value = false
  }
}

// ── 删除主机 ──────────────────────────────────────────────────────────────────
const deleteTarget = ref(null)
const deleting     = ref(false)

function confirmDelete(h) { deleteTarget.value = h }

async function doDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await api.deleteHost(deleteTarget.value.id)
    if (selectedHost.value?.id === deleteTarget.value.id) selectedHost.value = null
    deleteTarget.value = null
    await loadHosts()
  } catch (e) {
    alert('删除失败：' + (typeof e === 'string' ? e : '未知错误'))
  } finally {
    deleting.value = false
  }
}

// ── 详情面板 tab ─────────────────────────────────────────────────────────────
const detailTab = ref('info')

// ── 进程列表 ─────────────────────────────────────────────────────────────────
const procList     = ref([])
const procServices = ref([])
const procLoading  = ref(false)
const procError    = ref('')

// 服务名 → color key 映射（与后端保持一致）
const _SVC_COLOR_MAP = {
  'MySQL': 'mysql', 'Java': 'java', 'Python': 'python', 'Node.js': 'node',
  'Nginx': 'nginx', 'Redis': 'redis', 'PostgreSQL': 'postgres',
  'Elastic': 'elastic', 'Docker': 'docker', 'Kubernetes': 'k8s',
  'MongoDB': 'mongo', 'RabbitMQ': 'rabbit', 'Kafka/ZK': 'kafka',
  'SSH': 'ssh', 'PHP': 'php', 'Go': 'go',
}
function svcColor(svcName) { return _SVC_COLOR_MAP[svcName] || 'default' }
function cpuClass(cpu) { return cpu >= 50 ? 'cpu-high' : cpu >= 20 ? 'cpu-mid' : '' }

const DISPLAY_TIMEZONE = 'Asia/Shanghai'
const DISPLAY_TIMEZONE_LABEL = 'UTC+8'
const east8DateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: DISPLAY_TIMEZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

function parseServerTime(value) {
  if (!value) return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (typeof value !== 'string') {
    const parsed = new Date(value)
    return Number.isNaN(parsed.getTime()) ? null : parsed
  }

  const raw = value.trim()
  if (!raw) return null

  const normalized = raw.replace(' ', 'T')
  if (/(?:Z|[+-]\d{2}:\d{2})$/i.test(normalized)) {
    const parsed = new Date(normalized)
    if (!Number.isNaN(parsed.getTime())) return parsed
  } else {
    const match = normalized.match(
      /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?(?:\.(\d{1,3}))?)?$/
    )
    if (match) {
      const [
        ,
        year,
        month,
        day,
        hour = '00',
        minute = '00',
        second = '00',
        millisecond = '0',
      ] = match
      const parsed = new Date(
        Date.UTC(
          Number(year),
          Number(month) - 1,
          Number(day),
          Number(hour) - 8,
          Number(minute),
          Number(second),
          Number(millisecond.padEnd(3, '0'))
        )
      )
      if (!Number.isNaN(parsed.getTime())) return parsed
    }
  }

  const fallback = new Date(normalized)
  return Number.isNaN(fallback.getTime()) ? null : fallback
}

function formatEast8DateTime(value) {
  const parsed = parseServerTime(value)
  if (!parsed) return value || '-'

  const parts = Object.fromEntries(
    east8DateTimeFormatter
      .formatToParts(parsed)
      .filter(part => part.type !== 'literal')
      .map(part => [part.type, part.value])
  )
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second} ${DISPLAY_TIMEZONE_LABEL}`
}

function relativeTime(dateStr) {
  if (!dateStr) return '—'
  const parsed = parseServerTime(dateStr)
  if (!parsed) return '—'
  const diff = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 1000))
  if (diff < 60)   return `${diff}秒前`
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  return `${Math.floor(diff / 86400)}天前`
}
function syncTimeClass(dateStr) {
  if (!dateStr) return 'no-sync'
  const parsed = parseServerTime(dateStr)
  if (!parsed) return 'no-sync'
  const hours = (Date.now() - parsed.getTime()) / 3600000
  if (hours > 72) return 'sync-stale'
  if (hours > 24) return 'sync-warn'
  return 'sync-ok'
}

async function loadProcesses(host) {
  if (!host) return
  procLoading.value = true
  procError.value   = ''
  procList.value    = []
  procServices.value = []
  try {
    const res = await api.getHostProcesses(host.id)
    procList.value     = res.data || []
    procServices.value = res.detected_services || []
  } catch (e) {
    procError.value = typeof e === 'string' ? e : '获取进程失败，请检查 SSH 配置'
  } finally {
    procLoading.value = false
  }
}

function openProcTab() {
  detailTab.value = 'proc'
  if (procList.value.length === 0 && !procLoading.value && selectedHost.value) {
    loadProcesses(selectedHost.value)
  }
}

// 切换主机时重置进程面板
watch(selectedHost, (h) => {
  detailTab.value    = 'info'
  procList.value     = []
  procServices.value = []
  procError.value    = ''
})

// ── SSH 同步系统信息 ──────────────────────────────────────────────────────────
const syncingId = ref('')
const syncStates = reactive({})

function hostSyncState(hostId) {
  return syncStates[hostId] || null
}

const selectedHostSyncState = computed(() => {
  const hostId = selectedHost.value?.id
  return hostId ? syncStates[hostId] || null : null
})

const runtimeSyncKeys = [
  'cpu_usage_pct',
  'memory_usage_pct',
  'load5',
  'uptime_seconds',
  'uptime_text',
  'disk_io_read_bps',
  'disk_io_write_bps',
  'network_rx_bps',
  'network_tx_bps',
  'tcp_connections',
  'tcp_time_wait',
  'disk_usage',
  'metrics_updated_at',
]

function syncStatusClass(hostId) {
  return syncStates[hostId]?.ok === false ? 'err' : 'ok'
}

function isSyncedField(hostId, keys) {
  const state = syncStates[hostId]
  if (!state?.ok || !state.updatedKeys?.length) return false
  const fieldKeys = Array.isArray(keys) ? keys : [keys]
  return fieldKeys.some(key => state.updatedKeys.includes(key))
}

function mergeSyncedHost(hostId, syncedHost, updated) {
  const patch = syncedHost || updated || {}
  const index = hosts.value.findIndex(item => item.id === hostId)
  if (index >= 0) {
    hosts.value[index] = { ...hosts.value[index], ...patch }
  }
  if (selectedHost.value?.id === hostId) {
    selectedHost.value = { ...selectedHost.value, ...patch }
  }
}

async function syncHost(h) {
  syncingId.value = h.id
  syncStates[h.id] = { statusMsg: '同步中...', updatedKeys: [], ok: true }
  try {
    const res = await api.syncHost(h.id)
    const updated = res.updated || {}
    mergeSyncedHost(h.id, res.host, updated)
    const updatedKeys = Object.keys(updated).filter(key => updated[key] !== undefined)
    syncStates[h.id] = {
      statusMsg: updatedKeys.length ? '同步完成，字段已回填' : '同步完成（无字段变化）',
      updatedKeys,
      ok: true,
    }
    // 刷新列表
    await loadHosts()
    // 如果右侧面板是这台主机，更新
    if (selectedHost.value?.id === h.id) {
      selectedHost.value = hosts.value.find(x => x.id === h.id) || selectedHost.value
    }
  } catch (e) {
    syncStates[h.id] = {
      statusMsg: '同步失败：' + (typeof e === 'string' ? e : '请检查 SSH 密码和网络连通性'),
      updatedKeys: [],
      ok: false,
    }
  } finally {
    syncingId.value = ''
  }
}

// ── SSH 跳转 ──────────────────────────────────────────────────────────────────
function openSSH(h) {
  router.push({
    path: '/tools/ssh',
    query: {
      instance: h.ip,
      ...(h.credential_id ? { credential_id: h.credential_id } : {}),
    },
  })
}

// ── 巡检 ─────────────────────────────────────────────────────────────────────
const inspecting         = ref(false)
const inspectError       = ref('')
const inspectResults     = ref([])
const inspectSummary     = reactive({
  total: 0,
  normal: 0,
  warning: 0,
  critical: 0,
  group_id: '',
  group_name: '',
  metrics_updated_at: '',
  metrics_updated_count: 0,
  metrics_missing_count: 0,
  metrics_fallback_count: 0,
})
const inspectAiSummary   = ref('')
const inspectAiStreaming  = ref(false)
const inspectAiFallback  = ref(false)
const inspectAiProvider  = ref('')
const inspectGroupId     = ref('')
const notifyingGroups    = ref(false)
const inspectNotifyMessage = ref('')
const inspectNotifyStatus  = ref('ok')
const excelDownloading   = ref(false)
const aiExpanded         = ref(true)
const inspectSortKey     = ref('status')
const inspectSortAsc     = ref(false)

function inspectMetrics(row) {
  return row?.metrics && typeof row.metrics === 'object' ? row.metrics : {}
}

function inspectMetric(row, key) {
  return inspectMetrics(row)[key]
}

function toSortableNumber(value) {
  const numberValue = Number(value)
  return Number.isFinite(numberValue) ? numberValue : null
}

function statusRank(status) {
  return { critical: 3, warning: 2, normal: 1 }[status] || 0
}

function highestDisk(row) {
  return inspectPartitions(row).reduce((highest, partition) => {
    if (!highest) return partition
    const currentUsage = Number(partition.usage_pct ?? partition.used_pct)
    const highestUsage = Number(highest.usage_pct ?? highest.used_pct)
    if (!Number.isFinite(currentUsage)) return highest
    if (!Number.isFinite(highestUsage)) return partition
    return currentUsage > highestUsage ? partition : highest
  }, null)
}

function highestDiskUsage(row) {
  const disk = highestDisk(row)
  const usage = Number(disk?.usage_pct ?? disk?.used_pct)
  return Number.isFinite(usage) ? usage : null
}

function issueCount(row) {
  return abnormalChecks(row).length
}

function inspectSortValue(row, key) {
  if (key === 'status') return statusRank(row?.overall)
  if (key === 'hostname') return String(row?.hostname || row?.instance || row?.ip || '').toLowerCase()
  if (key === 'ip') return String(row?.ip || '').toLowerCase()
  if (key === 'os') return String(row?.os || '').toLowerCase()
  if (key === 'cpu') return toSortableNumber(inspectMetric(row, 'cpu_usage'))
  if (key === 'cpu_cores') return toSortableNumber(row?.cpu_cores)
  if (key === 'memory') return toSortableNumber(inspectMetric(row, 'mem_usage'))
  if (key === 'mem_total') return toSortableNumber(inspectMetric(row, 'mem_total_gb') || row?.memory_gb)
  if (key === 'load1') return toSortableNumber(inspectMetric(row, 'load1'))
  if (key === 'load') return toSortableNumber(inspectMetric(row, 'load5'))
  if (key === 'load15') return toSortableNumber(inspectMetric(row, 'load15'))
  if (key === 'uptime') return toSortableNumber(inspectMetric(row, 'uptime_seconds'))
  if (key === 'disk_mount') return String(highestDisk(row)?.mountpoint || highestDisk(row)?.mount || '').toLowerCase()
  if (key === 'disk') return highestDiskUsage(row)
  if (key === 'disk_size') return toSortableNumber(highestDisk(row)?.total_gb ?? highestDisk(row)?.size_gb)
  if (key === 'network') {
    const receive = toSortableNumber(inspectMetric(row, 'net_recv_mbps'))
    const send = toSortableNumber(inspectMetric(row, 'net_send_mbps'))
    return receive === null && send === null ? null : (receive || 0) + (send || 0)
  }
  if (key === 'network_rx') return toSortableNumber(inspectMetric(row, 'net_recv_mbps'))
  if (key === 'network_tx') return toSortableNumber(inspectMetric(row, 'net_send_mbps'))
  if (key === 'diskio') {
    const read = toSortableNumber(inspectMetric(row, 'disk_read_mbps'))
    const write = toSortableNumber(inspectMetric(row, 'disk_write_mbps'))
    return read === null && write === null ? null : (read || 0) + (write || 0)
  }
  if (key === 'disk_read') return toSortableNumber(inspectMetric(row, 'disk_read_mbps'))
  if (key === 'disk_write') return toSortableNumber(inspectMetric(row, 'disk_write_mbps'))
  if (key === 'tcp') return toSortableNumber(inspectMetric(row, 'tcp_estab'))
  if (key === 'tcp_tw') return toSortableNumber(inspectMetric(row, 'tcp_tw'))
  if (key === 'issues') return issueCount(row)
  return ''
}

function setInspectSort(key) {
  if (inspectSortKey.value === key) inspectSortAsc.value = !inspectSortAsc.value
  else {
    inspectSortKey.value = key
    inspectSortAsc.value = ['hostname', 'ip', 'os', 'disk_mount'].includes(key)
  }
}

function inspectSortIcon(key) {
  if (inspectSortKey.value !== key) return '⇅'
  return inspectSortAsc.value ? '↑' : '↓'
}

const sortedInspectResults = computed(() => {
  const list = [...inspectResults.value]
  list.sort((left, right) => {
    const leftValue = inspectSortValue(left, inspectSortKey.value)
    const rightValue = inspectSortValue(right, inspectSortKey.value)
    let result
    if (leftValue === null && rightValue !== null) return 1
    if (leftValue !== null && rightValue === null) return -1
    if (leftValue === null && rightValue === null) result = 0
    else if (typeof leftValue === 'number' && typeof rightValue === 'number') {
      result = leftValue - rightValue
    } else {
      result = String(leftValue).localeCompare(String(rightValue), 'zh-CN', { numeric: true, sensitivity: 'base' })
    }
    if (result === 0) {
      result = String(left?.hostname || left?.ip || '').localeCompare(String(right?.hostname || right?.ip || ''), 'zh-CN', { numeric: true, sensitivity: 'base' })
    }
    return inspectSortAsc.value ? result : -result
  })
  return list
})

function mbpsText(value) {
  if (value === null || value === undefined || value === '') return '-'
  const numberValue = Number(value)
  if (!Number.isFinite(numberValue)) return '-'
  return `${numberValue.toFixed(numberValue >= 10 ? 1 : 2)}MB/s`
}

function uptimeFromSeconds(value) {
  const seconds = Number(value)
  if (!Number.isFinite(seconds) || seconds < 0) return '-'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return `${days ? `${days}天` : ''}${hours || days ? `${hours}小时` : ''}${minutes}分钟`
}

function inspectUptimeText(row) {
  return uptimeFromSeconds(inspectMetric(row, 'uptime_seconds'))
}

function uptimeDaysText(row) {
  const seconds = Number(inspectMetric(row, 'uptime_seconds'))
  if (!Number.isFinite(seconds) || seconds < 0) return '-'
  return `${(seconds / 86400).toFixed(1)}天`
}

function inspectPartitions(row) {
  const partitions = Array.isArray(row?.partitions) ? [...row.partitions] : []
  const priority = ['/', '/data', '/var', '/home', '/boot', '/boot/efi']
  partitions.sort((left, right) => {
    const leftMount = left.mountpoint || left.mount || ''
    const rightMount = right.mountpoint || right.mount || ''
    const leftIndex = priority.indexOf(leftMount)
    const rightIndex = priority.indexOf(rightMount)
    if (leftIndex !== -1 || rightIndex !== -1) return (leftIndex === -1 ? 999 : leftIndex) - (rightIndex === -1 ? 999 : rightIndex)
    return String(leftMount).localeCompare(String(rightMount))
  })
  return partitions
}

function abnormalChecks(row) {
  return (row?.checks || []).filter(check => check.status !== 'normal')
}

async function runInspect() {
  inspecting.value = true
  inspectError.value = ''
  inspectResults.value = []
  inspectAiSummary.value = ''
  inspectNotifyMessage.value = ''
  Object.assign(inspectSummary, {
    total: 0,
    normal: 0,
    warning: 0,
    critical: 0,
    group_id: inspectGroupId.value || '',
    group_name: '',
    metrics_updated_at: '',
    metrics_updated_count: 0,
    metrics_missing_count: 0,
    metrics_fallback_count: 0,
  })
  const url = `/api/hosts/inspect${inspectGroupId.value ? `?group_id=${encodeURIComponent(inspectGroupId.value)}` : ''}`
  const es = new EventSource(url)
  es.onmessage = async (e) => {
    if (e.data === '[DONE]') {
      es.close()
      inspecting.value = false
      await loadHosts()
      if (inspectSummary.metrics_updated_count > 0) {
        inspectNotifyStatus.value = 'ok'
        const fallback = inspectSummary.metrics_fallback_count ? `，其中 ${inspectSummary.metrics_fallback_count} 台使用 SSH/Python 兜底` : ''
        inspectNotifyMessage.value = `已自动获取并更新 ${inspectSummary.metrics_updated_count} 台服务器指标${fallback}`
      } else if (inspectResults.value.length) {
        inspectNotifyStatus.value = 'err'
        inspectNotifyMessage.value = '未获取到服务器指标，请检查 Prometheus / node_exporter 配置'
      }
      return
    }
    try {
      const msg = JSON.parse(e.data)
      if (msg.type === 'inspect_data') {
        inspectResults.value = msg.data
        Object.assign(inspectSummary, msg.summary)
      } else if (msg.type === 'error') {
        inspectError.value = msg.message
        inspecting.value = false
        es.close()
      }
    } catch {}
  }
  es.onerror = () => { inspectError.value = '连接失败'; inspecting.value = false; es.close() }
}

async function runInspectAI() {
  inspectAiStreaming.value = true
  inspectAiSummary.value = ''
  inspectAiFallback.value = false
  const url = `/api/hosts/inspect/ai`
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ results: inspectResults.value, summary: inspectSummary }),
  })
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop()
    for (const line of lines) {
      if (!line.startsWith('data:')) continue
      const raw = line.slice(5).trim()
      if (raw === '[DONE]') { inspectAiStreaming.value = false; return }
      try {
        const msg = JSON.parse(raw)
        if (msg.type === 'ai_meta') { inspectAiProvider.value = msg.provider; inspectAiFallback.value = msg.fallback }
        if (msg.type === 'ai_chunk') inspectAiSummary.value += msg.text
      } catch {}
    }
  }
  inspectAiStreaming.value = false
}

async function openInspectRca() {
  const abnormal = inspectResults.value.filter(item => item.overall !== 'normal').slice(0, 20)
  const result = await api.rcaTrigger({
    service: inspectGroupId.value || 'host-inspection',
    alert_name: inspectGroupId.value ? `涓绘満宸℃寮傚父 / ${inspectSummary.group_name || inspectGroupId.value}` : '涓绘満宸℃寮傚父',
    hours: 1,
    extra_context: inspectAiSummary.value || `宸℃鍙戠幇涓ラ噸 ${inspectSummary.critical} 鍙帮紝璀﹀憡 ${inspectSummary.warning} 鍙?`,
    source_type: 'inspection',
    source_id: inspectSummary.group_id || 'all-hosts',
    source_name: inspectSummary.group_name || '鍏ㄩ儴涓绘満',
    inspection_summary: { ...inspectSummary },
    inspection_results: abnormal,
  })
  if (result?.rca_id) {
    router.push({ path: '/aiops/rca', query: { rca_id: result.rca_id } })
  }
}

async function notifyGroups() {
  notifyingGroups.value = true
  inspectNotifyMessage.value = ''
  try {
    const res = await api.notifyInspectGroups({ results: inspectResults.value, summary: inspectSummary, group_id: inspectGroupId.value })
    inspectNotifyMessage.value = res.message
    inspectNotifyStatus.value = res.ok ? 'ok' : 'err'
  } catch (e) {
    inspectNotifyMessage.value = '推送失败：' + (typeof e === 'string' ? e : '未知错误')
    inspectNotifyStatus.value = 'err'
  } finally {
    notifyingGroups.value = false
  }
}

async function downloadInspectExcel() {
  excelDownloading.value = true
  try {
    const resp = await fetch('/api/hosts/inspect/excel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ results: inspectResults.value, summary: inspectSummary, ai_text: inspectAiSummary.value }),
    })
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `主机巡检_${new Date().toLocaleDateString('zh-CN')}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    alert('下载失败')
  } finally {
    excelDownloading.value = false
  }
}

// ── 分组管理 ──────────────────────────────────────────────────────────────────
const showGroupModal = ref(false)
const editingGroup   = ref(null)
const savingGroup    = ref(false)
const groupFormError = ref('')
const groupForm = reactive({
  name: '', description: '', feishu_webhook: '', feishu_keyword: '',
  dingtalk_webhook: '', dingtalk_keyword: '', schedule_time: '09:00', schedule_enabled: false,
  alert_matchers_text: '',
})

function alertMatchersToText(matchers = []) {
  return (matchers || [])
    .filter(item => item?.label)
    .map(item => `${item.label}=${item.value || ''}`)
    .join('\n')
}

function parseAlertMatcherText(text = '') {
  const seen = new Set()
  const result = []
  for (const rawLine of String(text || '').split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line) continue
    const idx = line.indexOf('=')
    const label = (idx === -1 ? line : line.slice(0, idx)).trim()
    const value = (idx === -1 ? '' : line.slice(idx + 1)).trim()
    if (!label) continue
    const uniq = `${label}\u0000${value}`
    if (seen.has(uniq)) continue
    seen.add(uniq)
    result.push({ label, value })
  }
  return result
}

function formatAlertMatcherPreview(matchers = []) {
  return (matchers || [])
    .slice(0, 3)
    .map(item => `${item.label}=${item.value || '*'}`)
    .join('，') + ((matchers || []).length > 3 ? ' …' : '')
}

function openAddGroup() {
  editingGroup.value = null
  groupFormError.value = ''
  Object.assign(groupForm, {
    name: '', description: '', feishu_webhook: '', feishu_keyword: '',
    dingtalk_webhook: '', dingtalk_keyword: '', schedule_time: '09:00',
    schedule_enabled: false, alert_matchers_text: '',
  })
  showGroupModal.value = true
}

function openEditGroup(g) {
  editingGroup.value = g
  groupFormError.value = ''
  Object.assign(groupForm, {
    name: g.name,
    description: g.description || '',
    feishu_webhook: g.feishu_webhook || '',
    feishu_keyword: g.feishu_keyword || '',
    dingtalk_webhook: g.dingtalk_webhook || '',
    dingtalk_keyword: g.dingtalk_keyword || '',
    schedule_time: g.schedule_time || '09:00',
    schedule_enabled: !!g.schedule_enabled,
    alert_matchers_text: alertMatchersToText(g.alert_matchers),
  })
  showGroupModal.value = true
}

async function saveGroup() {
  groupFormError.value = ''
  if (!groupForm.name.trim()) { groupFormError.value = '分组名称不能为空'; return }
  savingGroup.value = true
  try {
    const payload = {
      name: groupForm.name,
      description: groupForm.description,
      feishu_webhook: groupForm.feishu_webhook,
      feishu_keyword: groupForm.feishu_keyword,
      dingtalk_webhook: groupForm.dingtalk_webhook,
      dingtalk_keyword: groupForm.dingtalk_keyword,
      schedule_time: groupForm.schedule_time,
      schedule_enabled: groupForm.schedule_enabled,
      alert_matchers: parseAlertMatcherText(groupForm.alert_matchers_text),
    }
    if (editingGroup.value) {
      await api.updateGroup(editingGroup.value.id, payload)
    } else {
      await api.createGroup(payload)
    }
    showGroupModal.value = false
    await loadGroups()
  } catch (e) {
    groupFormError.value = typeof e === 'string' ? e : '保存失败'
  } finally {
    savingGroup.value = false
  }
}

async function deleteGroup(g) {
  if (!confirm(`确定删除分组「${g.name}」？已分配该组的主机将清除分组关联。`)) return
  try {
    await api.deleteGroup(g.id)
    await loadGroups()
    await loadHosts()
  } catch (e) {
    alert('删除失败：' + (typeof e === 'string' ? e : '未知'))
  }
}
</script>

<style scoped>
.cmdb-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; padding: 16px; gap: 12px; }

/* 统计 */
.stats-row { display: flex; gap: 10px; flex-shrink: 0; }
.stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 12px 18px; min-width: 90px; }
.stat-card.ok .stat-val { color: var(--success); }
.stat-card.warn .stat-val { color: var(--warning); }
.stat-card.error .stat-val { color: var(--error); }
.stat-val { font-size: 22px; font-weight: 700; line-height: 1.2; }
.stat-label { font-size: 11px; color: var(--text-muted); margin-top: 2px; }

/* 工具栏 */
.toolbar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; flex-shrink: 0; }
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; align-items: center; gap: 6px; margin-left: auto; flex-wrap: wrap; }
.tab-group { display: flex; background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.tab-btn { padding: 6px 14px; font-size: 13px; border: none; background: transparent; color: var(--text-secondary); cursor: pointer; transition: background 0.15s; white-space: nowrap; }
.tab-btn:hover { background: var(--bg-hover); }
.tab-btn.active { background: var(--accent); color: #fff; }
.tab-count { display: inline-block; padding: 1px 8px; margin-left: 6px; border-radius: 99px; font-size: 11px; background: var(--bg-surface); color: var(--text-muted); }
.tab-count.warn { background: rgba(189,86,79,.14); color: var(--error); font-weight: 600; }

/* CMDB 浮动批量操作栏 */
.cmdb-batch-bar {
  position: fixed;
  left: 50%; bottom: 24px; transform: translateX(-50%);
  background: var(--bg-card);
  border: 1px solid var(--border-strong);
  border-radius: 14px;
  box-shadow: var(--shadow-md);
  padding: 10px 16px;
  display: flex; align-items: center; gap: 10px;
  z-index: 100;
  font-size: 12.5px;
}
.cb-count strong { color: var(--accent); font-weight: 700; margin: 0 3px; }
.cb-sep { width: 1px; height: 18px; background: var(--border); }
.cb-result { color: var(--success); font-size: 11.5px; }
.batch-select {
  background: var(--bg-input); border: 1px solid var(--border); border-radius: 8px;
  padding: 5px 10px; font-size: 12px; color: inherit; min-width: 110px;
}
.row-selected td { background: rgba(217,119,87,.06) !important; }
.batch-slide-enter-active, .batch-slide-leave-active { transition: transform .25s ease, opacity .2s ease; }
.batch-slide-enter-from, .batch-slide-leave-to { transform: translateX(-50%) translateY(24px); opacity: 0; }
.select-col { width: 36px; text-align: center; }
.select-col input { width: auto; cursor: pointer; }
.btn.danger { color: var(--error); border-color: var(--error); }
.btn.danger:hover { background: rgba(189,86,79,.08); }
.tab-btn.active .tab-count { background: var(--accent-soft); color: var(--accent); }
.credentials-tab-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }
.credential-panel { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 10px; }
.credential-panel-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
}
.credential-panel-title { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.credential-panel-sub { margin-top: 3px; font-size: 12px; color: var(--text-muted); }
.credential-kpis { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.credential-kpis span {
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--bg-input);
  border: 1px solid var(--border-faint, var(--border));
  color: var(--text-muted);
  font-size: 11px;
}
.credential-form-card,
.credential-list-card {
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  padding: 12px;
}
.credential-form-title,
.credential-list-title { font-size: 13px; font-weight: 700; color: var(--text-primary); }
.credential-list-sub { margin-top: 2px; font-size: 11px; color: var(--text-muted); }
.credential-form-grid {
  display: grid;
  grid-template-columns: minmax(180px, 1.5fr) minmax(140px, 1fr) minmax(180px, 1.4fr) 100px auto;
  gap: 10px;
  align-items: end;
  margin-top: 10px;
}
.credential-port-field { min-width: 90px; }
.credential-form-actions { display: flex; align-items: center; gap: 8px; justify-content: flex-end; }
.credential-list-card { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.credential-list-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 10px; flex-shrink: 0; }
.credential-table-wrap { flex: 1; min-height: 0; overflow: auto; border: 1px solid var(--border-faint, var(--border)); border-radius: 8px; }
.credential-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.credential-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--bg-header);
  padding: 8px 10px;
  text-align: left;
  font-weight: 600;
  font-size: 11px;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.credential-table td { padding: 8px 10px; border-bottom: 1px solid var(--border-faint, var(--border)); white-space: nowrap; }
.credential-table tbody tr:hover { background: var(--bg-hover); }
.credential-name-cell { display: flex; flex-direction: column; gap: 2px; min-width: 180px; }
.credential-name { font-weight: 600; color: var(--text-primary); }
.credential-id { color: var(--text-muted); font-size: 11px; font-family: 'Cascadia Code','Consolas',monospace; }
.credential-bind-count {
  display: inline-flex;
  min-width: 48px;
  justify-content: center;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(63,185,80,.12);
  color: var(--success);
  font-size: 11px;
}
.credential-bind-count.empty { background: var(--bg-input); color: var(--text-muted); }
.credential-actions { display: flex; align-items: center; gap: 6px; }
.credential-empty { min-height: 220px; border: 1px dashed var(--border); border-radius: 8px; background: var(--bg-input); }
@media (max-width: 1180px) {
  .credential-form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .credential-form-actions { justify-content: flex-start; }
}
@media (max-width: 720px) {
  .credential-panel-head,
  .credential-list-head { align-items: flex-start; flex-direction: column; }
  .credential-kpis { justify-content: flex-start; }
  .credential-form-grid { grid-template-columns: 1fr; }
}
.search-input { padding: 5px 10px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 13px; width: 200px; }
.filter-select { padding: 5px 8px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 12px; }

/* 紧凑 filter-group: 图标 + 内嵌输入/下拉，整体节省横向空间 */
.filter-group {
  display: inline-flex; align-items: center;
  border: 1px solid var(--border); border-radius: 5px;
  background: var(--bg-input);
  overflow: hidden;
  transition: border-color .15s, box-shadow .15s;
}
.filter-group:focus-within { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim, rgba(99, 102, 241, .15)); }
.filter-group:has(input:disabled),
.filter-group:has(select:disabled) { opacity: .55; }
.filter-icon { padding: 0 4px 0 8px; font-size: 12px; color: var(--text-muted); user-select: none; pointer-events: none; }
.filter-group .search-input {
  width: 140px;
  padding: 5px 10px 5px 2px;
  border: 0; outline: none; background: transparent;
  font-size: 13px;
  transition: width .2s ease;
}
.filter-group .search-input:focus { width: 220px; }
.filter-group .filter-select {
  padding: 5px 22px 5px 2px;
  min-width: 92px; max-width: 160px;
  border: 0; outline: none; background: transparent;
  cursor: pointer; font-size: 12px;
  appearance: none;
  -webkit-appearance: none;
  background-image: linear-gradient(45deg, transparent 50%, var(--text-muted) 50%),
                    linear-gradient(135deg, var(--text-muted) 50%, transparent 50%);
  background-position: calc(100% - 12px) 50%, calc(100% - 7px) 50%;
  background-size: 5px 5px;
  background-repeat: no-repeat;
}

/* 内容区 */
.content-row { display: flex; gap: 10px; flex: 1; overflow: hidden; min-height: 0; }
.content-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; gap: 10px; }

/* 表格 */
.cmdb-tab-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }
.table-wrap { flex: 1; overflow: auto; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; }
.host-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.host-table thead { position: sticky; top: 0; z-index: 2; }
.host-table th { background: var(--bg-header); padding: 8px 10px; text-align: left; font-weight: 600; font-size: 11px; color: var(--text-muted); white-space: nowrap; border-bottom: 1px solid var(--border); }
.host-table td { padding: 7px 10px; border-bottom: 1px solid var(--border-faint, var(--border)); white-space: nowrap; }
.host-table tbody tr:hover { background: var(--bg-hover); cursor: pointer; }
.th-sort { cursor: pointer; user-select: none; }
.th-sort:hover { color: var(--text-primary); }
.sort-icon { font-size: 10px; margin-left: 3px; opacity: 0.6; }
.hostname-cell { white-space: normal; }
.hostname-stack, .field-cell, .status-cell { display: flex; flex-direction: column; gap: 3px; white-space: normal; }
.hostname-line, .status-line { display: inline-flex; align-items: center; gap: 5px; }
.hostname { font-weight: 500; }
.ssh-badge { font-size: 10px; padding: 1px 5px; border-radius: 3px; background: rgba(56,139,253,.15); color: var(--accent); }
.mono { font-family: 'Cascadia Code','Consolas',monospace; font-size: 12px; }
.small-text { font-size: 12px; color: var(--text-muted); }
.runtime-cell { display: flex; flex-direction: column; gap: 2px; line-height: 1.25; white-space: normal; }
.field-sync { display: inline-block; max-width: 180px; padding: 2px 6px; border-radius: 6px; font-size: 11px; line-height: 1.35; white-space: normal; word-break: break-word; }
.field-sync.ok { background: rgba(63,185,80,.12); color: var(--success); }
.field-sync.err { background: rgba(248,81,73,.12); color: var(--error); }
.field-updated { background: rgba(63,185,80,.08); box-shadow: inset 2px 0 0 var(--success); }
.action-cell { display: flex; gap: 4px; }

/* 状态 */
.status-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; }
.status-dot.active { background: var(--success); }
.status-dot.offline { background: var(--error); }
.status-dot.maintenance { background: var(--warning); }
.status-text { font-size: 12px; }

/* 平台/环境标签 */
.platform-badge { font-size: 11px; padding: 1px 6px; border-radius: 3px; background: var(--bg-hover); }
.platform-badge.linux { background: rgba(63,185,80,.12); color: var(--success); }
.platform-badge.windows { background: rgba(56,139,253,.12); color: var(--accent); }
.env-badge { font-size: 11px; padding: 1px 6px; border-radius: 3px; }
.env-badge.production { background: rgba(248,81,73,.12); color: var(--error); }
.env-badge.staging { background: rgba(210,153,34,.12); color: var(--warning); }
.env-badge.development { background: rgba(63,185,80,.12); color: var(--success); }
.env-badge.testing { background: rgba(56,139,253,.12); color: var(--accent); }
.env-badge.dr { background: rgba(188,130,255,.12); color: #bc82ff; }
.group-badge-inline { font-size: 10px; padding: 1px 6px; border-radius: 10px; background: var(--bg-hover); color: var(--text-muted); }

/* 按钮 */
.btn { display: inline-flex; align-items: center; gap: 5px; padding: 5px 12px; border-radius: 5px; border: 1px solid transparent; font-size: 13px; cursor: pointer; white-space: nowrap; transition: all 0.15s; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.btn-outline { background: transparent; border-color: var(--border); color: var(--text-secondary); }
.btn-outline:hover { background: var(--bg-hover); }
.btn-ai { background: linear-gradient(135deg, #7c3aed, #2563eb); color: #fff; border: none; }
.btn-excel { background: rgba(63,185,80,.15); color: var(--success); border-color: var(--success); }
.btn-danger { background: rgba(248,81,73,.12); color: var(--error); border-color: var(--error); }
.btn-danger:hover { background: rgba(248,81,73,.22); }
.btn-sync { background: rgba(56,139,253,.12); color: var(--accent); border-color: var(--accent); }
.btn-sync:hover { background: rgba(56,139,253,.22); }
.btn-xs { padding: 2px 7px; font-size: 11px; }
.sync-msg { display: flex; flex-direction: column; gap: 4px; font-size: 12px; padding: 5px 10px; border-radius: 5px; }
.sync-msg.ok { background: rgba(63,185,80,.12); color: var(--success); }
.sync-msg.err { background: rgba(248,81,73,.12); color: var(--error); }
.file-input { padding: 5px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 13px; width: 100%; box-sizing: border-box; cursor: pointer; }
.import-result { font-size: 12px; padding: 8px 12px; border-radius: 5px; margin-top: 6px; }
.import-result.ok { background: rgba(99,130,91,.14); color: var(--success); }
.import-result.err { background: rgba(189,86,79,.12); color: var(--error); }

/* ── 导入向导样式 ──────────────────────────────────────────── */
.step-hint { color: var(--text-muted); font-size: 11px; margin-left: 8px; font-weight: 400; }
.wiz-intro { display: flex; gap: 12px; padding: 14px 16px; background: var(--bg-surface); border-radius: 10px; margin-bottom: 14px; }
.wiz-intro-icon { font-size: 26px; flex-shrink: 0; }
.wiz-intro-title { font-weight: 600; margin-bottom: 6px; font-size: 13px; }
.wiz-intro-sub { font-size: 12px; color: var(--text-secondary); line-height: 1.6; }
.wiz-actions-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.wiz-sep { color: var(--text-muted); font-size: 12px; }
.wiz-upload-btn { position: relative; cursor: pointer; }
.wiz-file-name { font-size: 12px; color: var(--text-secondary); padding: 4px 10px; background: var(--bg-surface); border-radius: 6px; }
.wiz-summary { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; margin-bottom: 14px; }
.wiz-stat { background: var(--bg-surface); border-radius: 8px; padding: 8px 10px; display: flex; flex-direction: column; gap: 2px; }
.wiz-stat span { font-size: 10.5px; color: var(--text-muted); }
.wiz-stat strong { font-size: 18px; font-weight: 600; }
.wiz-stat strong.ok { color: var(--success); }
.wiz-stat strong.warn { color: var(--warning); }
.wiz-stat strong.err { color: var(--error); }
.wiz-stat strong.info { color: var(--accent); }
.wiz-stat strong.muted { color: var(--text-muted); }
.wiz-auto-create { background: rgba(217,119,87,.06); border: 1px solid rgba(217,119,87,.18); border-radius: 8px; padding: 10px 12px; font-size: 12px; margin-bottom: 12px; line-height: 1.8; }
.wiz-chip { display: inline-block; padding: 1px 8px; margin: 2px 4px 2px 0; background: var(--bg-card); border: 1px solid var(--border); border-radius: 99px; font-size: 11px; color: var(--text-secondary); }
.wiz-rows { margin-bottom: 12px; }
.wiz-rows-title { font-size: 12px; font-weight: 600; margin-bottom: 6px; color: var(--text-secondary); }
.wiz-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.wiz-table th { padding: 6px 10px; font-size: 11px; color: var(--text-muted); border-bottom: 1px solid var(--border); text-align: left; }
.wiz-table td { padding: 6px 10px; border-bottom: 1px solid var(--border-light); }
.wiz-errors { background: rgba(189,86,79,.06); border: 1px solid rgba(189,86,79,.2); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px; font-size: 12px; color: var(--error); }
.wiz-err-line { font-family: var(--font-mono); font-size: 11px; padding: 1px 0; }
.chk { display: flex; align-items: center; gap: 6px; cursor: pointer; color: var(--text-secondary); }
.chk input { width: auto; }
.sync-all-bar { flex-shrink: 0; padding: 8px 12px; background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; margin-bottom: 8px; }
.sync-all-progress { display: flex; align-items: center; gap: 10px; font-size: 12px; }
.sync-all-label { color: var(--text-muted); white-space: nowrap; }
.sync-all-stat { color: var(--text-muted); white-space: nowrap; }
.progress-track { flex: 1; height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--accent); border-radius: 3px; transition: width .3s; }
.sync-all-done { font-size: 12px; display: flex; align-items: center; }
.sync-all-done.ok { color: var(--success); }
.sync-all-done.warn { color: var(--warning); }

/* 详情面板 tabs */
.detail-tabs { display: flex; gap: 2px; }
.detail-tab { padding: 3px 12px; font-size: 12px; border: 1px solid var(--border); border-radius: 4px; background: transparent; color: var(--text-muted); cursor: pointer; }
.detail-tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }

/* 进程列表 */
.proc-loading { display: flex; align-items: center; gap: 8px; color: var(--text-muted); font-size: 12px; padding: 20px 0; }
.proc-error { font-size: 12px; color: var(--error); padding: 8px; background: rgba(248,81,73,.08); border-radius: 5px; }
.proc-services-row { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 8px; }
.proc-svc-badge { font-size: 10px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
.proc-list { display: flex; flex-direction: column; gap: 5px; }
.proc-item { background: var(--bg-hover); border: 1px solid var(--border-faint, var(--border)); border-radius: 6px; padding: 7px 10px; }
.proc-item.proc-service { border-color: var(--accent); background: rgba(56,139,253,.05); }
.proc-top-row { display: flex; align-items: center; gap: 5px; font-size: 12px; margin-bottom: 3px; }
.proc-rank { font-size: 10px; color: var(--text-muted); min-width: 16px; }
.proc-svc-tag { font-size: 10px; padding: 1px 6px; border-radius: 3px; font-weight: 600; white-space: nowrap; }
.proc-comm { font-weight: 600; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100px; }
.proc-spacer { flex: 1; }
.proc-cpu { font-size: 11px; font-weight: 600; }
.proc-cpu.cpu-high { color: var(--error); }
.proc-cpu.cpu-mid  { color: var(--warning); }
.sync-time-cell { white-space: normal; min-width: 168px; }
.sync-time-stack { display: flex; flex-direction: column; line-height: 1.25; }
.sync-time-relative { color: var(--text-muted); font-size: 11px; margin-top: 2px; }
.sync-ok    { color: var(--success, #3fb950); }
.sync-warn  { color: var(--warning, #d29922); }
.sync-stale { color: var(--error, #f85149); }
.no-sync    { color: var(--text-muted); }
.proc-mem { font-size: 11px; color: var(--text-muted); }
.proc-meta-row { display: flex; gap: 6px; font-size: 10px; color: var(--text-muted); }
.proc-args { font-size: 10px; color: var(--text-muted); font-family: 'Cascadia Code','Consolas',monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 2px; cursor: help; }

/* 服务色系 */
.svc-mysql    { background: rgba(0,117,143,.15);   color: #00758f; }
.svc-java     { background: rgba(237,106,41,.15);  color: #ed6a29; }
.svc-python   { background: rgba(55,118,171,.15);  color: #3776ab; }
.svc-node     { background: rgba(104,160,99,.15);  color: #68a063; }
.svc-nginx    { background: rgba(0,152,68,.15);    color: #009844; }
.svc-redis    { background: rgba(220,50,50,.15);   color: #dc3232; }
.svc-postgres { background: rgba(51,103,145,.15);  color: #336791; }
.svc-elastic  { background: rgba(254,197,0,.15);   color: #c9a800; }
.svc-docker   { background: rgba(0,159,227,.15);   color: #009fe3; }
.svc-k8s      { background: rgba(50,108,229,.15);  color: #326ce5; }
.svc-mongo    { background: rgba(77,179,61,.15);   color: #4db33d; }
.svc-rabbit   { background: rgba(255,108,0,.15);   color: #ff6c00; }
.svc-kafka    { background: rgba(33,33,33,.12);    color: var(--text-secondary); }
.svc-ssh      { background: rgba(100,100,100,.1);  color: var(--text-muted); }
.svc-php      { background: rgba(119,123,180,.15); color: #777bb4; }
.svc-go       { background: rgba(0,173,216,.15);   color: #00acd8; }
.svc-default  { background: var(--bg-hover); color: var(--text-muted); }

/* 空状态 */
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); gap: 8px; }
.empty-state .icon { font-size: 32px; }
.spinner { display: inline-block; width: 18px; height: 18px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 详情面板 */
.detail-panel { width: 360px; flex-shrink: 0; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; display: flex; flex-direction: column; overflow: hidden; }
.detail-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; font-weight: 600; font-size: 13px; border-bottom: 1px solid var(--border); }
.detail-body { flex: 1; overflow-y: auto; padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; }
.detail-row { display: flex; gap: 6px; font-size: 12px; }
.dl { color: var(--text-muted); min-width: 64px; flex-shrink: 0; }
.dv { color: var(--text-primary); word-break: break-all; }
.detail-actions { margin-top: 8px; }
.detail-section-title { margin-top: 6px; padding-top: 8px; border-top: 1px solid var(--border); font-size: 12px; font-weight: 600; color: var(--text-muted); }
.metric-grid { display: grid; grid-template-columns: 1fr; gap: 6px; }
.metric-tile { padding: 7px 9px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-input); font-size: 12px; }
.metric-tile span { display: block; color: var(--text-muted); margin-bottom: 3px; }
.metric-tile b { color: var(--text-primary); font-weight: 600; word-break: break-all; }
.metric-tile.ok b, .disk-status-head b.ok { color: var(--success); }
.metric-tile.warn b, .disk-status-head b.warn { color: var(--warning); }
.metric-tile.crit b, .disk-status-head b.crit { color: var(--error); }
.disk-status-list { display: flex; flex-direction: column; gap: 8px; margin-top: 2px; }
.disk-status-item { padding: 7px 9px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-input); }
.disk-status-head { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; }
.disk-status-head span { color: var(--text-primary); font-weight: 600; }
.disk-bar { height: 5px; margin: 6px 0; border-radius: 999px; background: var(--bg-hover); overflow: hidden; }
.disk-bar i { display: block; height: 100%; border-radius: inherit; background: var(--success); }
.disk-bar i.warn { background: var(--warning); }
.disk-bar i.crit { background: var(--error); }
.disk-status-meta { color: var(--text-muted); font-size: 11px; }
.label-chip-detail { font-size: 11px; padding: 1px 6px; border-radius: 3px; background: var(--bg-hover); margin-right: 3px; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 14px; }

/* 巡检 */
.inspect-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; gap: 10px; }
.merged-inspect-wrap {
  flex: 1;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-card);
  padding: 10px;
}
.merged-inspect-wrap.is-empty {
  min-height: 0;
}
.inspect-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-shrink: 0;
}
.inspect-panel-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}
.inspect-panel-sub {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}
.inspect-panel-kpis {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--text-muted);
  font-size: 11px;
}
.inspect-panel-kpis span {
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--bg-input);
}
.inspect-scope-bar { display: flex; align-items: center; gap: 8px; font-size: 12px; flex-shrink: 0; }
.inspect-scope-label { color: var(--text-muted); }
.inspect-scope-badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.inspect-scope-badge.all { background: rgba(56,139,253,.12); color: var(--accent); }
.inspect-scope-badge.group { background: rgba(63,185,80,.12); color: var(--success); }
.inspect-scope-stat { color: var(--text-muted); }
.inspect-notify-msg { font-size: 12px; padding: 5px 10px; border-radius: 5px; flex-shrink: 0; }
.inspect-notify-msg.ok { background: rgba(63,185,80,.12); color: var(--success); }
.inspect-notify-msg.err { background: rgba(248,81,73,.12); color: var(--error); }
.inspect-ai-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; flex-shrink: 0; }
.inspect-ai-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px; }
.inspect-ai-title { font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
.inspect-ai-provider { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.inspect-ai-badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: rgba(56,139,253,.12); color: var(--accent); }
.inspect-ai-badge.fallback { background: rgba(210,153,34,.12); color: var(--warning); }
.inspect-ai-badge.streaming { background: rgba(124,58,237,.12); color: #7c3aed; }
.inspect-ai-content { font-size: 12px; line-height: 1.6; color: var(--text-secondary); white-space: pre-wrap; max-height: 200px; overflow-y: auto; }
.ai-placeholder { color: var(--text-muted); }
.ai-cursor { display: inline-block; width: 2px; height: 13px; background: var(--accent); margin-left: 2px; animation: blink 1s step-end infinite; vertical-align: middle; }
.ai-thinking-dot { width: 8px; height: 8px; border-radius: 50%; background: #7c3aed; animation: pulse 1s ease-in-out infinite; display: inline-block; }
.ai-toggle-btn { font-size: 11px; padding: 2px 8px; border-radius: 4px; border: 1px solid var(--border); background: transparent; color: var(--text-muted); cursor: pointer; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }
.inspect-table-wrap { flex: 1; overflow: auto; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; }
.inspect-table { width: 100%; border-collapse: collapse; font-size: 12px; table-layout: auto; }
.inspect-table th, .inspect-table td { padding: 8px 10px; box-sizing: border-box; }
.inspect-table th { position: sticky; top: 0; background: var(--bg-header); text-align: left; font-weight: 600; font-size: 11px; color: var(--text-muted); border-bottom: 1px solid var(--border); white-space: nowrap; }
.inspect-table td { border-bottom: 1px solid var(--border-faint, var(--border)); white-space: nowrap; vertical-align: middle; }
.inspect-table th.th-sort { cursor: pointer; user-select: none; }
.inspect-table th.th-sort:hover { color: var(--text-primary); }
.irow-warning { background: rgba(210,153,34,.04); }
.irow-critical { background: rgba(248,81,73,.06); }
.inspect-badge { font-size: 11px; padding: 2px 7px; border-radius: 10px; }
.inspect-badge.normal { background: rgba(63,185,80,.12); color: var(--success); }
.inspect-badge.warning { background: rgba(210,153,34,.12); color: var(--warning); }
.inspect-badge.critical { background: rgba(248,81,73,.12); color: var(--error); }
.check-cell { font-size: 11px; padding: 1px 5px; border-radius: 3px; }
.check-cell.normal { background: rgba(63,185,80,.1); color: var(--success); }
.check-cell.warning { background: rgba(210,153,34,.1); color: var(--warning); }
.check-cell.critical { background: rgba(248,81,73,.1); color: var(--error); }
.check-na { color: var(--text-muted); }
.itd-host { font-weight: 500; }
.inspect-host-name { color: var(--text-primary); font-weight: 600; }
.inspect-host-meta { color: var(--text-muted); font-size: 11px; margin-top: 3px; }
.itd-meta, .itd-ip, .itd-os, .itd-group { color: var(--text-muted); }
.itd-meta { min-width: 150px; line-height: 1.45; white-space: normal !important; }
/* td 必须保持 table-cell；用 block 子元素堆叠主值/副值，不要 display:flex 否则破列对齐 */
.inspect-metric-cell { min-width: 88px; color: var(--text-muted); line-height: 1.4; white-space: nowrap; vertical-align: middle; }
.inspect-metric-cell.compact { min-width: 72px; }
.inspect-metric-cell b { display: block; color: var(--text-primary); font-weight: 600; }
.inspect-metric-cell span { display: block; font-size: 11px; }
.inspect-metric-cell b { color: var(--text-primary); font-weight: 600; }
.inspect-metric-cell span { font-size: 11px; }
.inspect-metric-cell b.ok, .inspect-disk-line b.ok { color: var(--success); }
.inspect-metric-cell b.warn, .inspect-disk-line b.warn { color: var(--warning); }
.inspect-metric-cell b.crit, .inspect-disk-line b.crit { color: var(--error); }
.inspect-disk-cell { min-width: 190px; white-space: normal !important; }
.inspect-disk-list { display: flex; flex-direction: column; gap: 4px; }
.inspect-disk-line { display: grid; grid-template-columns: minmax(42px, 1fr) auto; gap: 4px 8px; align-items: center; padding: 4px 6px; border-radius: 5px; background: var(--bg-input); }
.inspect-disk-line span { color: var(--text-primary); font-weight: 500; overflow: hidden; text-overflow: ellipsis; }
.inspect-disk-line small { grid-column: 1 / -1; color: var(--text-muted); }
.inspect-issues-cell { min-width: 220px; white-space: normal !important; }
.inspect-issues-cell .check-cell { display: inline-block; margin: 0 4px 4px 0; }

/* 分组管理 */
.groups-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; gap: 10px; }
.groups-header { display: flex; justify-content: flex-end; flex-shrink: 0; }
.group-cards { flex: 1; overflow-y: auto; display: flex; flex-wrap: wrap; gap: 10px; align-content: flex-start; }
.group-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; width: 280px; }
.group-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.group-name { font-weight: 600; font-size: 14px; }
.group-actions { display: flex; gap: 4px; }
.group-card-meta { display: flex; flex-wrap: wrap; gap: 6px; font-size: 11px; margin-bottom: 4px; }
.group-meta-item { padding: 1px 7px; border-radius: 10px; background: var(--bg-hover); color: var(--text-muted); }
.group-meta-item.ok { background: rgba(63,185,80,.12); color: var(--success); }
.group-desc { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

/* 弹窗 */
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 200; display: flex; align-items: center; justify-content: center; }
.host-modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; width: 680px; max-height: 90vh; display: flex; flex-direction: column; overflow: hidden; }
.confirm-modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; width: 360px; }
.modal-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; border-bottom: 1px solid var(--border); font-weight: 600; font-size: 14px; }
.modal-body { flex: 1; overflow-y: auto; padding: 18px; }
.form-section-title { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; margin: 14px 0 8px; border-bottom: 1px solid var(--border); padding-bottom: 4px; }
.form-row { display: flex; gap: 12px; margin-bottom: 10px; }
.form-group { display: flex; flex-direction: column; gap: 4px; flex: 1; }
.form-group.full { flex: 100%; }
.form-group.required label::after { content: ' *'; color: var(--error); }
.form-group label { font-size: 12px; color: var(--text-muted); }
.form-hint { font-weight: 400; font-style: italic; }
.credential-hint { font-size: 11px; color: var(--text-muted); line-height: 1.4; }
.form-group input, .form-group select, .form-group textarea { padding: 6px 10px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 13px; width: 100%; box-sizing: border-box; }
.form-group textarea { resize: vertical; font-family: inherit; }
.form-error { color: var(--error); font-size: 12px; margin-top: 6px; padding: 6px 10px; background: rgba(248,81,73,.08); border-radius: 5px; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
</style>
