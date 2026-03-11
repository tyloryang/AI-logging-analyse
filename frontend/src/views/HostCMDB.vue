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
          <button class="tab-btn" :class="{ active: tab === 'inspect' }" @click="tab = 'inspect'; runInspect()">
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
        <button v-if="tab === 'inspect'" class="btn btn-primary" @click="runInspect" :disabled="inspecting">
          <span v-if="inspecting" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
          <span v-else>🔍</span> 执行巡检
        </button>
      </div>
    </div>

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
            <th>状态</th>
            <th>主机名</th>
            <th>IP</th>
            <th>CPU%</th>
            <th>内存%</th>
            <th>磁盘(/)</th>
            <th>I/O(R/W)</th>
            <th>网络(↓/↑)</th>
            <th>TCP</th>
            <th>负载</th>
            <th>运行时长</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="h in hosts" :key="h.instance" @click="selectHost(h)">
            <td><span class="dot" :class="h.state === 'up' ? 'ok' : 'err'"></span></td>
            <td class="hostname">{{ h.hostname || h.instance }}</td>
            <td>{{ h.ip }}</td>
            <td :class="usageClass(h.metrics.cpu_usage)">{{ fmt(h.metrics.cpu_usage, '%') }}</td>
            <td :class="usageClass(h.metrics.mem_usage)">{{ fmt(h.metrics.mem_usage, '%') }}</td>
            <td :class="usageClass(rootDiskUsage(h))">{{ fmt(rootDiskUsage(h), '%') }}</td>
            <td class="small-text">{{ fmtIO(h.metrics) }}</td>
            <td class="small-text">{{ fmtNet(h.metrics) }}</td>
            <td class="small-text">{{ fmtTcp(h.metrics) }}</td>
            <td>{{ h.metrics.load5 != null ? h.metrics.load5.toFixed(2) : '-' }}</td>
            <td>{{ fmtUptime(h.metrics.uptime_seconds) }}</td>
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
      <div v-else-if="!inspectResults.length" class="empty-state">
        <span class="icon">🔍</span><p>点击「执行巡检」开始</p>
      </div>
      <div v-else class="inspect-list">
        <div v-for="r in inspectResults" :key="r.instance" class="inspect-card" :class="'card-' + r.overall">
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

    <!-- SSH 终端 -->
    <div v-show="tab === 'ssh'" class="ssh-wrap">
      <!-- SSH 连接栏 -->
      <div class="ssh-toolbar">
        <select v-model="sshForm.host" class="ssh-input" style="width:180px">
          <option value="">选择主机...</option>
          <option v-for="h in hosts" :key="h.instance" :value="h.ip">
            {{ h.hostname || h.ip }} ({{ h.ip }})
          </option>
        </select>
        <input v-model.number="sshForm.port" class="ssh-input" style="width:70px" placeholder="端口" />
        <input v-model="sshForm.username" class="ssh-input" style="width:110px" placeholder="用户名" />
        <input v-model="sshForm.password" class="ssh-input" style="width:130px" type="password" placeholder="密码" />
        <button class="btn btn-primary" @click="connectSSH" :disabled="sshConnecting" v-if="!sshConnected">
          {{ sshConnecting ? '连接中...' : '连接' }}
        </button>
        <button class="btn btn-outline" style="border-color:var(--error);color:var(--error)" @click="disconnectSSH" v-else>
          断开
        </button>
      </div>
      <!-- 终端容器 -->
      <div ref="termRef" class="term-container"></div>
    </div>

    <!-- 主机详情侧栏 -->
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
          <button class="btn btn-primary" style="width:100%;margin-top:8px" @click="saveHost" :disabled="saving">
            {{ saving ? '保存中...' : '保存' }}
          </button>
          <button class="btn btn-outline" style="width:100%;margin-top:6px" @click="openSSH(selected)">
            >_ SSH 连接
          </button>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
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

const editForm = reactive({ owner: '', env: '', role: '', notes: '' })

// SSH 相关
const termRef        = ref(null)
const sshForm        = reactive({ host: '', port: 22, username: 'root', password: '' })
const sshConnected   = ref(false)
const sshConnecting  = ref(false)
let term = null
let fitAddon = null
let ws = null
let resizeObserver = null

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

function rootDiskUsage(h) {
  // 取根分区使用率
  if (h.partitions && h.partitions.length) {
    const root = h.partitions.find(p => p.mountpoint === '/')
    if (root) return root.usage_pct
    return h.partitions[0].usage_pct
  }
  return h.metrics.disk_usage
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
}

function openSSH(h) {
  sshForm.host     = h.ip
  sshForm.port     = h.ssh_port || 22
  sshForm.username = h.ssh_user || 'root'
  sshForm.password = ''
  tab.value = 'ssh'
  selected.value = null
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
    await api.updateHost(selected.value.instance, {
      owner: editForm.owner,
      env:   editForm.env,
      role:  editForm.role,
      notes: editForm.notes,
    })
    selected.value.owner = editForm.owner
    selected.value.env   = editForm.env
    selected.value.role  = editForm.role
    selected.value.notes = editForm.notes
  } finally {
    saving.value = false
  }
}

async function runInspect() {
  inspecting.value = true
  inspectResults.value = []
  try {
    const r = await api.inspectHosts()
    inspectResults.value = r.data
    inspectSummary.value = r.summary
  } catch (e) {
    error.value = typeof e === 'string' ? e : (e?.message || '巡检失败')
  } finally {
    inspecting.value = false
  }
}

// ────────── SSH 终端 ──────────

function initTerminal() {
  if (term) return
  term = new Terminal({
    cursorBlink: true,
    fontSize: 13,
    fontFamily: '"Cascadia Code", "JetBrains Mono", "Fira Code", Menlo, Monaco, monospace',
    theme: {
      background: '#0d1117',
      foreground: '#c9d1d9',
      cursor: '#58a6ff',
      selectionBackground: '#264f78',
      black: '#0d1117',
      red: '#ff7b72',
      green: '#7ee787',
      yellow: '#d29922',
      blue: '#58a6ff',
      magenta: '#bc8cff',
      cyan: '#76e3ea',
      white: '#c9d1d9',
    },
    scrollback: 5000,
  })
  fitAddon = new FitAddon()
  term.loadAddon(fitAddon)
  term.open(termRef.value)
  fitAddon.fit()
  term.writeln('\x1b[36m欢迎使用 SSH 终端\x1b[0m')
  term.writeln('\x1b[90m选择主机并输入凭据后点击「连接」\x1b[0m\r\n')

  // 监听容器大小变化
  resizeObserver = new ResizeObserver(() => {
    if (fitAddon) fitAddon.fit()
  })
  resizeObserver.observe(termRef.value)
}

async function connectSSH() {
  if (!sshForm.host || !sshForm.username || !sshForm.password) {
    term?.writeln('\x1b[31m请填写完整的连接信息\x1b[0m')
    return
  }

  sshConnecting.value = true
  await nextTick()
  if (!term) initTerminal()
  term.clear()
  term.writeln(`\x1b[36m正在连接 ${sshForm.username}@${sshForm.host}:${sshForm.port} ...\x1b[0m\r\n`)

  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const wsUrl = `${proto}://${location.host}/api/ws/ssh`

  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    // 通过 WebSocket 消息发送凭据（不暴露在 URL 中）
    ws.send(JSON.stringify({
      type: 'auth',
      host: sshForm.host,
      port: sshForm.port,
      username: sshForm.username,
      password: sshForm.password,
    }))
    sshConnected.value = true
    sshConnecting.value = false
    // 发送初始终端大小
    const dims = fitAddon.proposeDimensions()
    if (dims) {
      ws.send(`\x1b[RESIZE:${dims.cols},${dims.rows}]`)
    }
  }

  ws.onmessage = (e) => {
    term.write(e.data)
  }

  ws.onclose = () => {
    sshConnected.value = false
    sshConnecting.value = false
    term?.writeln('\r\n\x1b[90m连接已关闭\x1b[0m')
  }

  ws.onerror = () => {
    sshConnected.value = false
    sshConnecting.value = false
    term?.writeln('\r\n\x1b[31mWebSocket 连接错误\x1b[0m')
  }

  // 终端输入 → WebSocket
  term.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(data)
    }
  })

  // 终端大小变化 → 通知后端
  term.onResize(({ cols, rows }) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(`\x1b[RESIZE:${cols},${rows}]`)
    }
  })
}

function disconnectSSH() {
  if (ws) {
    ws.close()
    ws = null
  }
  sshConnected.value = false
}

onMounted(() => {
  loadHosts()
})

onBeforeUnmount(() => {
  disconnectSSH()
  if (resizeObserver) resizeObserver.disconnect()
  if (term) term.dispose()
})

// 切到 SSH tab 时初始化终端
watch(tab, (val) => {
  if (val === 'ssh') {
    nextTick(() => {
      if (!term) initTerminal()
      else fitAddon?.fit()
    })
  }
})
</script>

<style scoped>
.cmdb-page { display: flex; flex-direction: column; height: 100vh; overflow: hidden; padding: 16px; gap: 12px; position: relative; }

/* 统计卡片 */
.stats-row { display: flex; gap: 12px; flex-shrink: 0; }
.stat-card {
  flex: 1; background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 14px 16px; text-align: center;
}
.stat-val { font-size: 24px; font-weight: 700; color: var(--text-primary); }
.stat-label { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
.stat-card.ok .stat-val { color: var(--success); }
.stat-card.warn .stat-val { color: var(--warning); }
.stat-card.error .stat-val { color: var(--error); }

/* 工具栏 */
.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 8px 14px; flex-shrink: 0;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; }
.tab-group { display: flex; gap: 2px; background: var(--bg-base); padding: 3px; border-radius: 8px; }
.tab-btn {
  padding: 5px 14px; border-radius: 6px; border: none;
  background: transparent; color: var(--text-muted);
  font-size: 13px; cursor: pointer; transition: all .15s;
}
.tab-btn:hover { color: var(--text-primary); }
.tab-btn.active { background: var(--bg-active); color: var(--text-primary); }

/* 表格 */
.table-wrap { flex: 1; overflow-y: auto; }
.host-table {
  width: 100%; border-collapse: collapse; font-size: 12px;
}
.host-table th {
  text-align: left; padding: 8px 10px; font-weight: 600;
  color: var(--text-muted); font-size: 11px; text-transform: uppercase;
  letter-spacing: .5px; border-bottom: 1px solid var(--border);
  position: sticky; top: 0; background: var(--bg-base); z-index: 1;
}
.host-table td {
  padding: 8px 10px; border-bottom: 1px solid rgba(46,49,80,.3);
  color: var(--text-secondary); white-space: nowrap;
}
.host-table tr { cursor: pointer; transition: background .1s; }
.host-table tr:hover { background: var(--bg-hover); }
.hostname { color: var(--text-primary); font-weight: 600; }
.small-text { font-size: 11px; color: var(--text-muted); }
.tag.role {
  display: inline-block; font-size: 10px; padding: 1px 6px;
  border-radius: 9999px; background: rgba(99,102,241,.15);
  color: var(--accent-hover); margin-right: 4px;
}

.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; }
.dot.ok, .dot.normal { background: var(--success); box-shadow: 0 0 6px var(--success); }
.dot.err, .dot.critical { background: var(--error); box-shadow: 0 0 6px var(--error); }
.dot.warning { background: var(--warning); box-shadow: 0 0 6px var(--warning); }

.usage-ok { color: var(--success); }
.usage-warning { color: var(--warning); }
.usage-critical { color: var(--error); font-weight: 600; }

.text-muted { color: var(--text-muted); }

/* 巡检 */
.inspect-wrap { flex: 1; overflow-y: auto; }
.inspect-list { display: flex; flex-direction: column; gap: 10px; }
.inspect-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 14px 16px;
  transition: border-color .15s;
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
.ssh-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.ssh-toolbar {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 0; flex-shrink: 0;
}
.ssh-input {
  background: var(--bg-hover); border: 1px solid var(--border);
  color: var(--text-primary); padding: 5px 8px; border-radius: 5px;
  font-size: 12px; font-family: inherit;
}
.term-container {
  flex: 1; background: #0d1117; border-radius: var(--radius);
  border: 1px solid var(--border); overflow: hidden; padding: 4px;
}

/* 详情侧栏 */
.detail-panel {
  position: absolute; top: 0; right: 0; bottom: 0;
  width: 340px; background: var(--bg-card);
  border-left: 1px solid var(--border);
  display: flex; flex-direction: column;
  box-shadow: -4px 0 20px rgba(0,0,0,.3); z-index: 10;
}
.detail-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 16px; border-bottom: 1px solid var(--border);
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

/* 过渡 */
.slide-enter-active, .slide-leave-active { transition: transform .2s ease; }
.slide-enter-from, .slide-leave-to { transform: translateX(100%); }

/* 空状态 */
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; color: var(--text-muted); gap: 8px; }
.empty-state .icon { font-size: 36px; }
.spinner { width: 24px; height: 24px; border: 3px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
