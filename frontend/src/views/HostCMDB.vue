<template>
  <div class="cmdb-page" :class="{ 'ssh-mode': tab === 'ssh', 'ssh-fullscreen': sshFullscreen }">
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
          <button class="tab-btn" :class="{ active: tab === 'ssh' }" @click="tab = 'ssh'">
            SSH 终端
          </button>
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
    <div v-show="tab === 'cmdb'" class="table-wrap">
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
      <table v-else class="host-table">
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
          </tr>
        </thead>
        <tbody>
          <tr v-for="h in sortedHosts" :key="h.instance" @click="selectHost(h)">
            <td><span class="dot" :class="h.state === 'up' ? 'ok' : 'err'"></span></td>
            <td class="hostname">{{ h.hostname || h.instance }}</td>
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
            <td>
              <button class="btn btn-outline btn-xs" @click.stop="openSSH(h)" title="SSH 连接">
                >_
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

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

    <!-- SSH 终端 -->
    <div v-show="tab === 'ssh'" class="ssh-wrap">

      <div class="ssh-session-bar">
        <div v-for="s in sshSessions" :key="s.id"
             class="ssh-session-tab"
             :class="{ active: activeSshId === s.id, 'tab-on': s.connected, 'tab-ing': s.connecting }"
             @click="switchSession(s.id)">
          <span class="tab-dot" :class="s.connected ? 'ok' : s.connecting ? 'warn' : ''"></span>
          <span class="tab-label">{{ s.label }}</span>
          <span class="tab-close" @click.stop="closeSession(s.id)">x</span>
        </div>
        <button class="ssh-tab-add" @click="showNewConnForm = !showNewConnForm">+ 新建</button>
        <div class="ssh-bar-actions">
          <button class="btn btn-outline" @click="showCredModal = true" style="font-size:11px;padding:3px 10px">凭证管理</button>
          <button class="btn btn-outline ssh-fullscreen-btn" @click="toggleSSHFullscreen()" style="font-size:11px;padding:3px 10px">
            {{ sshFullscreen ? '退出全屏' : '全屏' }}
          </button>
        </div>
      </div>

      <transition name="slide-down">
        <div v-show="showNewConnForm && sshSessions.length > 0" class="ssh-toolbar">
          <select class="ssh-input" style="width:280px" @change="onSelectSSHHost($event.target.value)" :value="sshForm.instance">
            <option value="">选择主机...</option>
            <option v-for="h in hosts" :key="h.instance" :value="h.instance">
              {{ h.hostname || h.ip }} ({{ h.ip }}){{ (h.ssh_saved || h.credential_id) ? ' 已保存' : '' }}
            </option>
          </select>
          <select class="ssh-input" style="width:220px" v-model="sshForm.credentialId" @change="onSelectCredential">
            <option value="">手动输入凭证</option>
            <option v-for="c in credentials" :key="c.id" :value="c.id">{{ c.name }} ({{ c.username }})</option>
          </select>
          <input v-model.number="sshForm.port" class="ssh-input" style="width:88px" placeholder="端口" :disabled="sshForm.useSaved || !!sshForm.credentialId" />
          <input v-model="sshForm.username" class="ssh-input" style="width:150px" placeholder="用户名" :disabled="sshForm.useSaved || !!sshForm.credentialId" />
          <input v-model="sshForm.password" class="ssh-input" style="width:220px" type="password"
            :placeholder="sshForm.useSaved || sshForm.credentialId ? '已保存凭证' : '密码'" :disabled="sshForm.useSaved || !!sshForm.credentialId" />
          <span v-if="sshForm.useSaved || sshForm.credentialId" class="saved-badge">已保存</span>
          <button class="btn btn-primary" @click="connectSSH">连接</button>
        </div>
      </transition>

      <div class="term-area">
        <div v-if="!sshSessions.length" class="ssh-welcome-panel">
          <div class="ssh-welcome-card">
            <div class="ssh-welcome-title">
              SSH 终端连接
            </div>
            <div class="ssh-welcome-form">
              <div class="ssh-form-row">
                <label>主机</label>
                <select class="ssh-input" @change="onSelectSSHHost($event.target.value)" :value="sshForm.instance">
                  <option value="">选择主机...</option>
                  <option v-for="h in hosts" :key="h.instance" :value="h.instance">
                    {{ h.hostname || h.ip }} ({{ h.ip }}){{ (h.ssh_saved || h.credential_id) ? ' 已保存' : '' }}
                  </option>
                </select>
              </div>
              <div class="ssh-form-row">
                <label>凭证</label>
                <select class="ssh-input" v-model="sshForm.credentialId" @change="onSelectCredential">
                  <option value="">手动输入</option>
                  <option v-for="c in credentials" :key="c.id" :value="c.id">{{ c.name }} ({{ c.username }})</option>
                </select>
              </div>
              <div class="ssh-form-row">
                <label>端口</label>
                <input v-model.number="sshForm.port" class="ssh-input" placeholder="22" :disabled="sshForm.useSaved || !!sshForm.credentialId" />
              </div>
              <div class="ssh-form-row">
                <label>用户名</label>
                <input v-model="sshForm.username" class="ssh-input" placeholder="root" :disabled="sshForm.useSaved || !!sshForm.credentialId" />
              </div>
              <div class="ssh-form-row">
                <label>密码</label>
                <input v-model="sshForm.password" class="ssh-input" type="password"
                  :placeholder="sshForm.useSaved || sshForm.credentialId ? '已保存凭证' : '输入密码'" :disabled="sshForm.useSaved || !!sshForm.credentialId" />
              </div>
            </div>
            <div class="ssh-welcome-actions">
              <span v-if="sshForm.useSaved || sshForm.credentialId" class="saved-badge">已保存凭证</span>
              <button class="btn btn-primary ssh-connect-btn" @click="connectSSH">
                建立连接
              </button>
            </div>
            <div class="ssh-welcome-hint">支持同时建立多个 SSH 会话</div>
          </div>
        </div>
        <div v-for="s in sshSessions" :key="s.id"
             v-show="activeSshId === s.id"
             :ref="el => setTermRef(s.id, el)"
             class="term-container">
        </div>
      </div>

    </div>

    <transition name="fade">
      <div v-if="showCredModal" class="modal-overlay" @click.self="showCredModal = false">
        <div class="modal-box">
          <div class="modal-header">
            <span>凭证库管理</span>
            <button class="btn btn-outline btn-xs" @click="showCredModal = false">✕</button>
          </div>
          <div class="modal-body">
            <!-- 新建/编辑凭证表单 -->
            <div class="cred-form">
              <div class="cred-form-title">{{ credEditId ? '编辑凭证' : '新建凭证' }}</div>
              <div class="cred-form-row">
                <input v-model="credForm.name" placeholder="凭证名称，如：生产环境root" class="ssh-input" style="flex:2" />
                <input v-model="credForm.username" placeholder="用户名" class="ssh-input" style="flex:1" />
                <input v-model="credForm.password" type="password" :placeholder="credEditId ? '留空不修改' : '密码'" class="ssh-input" style="flex:1" />
                <input v-model.number="credForm.port" type="number" placeholder="端口" class="ssh-input" style="width:70px" />
                <button class="btn btn-primary" @click="saveCred" :disabled="credSaving">
                  {{ credEditId ? '更新' : '添加' }}
                </button>
                <button v-if="credEditId" class="btn btn-outline" @click="resetCredForm">取消</button>
              </div>
            </div>
            <!-- 凭证列表 -->
            <div class="cred-list">
              <div v-if="!credentials.length" class="text-muted" style="text-align:center;padding:20px;font-size:13px">
                暂无凭证，请添加
              </div>
              <div v-for="c in credentials" :key="c.id" class="cred-item">
                <div class="cred-info">
                  <span class="cred-name">{{ c.name }}</span>
                  <span class="cred-detail">{{ c.username }}  :{{ c.port }}</span>
                </div>
                <div class="cred-actions">
                  <button class="btn btn-outline btn-xs" @click="editCred(c)">编辑</button>
                  <button class="btn btn-outline btn-xs" style="border-color:var(--error);color:var(--error)" @click="deleteCred(c.id)">删除</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    </div><!-- /content-main -->

    <!-- 主机详情侧栏（flex 同级，向右扩展） -->
    <transition name="slide">
      <div v-if="selected && tab !== 'ssh'" class="detail-panel">
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
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { api } from '../api/index.js'
import { Terminal } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import 'xterm/css/xterm.css'

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

const editForm = reactive({ owner: '', env: '', role: '', notes: '', ssh_port: 22, ssh_user: '', ssh_password: '', credential_id: '' })

// 排序
const sortKey = ref('')   // 当前排序字段
const sortAsc = ref(true) // true=升序 false=降序
const inspectSortKey = ref('')
const inspectSortAsc = ref(false)
const showPwd = ref(false)

// 凭证库
const credentials     = ref([])
const showCredModal   = ref(false)
const credForm        = reactive({ name: '', username: 'root', password: '', port: 22 })
const credEditId      = ref('')
const credSaving      = ref(false)

// SSH 多会话
const sshSessions     = ref([])    // [{ id, label, host, port, username, password, instance, useSaved, credentialId, connected, connecting }]
const activeSshId     = ref('')
const showNewConnForm = ref(true)
const sshFullscreen   = ref(false)
const sshForm         = reactive({ host: '', port: 22, username: 'root', password: '', instance: '', useSaved: false, credentialId: '' })
const _meta           = {}         // { [id]: { term, fitAddon, ws, resizeObserver } }
const _termEls        = {}         // { [id]: HTMLElement }

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
]
const defaultVisibleCols = new Set(['job', 'cpu', 'mem', 'disk', 'disk_read', 'net_recv', 'tcp_estab', 'load5', 'uptime'])

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

const sortedHosts = computed(() => {
  if (!sortKey.value) return hosts.value
  return [...hosts.value].sort((a, b) => {
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
  editForm.ssh_port = h.ssh_port || 22
  editForm.ssh_user = h.ssh_user || ''
  editForm.ssh_password = ''  // 密码不从后端返回，留空表示不修改
  editForm.credential_id = h.credential_id || ''
  showPwd.value = false
}

function onSelectSSHHost(instance) {
  const h = hosts.value.find(x => x.instance === instance)
  if (!h) return
  sshForm.host     = h.ip
  sshForm.port     = h.ssh_port || 22
  sshForm.username = h.ssh_user || 'root'
  sshForm.password = ''
  sshForm.instance = h.instance
  sshForm.useSaved = !!(h.ssh_saved || h.credential_id)
  sshForm.credentialId = h.credential_id || ''
  // 如果主机绑定了凭证，填充凭证信息
  if (h.credential_id) {
    const c = credentials.value.find(x => x.id === h.credential_id)
    if (c) {
      sshForm.port     = c.port
      sshForm.username = c.username
    }
  }
}

function onSelectCredential() {
  if (sshForm.credentialId) {
    const c = credentials.value.find(x => x.id === sshForm.credentialId)
    if (c) {
      sshForm.port     = c.port
      sshForm.username = c.username
      sshForm.password = ''
      sshForm.useSaved = false  // 凭证库模式，不走 use_saved
    }
  }
}

function openSSH(h) {
  sshForm.host     = h.ip
  sshForm.port     = h.ssh_port || 22
  sshForm.username = h.ssh_user || 'root'
  sshForm.password = ''
  sshForm.instance = h.instance
  sshForm.useSaved = !!(h.ssh_saved || h.credential_id)
  sshForm.credentialId = h.credential_id || ''
  if (h.credential_id) {
    const c = credentials.value.find(x => x.id === h.credential_id)
    if (c) { sshForm.port = c.port; sshForm.username = c.username }
  }
  tab.value = 'ssh'
  selected.value = null
  // 有保存凭证直接新建会话并连接
  if (h.ssh_saved || h.credential_id) {
    nextTick(() => connectSSH())
  } else {
    showNewConnForm.value = true
  }
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

function switchToInspect() {
  tab.value = 'inspect'
  if (!inspecting.value && !inspectResults.value.length) {
    runInspect()
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

// ────────── SSH 多会话 ──────────

function setTermRef(id, el) {
  if (el) _termEls[id] = el
  else delete _termEls[id]
}

function _makeTerminal() {
  return new Terminal({
    cursorBlink: true,
    fontSize: 12,
    fontFamily: '"Cascadia Code", "JetBrains Mono", "Fira Code", "Microsoft YaHei UI", "PingFang SC", "Noto Sans Mono CJK SC", Menlo, Monaco, monospace',
    theme: {
      background: '#0d1117', foreground: '#c9d1d9', cursor: '#58a6ff',
      selectionBackground: '#264f78', black: '#0d1117', red: '#ff7b72',
      green: '#7ee787', yellow: '#d29922', blue: '#58a6ff',
      magenta: '#bc8cff', cyan: '#76e3ea', white: '#c9d1d9',
    },
    scrollback: 5000,
  })
}

function _fitSession(id = activeSshId.value) {
  if (!id) return
  const m = _meta[id]
  if (!m?.fitAddon) return
  m.fitAddon.fit()
  const dims = m.fitAddon.proposeDimensions?.()
  if (dims && m.ws?.readyState === WebSocket.OPEN) {
    m.ws.send(`\x1b[RESIZE:${dims.cols},${dims.rows}]`)
  }
}

function _scheduleFit(id = activeSshId.value, delay = 0) {
  if (!id) return
  const run = () => requestAnimationFrame(() => _fitSession(id))
  if (delay > 0) {
    setTimeout(run, delay)
    return
  }
  nextTick(run)
}

function toggleSSHFullscreen(force) {
  sshFullscreen.value = typeof force === 'boolean' ? force : !sshFullscreen.value
}

function handleWindowKeydown(event) {
  if (event.key === 'Escape' && sshFullscreen.value) {
    toggleSSHFullscreen(false)
  }
}

async function initSessionTerm(id) {
  const el = _termEls[id]
  if (!el || _meta[id]?.term) return
  const m = _meta[id]
  m.term = _makeTerminal()
  m.fitAddon = new FitAddon()
  m.term.loadAddon(m.fitAddon)
  m.term.open(el)
  await nextTick()
  _fitSession(id)
  m.resizeObserver = new ResizeObserver(() => {
    if (activeSshId.value === id) {
      requestAnimationFrame(() => _fitSession(id))
    }
  })
  m.resizeObserver.observe(el)
}

function _buildAuthMsg(s) {
  const useSaved = (s.useSaved || s.credentialId) && s.instance
  if (s.credentialId)
    return { type: 'auth', credential_id: s.credentialId, instance: s.instance, host: s.host }
  if (useSaved)
    return { type: 'auth', use_saved: true, instance: s.instance, host: s.host, port: s.port }
  return { type: 'auth', host: s.host, port: s.port, username: s.username, password: s.password }
}

async function _doConnect(id) {
  const s = sshSessions.value.find(x => x.id === id)
  if (!s) return
  const m = _meta[id]
  const useSaved = (s.useSaved || s.credentialId) && s.instance
  if (!useSaved && (!s.host || !s.username || !s.password)) {
    m.term?.writeln('\x1b[31m请填写完整连接信息\x1b[0m')
    return
  }
  s.connecting = true
  await nextTick()
  await initSessionTerm(id)
  m.term.clear()
  m.term.writeln(`\x1b[36m正在连接 ${s.label} ...\x1b[0m\r\n`)

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  m.ws = new WebSocket(`${proto}://${location.host}/api/ws/ssh`)

  m.ws.onopen = () => {
    m.ws.send(JSON.stringify(_buildAuthMsg(s)))
    s.connected = true
    s.connecting = false
    s.label = s.username + '@' + s.host
    _scheduleFit(id)
    _scheduleFit(id, 240)
  }
  m.ws.onmessage = (e) => m.term.write(e.data)
  m.ws.onclose = () => {
    s.connected = false
    s.connecting = false
    m.term?.writeln('\r\n\x1b[90m连接已关闭\x1b[0m')
  }
  m.ws.onerror = () => {
    s.connected = false
    s.connecting = false
    m.term?.writeln('\r\n\x1b[31mWebSocket 连接错误\x1b[0m')
  }
  m.term.onData((data) => {
    if (m.ws?.readyState === WebSocket.OPEN) m.ws.send(data)
  })
  m.term.onResize(({ cols, rows }) => {
    if (m.ws?.readyState === WebSocket.OPEN) m.ws.send(`\x1b[RESIZE:${cols},${rows}]`)
  })
}

function switchSession(id) {
  activeSshId.value = id
  _scheduleFit(id)
  _scheduleFit(id, 180)
}

function closeSession(id) {
  const m = _meta[id]
  if (m) {
    m.ws?.close()
    m.resizeObserver?.disconnect()
    m.term?.dispose()
    delete _meta[id]
  }
  const idx = sshSessions.value.findIndex(s => s.id === id)
  if (idx !== -1) sshSessions.value.splice(idx, 1)
  if (activeSshId.value === id) {
    const next = sshSessions.value[Math.max(0, idx - 1)]
    activeSshId.value = next?.id || ''
    if (next) {
      _scheduleFit(next.id)
      _scheduleFit(next.id, 180)
    }
    else showNewConnForm.value = true
  }
}

async function connectSSH() {
  const useSaved = (sshForm.useSaved || sshForm.credentialId) && sshForm.instance
  if (!useSaved && (!sshForm.host || !sshForm.username || !sshForm.password)) {
    alert('请填写完整连接信息（主机、用户名、密码）')
    return
  }
  const id = `sess_${Date.now()}`
  const label = sshForm.instance
    ? (hosts.value.find(h => h.instance === sshForm.instance)?.hostname || sshForm.host)
    : sshForm.host
  sshSessions.value.push({
    id, label,
    host: sshForm.host, port: sshForm.port,
    username: sshForm.username, password: sshForm.password,
    instance: sshForm.instance, useSaved: sshForm.useSaved,
    credentialId: sshForm.credentialId,
    connected: false, connecting: false,
  })
  _meta[id] = { term: null, fitAddon: null, ws: null, resizeObserver: null }
  activeSshId.value = id
  showNewConnForm.value = false
  await nextTick()
  await _doConnect(id)
}

onMounted(() => {
  loadHosts()
  loadCredentials()
  window.addEventListener('keydown', handleWindowKeydown)
  document.addEventListener('click', onDocClick)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleWindowKeydown)
  document.removeEventListener('click', onDocClick)
  for (const id of Object.keys(_meta)) closeSession(id)
})

// 切到 SSH tab 时 fit 当前会话
watch(tab, (val) => {
  if (val !== 'ssh' && sshFullscreen.value) {
    sshFullscreen.value = false
  }
  if (val === 'ssh') {
    _scheduleFit()
    _scheduleFit(activeSshId.value, 240)
  }
})

// 连接表单收起/展开时重新 fit（高度变化）
watch(showNewConnForm, () => {
  _scheduleFit()
  _scheduleFit(activeSshId.value, 240)
})

watch(sshFullscreen, () => {
  _scheduleFit()
  _scheduleFit(activeSshId.value, 240)
})
</script>

<style scoped>
.cmdb-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; padding: 8px 12px; gap: 8px; }
.cmdb-page.ssh-mode { padding-left: 4px; padding-right: 4px; }
.cmdb-page.ssh-fullscreen {
  position: fixed; inset: 0; z-index: 1200;
  background: var(--bg-base); padding: 8px 10px;
}
.cmdb-page.ssh-fullscreen .stats-row,
.cmdb-page.ssh-fullscreen .toolbar { display: none; }
.cmdb-page.ssh-fullscreen .content-row { min-height: 100%; }
.cmdb-page.ssh-fullscreen .ssh-session-bar { padding-top: 0; }

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

/* 表格 */
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

/* SSH 终端 */
.ssh-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; gap: 0; width: 100%; }

/* 会话标签栏 */
.ssh-session-bar {
  display: flex; align-items: center; gap: 2px; flex-shrink: 0;
  padding: 6px 0 0; border-bottom: 1px solid var(--border);
  min-height: 36px;
}
.ssh-session-tab {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 10px 4px 8px; border-radius: 5px 5px 0 0;
  font-size: 12px; cursor: pointer; color: var(--text-muted);
  background: var(--bg-base); border: 1px solid var(--border);
  border-bottom: none; transition: all .12s; white-space: nowrap;
  position: relative; bottom: -1px;
}
.ssh-session-tab:hover { color: var(--text-primary); background: var(--bg-hover); }
.ssh-session-tab.active { background: var(--bg-card); color: var(--text-primary); border-color: var(--border); }
.ssh-bar-actions { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.ssh-fullscreen-btn { min-width: 88px; justify-content: center; }
.tab-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
  background: var(--text-muted);
}
.tab-dot.ok   { background: var(--success); }
.tab-dot.warn { background: var(--warning); animation: pulse .8s infinite; }
@keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: .4 } }
.tab-label { max-width: 140px; overflow: hidden; text-overflow: ellipsis; }
.tab-close {
  font-size: 14px; line-height: 1; color: var(--text-muted); margin-left: 2px;
  cursor: pointer; border-radius: 3px; padding: 0 2px;
}
.tab-close:hover { color: var(--error); }
.ssh-tab-add {
  padding: 4px 10px; border-radius: 5px 5px 0 0;
  border: 1px solid var(--border); border-bottom: none;
  background: transparent; color: var(--text-muted);
  font-size: 12px; cursor: pointer; white-space: nowrap;
  position: relative; bottom: -1px; transition: all .12s;
}
.ssh-tab-add:hover { color: var(--text-primary); background: var(--bg-hover); }

/* 新建连接表单（紧凑模式，有会话时使用） */
.ssh-toolbar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  padding: 8px 0; flex-shrink: 0; width: 100%;
  border-bottom: 1px solid var(--border);
}
.slide-down-enter-active, .slide-down-leave-active { transition: all .2s ease; overflow: hidden; }
.slide-down-enter-from, .slide-down-leave-to { max-height: 0; opacity: 0; padding: 0; }
.slide-down-enter-to, .slide-down-leave-from { max-height: 60px; opacity: 1; }

/* 终端区域 & 宽大新建表单 */
.term-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; position: relative; min-height: 0; width: 100%; }
.ssh-welcome-panel {
  flex: 1; display: flex; align-items: stretch; justify-content: flex-start;
  padding: 12px 0 0;
}
.ssh-welcome-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 32px 40px;
  width: 100%; max-width: none; min-height: 100%;
  box-shadow: var(--shadow);
  display: flex; flex-direction: column; gap: 20px;
}
.ssh-welcome-title {
  display: flex; align-items: center; gap: 10px;
  font-size: 16px; font-weight: 600; color: var(--text-primary);
}
.ssh-welcome-icon {
  font-size: 20px; line-height: 1;
}
.ssh-welcome-form {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px 16px;
}
.ssh-form-row { display: flex; flex-direction: column; gap: 5px; }
.ssh-form-row label { font-size: 12px; font-weight: 500; color: var(--text-secondary); margin-bottom: 2px; }
.ssh-form-row .ssh-input { width: 100%; }
.ssh-welcome-actions {
  display: flex; align-items: center; gap: 12px;
}
.ssh-connect-btn { padding: 8px 24px; font-size: 14px; }
.ssh-welcome-hint {
  font-size: 12px; color: var(--text-muted); text-align: center;
}
.ssh-input {
  background: var(--bg-input, var(--bg-hover)); border: 1px solid var(--border);
  color: var(--text-primary); padding: 6px 10px; border-radius: 6px;
  font-size: 13px; font-family: inherit; outline: none;
  transition: border-color .15s, box-shadow .15s;
}
.ssh-input:focus { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }
.ssh-input:disabled { opacity: .45; cursor: not-allowed; }
.saved-badge {
  font-size: 11px; padding: 3px 10px; border-radius: 9999px;
  background: rgba(0,255,136,.12); color: var(--success); font-weight: 600;
  border: 1px solid var(--success);
}
.password-wrap { display: flex; gap: 4px; }
.password-wrap input { flex: 1; }
.pwd-toggle {
  background: var(--bg-hover); border: 1px solid var(--border); color: var(--text-muted);
  padding: 4px 8px; border-radius: 5px; font-size: 11px; cursor: pointer; white-space: nowrap;
  transition: color .15s;
}
.pwd-toggle:hover { color: var(--accent); }
.term-container {
  position: absolute; inset: 0;
  background: #0d1117; border-radius: var(--radius);
  border: 1px solid var(--border); overflow: hidden; padding: 0;
  display: flex; flex-direction: column;
}
/* xterm 内部元素撑满容器 */
.term-container :deep(.xterm) { flex: 1; min-height: 0; width: 100%; padding: 8px 10px; }
.term-container :deep(.xterm-viewport) { overflow-y: auto !important; }
.term-container :deep(.xterm-screen) { width: 100% !important; }

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

/* 凭证弹窗 */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.5);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.modal-box {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); width: 680px; max-width: 95vw; max-height: 80vh;
  display: flex; flex-direction: column;
  box-shadow: var(--shadow);
}
.modal-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid var(--border);
  font-weight: 600; font-size: 14px; color: var(--text-primary);
}
.modal-body { flex: 1; overflow-y: auto; padding: 16px 18px; }
.cred-form { margin-bottom: 16px; }
.cred-form-title { font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 8px; }
.cred-form-row { display: flex; gap: 6px; align-items: center; }
.cred-list { display: flex; flex-direction: column; gap: 6px; }
.cred-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 12px; background: var(--bg-base); border-radius: 6px;
  border: 1px solid var(--border);
}
.cred-info { display: flex; flex-direction: column; gap: 2px; }
.cred-name { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.cred-detail { font-size: 11px; color: var(--text-muted); }
.cred-actions { display: flex; gap: 6px; }

.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

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
</style>
