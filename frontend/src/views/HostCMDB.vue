<template>
  <div class="cmdb-page">
    <!-- 顶部统计 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-val">{{ hosts.length }}</div>
        <div class="stat-label">主机总数</div>
      </div>
      <div class="stat-card ok">
        <div class="stat-val">{{ countByState('up') }}</div>
        <div class="stat-label">在线</div>
      </div>
      <div class="stat-card warn">
        <div class="stat-val">{{ inspectSummary.warning }}</div>
        <div class="stat-label">警告</div>
      </div>
      <div class="stat-card error">
        <div class="stat-val">{{ inspectSummary.critical }}</div>
        <div class="stat-label">严重</div>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <div class="tab-group">
          <button class="tab-btn" :class="{ active: tab === 'cmdb' }" @click="tab = 'cmdb'">
            主机 CMDB
          </button>
          <button class="tab-btn" :class="{ active: tab === 'inspect' }" @click="switchToInspect">
            巡检报告
          </button>
          <button class="tab-btn" :class="{ active: tab === 'groups' }" @click="tab = 'groups'">
            分组管理
          </button>
          <RouterLink to="/ssh" class="tab-btn ssh-link">
            SSH 终端 →
          </RouterLink>
        </div>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-outline" @click="loadHosts" :disabled="loading">
          <span v-if="loading" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
          <span v-else>🔄</span> 刷新
        </button>
        <!-- 列设置 -->
        <div v-if="tab === 'cmdb'" class="col-picker-wrap">
          <button class="btn btn-outline" @click.stop="showColPicker = !showColPicker">⚙ 列设置</button>
          <div v-if="showColPicker" class="col-picker-dropdown" @click.stop>
            <div class="col-picker-title">显示列</div>
            <label v-for="col in optionalColumns" :key="col.key" class="col-picker-item">
              <input type="checkbox" :checked="visibleCols.has(col.key)" @change="toggleCol(col.key)" />
              {{ col.label }}
            </label>
          </div>
        </div>
        <template v-if="tab === 'inspect'">
          <button class="btn btn-primary" @click="runInspect" :disabled="inspecting || inspectAiStreaming">
            <span v-if="inspecting" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>🔍</span> 执行巡检
          </button>
          <button
            v-if="inspectResults.length && !inspecting"
            class="btn btn-ai"
            :disabled="inspectAiStreaming"
            @click="runInspectAI"
          >
            <span v-if="inspectAiStreaming" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>🤖</span> AI分析
          </button>
          <button
            v-if="inspectResults.length && !inspecting && groups.length"
            class="btn btn-outline"
            :disabled="notifyingGroups"
            @click="notifyGroups"
            title="将告警主机按分组推送到飞书/钉钉"
          >
            <span v-if="notifyingGroups" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>📤</span> 按分组推送
          </button>
          <button
            v-if="inspectResults.length && !inspecting"
            class="btn btn-excel"
            :disabled="excelDownloading"
            @click="downloadInspectExcel"
          >
            <span v-if="excelDownloading" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>📥</span> 下载 Excel
          </button>
        </template>
      </div>
    </div>

    <!-- 内容区（左：三个 tab 内容；右：详情栏） -->
    <div class="content-row">
    <div class="content-main">

    <!-- CMDB 主机表 -->
    <div v-show="tab === 'cmdb'" class="cmdb-tab-wrap">
      <!-- 标签筛选栏（在滚动区外，不影响 sticky 表头） -->
      <div v-if="allLabelKeys.length" class="label-filter-bar">
        <span class="label-filter-title">标签筛选：</span>
        <div class="label-filter-tags">
          <template v-for="key in allLabelKeys" :key="key">
            <div class="label-filter-group">
              <span class="label-key-name">{{ key }}</span>
              <button
                v-for="val in labelValuesByKey(key)" :key="val"
                class="label-filter-chip"
                :class="{ active: isLabelFilterActive(key, val) }"
                @click="toggleLabelFilter(key, val)"
              >{{ val }}</button>
            </div>
          </template>
          <button v-if="labelFilters.size" class="label-filter-clear" @click="labelFilters.clear(); labelFilters = new Map(labelFilters)">✕ 清除</button>
        </div>
      </div>

      <!-- 分组筛选 -->
      <div v-if="groups.length" class="group-filter-bar">
        <span class="label-filter-title">分组：</span>
        <input
          v-model="groupSearch"
          class="group-filter-search"
          placeholder="搜索分组..."
        />
        <button class="label-filter-chip" :class="{ active: groupFilter === '' }" @click="groupFilter = ''">全部（{{ hosts.length }}）</button>
        <button
          v-for="g in filteredGroupsForFilter" :key="g.id"
          class="label-filter-chip"
          :class="{ active: groupFilter === g.id }"
          @click="groupFilter = groupFilter === g.id ? '' : g.id"
        >{{ g.name }}（{{ g.host_count || 0 }}）</button>
      </div>

      <!-- 表格滚动区 -->
      <div class="table-wrap">
      <div v-if="loading && !hosts.length" class="empty-state">
        <div class="spinner"></div><p>发现主机中...</p>
      </div>
      <div v-else-if="error" class="empty-state">
        <span class="icon">⚠️</span>
        <p style="color:var(--error)">{{ error }}</p>
        <p style="color:var(--text-muted);font-size:12px">请检查 .env 中 PROMETHEUS_URL 配置</p>
      </div>
      <div v-else-if="!hosts.length" class="empty-state">
        <span class="icon">🖥️</span><p>未发现主机<br><small style="color:var(--text-muted)">请确认 Prometheus 已配置 node_exporter targets</small></p>
      </div>
      <table v-if="hosts.length" class="host-table">
        <thead>
          <tr>
            <th class="th-sort" @click="setSort('state')">状态<span class="sort-icon">{{ sortKey==='state' ? (sortAsc?'↑':'↓') : '⇅' }}</span></th>
            <th class="th-sort" @click="setSort('hostname')">主机名<span class="sort-icon">{{ sortKey==='hostname' ? (sortAsc?'↑':'↓') : '⇅' }}</span></th>
            <th class="th-sort" @click="setSort('ip')">IP<span class="sort-icon">{{ sortKey==='ip' ? (sortAsc?'↑':'↓') : '⇅' }}</span></th>
            <th v-if="visibleCols.has('job')" class="th-sort" @click="setSort('job')">Job<span class="sort-icon">{{ sortKey==='job' ? (sortAsc?'↑':'↓') : '⇅' }}</span></th>
            <th v-if="visibleCols.has('cpu')" class="th-sort" @click="setSort('cpu')">CPU%<span class="sort-icon">{{ sortKey==='cpu' ? (sortAsc?'↑':'↓') : '⇅' }}</span></th>
            <th v-if="visibleCols.has('mem')" class="th-sort" @click="setSort('mem')">内存%<span class="sort-icon">{{ sortKey==='mem' ? (sortAsc?'↑':'↓') : '⇅' }}</span></th>
            <th v-if="visibleCols.has('disk')" class="th-sort" @click="setSort('disk')">磁盘(/)<span class="sort-icon">{{ sortKey==='disk' ? (sortAsc?'↑':'↓') : '⇅' }}</span></th>
            <th v-if="visibleCols.has('disk_read')" class="th-sort" @click="setSort('disk_read')">I/O(R/W)<span class="sort-icon">{{ sortKey==='disk_read' ? (sortAsc?'↑':'↓') : '⇅' }}</span></th>
            <th v-if="visibleCols.has('net_recv')" class="th-sort" @click="setSort('net_recv')">网络(↓/↑)<span class="sort-icon">{{ sortKey==='net_recv' ? (sortAsc?'↑':'↓') : '⇅' }}</span></th>
            <th v-if="visibleCols.has('tcp_estab')" class="th-sort" @click="setSort('tcp_estab')">TCP<span class="sort-icon">{{ sortKey==='tcp_estab' ? (sortAsc?'↑':'↓') : '⇅' }}</span></th>
            <th v-if="visibleCols.has('load5')" class="th-sort" @click="setSort('load5')">负载<span class="sort-icon">{{ sortKey==='load5' ? (sortAsc?'↑':'↓') : '⇅' }}</span></th>
            <th v-if="visibleCols.has('uptime')" class="th-sort" @click="setSort('uptime')">运行时长<span class="sort-icon">{{ sortKey==='uptime' ? (sortAsc?'↑':'↓') : '⇅' }}</span></th>
            <th>操作</th>
            <th v-if="visibleCols.has('labels') && allLabelKeys.length">标签</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="h in sortedHosts" :key="h.instance" @click="selectHost(h)">
            <td><span class="dot" :class="h.state === 'up' ? 'ok' : 'err'"></span></td>
            <td class="hostname">
              {{ h.hostname || h.instance }}
              <span v-if="h.group && groupMap[h.group]" class="group-badge-inline">{{ groupMap[h.group] }}</span>
            </td>
            <td>{{ h.ip }}</td>
            <td v-if="visibleCols.has('job')" class="small-text">{{ h.job || '-' }}</td>
            <td v-if="visibleCols.has('cpu')" :class="usageClass(h.metrics.cpu_usage)">{{ fmt(h.metrics.cpu_usage, '%') }}</td>
            <td v-if="visibleCols.has('mem')" :class="usageClass(h.metrics.mem_usage)">{{ fmt(h.metrics.mem_usage, '%') }}</td>
            <td v-if="visibleCols.has('disk')" :class="usageClass(rootDiskUsage(h))">
              {{ fmt(rootDiskUsage(h), '%') }}
              <span v-if="maxDiskPartition(h)" class="disk-mount">{{ maxDiskPartition(h).mountpoint }}</span>
            </td>
            <td v-if="visibleCols.has('disk_read')" class="small-text">{{ fmtIO(h.metrics) }}</td>
            <td v-if="visibleCols.has('net_recv')" class="small-text">{{ fmtNet(h.metrics) }}</td>
            <td v-if="visibleCols.has('tcp_estab')" class="small-text">{{ fmtTcp(h.metrics) }}</td>
            <td v-if="visibleCols.has('load5')">{{ h.metrics.load5 != null ? h.metrics.load5.toFixed(2) : '-' }}</td>
            <td v-if="visibleCols.has('uptime')">{{ fmtUptime(h.metrics.uptime_seconds) }}</td>
            <td class="action-cell" @click.stop>
              <button class="btn btn-outline btn-xs" @click="openSSH(h)" title="SSH 连接">>_</button>
            </td>
            <td v-if="visibleCols.has('labels') && allLabelKeys.length" class="label-cell">
              <div class="label-chips-wrap">
                <span
                  v-for="(val, key) in h.custom_labels" :key="key"
                  class="label-chip"
                  :style="{ '--label-hue': labelHue(key) }"
                  @click.stop="toggleLabelFilter(key, val)"
                >{{ key }}=<b>{{ val }}</b></span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
      </div><!-- /table-wrap -->
    </div><!-- /cmdb-tab-wrap -->

    <!-- 巡检报告 -->
    <div v-show="tab === 'inspect'" class="inspect-wrap">
      <div v-if="inspecting" class="empty-state">
        <div class="spinner"></div><p>巡检中，请稍候...</p>
      </div>
      <div v-else-if="inspectError" class="empty-state">
        <span class="icon">⚠️</span>
        <p style="color:var(--error)">{{ inspectError }}</p>
        <button class="btn btn-outline" style="margin-top:10px" @click="runInspect">重试</button>
      </div>
      <div v-else-if="!inspectResults.length && !inspectAiStreaming" class="empty-state">
        <span class="icon">🔍</span><p>点击「执行巡检」开始</p>
      </div>
      <div v-else>
        <!-- AI 分析总结卡片（流式显示） -->
        <div v-if="inspectAiSummary || inspectAiStreaming" class="inspect-ai-card" :class="{ streaming: inspectAiStreaming }">
          <div class="inspect-ai-header">
            <div>
              <div class="inspect-ai-title">
                <span v-if="inspectAiStreaming" class="ai-thinking-dot"></span>
                AI 分析总结
              </div>
              <div v-if="inspectAiProvider" class="inspect-ai-provider">模型：{{ inspectAiProvider }}</div>
            </div>
            <span class="inspect-ai-badge" :class="{ fallback: inspectAiFallback, streaming: inspectAiStreaming }">
              {{ inspectAiStreaming ? '生成中...' : inspectAiFallback ? '规则兜底' : 'AI生成' }}
            </span>
          </div>
          <div class="inspect-ai-content">
            <span v-if="inspectAiSummary">{{ inspectAiSummary }}</span>
            <span v-else-if="inspectAiStreaming" class="ai-placeholder">AI 正在分析巡检数据...</span>
            <span v-else class="ai-placeholder">暂无分析结果</span>
            <span v-if="inspectAiStreaming" class="ai-cursor"></span>
          </div>
          <div v-if="inspectAiFallback && !inspectAiStreaming" class="inspect-ai-note">
            AI 服务暂不可用，当前显示规则摘要。
          </div>
        </div>
        <div class="inspect-sortbar">
          <span class="inspect-sort-label">排序：</span>
          <button class="inspect-sort-btn" :class="{ active: inspectSortKey === 'overall' }" @click="setInspectSort('overall')">
            报警级别
            <span class="inspect-sort-icon">{{ inspectSortKey === 'overall' ? (inspectSortAsc ? '↑' : '↓') : '↕' }}</span>
          </button>
          <button class="inspect-sort-btn" :class="{ active: inspectSortKey === 'ip' }" @click="setInspectSort('ip')">
            IP
            <span class="inspect-sort-icon">{{ inspectSortKey === 'ip' ? (inspectSortAsc ? '↑' : '↓') : '↕' }}</span>
          </button>
        </div>
        <div class="inspect-list">
          <div v-for="r in sortedInspectResults" :key="r.instance" class="inspect-card" :class="'card-' + r.overall">
            <div class="inspect-header">
              <span class="dot" :class="r.overall"></span>
              <span class="inspect-host">{{ r.hostname || r.instance }}</span>
              <span class="inspect-ip">{{ r.ip }}</span>
              <span class="inspect-os">{{ r.os }}</span>
              <span class="inspect-badge" :class="r.overall">{{ statusLabel(r.overall) }}</span>
            </div>
            <div class="check-grid">
              <div v-for="c in r.checks" :key="c.item" class="check-item" :class="c.status">
                <span class="check-name">{{ c.item }}</span>
                <span class="check-value">{{ c.value }}</span>
                <span class="check-status-dot" :class="c.status"></span>
              </div>
            </div>
            <!-- 分区详情 -->
            <div v-if="r.partitions && r.partitions.length" class="partitions-section">
              <div class="part-title">分区详情</div>
              <div class="part-grid">
                <div v-for="p in r.partitions" :key="p.mountpoint" class="part-item">
                  <div class="part-mount">{{ p.mountpoint }}</div>
                  <div class="part-bar-wrap">
                    <div class="part-bar" :style="{ width: p.usage_pct + '%' }" :class="usageBarClass(p.usage_pct)"></div>
                  </div>
                  <div class="part-info">{{ p.used_gb }}/{{ p.total_gb }}GB ({{ p.usage_pct }}%)</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>



    <!-- 分组管理 -->
    <div v-show="tab === 'groups'" class="groups-wrap">
      <div class="groups-layout">
        <!-- 左：分组列表 -->
        <div class="groups-list-panel">
          <div class="groups-panel-title">主机分组</div>
          <div v-if="!groups.length" class="empty-state" style="min-height:120px">
            <span class="icon">📂</span><p>暂无分组</p>
          </div>
          <div
            v-for="g in groups" :key="g.id"
            class="group-item"
            :class="{ active: selectedGroup && selectedGroup.id === g.id }"
            @click="selectGroup(g)"
          >
            <div class="group-item-name">{{ g.name }}</div>
            <div class="group-item-meta">
              <span class="group-host-count">{{ g.host_count || 0 }} 台主机</span>
              <span v-if="g.feishu_webhook" class="group-badge feishu">飞书</span>
              <span v-if="g.dingtalk_webhook" class="group-badge dingtalk">钉钉</span>
            </div>
          </div>
          <button class="btn btn-primary" style="width:100%;margin-top:12px" @click="startCreateGroup">
            + 新建分组
          </button>
        </div>

        <!-- 右：分组编辑 -->
        <div class="groups-edit-panel">
          <template v-if="groupForm.visible">
            <div class="groups-panel-title">{{ groupForm.id ? '编辑分组' : '新建分组' }}</div>
            <div class="edit-row">
              <label>分组名称</label>
              <input v-model="groupForm.name" placeholder="如：生产环境、DBA组" />
            </div>
            <div class="edit-row">
              <label>飞书 Webhook</label>
              <input v-model="groupForm.feishu_webhook" placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
            </div>
            <div class="edit-row">
              <label>飞书关键词</label>
              <input v-model="groupForm.feishu_keyword" placeholder="如：运维（飞书机器人安全关键词）" />
            </div>
            <div class="edit-row">
              <label>钉钉 Webhook</label>
              <input v-model="groupForm.dingtalk_webhook" placeholder="https://oapi.dingtalk.com/robot/send?..." />
            </div>
            <div class="edit-row">
              <label>钉钉关键词</label>
              <input v-model="groupForm.dingtalk_keyword" placeholder="如：运维" />
            </div>
            <div class="group-form-note">
              💡 主机巡检日报执行时，有告警的主机将按分组推送到各自的飞书/钉钉群
            </div>
            <div style="display:flex;gap:8px;margin-top:12px">
              <button class="btn btn-primary" style="flex:1" @click="saveGroup" :disabled="groupSaving">
                {{ groupSaving ? '保存中...' : '保存' }}
              </button>
              <button v-if="groupForm.id" class="btn btn-danger" @click="deleteGroup(groupForm.id)">删除</button>
              <button class="btn btn-outline" @click="groupForm.visible = false">取消</button>
            </div>
          </template>
          <template v-else>
            <div class="empty-state" style="min-height:200px">
              <span class="icon">👈</span>
              <p>选择左侧分组查看详情<br>或点击「新建分组」</p>
            </div>
          </template>

          <!-- 该分组下的主机 -->
          <template v-if="selectedGroup">
            <div class="groups-panel-title" style="margin-top:20px">
              「{{ selectedGroup.name }}」的主机（{{ groupHosts.length }} 台）
            </div>
            <div v-if="!groupHosts.length" class="text-muted" style="font-size:12px;padding:8px 0">
              暂无主机关联到此分组，在左侧主机列表点击主机，在 CMDB 信息中设置「所属分组」
            </div>
            <div v-else class="group-hosts-list">
              <div v-for="h in groupHosts" :key="h.instance" class="group-host-chip">
                <span class="dot" :class="h.state === 'up' ? 'ok' : 'err'"></span>
                {{ h.hostname || h.ip }}
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>

    </div><!-- /content-main -->

    <!-- 主机详情侧栏（flex 同级，向右扩展） -->
    <transition name="slide">
      <div v-if="selected" class="detail-panel">
        <div class="detail-header">
          <span>{{ selected.hostname || selected.instance }}</span>
          <button class="btn btn-outline btn-xs" @click="selected = null">✕</button>
        </div>
        <div class="detail-body">
          <div class="detail-row"><span>Instance</span><span>{{ selected.instance }}</span></div>
          <div class="detail-row"><span>IP</span><span>{{ selected.ip }}</span></div>
          <div class="detail-row"><span>Job</span><span>{{ selected.job }}</span></div>
          <div class="detail-row"><span>OS</span><span>{{ selected.os || '-' }}</span></div>
          <div class="detail-row"><span>架构</span><span>{{ selected.arch || '-' }}</span></div>
          <div class="detail-row"><span>CPU 核数</span><span>{{ selected.cpu_cores || '-' }}</span></div>
          <div class="detail-row"><span>内存</span><span>{{ selected.metrics.mem_total_gb ? selected.metrics.mem_total_gb + ' GB' : '-' }}</span></div>

          <!-- Prometheus 自定义标签 -->
          <template v-if="selected.custom_labels && Object.keys(selected.custom_labels).length">
            <div class="detail-section">Prometheus 标签</div>
            <div class="detail-label-list">
              <span
                v-for="(val, key) in selected.custom_labels" :key="key"
                class="label-chip"
                :style="{ '--label-hue': labelHue(key) }"
              >{{ key }}=<b>{{ val }}</b></span>
            </div>
          </template>

          <!-- 网络 & I/O -->
          <div class="detail-section">实时指标</div>
          <div class="detail-row"><span>磁盘读</span><span>{{ selected.metrics.disk_read_mbps != null ? selected.metrics.disk_read_mbps + ' MB/s' : '-' }}</span></div>
          <div class="detail-row"><span>磁盘写</span><span>{{ selected.metrics.disk_write_mbps != null ? selected.metrics.disk_write_mbps + ' MB/s' : '-' }}</span></div>
          <div class="detail-row"><span>下载带宽</span><span>{{ selected.metrics.net_recv_mbps != null ? selected.metrics.net_recv_mbps + ' MB/s' : '-' }}</span></div>
          <div class="detail-row"><span>上传带宽</span><span>{{ selected.metrics.net_send_mbps != null ? selected.metrics.net_send_mbps + ' MB/s' : '-' }}</span></div>
          <div class="detail-row"><span>TCP 连接</span><span>{{ selected.metrics.tcp_estab ?? '-' }}</span></div>
          <div class="detail-row"><span>TCP TIME_WAIT</span><span>{{ selected.metrics.tcp_tw ?? '-' }}</span></div>

          <!-- 分区详情 -->
          <div class="detail-section">磁盘分区</div>
          <div v-if="selected.partitions && selected.partitions.length">
            <div v-for="p in selected.partitions" :key="p.mountpoint" class="part-detail-item">
              <div class="part-detail-head">
                <span class="part-mount-label">{{ p.mountpoint }}</span>
                <span :class="usageClass(p.usage_pct)">{{ p.usage_pct }}%</span>
              </div>
              <div class="part-bar-wrap">
                <div class="part-bar" :style="{ width: p.usage_pct + '%' }" :class="usageBarClass(p.usage_pct)"></div>
              </div>
              <div class="part-detail-info">{{ p.fstype }} | {{ p.used_gb }}/{{ p.total_gb }} GB</div>
            </div>
          </div>
          <div v-else class="text-muted" style="font-size:12px">无分区数据</div>

          <!-- CMDB 信息 -->
          <div class="detail-section">CMDB 信息</div>
          <div class="edit-row">
            <label>用途</label>
            <input v-model="editForm.role" placeholder="如：Web服务器、数据库" />
          </div>
          <div class="edit-row">
            <label>负责人</label>
            <input v-model="editForm.owner" placeholder="如：张三" />
          </div>
          <div class="edit-row">
            <label>环境</label>
            <select v-model="editForm.env">
              <option value="">未分类</option>
              <option value="production">生产</option>
              <option value="staging">预发布</option>
              <option value="development">开发</option>
              <option value="testing">测试</option>
            </select>
          </div>
          <div class="edit-row">
            <label>所属分组</label>
            <select v-model="editForm.group">
              <option value="">不分组</option>
              <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
            </select>
          </div>
          <div class="edit-row">
            <label>备注</label>
            <textarea v-model="editForm.notes" rows="2" placeholder="补充说明"></textarea>
          </div>

          <!-- SSH 凭证 -->
          <div class="detail-section">SSH 凭证</div>
          <div class="edit-row">
            <label>使用凭证库</label>
            <select v-model="editForm.credential_id">
              <option value="">不使用（手动配置）</option>
              <option v-for="c in credentials" :key="c.id" :value="c.id">
                {{ c.name }} ({{ c.username }}:{{ c.port }})
              </option>
            </select>
          </div>
          <template v-if="!editForm.credential_id">
            <div class="edit-row">
              <label>SSH 端口</label>
              <input v-model.number="editForm.ssh_port" type="number" placeholder="22" />
            </div>
            <div class="edit-row">
              <label>SSH 用户名</label>
              <input v-model="editForm.ssh_user" placeholder="root" />
            </div>
            <div class="edit-row">
              <label>SSH 密码</label>
              <div class="password-wrap">
                <input v-model="editForm.ssh_password" :type="showPwd ? 'text' : 'password'"
                  :placeholder="selected.ssh_saved ? '已保存（留空不修改）' : '输入密码'" />
                <button class="pwd-toggle" @click="showPwd = !showPwd" type="button">
                  {{ showPwd ? '隐藏' : '显示' }}
                </button>
              </div>
            </div>
          </template>

          <button class="btn btn-primary" style="width:100%;margin-top:8px" @click="saveHost" :disabled="saving">
            {{ saving ? '保存中...' : '保存' }}
          </button>
          <button class="btn btn-outline" style="width:100%;margin-top:6px" @click="openSSH(selected)">
            {{ selected.ssh_saved ? '>_ SSH 快连（已保存凭证）' : '>_ SSH 连接' }}
          </button>
        </div>
      </div>
    </transition>

    </div><!-- /content-row -->
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api } from '../api/index.js'

const router          = useRouter()
const tab             = ref('cmdb')
const hosts           = ref([])
const loading         = ref(false)
const error           = ref('')
const selected        = ref(null)
const saving          = ref(false)
const inspecting      = ref(false)
const inspectResults  = ref([])
const inspectSummary  = ref({ normal: 0, warning: 0, critical: 0 })
const inspectAiSummary = ref('')
const inspectAiProvider = ref('')
const inspectAiFallback = ref(false)
const inspectError = ref('')

const editForm = reactive({ owner: '', env: '', role: '', notes: '', group: '', ssh_port: 22, ssh_user: '', ssh_password: '', credential_id: '' })

// ────────── 自定义标签筛选 ──────────
// labelFilters: Map<key, Set<val>>  — 同 key 多值 OR，不同 key AND
const labelFilters = ref(new Map())

const allLabelKeys = computed(() => {
  const keys = new Set()
  for (const h of hosts.value) {
    for (const k of Object.keys(h.custom_labels || {})) keys.add(k)
  }
  return [...keys].sort()
})

function labelValuesByKey(key) {
  const vals = new Set()
  for (const h of hosts.value) {
    const v = (h.custom_labels || {})[key]
    if (v !== undefined) vals.add(v)
  }
  return [...vals].sort()
}

function isLabelFilterActive(key, val) {
  return labelFilters.value.get(key)?.has(val) ?? false
}

function toggleLabelFilter(key, val) {
  const m = new Map(labelFilters.value)
  if (!m.has(key)) m.set(key, new Set())
  const s = new Set(m.get(key))
  if (s.has(val)) s.delete(val)
  else s.add(val)
  if (s.size === 0) m.delete(key)
  else m.set(key, s)
  labelFilters.value = m
}

// 为每个 label key 生成稳定的色相（基于字符串 hash）
function labelHue(key) {
  let h = 0
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) & 0xffff
  return h % 360
}

// ────────── 分组 ──────────
const groups         = ref([])
const selectedGroup  = ref(null)
const groupSaving    = ref(false)
const groupForm      = reactive({ visible: false, id: '', name: '', feishu_webhook: '', feishu_keyword: '', dingtalk_webhook: '', dingtalk_keyword: '' })

// CMDB 列表：按分组筛选（分组多时可搜索）
const groupFilter = ref('')
const groupSearch = ref('')
const groupMap = computed(() => Object.fromEntries((groups.value || []).map(g => [g.id, g.name])))
const filteredGroupsForFilter = computed(() => {
  const kw = groupSearch.value.trim().toLowerCase()
  const list = [...(groups.value || [])].sort((a, b) => String(a.name || '').localeCompare(String(b.name || '')))
  if (!kw) return list
  return list.filter(g => String(g.name || '').toLowerCase().includes(kw) || String(g.id || '').toLowerCase().includes(kw))
})

const groupHosts = computed(() => {
  if (!selectedGroup.value) return []
  return hosts.value.filter(h => h.group === selectedGroup.value.id)
})

function selectGroup(g) {
  selectedGroup.value = g
  groupForm.id              = g.id
  groupForm.name            = g.name
  groupForm.feishu_webhook  = g.feishu_webhook || ''
  groupForm.feishu_keyword  = g.feishu_keyword || ''
  groupForm.dingtalk_webhook = g.dingtalk_webhook || ''
  groupForm.dingtalk_keyword = g.dingtalk_keyword || ''
  groupForm.visible         = true
}

function startCreateGroup() {
  selectedGroup.value       = null
  groupForm.id              = ''
  groupForm.name            = ''
  groupForm.feishu_webhook  = ''
  groupForm.feishu_keyword  = ''
  groupForm.dingtalk_webhook = ''
  groupForm.dingtalk_keyword = ''
  groupForm.visible         = true
}

async function loadGroups() {
  try {
    const r = await api.listGroups()
    groups.value = r.data || []
  } catch (e) { console.error('加载分组失败', e) }
}

async function saveGroup() {
  if (!groupForm.name.trim()) return alert('请输入分组名称')
  groupSaving.value = true
  try {
    const payload = {
      name: groupForm.name,
      feishu_webhook: groupForm.feishu_webhook,
      feishu_keyword: groupForm.feishu_keyword,
      dingtalk_webhook: groupForm.dingtalk_webhook,
      dingtalk_keyword: groupForm.dingtalk_keyword,
    }
    if (groupForm.id) {
      await api.updateGroup(groupForm.id, payload)
    } else {
      await api.createGroup(payload)
    }
    await loadGroups()
    groupForm.visible = false
    selectedGroup.value = null
  } catch (e) {
    alert('保存分组失败: ' + (typeof e === 'string' ? e : e?.message || '未知错误'))
  } finally {
    groupSaving.value = false
  }
}

async function deleteGroup(id) {
  if (!confirm('确定删除该分组？已关联该分组的主机将取消关联。')) return
  try {
    await api.deleteGroup(id)
    await loadGroups()
    await loadHosts()
    groupForm.visible = false
    selectedGroup.value = null
  } catch (e) {
    alert('删除失败: ' + (typeof e === 'string' ? e : e?.message || '未知错误'))
  }
}

// 排序
const sortKey = ref('')   // 当前排序字段
const sortAsc = ref(true) // true=升序 false=降序
const inspectSortKey = ref('')
const inspectSortAsc = ref(false)
const showPwd = ref(false)

// 凭证库
const credentials     = ref([])
const credForm        = reactive({ name: '', username: 'root', password: '', port: 22 })
const credEditId      = ref('')
const credSaving      = ref(false)


// ────────── 列设置 ──────────
const STORAGE_KEY = 'cmdb_visible_cols'
const optionalColumns = [
  { key: 'job',      label: 'Job' },
  { key: 'cpu',      label: 'CPU%' },
  { key: 'mem',      label: '内存%' },
  { key: 'disk',     label: '磁盘(/)' },
  { key: 'disk_read',label: 'I/O(R/W)' },
  { key: 'net_recv', label: '网络(↓/↑)' },
  { key: 'tcp_estab',label: 'TCP' },
  { key: 'load5',    label: '负载' },
  { key: 'uptime',   label: '运行时长' },
  { key: 'labels',   label: 'Prom 标签' },
]
const defaultVisibleCols = new Set(['job', 'cpu', 'mem', 'disk', 'disk_read', 'net_recv', 'tcp_estab', 'load5', 'uptime', 'labels'])

function loadVisibleCols() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) return new Set(JSON.parse(saved))
  } catch {}
  return new Set(defaultVisibleCols)
}

const visibleCols = ref(loadVisibleCols())
const showColPicker = ref(false)

function toggleCol(key) {
  const s = new Set(visibleCols.value)
  if (s.has(key)) s.delete(key)
  else s.add(key)
  visibleCols.value = s
  localStorage.setItem(STORAGE_KEY, JSON.stringify([...s]))
}

function onDocClick() { showColPicker.value = false }

// ────────── 排序取值 ──────────
function sortVal(h, key) {
  switch (key) {
    case 'state':    return h.state === 'up' ? 0 : 1
    case 'hostname': return (h.hostname || h.instance || '').toLowerCase()
    case 'ip':       return h.ip || ''
    case 'job':      return (h.job || '').toLowerCase()
    case 'cpu':      return h.metrics.cpu_usage ?? -1
    case 'mem':      return h.metrics.mem_usage ?? -1
    case 'disk':     return rootDiskUsage(h) ?? -1
    case 'disk_read':  return h.metrics.disk_read_mbps ?? -1
    case 'net_recv':   return h.metrics.net_recv_mbps ?? -1
    case 'tcp_estab':  return h.metrics.tcp_estab ?? -1
    case 'load5':    return h.metrics.load5 ?? -1
    case 'uptime':   return h.metrics.uptime_seconds ?? -1
    default:         return ''
  }
}

function setSort(key) {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value
  } else {
    sortKey.value = key
    sortAsc.value = true
  }
}

const filteredHosts = computed(() => {
  let base = hosts.value
  if (groupFilter.value) {
    base = base.filter(h => h.group === groupFilter.value)
  }
  if (!labelFilters.value.size) return base
  return base.filter(h => {
    for (const [key, vals] of labelFilters.value) {
      const hv = (h.custom_labels || {})[key]
      if (!vals.has(hv)) return false
    }
    return true
  })
})

const sortedHosts = computed(() => {
  const base = filteredHosts.value
  if (!sortKey.value) return base
  return [...base].sort((a, b) => {
    const va = sortVal(a, sortKey.value)
    const vb = sortVal(b, sortKey.value)
    if (va < vb) return sortAsc.value ? -1 : 1
    if (va > vb) return sortAsc.value ? 1 : -1
    return 0
  })
})

const inspectSeverityRank = { critical: 3, warning: 2, normal: 1 }

function compareIp(ipA, ipB) {
  const a = String(ipA || '').split('.').map(v => Number.parseInt(v, 10))
  const b = String(ipB || '').split('.').map(v => Number.parseInt(v, 10))
  const len = Math.max(a.length, b.length)
  for (let i = 0; i < len; i++) {
    const av = Number.isFinite(a[i]) ? a[i] : -1
    const bv = Number.isFinite(b[i]) ? b[i] : -1
    if (av !== bv) return av - bv
  }
  return String(ipA || '').localeCompare(String(ipB || ''))
}

function setInspectSort(key) {
  if (inspectSortKey.value === key) {
    inspectSortAsc.value = !inspectSortAsc.value
    return
  }
  inspectSortKey.value = key
  inspectSortAsc.value = key === 'ip'
}

const sortedInspectResults = computed(() => {
  const items = [...inspectResults.value]
  if (!inspectSortKey.value) return items
  return items.sort((a, b) => {
    let diff = 0
    if (inspectSortKey.value === 'overall') {
      diff = (inspectSeverityRank[a.overall] || 0) - (inspectSeverityRank[b.overall] || 0)
    } else if (inspectSortKey.value === 'ip') {
      diff = compareIp(a.ip, b.ip)
    }
    if (diff === 0) {
      diff = String(a.hostname || a.instance || '').localeCompare(String(b.hostname || b.instance || ''))
    }
    return inspectSortAsc.value ? diff : -diff
  })
})

function countByState(state) {
  return hosts.value.filter(h => h.state === state).length
}

function fmt(val, suffix = '') {
  return val != null ? val + suffix : '-'
}

function fmtUptime(sec) {
  if (sec == null) return '-'
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  return d > 0 ? `${d}天${h}时` : `${h}小时`
}

function fmtIO(m) {
  if (m.disk_read_mbps == null) return '-'
  return `${m.disk_read_mbps}/${m.disk_write_mbps}`
}

function fmtNet(m) {
  if (m.net_recv_mbps == null) return '-'
  return `${m.net_recv_mbps}/${m.net_send_mbps}`
}

function fmtTcp(m) {
  if (m.tcp_estab == null) return '-'
  return `${m.tcp_estab}/${m.tcp_tw ?? 0}`
}

function maxDiskPartition(h) {
  // 返回占用率最高的分区，无分区数据时回退到 metrics
  if (h.partitions && h.partitions.length) {
    return h.partitions.reduce((a, b) => (a.usage_pct >= b.usage_pct ? a : b))
  }
  return null
}

function rootDiskUsage(h) {
  const p = maxDiskPartition(h)
  return p ? p.usage_pct : h.metrics.disk_usage
}

function usageClass(val) {
  if (val == null) return ''
  if (val > 90) return 'usage-critical'
  if (val > 70) return 'usage-warning'
  return 'usage-ok'
}

function usageBarClass(val) {
  if (val > 90) return 'bar-critical'
  if (val > 70) return 'bar-warning'
  return 'bar-ok'
}

function statusLabel(s) {
  return { normal: '正常', warning: '警告', critical: '严重' }[s] || s
}

function selectHost(h) {
  selected.value = h
  editForm.owner = h.owner || ''
  editForm.env   = h.env || ''
  editForm.role  = h.role || ''
  editForm.notes = h.notes || ''
  editForm.group = h.group || ''
  editForm.ssh_port = h.ssh_port || 22
  editForm.ssh_user = h.ssh_user || ''
  editForm.ssh_password = ''  // 密码不从后端返回，留空表示不修改
  editForm.credential_id = h.credential_id || ''
  showPwd.value = false
}


function openSSH(h) {
  const query = { instance: h.instance }
  if (h.credential_id) query.credential_id = h.credential_id
  router.push({ path: '/ssh', query })
}

async function loadHosts() {
  loading.value = true
  error.value = ''
  try {
    const r = await api.getHosts()
    hosts.value = r.data
  } catch (e) {
    error.value = typeof e === 'string' ? e : (e?.message || 'Prometheus 连接失败')
  } finally {
    loading.value = false
  }
}

async function saveHost() {
  if (!selected.value) return
  saving.value = true
  try {
    const payload = {
      owner: editForm.owner,
      env:   editForm.env,
      role:  editForm.role,
      notes: editForm.notes,
      group: editForm.group,
      credential_id: editForm.credential_id,
    }
    // 仅在未使用凭证库时发送独立 SSH 配置
    if (!editForm.credential_id) {
      payload.ssh_port = editForm.ssh_port
      payload.ssh_user = editForm.ssh_user
      if (editForm.ssh_password) {
        payload.ssh_password = editForm.ssh_password
      }
    }
    await api.updateHost(selected.value.instance, payload)
    selected.value.owner = editForm.owner
    selected.value.env   = editForm.env
    selected.value.role  = editForm.role
    selected.value.notes = editForm.notes
    selected.value.group = editForm.group
    selected.value.credential_id = editForm.credential_id
    if (editForm.credential_id) {
      selected.value.ssh_saved = true
    } else {
      selected.value.ssh_port = editForm.ssh_port
      selected.value.ssh_user = editForm.ssh_user
      if (editForm.ssh_password) {
        selected.value.ssh_saved = true
        editForm.ssh_password = ''
      }
    }
  } finally {
    saving.value = false
  }
}

const inspectAiStreaming = ref(false)
const excelDownloading = ref(false)
const notifyingGroups = ref(false)

function switchToInspect() {
  tab.value = 'inspect'
  if (!inspecting.value && !inspectResults.value.length) {
    runInspect()
  }
}

async function notifyGroups(resultsOverride = null) {
  const results = resultsOverride ?? inspectResults.value
  if (notifyingGroups.value || !results?.length) return
  notifyingGroups.value = true
  try {
    await api.notifyInspectGroups({ results })
  } catch (e) {
    alert('按分组推送失败: ' + (typeof e === 'string' ? e : e?.message || '未知错误'))
  } finally {
    notifyingGroups.value = false
  }
}

async function runInspect() {
  inspecting.value = true
  inspectResults.value = []
  inspectAiSummary.value = ''
  inspectAiProvider.value = ''
  inspectAiFallback.value = false
  inspectAiStreaming.value = false
  inspectError.value = ''

  try {
    const resp = await fetch('/api/hosts/inspect')
    if (!resp.ok) throw new Error(`巡检请求失败: ${resp.status}`)

    const ct = resp.headers.get('content-type') || ''

    // ── 旧版后端：直接返回 JSON ──
    if (ct.includes('application/json')) {
      const data = await resp.json()
      inspectResults.value = data.data || []
      inspectSummary.value = data.summary || {}
      // 手动巡检：对齐定时推送，自动按分组推送到各群
      notifyGroups(inspectResults.value)
      inspecting.value = false
      return
    }

    // ── 新版后端：SSE 流式 ──
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
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') break
        try {
          const msg = JSON.parse(raw)
          if (msg.type === 'inspect_data') {
            inspectResults.value = msg.data
            inspectSummary.value = msg.summary
            // 手动巡检：对齐定时推送，自动按分组推送到各群
            notifyGroups(msg.data)
            inspecting.value = false
          } else if (msg.type === 'error') {
            inspectError.value = msg.message || '巡检失败'
          }
        } catch { /* ignore parse errors */ }
      }
    }
  } catch (e) {
    inspectError.value = typeof e === 'string' ? e : (e?.message || '巡检失败')
  } finally {
    inspecting.value = false
  }
}

async function runInspectAI() {
  if (inspectAiStreaming.value || !inspectResults.value.length) return
  inspectAiSummary.value = ''
  inspectAiProvider.value = ''
  inspectAiFallback.value = false
  inspectAiStreaming.value = true

  try {
    const resp = await fetch('/api/hosts/inspect/ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ results: inspectResults.value, summary: inspectSummary.value }),
    })
    if (!resp.ok) throw new Error(`AI分析请求失败: ${resp.status}`)

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
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (raw === '[DONE]') break
        try {
          const msg = JSON.parse(raw)
          if (msg.type === 'ai_meta') {
            inspectAiProvider.value = msg.provider || ''
            inspectAiFallback.value = !!msg.fallback
          } else if (msg.type === 'ai_chunk') {
            inspectAiSummary.value += msg.text
          }
        } catch { /* ignore */ }
      }
    }
  } catch (e) {
    inspectAiSummary.value = `AI分析失败：${e?.message || e}`
  } finally {
    inspectAiStreaming.value = false
  }
}

async function downloadInspectExcel() {
  if (excelDownloading.value || !inspectResults.value.length) return
  excelDownloading.value = true
  try {
    const resp = await fetch('/api/hosts/inspect/excel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        results: inspectResults.value,
        summary: inspectSummary.value,
        ai_text: inspectAiSummary.value || '',
      }),
    })
    if (!resp.ok) throw new Error(`Excel导出失败: ${resp.status}`)
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `巡检报告_${new Date().toISOString().slice(0,10)}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    inspectError.value = e?.message || 'Excel导出失败'
  } finally {
    excelDownloading.value = false
  }
}

// ────────── 凭证库 ──────────

async function loadCredentials() {
  try {
    const r = await api.listCredentials()
    credentials.value = r.data
  } catch (e) {
    console.error('加载凭证失败', e)
  }
}

function resetCredForm() {
  credForm.name = ''
  credForm.username = 'root'
  credForm.password = ''
  credForm.port = 22
  credEditId.value = ''
}

function editCred(c) {
  credEditId.value = c.id
  credForm.name = c.name
  credForm.username = c.username
  credForm.password = ''
  credForm.port = c.port
}

async function saveCred() {
  if (!credForm.name) return alert('请输入凭证名称')
  if (!credEditId.value && !credForm.password) return alert('请输入密码')
  credSaving.value = true
  try {
    const payload = {
      name: credForm.name,
      username: credForm.username || 'root',
      password: credForm.password || '',
      port: credForm.port || 22,
    }
    if (credEditId.value) {
      await api.updateCredential(credEditId.value, payload)
    } else {
      await api.createCredential(payload)
    }
    resetCredForm()
    await loadCredentials()
  } catch (e) {
    alert('保存凭证失败: ' + (typeof e === 'string' ? e : e?.message || '未知错误'))
  } finally {
    credSaving.value = false
  }
}

async function deleteCred(id) {
  if (!confirm('确定删除此凭证？已绑定该凭证的主机将需要重新配置。')) return
  await api.deleteCredential(id)
  await loadCredentials()
}


onMounted(() => {
  loadHosts()
  loadCredentials()
  loadGroups()
  document.addEventListener('click', onDocClick)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
})

</script>

<style scoped>
.cmdb-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; padding: 8px 12px; gap: 8px; }
/* 内容行：左侧主内容 + 右侧详情栏 */
.content-row { flex: 1; display: flex; min-height: 0; gap: 0; }
.content-main { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: hidden; }

/* 统计卡片 */
.stats-row { display: flex; gap: 10px; flex-shrink: 0; }
.stat-card {
  flex: 1;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 12px 16px; text-align: center;
  box-shadow: var(--shadow-sm);
}
.stat-val { font-size: 22px; font-weight: 700; color: var(--text-primary); }
.stat-label { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
.stat-card.ok .stat-val { color: var(--success); }
.stat-card.warn .stat-val { color: var(--warning); }
.stat-card.error .stat-val { color: var(--error); }

/* 工具栏 */
.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 7px 12px; flex-shrink: 0;
  box-shadow: var(--shadow-sm);
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; }
.btn-ai {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px; border-radius: 6px;
  border: 1px solid rgba(145, 109, 213, .45);
  background: rgba(145, 109, 213, .12);
  color: #b58bf5; font-size: 12px; font-weight: 500;
  cursor: pointer; transition: background .15s;
}
.btn-ai:hover:not(:disabled) { background: rgba(145, 109, 213, .22); }
.btn-ai:disabled { opacity: .5; cursor: not-allowed; }
.btn-excel {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px; border-radius: 6px;
  border: 1px solid rgba(82, 196, 26, .4);
  background: rgba(82, 196, 26, .1);
  color: #52c41a; font-size: 12px; font-weight: 500;
  cursor: pointer; transition: background .15s;
}
.btn-excel:hover:not(:disabled) { background: rgba(82, 196, 26, .2); }
.btn-excel:disabled { opacity: .5; cursor: not-allowed; }
.tab-group { display: flex; gap: 2px; background: var(--bg-base); padding: 3px; border-radius: 6px; border: 1px solid var(--border); }
.tab-btn {
  padding: 4px 12px; border-radius: 4px; border: none;
  background: transparent; color: var(--text-muted);
  font-size: 13px; cursor: pointer; transition: all .12s;
}
.tab-btn:hover { color: var(--text-primary); background: var(--bg-hover); }
.tab-btn.active { background: var(--bg-active); color: var(--text-primary); }
.ssh-link { text-decoration: none; color: var(--accent); border: 1px dashed var(--border-accent); }
.ssh-link:hover { background: var(--accent-dim); }

/* 表格 */
.cmdb-tab-wrap { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.table-wrap { flex: 1; overflow: auto; min-height: 0; }
.host-table {
  width: 100%; border-collapse: collapse; font-size: 12px;
}
.host-table th {
  text-align: left; padding: 7px 10px; font-weight: 600;
  color: var(--text-muted); font-size: 11px; text-transform: uppercase;
  letter-spacing: .04em; border-bottom: 1px solid var(--border);
  position: sticky; top: 0; background: var(--bg-hover); z-index: 1;
  white-space: nowrap;
}
.th-sort { cursor: pointer; user-select: none; }
.th-sort:hover { color: var(--text-primary); background: var(--bg-active); }
.sort-icon { margin-left: 4px; font-size: 10px; opacity: .5; }
.th-sort:hover .sort-icon { opacity: 1; }
.host-table td {
  padding: 7px 10px; border-bottom: 1px solid var(--border);
  color: var(--text-secondary); white-space: nowrap;
}
.host-table tr { cursor: pointer; transition: background .1s; }
.host-table tr:hover td { background: var(--bg-hover); }
.hostname { color: var(--text-primary); font-weight: 500; }
.small-text { font-size: 11px; color: var(--text-muted); }
.disk-mount { font-size: 10px; color: var(--text-muted); margin-left: 3px; }
.tag.role {
  display: inline-block; font-size: 10px; padding: 1px 6px;
  border-radius: 4px; background: var(--accent-dim);
  color: var(--accent); margin-right: 4px;
}

.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; }
.dot.ok, .dot.normal { background: var(--success); }
.dot.err, .dot.critical { background: var(--error); }
.dot.warning { background: var(--warning); }

.usage-ok { color: var(--success); }
.usage-warning { color: var(--warning); }
.usage-critical { color: var(--error); font-weight: 600; }

.text-muted { color: var(--text-muted); }

/* 巡检 */
.inspect-wrap { flex: 1; overflow-y: auto; min-height: 0; }
.inspect-ai-card {
  background: linear-gradient(180deg, rgba(88,166,255,.08), rgba(88,166,255,.03));
  border: 1px solid rgba(88,166,255,.28);
  border-radius: var(--radius);
  padding: 16px 18px;
  margin-bottom: 12px;
  box-shadow: var(--shadow-sm);
}
.inspect-ai-header {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 12px; margin-bottom: 10px;
}
.inspect-ai-title {
  font-size: 15px; font-weight: 700; color: var(--text-primary);
}
.inspect-ai-provider {
  margin-top: 4px; font-size: 12px; color: var(--text-muted);
}
.inspect-ai-badge {
  flex-shrink: 0;
  font-size: 11px; font-weight: 700;
  color: var(--accent); background: rgba(88,166,255,.12);
  border: 1px solid rgba(88,166,255,.32);
  border-radius: 9999px; padding: 4px 10px;
}
.inspect-ai-badge.fallback {
  color: var(--warning);
  background: rgba(234,179,8,.12);
  border-color: rgba(234,179,8,.35);
}
.inspect-ai-content {
  font-size: 13px; line-height: 1.75; color: var(--text-secondary);
  white-space: pre-wrap;
}
.inspect-ai-note {
  margin-top: 10px; font-size: 12px; color: var(--text-muted);
}
/* 流式状态 */
.inspect-ai-card.streaming {
  border-color: rgba(58,132,255,.4);
  background: linear-gradient(180deg, rgba(58,132,255,.06), rgba(58,132,255,.02));
}
.inspect-ai-badge.streaming {
  color: var(--accent); border-color: rgba(58,132,255,.4);
  background: rgba(58,132,255,.12); animation: badge-pulse 1.2s ease infinite;
}
@keyframes badge-pulse { 0%,100% { opacity: 1 } 50% { opacity: .5 } }
.ai-thinking-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: var(--accent); margin-right: 6px;
  animation: badge-pulse 1s ease infinite;
}
.ai-cursor {
  display: inline-block; width: 2px; height: 1em; background: var(--accent);
  margin-left: 2px; vertical-align: text-bottom;
  animation: blink .7s step-start infinite;
}
@keyframes blink { 0%,100% { opacity: 1 } 50% { opacity: 0 } }
.ai-placeholder { color: var(--text-muted); font-style: italic; }
.inspect-sortbar {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 10px; flex-wrap: wrap;
}
.inspect-sort-label { font-size: 12px; color: var(--text-muted); }
.inspect-sort-btn {
  display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid var(--border); background: var(--bg-card);
  color: var(--text-secondary); border-radius: 9999px;
  padding: 5px 12px; font-size: 12px; cursor: pointer;
  transition: all .15s ease;
}
.inspect-sort-btn:hover { color: var(--text-primary); border-color: var(--accent); }
.inspect-sort-btn.active {
  color: var(--accent); border-color: var(--accent);
  background: var(--accent-dim);
}
.inspect-sort-icon { font-size: 11px; line-height: 1; }
.inspect-list { display: flex; flex-direction: column; gap: 10px; }
.inspect-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 14px 16px;
  box-shadow: var(--shadow-sm);
}
.inspect-card.card-warning { border-left: 3px solid var(--warning); }
.inspect-card.card-critical { border-left: 3px solid var(--error); }
.inspect-card.card-normal { border-left: 3px solid var(--success); }

.inspect-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.inspect-host { font-weight: 600; color: var(--text-primary); }
.inspect-ip { color: var(--text-muted); font-size: 12px; }
.inspect-os { color: var(--text-muted); font-size: 11px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.inspect-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 9999px; font-weight: 600;
}
.inspect-badge.normal { background: rgba(34,197,94,.15); color: var(--success); }
.inspect-badge.warning { background: rgba(234,179,8,.15); color: var(--warning); }
.inspect-badge.critical { background: rgba(239,68,68,.15); color: var(--error); }

.check-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.check-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 12px; border-radius: 6px; font-size: 12px;
  background: var(--bg-base); min-width: 150px;
}
.check-name { color: var(--text-muted); }
.check-value { color: var(--text-primary); font-weight: 600; flex: 1; }
.check-status-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; }
.check-status-dot.normal { background: var(--success); }
.check-status-dot.warning { background: var(--warning); }
.check-status-dot.critical { background: var(--error); }

/* 分区 */
.partitions-section { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }
.part-title { font-size: 11px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px; }
.part-grid { display: flex; flex-wrap: wrap; gap: 8px; }
.part-item { background: var(--bg-base); border-radius: 6px; padding: 6px 10px; min-width: 200px; flex: 1; max-width: 300px; }
.part-mount { font-size: 11px; color: var(--text-primary); font-weight: 600; margin-bottom: 3px; }
.part-bar-wrap { width: 100%; height: 6px; background: rgba(255,255,255,.06); border-radius: 3px; overflow: hidden; }
.part-bar { height: 100%; border-radius: 3px; transition: width .3s; }
.bar-ok { background: var(--success); }
.bar-warning { background: var(--warning); }
.bar-critical { background: var(--error); }
.part-info { font-size: 10px; color: var(--text-muted); margin-top: 2px; }

/* 详情侧栏分区 */
.part-detail-item { margin-bottom: 8px; }
.part-detail-head { display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 3px; }
.part-mount-label { color: var(--text-primary); font-weight: 600; }
.part-detail-info { font-size: 10px; color: var(--text-muted); margin-top: 2px; }

/* 详情侧栏 */
.detail-panel {
  width: 320px; flex-shrink: 0;
  background: var(--bg-card);
  border-left: 1px solid var(--border);
  display: flex; flex-direction: column;
  box-shadow: var(--shadow);
  overflow: hidden;
}
.detail-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 16px; border-bottom: 1px solid var(--border);
  font-weight: 600; font-size: 14px; color: var(--text-primary);
}
.btn-xs { padding: 2px 8px; font-size: 11px; }
.detail-body { flex: 1; overflow-y: auto; padding: 12px 16px; }
.detail-row {
  display: flex; justify-content: space-between; padding: 6px 0;
  font-size: 12px; border-bottom: 1px solid rgba(46,49,80,.3);
}
.detail-row span:first-child { color: var(--text-muted); }
.detail-row span:last-child { color: var(--text-primary); }
.detail-section {
  font-size: 11px; font-weight: 600; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: .8px;
  margin-top: 16px; margin-bottom: 8px; padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
}
.edit-row { margin-bottom: 8px; }
.edit-row label { display: block; font-size: 11px; color: var(--text-muted); margin-bottom: 3px; }
.edit-row input, .edit-row select, .edit-row textarea {
  width: 100%; background: var(--bg-hover);
  border: 1px solid var(--border); color: var(--text-primary);
  padding: 5px 8px; border-radius: 5px; font-size: 12px;
  font-family: inherit; resize: vertical;
}
.password-wrap { display: flex; gap: 4px; }
.password-wrap input { flex: 1; }
.pwd-toggle {
  background: var(--bg-hover); border: 1px solid var(--border); color: var(--text-muted);
  padding: 4px 8px; border-radius: 5px; font-size: 11px; cursor: pointer; white-space: nowrap;
  transition: color .15s;
}
.pwd-toggle:hover { color: var(--accent); }

/* 详情栏滑入 */
.slide-enter-active, .slide-leave-active { transition: width .2s ease, opacity .2s ease; overflow: hidden; }
.slide-enter-from, .slide-leave-to { width: 0 !important; opacity: 0; }

/* 空状态 */
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; color: var(--text-muted); gap: 8px; }
.empty-state .icon { font-size: 36px; }
.spinner { width: 24px; height: 24px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 列设置 */
.col-picker-wrap { position: relative; }
.col-picker-dropdown {
  position: absolute; right: 0; top: calc(100% + 6px); z-index: 200;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 10px 14px; min-width: 150px;
  box-shadow: 0 8px 24px rgba(0,0,0,.4);
}
.col-picker-title { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 8px; }
.col-picker-item { display: flex; align-items: center; gap: 7px; font-size: 13px; padding: 4px 0; cursor: pointer; white-space: nowrap; color: var(--text-base); }
.col-picker-item input[type=checkbox] { accent-color: var(--accent); cursor: pointer; }
/* ── Prometheus 自定义标签 ── */
.label-filter-bar {
  display: flex; align-items: flex-start; gap: 8px; padding: 6px 0 4px;
  border-bottom: 1px solid var(--border); margin-bottom: 4px; flex-wrap: wrap;
}
.label-filter-title { font-size: 11px; color: var(--text-muted); padding-top: 4px; white-space: nowrap; }
.label-filter-tags { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; flex: 1; }
.label-filter-group { display: flex; align-items: center; gap: 3px; flex-wrap: wrap; }
.label-key-name { font-size: 11px; color: var(--text-muted); margin-right: 2px; }
.label-filter-chip {
  font-size: 11px; padding: 2px 8px; border-radius: 12px; cursor: pointer;
  border: 1px solid var(--border); background: var(--bg-hover);
  color: var(--text-secondary); transition: all .15s; white-space: nowrap;
}
.label-filter-chip.active {
  background: rgba(82,130,255,.18); border-color: #5282ff; color: #7aa6ff; font-weight: 500;
}
.label-filter-chip:hover { border-color: #5282ff; }
.label-filter-clear {
  font-size: 11px; padding: 2px 8px; border-radius: 12px; cursor: pointer;
  border: 1px solid var(--border); background: transparent;
  color: var(--text-muted); transition: all .15s;
}
.label-filter-clear:hover { color: var(--error); border-color: var(--error); }

/* 鈹€鈹€ 分组筛选（CMDB 主表）鈹€鈹€ */
.group-filter-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 0 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
  flex-wrap: wrap;
}
.group-filter-search {
  width: 180px; max-width: 48vw;
  height: 28px;
  padding: 0 10px;
  border-radius: 9999px;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 12px;
  outline: none;
}
.group-filter-search:focus { border-color: var(--accent); box-shadow: 0 0 0 2px rgba(82,130,255,.15); }
.group-badge-inline {
  display: inline-flex; align-items: center;
  margin-left: 6px;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 9999px;
  border: 1px solid rgba(82,130,255,.35);
  background: rgba(82,130,255,.12);
  color: #7aa6ff;
}
.action-cell { width: 40px; white-space: nowrap; }
.label-cell { max-width: 260px; }
.label-chips-wrap { display: flex; flex-wrap: wrap; gap: 2px; max-height: 44px; overflow: hidden; }
.label-chip {
  display: inline-flex; align-items: center; gap: 2px;
  font-size: 10px; padding: 1px 6px; border-radius: 10px; cursor: pointer;
  margin: 1px 2px; white-space: nowrap;
  background: hsl(var(--label-hue, 210), 40%, 18%);
  border: 1px solid hsl(var(--label-hue, 210), 50%, 30%);
  color: hsl(var(--label-hue, 210), 80%, 75%);
  transition: opacity .15s;
}
.label-chip:hover { opacity: .8; }
.label-chip b { font-weight: 600; }
.detail-label-list { display: flex; flex-wrap: wrap; gap: 4px; padding: 4px 0 8px; }

/* ── 分组管理 ── */
.groups-wrap { flex: 1; overflow-y: auto; padding: 4px 0; }
.groups-layout { display: flex; gap: 16px; height: 100%; }
.groups-list-panel {
  width: 220px; flex-shrink: 0;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 12px; display: flex; flex-direction: column; gap: 6px;
}
.groups-edit-panel {
  flex: 1; background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 16px; overflow-y: auto;
}
.groups-panel-title { font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 4px; }
.group-item {
  padding: 8px 10px; border-radius: 6px; cursor: pointer;
  border: 1px solid transparent; transition: all .15s;
}
.group-item:hover { background: var(--bg-hover); }
.group-item.active { background: var(--accent-muted, rgba(82,130,255,.12)); border-color: var(--accent, #5282ff); }
.group-item-name { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.group-item-meta { display: flex; align-items: center; gap: 4px; margin-top: 3px; }
.group-host-count { font-size: 11px; color: var(--text-muted); flex: 1; }
.group-badge { font-size: 10px; padding: 1px 5px; border-radius: 10px; font-weight: 500; }
.group-badge.feishu { background: rgba(50,195,120,.15); color: #32c378; }
.group-badge.dingtalk { background: rgba(82,130,255,.15); color: #5282ff; }
.group-form-note {
  font-size: 11px; color: var(--text-muted); background: var(--bg-hover);
  border-radius: 6px; padding: 8px 10px; margin-top: 8px; line-height: 1.5;
}
.group-hosts-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.group-host-chip {
  display: flex; align-items: center; gap: 5px;
  background: var(--bg-hover); border: 1px solid var(--border);
  border-radius: 20px; padding: 3px 10px; font-size: 12px; color: var(--text-secondary);
}
.btn-danger {
  background: rgba(255,70,70,.12); color: var(--error);
  border: 1px solid rgba(255,70,70,.3); border-radius: var(--radius);
  padding: 6px 14px; cursor: pointer; font-size: 13px; transition: all .15s;
}
.btn-danger:hover { background: rgba(255,70,70,.2); }
</style>
