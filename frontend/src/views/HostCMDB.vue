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
          <button class="tab-btn" :class="{ active: tab === 'cmdb' }" @click="tab = 'cmdb'">主机 CMDB</button>
          <button class="tab-btn" :class="{ active: tab === 'inspect' }" @click="switchToInspect">巡检报告</button>
          <button class="tab-btn" :class="{ active: tab === 'groups' }" @click="tab = 'groups'">分组管理</button>
          <RouterLink to="/tools/ssh" class="tab-btn ssh-link">SSH 终端 →</RouterLink>
        </div>
      </div>
      <div class="toolbar-right">
        <input v-if="tab === 'cmdb'" v-model="search" class="search-input" placeholder="搜索主机名/IP/负责人..." />
        <template v-if="tab === 'cmdb'">
          <select v-model="envFilter" class="filter-select">
            <option value="">全部环境</option>
            <option value="production">生产</option>
            <option value="staging">预发</option>
            <option value="development">开发</option>
            <option value="testing">测试</option>
            <option value="dr">容灾</option>
          </select>
          <select v-model="groupFilter" class="filter-select">
            <option value="">全部分组</option>
            <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
          </select>
          <button class="btn btn-primary" @click="openAdd">+ 添加主机</button>
        </template>
        <button class="btn btn-outline" @click="tab === 'cmdb' ? loadHosts() : (tab === 'groups' ? loadGroups() : null)" :disabled="loading">
          <span v-if="loading" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
          <span v-else>↺</span> 刷新
        </button>
        <!-- 巡检操作按钮 -->
        <template v-if="tab === 'inspect'">
          <select v-model="inspectGroupId" class="filter-select" :disabled="inspecting">
            <option value="">全部主机</option>
            <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}（{{ g.host_count || 0 }}台）</option>
          </select>
          <button class="btn btn-primary" @click="runInspect" :disabled="inspecting || inspectAiStreaming">
            <span v-if="inspecting" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>🔍</span> {{ inspectGroupId ? '巡检此分组' : '执行巡检' }}
          </button>
          <button v-if="inspectResults.length && !inspecting" class="btn btn-ai" :disabled="inspectAiStreaming" @click="runInspectAI">
            <span v-if="inspectAiStreaming" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>🤖</span> AI分析
          </button>
          <button v-if="inspectResults.length && !inspecting && groups.length" class="btn btn-outline"
            :disabled="notifyingGroups || !inspectGroupId" @click="notifyGroups()">
            <span v-if="notifyingGroups" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>📤</span> 推送当前分组
          </button>
          <button v-if="inspectResults.length && !inspecting" class="btn btn-excel" :disabled="excelDownloading" @click="downloadInspectExcel">
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
              <th>状态</th>
              <th class="th-sort" @click="setSort('hostname')">主机名<span class="sort-icon">{{ sortKey==='hostname'?(sortAsc?'↑':'↓'):'⇅'}}</span></th>
              <th class="th-sort" @click="setSort('ip')">IP<span class="sort-icon">{{ sortKey==='ip'?(sortAsc?'↑':'↓'):'⇅'}}</span></th>
              <th>平台</th>
              <th>操作系统</th>
              <th>配置</th>
              <th class="th-sort" @click="setSort('env')">环境<span class="sort-icon">{{ sortKey==='env'?(sortAsc?'↑':'↓'):'⇅'}}</span></th>
              <th>用途</th>
              <th>负责人</th>
              <th>机房</th>
              <th>分组</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="h in sortedHosts" :key="h.id" @click="selectHost(h)">
              <td><span class="status-dot" :class="h.status"></span><span class="status-text">{{ statusLabel(h.status) }}</span></td>
              <td class="hostname-cell">
                <span class="hostname">{{ h.hostname }}</span>
                <span v-if="h.ssh_saved" class="ssh-badge" title="已配置 SSH 凭证">SSH</span>
              </td>
              <td class="mono">{{ h.ip }}</td>
              <td><span class="platform-badge" :class="h.platform?.toLowerCase()">{{ h.platform || '-' }}</span></td>
              <td class="small-text">{{ h.os_version || '-' }}</td>
              <td class="small-text">
                <span v-if="h.cpu_cores">{{ h.cpu_cores }}C</span>
                <span v-if="h.cpu_cores && h.memory_gb"> / </span>
                <span v-if="h.memory_gb">{{ h.memory_gb }}G</span>
                <span v-if="!h.cpu_cores && !h.memory_gb">-</span>
              </td>
              <td><span class="env-badge" :class="h.env">{{ envLabel(h.env) }}</span></td>
              <td class="small-text">{{ h.role || '-' }}</td>
              <td class="small-text">{{ h.owner || '-' }}</td>
              <td class="small-text">{{ h.datacenter || '-' }}</td>
              <td><span v-if="h.group && groupMap[h.group]" class="group-badge-inline">{{ groupMap[h.group] }}</span><span v-else>-</span></td>
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
    </div>

    <!-- 巡检报告 -->
    <div v-show="tab === 'inspect'" class="inspect-wrap">
      <div v-if="inspecting" class="empty-state"><div class="spinner"></div><p>巡检中，请稍候...</p></div>
      <div v-else-if="inspectError" class="empty-state">
        <span class="icon">⚠️</span><p style="color:var(--error)">{{ inspectError }}</p>
        <button class="btn btn-outline" style="margin-top:10px" @click="runInspect">重试</button>
      </div>
      <div v-else-if="!inspectResults.length" class="empty-state">
        <span class="icon">🔍</span><p>点击「执行巡检」开始<br><small style="color:var(--text-muted)">巡检依赖 Prometheus node_exporter 指标</small></p>
      </div>
      <div v-else style="flex:1;display:flex;flex-direction:column;overflow:hidden;min-height:0">
        <div class="inspect-scope-bar">
          <span class="inspect-scope-label">巡检范围：</span>
          <span class="inspect-scope-badge" :class="inspectSummary.group_id ? 'group' : 'all'">
            {{ inspectSummary.group_name || '全部主机' }}
          </span>
          <span class="inspect-scope-stat">共 {{ inspectSummary.total }} 台 · 正常 {{ inspectSummary.normal }} · 警告 {{ inspectSummary.warning }} · 严重 {{ inspectSummary.critical }}</span>
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
                <th>状态</th>
                <th>主机名</th>
                <th>IP</th>
                <th>OS</th>
                <th>分组</th>
                <th v-for="col in inspectCheckCols" :key="col">{{ col }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in inspectResults" :key="r.instance" :class="'irow-'+r.overall">
                <td><span class="inspect-badge" :class="r.overall">{{ inspectStatusLabel(r.overall) }}</span></td>
                <td class="itd-host">{{ r.hostname || r.instance }}</td>
                <td class="mono itd-ip">{{ r.ip }}</td>
                <td class="itd-os">{{ r.os || '-' }}</td>
                <td class="itd-group">{{ groupMap[r.group] || '-' }}</td>
                <td v-for="col in inspectCheckCols" :key="col">
                  <span v-if="checkStatus(r, col)" class="check-cell" :class="checkStatus(r, col)">
                    {{ checkValue(r, col) }}
                  </span>
                  <span v-else class="check-na">-</span>
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
            <span v-if="g.schedule_enabled" class="group-meta-item ok">定时 {{ g.schedule_time }}</span>
          </div>
          <div v-if="g.description" class="group-desc">{{ g.description }}</div>
        </div>
      </div>
    </div>

    </div><!-- /content-main -->

    <!-- 右侧详情面板 -->
    <div v-if="selectedHost" class="detail-panel">
      <div class="detail-header">
        <span>主机详情</span>
        <button class="close-btn" @click="selectedHost = null">✕</button>
      </div>
      <div class="detail-body">
        <div class="detail-row"><span class="dl">主机名</span><span class="dv">{{ selectedHost.hostname }}</span></div>
        <div class="detail-row"><span class="dl">IP 地址</span><span class="dv mono">{{ selectedHost.ip }}</span></div>
        <div class="detail-row"><span class="dl">平台</span><span class="dv">{{ selectedHost.platform }}</span></div>
        <div class="detail-row"><span class="dl">操作系统</span><span class="dv">{{ selectedHost.os_version || '-' }}</span></div>
        <div class="detail-row"><span class="dl">CPU核心</span><span class="dv">{{ selectedHost.cpu_cores ? selectedHost.cpu_cores + ' 核' : '-' }}</span></div>
        <div class="detail-row"><span class="dl">内存</span><span class="dv">{{ selectedHost.memory_gb ? selectedHost.memory_gb + ' GB' : '-' }}</span></div>
        <div class="detail-row"><span class="dl">磁盘</span><span class="dv">{{ selectedHost.disk_gb ? selectedHost.disk_gb + ' GB' : '-' }}</span></div>
        <div class="detail-row"><span class="dl">状态</span><span class="dv">{{ statusLabel(selectedHost.status) }}</span></div>
        <div class="detail-row"><span class="dl">环境</span><span class="dv">{{ envLabel(selectedHost.env) }}</span></div>
        <div class="detail-row"><span class="dl">用途</span><span class="dv">{{ selectedHost.role || '-' }}</span></div>
        <div class="detail-row"><span class="dl">负责人</span><span class="dv">{{ selectedHost.owner || '-' }}</span></div>
        <div class="detail-row"><span class="dl">机房</span><span class="dv">{{ selectedHost.datacenter || '-' }}</span></div>
        <div class="detail-row"><span class="dl">SSH 端口</span><span class="dv">{{ selectedHost.ssh_port }}</span></div>
        <div class="detail-row"><span class="dl">SSH 用户</span><span class="dv">{{ selectedHost.ssh_user || '-' }}</span></div>
        <div class="detail-row"><span class="dl">SSH 凭证</span><span class="dv">{{ selectedHost.ssh_saved ? '已配置' : '未配置' }}</span></div>
        <div class="detail-row"><span class="dl">备注</span><span class="dv">{{ selectedHost.notes || '-' }}</span></div>
        <div v-if="selectedHost.labels && Object.keys(selectedHost.labels).length" class="detail-row">
          <span class="dl">标签</span>
          <span class="dv">
            <span v-for="(v, k) in selectedHost.labels" :key="k" class="label-chip-detail">{{ k }}={{ v }}</span>
          </span>
        </div>
        <div class="detail-row"><span class="dl">录入时间</span><span class="dv small-text">{{ selectedHost.created_at }}</span></div>
        <div class="detail-row"><span class="dl">更新时间</span><span class="dv small-text">{{ selectedHost.updated_at }}</span></div>
        <div v-if="syncMsg" class="sync-msg" :class="syncOk ? 'ok' : 'err'">{{ syncMsg }}</div>
        <div class="detail-actions">
          <button class="btn btn-primary" style="width:100%;margin-bottom:6px" @click="openEdit(selectedHost)">编辑主机</button>
          <button class="btn btn-sync" style="width:100%;margin-bottom:6px" :disabled="syncingId === selectedHost.id" @click="syncHost(selectedHost)">
            <span v-if="syncingId === selectedHost.id" class="spinner" style="width:13px;height:13px;border-width:2px"></span>
            <span v-else>⟳</span> 同步系统信息
          </button>
          <button class="btn btn-outline" style="width:100%" @click="openSSH(selectedHost)">SSH 连接</button>
        </div>
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
              <div class="form-group required">
                <label>主机名</label>
                <input v-model="hostForm.hostname" placeholder="e.g. web-01" required />
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
                <input v-model.number="hostForm.cpu_cores" type="number" min="1" placeholder="e.g. 8" />
              </div>
              <div class="form-group">
                <label>内存 (GB)</label>
                <input v-model.number="hostForm.memory_gb" type="number" min="0" step="0.5" placeholder="e.g. 16" />
              </div>
              <div class="form-group">
                <label>磁盘 (GB)</label>
                <input v-model.number="hostForm.disk_gb" type="number" min="0" placeholder="e.g. 500" />
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
                <label>SSH 密码 <span class="form-hint">{{ editingHost ? '（留空保持不变）' : '' }}</span></label>
                <input v-model="hostForm.ssh_password" type="password" placeholder="输入密码加密存储" autocomplete="new-password" />
              </div>
              <div class="form-group">
                <label>或关联凭证</label>
                <select v-model="hostForm.credential_id">
                  <option value="">不使用凭证库</option>
                  <option v-for="c in credentials" :key="c.id" :value="c.id">{{ c.name }}</option>
                </select>
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
import { ref, reactive, computed, watch, onMounted } from 'vue'
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

async function loadHosts() {
  loading.value = true
  try {
    const res = await api.getHosts()
    hosts.value = res.data || []
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
    credentials.value = res || []
  } catch {}
}

onMounted(() => { loadHosts(); loadGroups(); loadCredentials() })

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

// ── 添加/编辑主机 ─────────────────────────────────────────────────────────────
const showHostModal = ref(false)
const editingHost   = ref(null)
const saving        = ref(false)
const hostFormError = ref('')
const labelsText    = ref('')

const hostForm = reactive({
  hostname: '', ip: '', platform: 'Linux', os_version: '',
  cpu_cores: null, memory_gb: null, disk_gb: null,
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

function openAdd() {
  editingHost.value = null
  hostFormError.value = ''
  labelsText.value = ''
  Object.assign(hostForm, {
    hostname: '', ip: '', platform: 'Linux', os_version: '',
    cpu_cores: null, memory_gb: null, disk_gb: null,
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
    os_version: h.os_version || '', cpu_cores: h.cpu_cores || null,
    memory_gb: h.memory_gb || null, disk_gb: h.disk_gb || null,
    status: h.status || 'active', env: h.env || 'production',
    role: h.role || '', owner: h.owner || '', datacenter: h.datacenter || '',
    group: h.group || '', ssh_port: h.ssh_port || 22,
    ssh_user: h.ssh_user || '', ssh_password: '',
    credential_id: h.credential_id || '', notes: h.notes || '',
  })
  showHostModal.value = true
}

async function saveHost() {
  hostFormError.value = ''
  if (!hostForm.hostname.trim()) { hostFormError.value = '主机名不能为空'; return }
  if (!hostForm.ip.trim()) { hostFormError.value = 'IP 地址不能为空'; return }
  saving.value = true
  const payload = { ...hostForm, labels: parseLabels(labelsText.value) }
  if (!payload.cpu_cores) payload.cpu_cores = null
  if (!payload.memory_gb) payload.memory_gb = null
  if (!payload.disk_gb) payload.disk_gb = null
  try {
    if (editingHost.value) {
      await api.updateHost(editingHost.value.id, payload)
    } else {
      await api.createHost(payload)
    }
    showHostModal.value = false
    await loadHosts()
    selectedHost.value = null
  } catch (e) {
    hostFormError.value = typeof e === 'string' ? e : '保存失败，请重试'
  } finally {
    saving.value = false
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

// ── SSH 同步系统信息 ──────────────────────────────────────────────────────────
const syncingId = ref('')
const syncMsg   = ref('')
const syncOk    = ref(false)

async function syncHost(h) {
  if (!h.ssh_saved && !h.credential_id) {
    syncMsg.value = '请先配置 SSH 密码或关联凭证'
    syncOk.value = false
    return
  }
  syncingId.value = h.id
  syncMsg.value = ''
  try {
    const res = await api.syncHost(h.id)
    const updated = res.updated || {}
    const parts = []
    if (updated.os_version)  parts.push(`OS: ${updated.os_version}`)
    if (updated.cpu_cores)   parts.push(`CPU: ${updated.cpu_cores}核`)
    if (updated.memory_gb)   parts.push(`内存: ${updated.memory_gb}G`)
    if (updated.disk_gb)     parts.push(`磁盘: ${updated.disk_gb}G`)
    if (updated.hostname)    parts.push(`主机名: ${updated.hostname}`)
    syncMsg.value = parts.length ? `已同步：${parts.join(' / ')}` : '同步完成'
    syncOk.value = true
    // 刷新列表
    await loadHosts()
    // 如果右侧面板是这台主机，更新
    if (selectedHost.value?.id === h.id) {
      selectedHost.value = hosts.value.find(x => x.id === h.id) || selectedHost.value
    }
  } catch (e) {
    syncMsg.value = '同步失败：' + (typeof e === 'string' ? e : '请检查 SSH 密码和网络连通性')
    syncOk.value = false
  } finally {
    syncingId.value = ''
  }
}

// ── SSH 跳转 ──────────────────────────────────────────────────────────────────
function openSSH(h) {
  sessionStorage.setItem('ssh_prefill', JSON.stringify({
    host: h.ip, port: h.ssh_port || 22, username: h.ssh_user || 'root',
    credential_id: h.credential_id || '',
  }))
  router.push('/tools/ssh')
}

// ── 巡检 ─────────────────────────────────────────────────────────────────────
const inspecting         = ref(false)
const inspectError       = ref('')
const inspectResults     = ref([])
const inspectSummary     = reactive({ total: 0, normal: 0, warning: 0, critical: 0, group_id: '', group_name: '' })
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

const inspectCheckCols = computed(() => {
  const cols = new Set()
  inspectResults.value.forEach(r => (r.checks || []).forEach(c => cols.add(c.item)))
  return [...cols]
})

function checkStatus(r, col) {
  const c = (r.checks || []).find(c => c.item === col)
  return c?.status
}
function checkValue(r, col) {
  const c = (r.checks || []).find(c => c.item === col)
  return c?.value ?? '-'
}

function switchToInspect() { tab.value = 'inspect' }

async function runInspect() {
  inspecting.value = true
  inspectError.value = ''
  inspectResults.value = []
  inspectAiSummary.value = ''
  inspectNotifyMessage.value = ''
  const url = `/api/hosts/inspect${inspectGroupId.value ? `?group_id=${encodeURIComponent(inspectGroupId.value)}` : ''}`
  const es = new EventSource(url)
  es.onmessage = (e) => {
    if (e.data === '[DONE]') { es.close(); inspecting.value = false; return }
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
})

function openAddGroup() {
  editingGroup.value = null
  groupFormError.value = ''
  Object.assign(groupForm, { name: '', description: '', feishu_webhook: '', feishu_keyword: '', dingtalk_webhook: '', dingtalk_keyword: '', schedule_time: '09:00', schedule_enabled: false })
  showGroupModal.value = true
}

function openEditGroup(g) {
  editingGroup.value = g
  groupFormError.value = ''
  Object.assign(groupForm, { name: g.name, description: g.description || '', feishu_webhook: g.feishu_webhook || '', feishu_keyword: g.feishu_keyword || '', dingtalk_webhook: g.dingtalk_webhook || '', dingtalk_keyword: g.dingtalk_keyword || '', schedule_time: g.schedule_time || '09:00', schedule_enabled: !!g.schedule_enabled })
  showGroupModal.value = true
}

async function saveGroup() {
  groupFormError.value = ''
  if (!groupForm.name.trim()) { groupFormError.value = '分组名称不能为空'; return }
  savingGroup.value = true
  try {
    if (editingGroup.value) {
      await api.updateGroup(editingGroup.value.id, { ...groupForm })
    } else {
      await api.createGroup({ ...groupForm })
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
.tab-btn.ssh-link { text-decoration: none; display: flex; align-items: center; color: var(--text-muted); }
.search-input { padding: 5px 10px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 13px; width: 200px; }
.filter-select { padding: 5px 8px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 12px; }

/* 内容区 */
.content-row { display: flex; gap: 10px; flex: 1; overflow: hidden; min-height: 0; }
.content-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }

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
.hostname-cell { display: flex; align-items: center; gap: 5px; }
.hostname { font-weight: 500; }
.ssh-badge { font-size: 10px; padding: 1px 5px; border-radius: 3px; background: rgba(56,139,253,.15); color: var(--accent); }
.mono { font-family: 'Cascadia Code','Consolas',monospace; font-size: 12px; }
.small-text { font-size: 12px; color: var(--text-muted); }
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
.sync-msg { font-size: 12px; padding: 5px 10px; border-radius: 5px; }
.sync-msg.ok { background: rgba(63,185,80,.12); color: var(--success); }
.sync-msg.err { background: rgba(248,81,73,.12); color: var(--error); }

/* 空状态 */
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); gap: 8px; }
.empty-state .icon { font-size: 32px; }
.spinner { display: inline-block; width: 18px; height: 18px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 详情面板 */
.detail-panel { width: 280px; flex-shrink: 0; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; display: flex; flex-direction: column; overflow: hidden; }
.detail-header { display: flex; justify-content: space-between; align-items: center; padding: 10px 14px; font-weight: 600; font-size: 13px; border-bottom: 1px solid var(--border); }
.detail-body { flex: 1; overflow-y: auto; padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; }
.detail-row { display: flex; gap: 6px; font-size: 12px; }
.dl { color: var(--text-muted); min-width: 64px; flex-shrink: 0; }
.dv { color: var(--text-primary); word-break: break-all; }
.detail-actions { margin-top: 8px; }
.label-chip-detail { font-size: 11px; padding: 1px 6px; border-radius: 3px; background: var(--bg-hover); margin-right: 3px; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 14px; }

/* 巡检 */
.inspect-wrap { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; gap: 10px; }
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
.inspect-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.inspect-table th { position: sticky; top: 0; background: var(--bg-header); padding: 7px 10px; text-align: left; font-weight: 600; font-size: 11px; color: var(--text-muted); border-bottom: 1px solid var(--border); white-space: nowrap; }
.inspect-table td { padding: 6px 10px; border-bottom: 1px solid var(--border-faint, var(--border)); white-space: nowrap; }
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
.itd-ip, .itd-os, .itd-group { color: var(--text-muted); }

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
.form-group input, .form-group select, .form-group textarea { padding: 6px 10px; border: 1px solid var(--border); border-radius: 5px; background: var(--bg-input); color: var(--text-primary); font-size: 13px; width: 100%; box-sizing: border-box; }
.form-group textarea { resize: vertical; font-family: inherit; }
.form-error { color: var(--error); font-size: 12px; margin-top: 6px; padding: 6px 10px; background: rgba(248,81,73,.08); border-radius: 5px; }
.form-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
</style>
