<template>
  <div class="page">
    <div class="page-header">
      <h1>分析报告</h1>
    </div>

    <!-- Toast -->
    <transition name="fade">
      <div v-if="errorMsg" class="error-toast">
        ❌ {{ errorMsg }}
        <button class="toast-close" @click="errorMsg = ''">✕</button>
      </div>
    </transition>
    <transition name="fade">
      <div v-if="successMsg" class="success-toast">
        ✅ {{ successMsg }}
        <button class="toast-close" @click="successMsg = ''">✕</button>
      </div>
    </transition>

    <div class="report-layout">
      <!-- 左侧报告列表 -->
      <aside class="report-list-panel">
        <div class="panel-top">
          <select v-model="reportType" class="time-select" @change="onTypeChange">
            <option value="daily">运维日报</option>
            <option value="inspect">主机巡检日报</option>
            <option value="slowlog">MySQL 慢日志报告</option>
          </select>
          <select v-if="reportType === 'inspect'" v-model="inspectGroupId" class="time-select">
            <option value="">全部主机</option>
            <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name }}</option>
          </select>
          <button class="btn btn-primary btn-full" @click="generateReport" :disabled="generating">
            <span v-if="generating" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>▶</span>
            {{ generating ? 'AI 分析中...' : genBtnLabel }}
          </button>
          <button
            v-if="reportType === 'inspect'"
            class="btn btn-outline btn-full"
            @click="generateAllGroups"
            :disabled="groupGenerating"
            title="为每个配置了飞书 webhook 的分组分别生成巡检报告并推送"
          >
            <span v-if="groupGenerating" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>📤</span>
            {{ groupGenerating ? '推送中...' : '按分组生成并推送' }}
          </button>
        </div>

        <div class="history-list">
          <div v-if="loadingList" class="empty-state" style="padding:30px">
            <div class="spinner"></div>
          </div>
          <div
            v-for="r in filteredList" :key="r.id"
            class="history-item"
            :class="{ active: currentReport?.id === r.id }"
            @click="loadReport(r.id)"
          >
            <div class="history-title">{{ r.title }}</div>
            <div class="history-meta">
              <span>{{ formatDate(r.created_at) }}</span>
              <span class="badge" :class="healthBadge(r.health_score)">{{ r.health_score }}/100</span>
            </div>
          </div>
          <div v-if="!loadingList && !filteredList.length" class="empty-state" style="padding:30px">
            <span class="icon" style="font-size:28px">📋</span>
            <p>暂无历史报告</p>
          </div>
        </div>
      </aside>

      <!-- 右侧：慢日志目标配置面板（仅 slowlog 类型时显示） -->
      <div v-if="reportType === 'slowlog'" class="slowlog-config-panel" :class="{ expanded: slcOpen }">
        <div class="slc-header" @click="slcOpen = !slcOpen">
          <span>⚙️ 慢日志报告目标配置</span>
          <span class="slc-saved" v-if="slcSaved">已保存 ✓</span>
          <svg class="chevron" :class="{ open: slcOpen }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
        </div>

        <div v-if="slcOpen" class="slc-body">
          <!-- 全局参数 -->
          <div class="slc-row">
            <label class="slc-label">分析最近天数</label>
            <input v-model.number="slcConfig.date_days" type="number" min="1" max="30" class="inp-num" />
            <label class="slc-label" style="margin-left:16px">慢查询阈值(s)</label>
            <input v-model.number="slcConfig.threshold_sec" type="number" step="0.1" min="0.1" class="inp-num" />
            <label class="slc-label" style="margin-left:16px">告警阈值(s)</label>
            <input v-model.number="slcConfig.alert_sec" type="number" step="1" min="1" class="inp-num" />
          </div>
          <div class="slc-row" style="margin-top:6px">
            <label class="slc-label">定时推送</label>
            <label class="toggle-label">
              <input type="checkbox" v-model="slcConfig.enabled" />
              <span>{{ slcConfig.enabled ? '已启用（随定时日报一起推送）' : '未启用' }}</span>
            </label>
          </div>

          <!-- 目标主机列表 -->
          <div class="slc-targets-header">
            <span class="slc-label">目标主机</span>
            <button class="btn-xs" @click="addSlcTarget">+ 添加主机</button>
          </div>

          <div v-for="(t, i) in slcConfig.targets" :key="i" class="slc-target-row">
            <span class="slc-idx">{{ i + 1 }}</span>
            <input v-model="t.host_ip"   placeholder="IP 地址"    class="inp-s" />
            <input v-model="t.log_path"  placeholder="/mysqldata/.../mysql-slow.log" class="inp-path-s" />
            <select v-model="t.credential_id" class="inp-sel-s">
              <option value="">-- 凭证库 --</option>
              <option v-for="c in credList" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <span class="slc-or">或</span>
            <input v-model="t.ssh_user"     placeholder="用户名" class="inp-xs" />
            <input v-model="t.ssh_password" placeholder="密码"   class="inp-xs" type="password" />
            <input v-model.number="t.ssh_port" placeholder="22"  class="inp-port" type="number" />
            <button class="btn-remove-xs" @click="slcConfig.targets.splice(i, 1)" title="删除">✕</button>
          </div>

          <div v-if="!slcConfig.targets.length" class="slc-empty">暂无目标主机，点击「+ 添加主机」</div>

          <div class="slc-footer">
            <button class="btn btn-primary btn-sm" @click="saveSlcConfig" :disabled="slcSaving">
              {{ slcSaving ? '保存中...' : '保存配置' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 右侧报告详情 -->
      <div class="report-detail">

        <!-- 生成中（无报告） -->
        <div v-if="generating && !currentReport" class="empty-state" style="height:100%">
          <div class="spinner" style="width:36px;height:36px;border-width:3px"></div>
          <p style="margin-top:12px;color:var(--text-secondary)">正在采集数据并生成报告...</p>
        </div>

        <!-- 无报告 -->
        <div v-else-if="!currentReport" class="empty-state" style="height:100%">
          <span class="icon">📋</span>
          <p>
            <template v-if="reportType === 'slowlog'">请先配置目标主机，然后点击「立即生成慢日志报告」</template>
            <template v-else>请点击「立即生成日报」或选择历史报告</template>
          </p>
        </div>

        <!-- 报告内容 -->
        <div v-else class="report-content">

          <!-- 标题栏 -->
          <div class="report-title-bar">
            <div>
              <h2>{{ currentReport.title }}</h2>
              <p class="report-date">报告时间：{{ formatDate(currentReport.created_at) }}</p>
            </div>
            <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
              <!-- 导出按钮 -->
              <div v-if="currentReport?.id && !generating" class="export-group">
                <span class="export-label">导出</span>
                <button
                  v-if="currentReport.type === 'slowlog'"
                  class="btn-export-r"
                  @click="exportReport('csv')"
                  title="导出慢查询为 CSV（Excel 可直接打开）"
                >CSV</button>
                <button
                  v-if="currentReport.type === 'slowlog'"
                  class="btn-export-r"
                  @click="exportReport('host_csv')"
                  title="导出各主机汇总为 CSV"
                >主机 CSV</button>
                <button
                  v-if="currentReport.type === 'inspect'"
                  class="btn-export-r"
                  @click="exportInspectExcel"
                  title="导出按组分类的完整主机巡检明细"
                >Excel</button>
                <button
                  class="btn-export-r"
                  @click="exportReport('json')"
                  title="导出完整报告 JSON"
                >JSON</button>
                <button
                  class="btn-export-r btn-export-pdf"
                  @click="exportPdf"
                  :disabled="pdfExporting"
                  title="直接下载 PDF 格式报告"
                >{{ pdfExporting ? '生成中…' : '📄 PDF' }}</button>
                <button
                  class="btn-export-r"
                  @click="exportPrintHtml"
                  title="打印视图（浏览器 Ctrl+P）"
                >打印</button>
              </div>
              <button v-if="!generating" class="btn btn-outline" @click="generateReport" title="重新生成">
                🔄 重新生成
              </button>
              <button
                v-if="currentReport?.id && !generating"
                class="btn btn-notify feishu"
                :disabled="notifying.feishu"
                @click="sendNotify('feishu')"
              >
                <span v-if="notifying.feishu" class="spinner" style="width:12px;height:12px;border-width:2px"></span>
                <span v-else>🔔</span> 飞书
              </button>
              <button
                v-if="currentReport?.id && !generating"
                class="btn btn-notify dingtalk"
                :disabled="notifying.dingtalk"
                @click="sendNotify('dingtalk')"
              >
                <span v-if="notifying.dingtalk" class="spinner" style="width:12px;height:12px;border-width:2px"></span>
                <span v-else>🔔</span> 钉钉
              </button>
              <button
                v-if="currentReport?.id && !generating && groups.length"
                class="btn btn-notify group-push"
                :disabled="notifying.groups"
                @click="sendNotifyGroups"
                title="推送到所有已配置飞书/钉钉的分组"
              >
                <span v-if="notifying.groups" class="spinner" style="width:12px;height:12px;border-width:2px"></span>
                <span v-else>📢</span> 按分组推送
              </button>
              <div class="health-circle" :class="healthClass(currentReport.health_score)">
                <div class="health-num">{{ currentReport.health_score }}</div>
                <div class="health-label">健康评分 /100</div>
              </div>
            </div>
          </div>

          <!-- 第一部分：直接给出 AI 结论 -->
          <div class="section ai-conclusion-section">
            <div class="section-title-row">
              <h3 class="section-title">🤖 第一部分 · AI 结论</h3>
              <span v-if="generating" class="analyzing-badge">
                <span class="dot1">·</span><span class="dot2">·</span><span class="dot3">·</span>
                分析中
              </span>
            </div>
            <div class="ai-analysis-box">
              <div v-if="aiStreamContent" class="ai-text" v-html="renderText(aiStreamContent)"></div>
              <div v-else-if="inspectGroupAnalyses.length" class="group-ai-list">
                <div
                  v-for="group in inspectGroupAnalyses"
                  :key="group.group_id || group.group_name"
                  class="group-ai-card"
                >
                  <div class="group-ai-header">
                    <div>
                      <div class="group-ai-name">{{ group.group_name || '未分组' }}</div>
                      <div class="group-ai-meta">{{ formatGroupSummary(group.host_summary) }}</div>
                    </div>
                    <span class="badge" :class="healthBadge(group.health_score ?? 0)">
                      {{ group.health_score ?? 0 }}/100
                    </span>
                  </div>
                  <div class="ai-text" v-html="renderText(group.ai_analysis)"></div>
                </div>
              </div>
              <div v-else-if="currentReport.ai_analysis" class="ai-text" v-html="renderText(currentReport.ai_analysis)"></div>
              <div v-else-if="generating" class="ai-placeholder">
                <div class="spinner" style="width:20px;height:20px;border-width:2px"></div>
                <span>等待 AI 响应...</span>
              </div>
              <div v-else class="empty-state" style="padding:24px">
                <p>AI 结论尚未生成，请点击「重新生成」</p>
              </div>
            </div>
          </div>

          <!-- ① 运维日报指标 -->
          <template v-if="!currentReport.type || currentReport.type === 'daily'">
            <div class="metrics-row">
              <div class="metric-card">
                <div class="metric-icon">🔧</div>
                <div class="metric-val">{{ currentReport.service_count }}</div>
                <div class="metric-label">覆盖微服务</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🖥️</div>
                <div class="metric-val" style="font-size:15px">
                  <span style="color:var(--success)">{{ currentReport.node_status?.normal ?? 0 }} 正常</span>
                  <span style="color:var(--text-muted);font-size:11px;margin:0 4px">/</span>
                  <span style="color:var(--error)">{{ currentReport.node_status?.abnormal ?? 0 }} 异常</span>
                </div>
                <div class="metric-label">节点状态</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🌐</div>
                <div class="metric-val" :class="'status-' + (currentReport.interface_status?.status || 'unknown')">
                  {{ interfaceStatusLabel(currentReport.interface_status?.status) }}
                </div>
                <div class="metric-label">接口监控状态</div>
              </div>
            </div>

            <div class="section" v-if="currentReport.service_error_summaries?.length">
              <h3 class="section-title">第二部分 · 微服务错误一句话概括</h3>
              <div class="summary-table-wrap">
                <table class="report-table">
                  <thead><tr><th>微服务</th><th>错误关键字</th><th>一句话结论</th></tr></thead>
                  <tbody>
                    <tr v-for="item in currentReport.service_error_summaries" :key="item.service">
                      <td class="service-cell">{{ item.service }}</td>
                      <td>
                        <span v-for="keyword in item.keywords" :key="keyword" class="keyword-chip">{{ keyword }}</span>
                        <span v-if="!item.keywords?.length" class="muted">样本不足</span>
                      </td>
                      <td>{{ item.summary }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="section" v-if="currentReport.error_keywords?.length">
              <h3 class="section-title">第三部分 · 高频错误关键字统计</h3>
              <div class="summary-table-wrap">
                <table class="report-table compact">
                  <thead><tr><th>关键字</th><th>样本频次</th><th>涉及服务</th></tr></thead>
                  <tbody>
                    <tr v-for="item in currentReport.error_keywords" :key="item.keyword">
                      <td><strong>{{ item.keyword }}</strong></td>
                      <td>{{ item.count }}</td>
                      <td>{{ (item.services || []).join('、') || '-' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="section">
              <h3 class="section-title">第四部分 · 接口监控状况评估</h3>
              <div v-if="!currentReport.interface_status?.available" class="inspect-scope-note">
                未采集到 http_server 接口指标，本日报无法评估接口成功率与延迟；请检查指标暴露和 Prometheus 抓取配置。
              </div>
              <div v-else class="summary-table-wrap">
                <table class="report-table">
                  <thead><tr><th>状态</th><th>应用</th><th>方法</th><th>接口</th><th>5xx率</th><th>P95</th></tr></thead>
                  <tbody>
                    <tr v-for="row in currentReport.interface_status.rows" :key="[row.application,row.method,row.uri].join('|')">
                      <td><span class="status-pill" :class="row.status">{{ statusText(row.status) }}</span></td>
                      <td>{{ row.application }}</td>
                      <td>{{ row.method }}</td>
                      <td class="mono">{{ row.uri }}</td>
                      <td>{{ row.error_ratio }}%</td>
                      <td>{{ row.p95_ms }}ms</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </template>

          <!-- ② 主机巡检日报指标 -->
          <template v-else-if="currentReport.type === 'inspect'">
            <div class="metrics-row">
              <div class="metric-card">
                <div class="metric-icon">🖥️</div>
                <div class="metric-val">{{ currentReport.host_summary?.total ?? 0 }}</div>
                <div class="metric-label">巡检主机总数</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">✅</div>
                <div class="metric-val" style="color:var(--success)">{{ currentReport.host_summary?.normal ?? 0 }}</div>
                <div class="metric-label">正常主机</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">⚠️</div>
                <div class="metric-val" style="color:var(--warning)">{{ currentReport.host_summary?.warning ?? 0 }}</div>
                <div class="metric-label">警告主机</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🔴</div>
                <div class="metric-val" style="color:var(--error)">{{ currentReport.host_summary?.critical ?? 0 }}</div>
                <div class="metric-label">严重主机</div>
              </div>
            </div>
            <div class="section" v-if="currentReport.summary_scope_note || currentReport.host_summary?.scope_note">
              <div class="inspect-scope-note">
                {{ currentReport.summary_scope_note || currentReport.host_summary?.scope_note }}
              </div>
            </div>
            <div class="section">
              <h3 class="section-title">第二部分 · 按组分类主机巡检明细（告警优先）</h3>
              <div v-if="!inspectGroupSections.length" class="inspect-scope-note">当前报告没有主机明细。</div>
              <div v-for="group in inspectGroupSections" :key="group.group_name" class="host-group-section">
                <div class="host-group-header">
                  <div>
                    <strong>{{ group.group_name }}</strong>
                    <span class="group-count">共 {{ group.total }} 台</span>
                  </div>
                  <div class="group-status-counts">
                    <span v-if="group.critical" class="status-pill critical">严重 {{ group.critical }}</span>
                    <span v-if="group.warning" class="status-pill warning">警告 {{ group.warning }}</span>
                    <span class="status-pill normal">正常 {{ group.normal }}</span>
                  </div>
                </div>
                <div class="host-table-wrap">
                  <table class="report-table host-detail-table">
                    <thead>
                      <tr>
                        <th>状态</th><th>服务器 IP</th><th>服务器</th><th>主机名</th>
                        <th>CPU</th><th>内存</th><th>磁盘具体占用</th><th>进程占用 Top 10</th>
                        <th>负责人</th><th>机房</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="host in group.hosts" :key="host.ip || host.instance" :class="'host-row-' + host.overall">
                        <td><span class="status-pill" :class="host.overall">{{ statusText(host.overall) }}</span></td>
                        <td class="mono">{{ host.ip || '-' }}</td>
                        <td>{{ host.role || host.os || '-' }}</td>
                        <td>{{ host.hostname || '-' }}</td>
                        <td>{{ metricPct(host.cpu_pct) }}<small v-if="host.cpu_cores"> / {{ host.cpu_cores }} 核</small></td>
                        <td>{{ metricPct(host.mem_pct) }}<small v-if="host.mem_total"> / {{ host.mem_total }}GB</small></td>
                        <td class="disk-cell">
                          <span v-for="disk in host.partitions" :key="disk.mountpoint || disk.mount">
                            {{ disk.mountpoint || disk.mount }} {{ disk.usage_pct ?? disk.used_pct ?? '-' }}%
                            ({{ disk.used_gb ?? '-' }}/{{ disk.total_gb ?? disk.size_gb ?? '-' }}GB)
                          </span>
                          <span v-if="!host.partitions?.length" class="muted">未采集</span>
                        </td>
                        <td class="process-cell">
                          <span v-for="(proc, index) in host.process_top10" :key="proc.pid || index">
                            {{ index + 1 }}. {{ proc.service || proc.comm }} CPU {{ proc.cpu }}% / MEM {{ proc.mem }}%
                          </span>
                          <span v-if="!host.process_top10?.length" class="muted">{{ host.process_error || '未采集' }}</span>
                        </td>
                        <td>{{ host.owner || '未配置' }}</td>
                        <td>{{ host.datacenter || '未配置' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
            <div class="section" v-if="currentReport.prometheus_extra_hosts?.length">
              <h3 class="section-title">🧩 Prometheus 额外发现的非 CMDB 实例</h3>
              <div class="extra-prom-list">
                <div
                  v-for="h in currentReport.prometheus_extra_hosts"
                  :key="h.ip || h.instance"
                  class="extra-prom-row"
                >
                  <span class="extra-prom-ip">{{ h.ip || h.instance }}</span>
                  <span class="extra-prom-host">{{ h.hostname || h.instance || '-' }}</span>
                  <span class="extra-prom-job">{{ h.job || 'unknown job' }}</span>
                  <span class="badge" :class="h.overall === 'critical' ? 'badge-error' : (h.overall === 'warning' ? 'badge-warn' : 'badge-ok')">
                    {{ h.overall || 'normal' }}
                  </span>
                </div>
              </div>
            </div>
          </template>

          <!-- ③ 慢日志报告指标 -->
          <template v-else-if="currentReport.type === 'slowlog'">
            <!-- 时间段 -->
            <div class="slowlog-date-range">
              📅 分析时段：<strong>{{ currentReport.date_from }}</strong> ~ <strong>{{ currentReport.date_to }}</strong>
              <span class="slowlog-threshold">慢查询 ≥ {{ currentReport.threshold_sec ?? 1 }}s · 告警 ≥ {{ currentReport.alert_sec ?? 10 }}s</span>
            </div>
            <!-- 指标卡 -->
            <div class="metrics-row">
              <div class="metric-card">
                <div class="metric-icon">🖥️</div>
                <div class="metric-val">{{ currentReport.hosts_count ?? 0 }}</div>
                <div class="metric-label">分析主机数</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🐌</div>
                <div class="metric-val">{{ fmtNum(currentReport.total_queries) }}</div>
                <div class="metric-label">慢查询总数</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🔔</div>
                <div class="metric-val" :style="{ color: currentReport.alert_queries > 0 ? 'var(--error)' : 'var(--success)' }">
                  {{ fmtNum(currentReport.alert_queries) }}
                </div>
                <div class="metric-label">告警数（高耗时）</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">⏱️</div>
                <div class="metric-val" style="color:var(--warning)">{{ currentReport.avg_query_time }}s</div>
                <div class="metric-label">平均耗时</div>
              </div>
              <div class="metric-card">
                <div class="metric-icon">🚨</div>
                <div class="metric-val" style="color:var(--error)">{{ currentReport.max_query_time }}s</div>
                <div class="metric-label">最大耗时</div>
              </div>
            </div>

            <!-- Top 慢查询：报告结果优先展示 -->
            <div class="section" v-if="currentReport.top_slow?.length">
              <h3 class="section-title">🐌 核心结果 · Top 10 最慢查询</h3>
              <div class="slowlog-list">
                <div v-for="(s, i) in currentReport.top_slow" :key="i" class="slowlog-row">
                  <span class="rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
                  <span class="sl-host mono">{{ s.host_ip }}</span>
                  <span class="sl-time" :class="s.query_time >= (currentReport.alert_sec || 10) ? 'sl-time-alert' : ''">{{ s.query_time }}s</span>
                  <span class="sl-rows">扫 {{ fmtNum(s.rows_examined) }} 行</span>
                  <span class="sl-sql" :title="s.sql_brief">{{ s.sql_brief }}</span>
                </div>
              </div>
            </div>

            <!-- 各主机明细 -->
            <div class="section" v-if="currentReport.host_results?.length">
              <h3 class="section-title">🖥️ 主机级分析结果（告警优先）</h3>
              <table class="sl-table">
                <thead>
                  <tr>
                    <th>状态</th><th>主机 IP</th><th>慢查询数</th><th>告警数</th>
                    <th>平均耗时(s)</th><th>最大耗时(s)</th><th>Top SQL 模板</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="h in currentReport.host_results" :key="h.host_ip">
                    <td><span class="status-pill" :class="slowlogHostStatus(h)">{{ statusText(slowlogHostStatus(h)) }}</span></td>
                    <td class="mono">{{ h.host_ip }}</td>
                    <td>{{ h.total }}</td>
                    <td :style="{ color: h.alert_count > 0 ? 'var(--error)' : 'var(--success)' }">{{ h.alert_count }}</td>
                    <td>{{ h.avg_query_time }}</td>
                    <td>{{ h.max_query_time }}</td>
                    <td class="sl-clusters">
                      <span v-for="c in (h.top_clusters||[]).slice(0,2)" :key="c.rank" class="cluster-tag" :title="c.template">
                        ×{{ c.count }} {{ c.template.slice(0, 60) }}{{ c.template.length > 60 ? '...' : '' }}
                      </span>
                      <span v-if="!h.top_clusters?.length" class="muted">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- SSH 错误提示 -->
            <div v-if="currentReport.errors?.length" class="section">
              <h3 class="section-title" style="color:var(--error)">⚠️ 采集失败的主机</h3>
              <div v-for="e in currentReport.errors" :key="e.host_ip" class="err-row">
                <span class="mono">{{ e.host_ip }}</span>：{{ e.error }}
              </div>
            </div>
          </template>

        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { api, streamSSE } from '../api/index.js'

const reportType    = ref('daily')
const reportList    = ref([])
const currentReport = ref(null)
const generating    = ref(false)
const loadingList   = ref(false)
const aiStreamContent = ref('')
const errorMsg      = ref('')
const successMsg    = ref('')
const notifying     = ref({ feishu: false, dingtalk: false, groups: false })
const credList      = ref([])
const groups        = ref([])
const inspectGroupId = ref('')
const groupGenerating = ref(false)

// ── 慢日志目标配置状态 ─────────────────────────────────────────────────
const slcOpen   = ref(false)
const slcSaved  = ref(false)
const slcSaving = ref(false)
const slcConfig = reactive({
  enabled: false, date_days: 1, threshold_sec: 1.0, alert_sec: 10.0, targets: [],
})

function addSlcTarget() {
  slcConfig.targets.push({
    host_ip: '', log_path: '/mysqldata/mysql/data/3306/mysql-slow.log',
    credential_id: '', ssh_user: '', ssh_password: '', ssh_port: 22,
  })
}

async function saveSlcConfig() {
  slcSaving.value = true
  try {
    await api.saveSlowlogTargets({ ...slcConfig, targets: [...slcConfig.targets] })
    slcSaved.value = true
    slcOpen.value = false
    setTimeout(() => { slcSaved.value = false }, 3000)
  } catch (e) {
    errorMsg.value = '保存失败：' + e
  } finally {
    slcSaving.value = false
  }
}

async function loadSlcConfig() {
  try {
    const data = await api.getSlowlogTargets()
    Object.assign(slcConfig, data)
    if (!slcConfig.targets) slcConfig.targets = []
  } catch {}
}

// ── 工具函数 ───────────────────────────────────────────────────────────
function fmtNum(n) { return n != null ? Number(n).toLocaleString() : '0' }

function formatDate(d) {
  if (!d) return ''
  return new Date(d).toLocaleString('zh-CN', { hour12: false })
}

function healthBadge(score) {
  if (score >= 80) return 'badge-success'
  if (score >= 60) return 'badge-warn'
  return 'badge-error'
}

function healthClass(score) {
  if (score >= 80) return 'health-good'
  if (score >= 60) return 'health-mid'
  return 'health-bad'
}

function renderText(t) {
  if (!t) return ''
  return String(t)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/⚠️/g, '<span class="ai-warn">⚠️</span>')
    .replace(/✅/g, '<span class="ai-ok">✅</span>')
    .replace(/\n/g, '<br>')
}

const genBtnLabel = computed(() => {
  if (reportType.value === 'inspect') return '立即生成巡检日报'
  if (reportType.value === 'slowlog') return '立即生成慢日志报告'
  return '立即生成日报'
})

const filteredList = computed(() => {
  if (reportType.value === 'slowlog') return reportList.value.filter(r => r.type === 'slowlog')
  if (reportType.value === 'inspect') return reportList.value.filter(r => r.type === 'inspect')
  return reportList.value.filter(r => !r.type || r.type === 'daily')
})

const inspectGroupAnalyses = computed(() => {
  if (currentReport.value?.type !== 'inspect') return []
  const items = currentReport.value?.group_analyses
  return Array.isArray(items) ? items : []
})

const inspectGroupSections = computed(() => {
  if (currentReport.value?.type !== 'inspect') return []
  const sections = currentReport.value?.group_sections
  if (Array.isArray(sections) && sections.length) return sections
  const hosts = Array.isArray(currentReport.value?.all_hosts) ? currentReport.value.all_hosts : []
  if (!hosts.length) return []
  return [{
    group_name: currentReport.value.group_name || '全部主机',
    total: hosts.length,
    critical: hosts.filter(h => h.overall === 'critical').length,
    warning: hosts.filter(h => h.overall === 'warning').length,
    normal: hosts.filter(h => h.overall === 'normal').length,
    hosts: [...hosts].sort((a, b) => ({ critical: 2, warning: 1, normal: 0 }[b.overall] || 0) - ({ critical: 2, warning: 1, normal: 0 }[a.overall] || 0)),
  }]
})

const maxTop   = computed(() => currentReport.value?.top10_errors?.[0]?.count || 1)
const maxIssue = computed(() => currentReport.value?.top_issues?.[0]?.count || 1)
function topBarWidth(cnt)   { return Math.round((cnt / maxTop.value) * 100) }
function issueBarWidth(cnt) { return Math.round((cnt / maxIssue.value) * 100) }

function statusText(status) {
  return { critical: '严重', warning: '警告', normal: '正常', unknown: '未采集' }[status] || status || '未知'
}

function interfaceStatusLabel(status) {
  return { critical: '严重', warning: '需关注', normal: '正常', unknown: '未采集' }[status] || '未采集'
}

function metricPct(value) {
  const number = Number(value)
  return Number.isFinite(number) ? `${number.toFixed(1)}%` : '未采集'
}

function slowlogHostStatus(host) {
  if (host?.status) return host.status
  if (Number(host?.alert_count || 0) > 0) return 'critical'
  if (Number(host?.total || 0) > 0) return 'warning'
  return 'normal'
}

function formatGroupSummary(summary) {
  if (!summary) return ''
  return `主机 ${summary.total ?? 0} 台，正常 ${summary.normal ?? 0}，告警 ${summary.warning ?? 0}，严重 ${summary.critical ?? 0}`
}

// ── 列表 ───────────────────────────────────────────────────────────────
async function loadReportList() {
  loadingList.value = true
  try {
    const r = await api.listReports()
    reportList.value = r.data
  } catch (e) {
    errorMsg.value = '加载报告列表失败：' + e
  } finally {
    loadingList.value = false
  }
}

async function loadReport(id) {
  aiStreamContent.value = ''
  errorMsg.value = ''
  try {
    currentReport.value = await api.getReport(id)
  } catch (e) {
    errorMsg.value = '加载报告失败：' + e
  }
}

function onTypeChange() {
  currentReport.value = null
  aiStreamContent.value = ''
  inspectGroupId.value = ''
}

// ── 生成报告（SSE） ───────────────────────────────────────────────────
function generateReport() {
  if (generating.value) return
  generating.value   = true
  aiStreamContent.value = ''
  errorMsg.value     = ''

  const urlMap = {
    inspect: '/api/report/inspect/generate',
    slowlog: '/api/report/slowlog/generate',
    daily:   '/api/report/generate',
  }
  let url = urlMap[reportType.value] || urlMap.daily
  if (reportType.value === 'inspect' && inspectGroupId.value) {
    url += `?group_id=${encodeURIComponent(inspectGroupId.value)}`
  }
  const isSlowlogGeneration = reportType.value === 'slowlog'
  let generatedReportId = ''

  streamSSE(
    url,
    (raw) => {
      if (raw.startsWith('__META__')) {
        try {
          const meta = JSON.parse(raw.slice(8))
          currentReport.value = meta
          generatedReportId = meta.id || ''
          aiStreamContent.value = ''
          if (isSlowlogGeneration && generatedReportId) {
            const id = generatedReportId
            loadReportList()
            api.getReport(id).then((report) => {
              if (currentReport.value?.id === id) currentReport.value = report
            }).catch(() => {})
          }
        }
        catch (e) { console.error('META parse error', e) }
        return
      }
      try { aiStreamContent.value += JSON.parse(raw) }
      catch { aiStreamContent.value += raw }
    },
    async () => {
      generating.value = false
      await loadReportList()
      if (currentReport.value?.id) {
        try { currentReport.value = await api.getReport(currentReport.value.id) } catch {}
      }
    },
    (err) => {
      generating.value = false
      if (isSlowlogGeneration && generatedReportId) {
        const id = generatedReportId
        loadReportList()
        api.getReport(id).then((report) => {
          if (currentReport.value?.id === id) currentReport.value = report
        }).catch(() => {})
        console.warn('Slowlog SSE closed after report metadata was saved', err)
        return
      }
      errorMsg.value   = '生成失败，请检查后端连接和配置'
      console.error('SSE error', err)
    },
  )
}

// ── 按分组生成并推送 ───────────────────────────────────────────────────
async function generateAllGroups() {
  if (groupGenerating.value) return
  groupGenerating.value = true
  errorMsg.value   = ''
  successMsg.value = ''
  try {
    const data = await api.generateInspectGroups()
    const results = data.results || []
    const pushed  = results.filter(x => x.push?.ok).length
    const skipped = results.filter(x => x.skipped).length
    const failed  = results.filter(x => x.error || (x.push && !x.push.ok)).length
    successMsg.value = `分组推送完成：${pushed} 个成功，${skipped} 个跳过，${failed} 个失败`
    setTimeout(() => { successMsg.value = '' }, 6000)
    await loadReportList()
  } catch (e) {
    errorMsg.value = '按分组推送失败：' + e
  } finally {
    groupGenerating.value = false
  }
}

// ── 通知推送 ───────────────────────────────────────────────────────────
async function sendNotify(channel) {
  if (!currentReport.value?.id) return
  notifying.value[channel] = true
  errorMsg.value   = ''
  successMsg.value = ''
  try {
    const r   = await api.notifyReport(currentReport.value.id, [channel])
    const res = r.results?.[channel]
    if (res?.ok) {
      successMsg.value = `已成功发送到${channel === 'feishu' ? '飞书' : '钉钉'}`
      setTimeout(() => { successMsg.value = '' }, 4000)
    } else {
      errorMsg.value = `发送失败：${res?.msg || '未知错误'}`
    }
  } catch (e) {
    errorMsg.value = `发送失败：${e}`
  } finally {
    notifying.value[channel] = false
  }
}

async function sendNotifyGroups() {
  if (!currentReport.value?.id || notifying.value.groups) return
  notifying.value.groups = true
  errorMsg.value   = ''
  successMsg.value = ''
  try {
    // 有 group_id 则只推送该分组，否则推送全部
    const gid = currentReport.value.group_id || ''
    const data = await api.notifyReportGroups(currentReport.value.id, gid)
    const results  = data.results || []
    const pushed   = results.filter(x => x.push && (x.push.feishu?.ok || x.push.dingtalk?.ok)).length
    const skipped  = results.filter(x => x.skipped).length
    const failed   = results.filter(x => x.push && !x.push.feishu?.ok && !x.push.dingtalk?.ok).length
    const groupLabel = gid ? `「${currentReport.value.group_name || gid}」` : '全部分组'
    successMsg.value = `${groupLabel} 推送完成：${pushed} 成功，${skipped} 跳过，${failed} 失败`
    setTimeout(() => { successMsg.value = '' }, 6000)
  } catch (e) {
    errorMsg.value = `按分组推送失败：${e}`
  } finally {
    notifying.value.groups = false
  }
}

// ── 导出报告 ───────────────────────────────────────────────────────────
function exportReport(fmt) {
  const r = currentReport.value
  if (!r) return

  // 构造文件名前缀
  const dateTag = r.created_at
    ? new Date(r.created_at).toISOString().slice(0, 10).replace(/-/g, '')
    : 'export'
  const typeTag = r.type || 'daily'

  if (fmt === 'json') {
    const content  = JSON.stringify(r, null, 2)
    const filename = `report_${typeTag}_${dateTag}.json`
    _downloadBlob(new Blob([content], { type: 'application/json;charset=utf-8' }), filename)
    return
  }

  // CSV：慢查询 Top 列表
  if (fmt === 'csv' && r.type === 'slowlog') {
    const rows = [
      ['排名', '主机 IP', '耗时(s)', '扫描行数', 'SQL 摘要'],
      ...(r.top_slow || []).map((s, i) => [
        i + 1,
        s.host_ip,
        s.query_time,
        s.rows_examined,
        (s.sql_brief || '').replace(/,/g, '，'),
      ]),
    ]
    const content  = '\ufeff' + rows.map(row => row.join(',')).join('\r\n')
    const filename = `slowlog_top_${dateTag}.csv`
    _downloadBlob(new Blob([content], { type: 'text/csv;charset=utf-8-sig' }), filename)
    return
  }

  // CSV：各主机汇总
  if (fmt === 'host_csv' && r.type === 'slowlog') {
    const rows = [
      ['主机 IP', '慢查询数', '告警数', '平均耗时(s)', '最大耗时(s)', 'Top SQL 模板'],
      ...(r.host_results || []).map(h => [
        h.host_ip,
        h.total,
        h.alert_count,
        h.avg_query_time,
        h.max_query_time,
        ((h.top_clusters || [])[0]?.template || '').replace(/,/g, '，').slice(0, 100),
      ]),
    ]
    const content  = '\ufeff' + rows.map(row => row.join(',')).join('\r\n')
    const filename = `slowlog_hosts_${dateTag}.csv`
    _downloadBlob(new Blob([content], { type: 'text/csv;charset=utf-8-sig' }), filename)
  }
}

const pdfExporting = ref(false)

async function exportPdf() {
  const r = currentReport.value
  if (!r?.id || pdfExporting.value) return
  pdfExporting.value = true
  try {
    const resp = await fetch(`/api/report/${r.id}/export.pdf`, { credentials: 'include' })
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}))
      throw new Error(body.detail || `HTTP ${resp.status}`)
    }
    _downloadBlob(await resp.blob(), `${r.title || r.id}.pdf`)
  } catch (error) {
    alert(`PDF 导出失败：${error.message || error}`)
  } finally {
    pdfExporting.value = false
  }
}

function exportInspectExcel() {
  const r = currentReport.value
  if (!r?.id || r.type !== 'inspect') return
  window.open(`/api/report/inspect/${encodeURIComponent(r.id)}/excel`, '_blank', 'noopener')
}

function exportPrintHtml() {
  const r = currentReport.value
  if (!r?.id) return
  window.open(`/api/report/${r.id}/export.html`, '_blank', 'noopener')
}

function _downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a   = document.createElement('a')
  a.href    = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(async () => {
  await loadReportList()
  try {
    const c = await api.listCredentials()
    credList.value = c.data || c
  } catch {}
  loadSlcConfig()
  try {
    const d = await api.listGroups()
    groups.value = d.data || d
  } catch {}
})
</script>

<style scoped>
.page {
  padding: 24px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}
.page-header { margin-bottom: 16px; flex-shrink: 0; }
.page-header h1 { font-size: 22px; font-weight: 700; }

/* Toast */
.error-toast {
  position: absolute; top: 16px; right: 16px;
  background: rgba(239,68,68,.15); border: 1px solid rgba(239,68,68,.4);
  color: #fca5a5; padding: 10px 16px; border-radius: var(--radius);
  font-size: 13px; display: flex; align-items: center; gap: 10px; z-index: 100;
}
.success-toast {
  position: absolute; top: 16px; right: 16px;
  background: rgba(34,197,94,.15); border: 1px solid rgba(34,197,94,.4);
  color: #86efac; padding: 10px 16px; border-radius: var(--radius);
  font-size: 13px; display: flex; align-items: center; gap: 10px; z-index: 100;
}
.toast-close { background: none; border: none; color: inherit; cursor: pointer; font-size: 14px; opacity: .7; }
.toast-close:hover { opacity: 1; }

/* 布局 */
.report-layout { flex: 1; display: flex; gap: 16px; overflow: hidden; min-height: 0; }

/* 左侧 */
.report-list-panel {
  width: 240px; min-width: 240px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); display: flex; flex-direction: column; overflow: hidden;
}
.panel-top {
  padding: 12px; border-bottom: 1px solid var(--border);
  display: flex; flex-direction: column; gap: 10px; flex-shrink: 0;
}
.time-select {
  background: var(--bg-hover); border: 1px solid var(--border);
  color: var(--text-primary); padding: 6px 10px;
  border-radius: 6px; font-size: 13px; cursor: pointer;
}
.btn-full { width: 100%; justify-content: center; }
.history-list { flex: 1; overflow-y: auto; padding: 8px; }
.history-item {
  padding: 10px 12px; border-radius: 6px;
  cursor: pointer; margin-bottom: 4px; transition: background .12s;
}
.history-item:hover  { background: var(--bg-hover); }
.history-item.active { background: var(--accent-dim); color: var(--accent); }
.history-title {
  font-size: 13px; font-weight: 500; color: var(--text-primary);
  margin-bottom: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.history-meta { display: flex; align-items: center; justify-content: space-between; font-size: 11px; color: var(--text-muted); }

/* 慢日志配置面板 */
.slowlog-config-panel {
  width: 230px; flex: 0 0 230px;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); margin-bottom: 0;
  align-self: flex-start; max-height: 100%; overflow: auto;
  transition: width .2s ease, flex-basis .2s ease;
}
.slowlog-config-panel.expanded { width: 420px; flex-basis: 420px; }
.slc-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px; cursor: pointer; font-size: 13px; font-weight: 600;
  color: var(--text-primary); border-bottom: 1px solid transparent;
}
.slowlog-config-panel .slc-header:hover { background: var(--bg-hover); }
.slc-saved { font-size: 11px; color: var(--success); margin-left: auto; }
.chevron { transition: transform .2s; flex-shrink: 0; }
.chevron.open { transform: rotate(180deg); }
.slc-body { padding: 12px 16px 14px; border-top: 1px solid var(--border); }
.slc-row  { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.slc-label { font-size: 12px; color: var(--text-secondary); white-space: nowrap; }
.inp-num  { width: 64px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius); padding: 4px 7px; color: var(--text-primary); font-size: 12px; outline: none; }
.inp-num:focus { border-color: var(--accent); }
.toggle-label { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); cursor: pointer; }
.toggle-label input { accent-color: var(--accent); }
.slc-targets-header { display: flex; align-items: center; justify-content: space-between; margin: 12px 0 6px; }
.btn-xs {
  padding: 3px 10px; background: var(--accent); color: #fff;
  border: none; border-radius: var(--radius); font-size: 11px; cursor: pointer;
}
.btn-xs:hover { opacity: .85; }
.slc-target-row {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  padding: 6px 8px; background: var(--bg-hover);
  border-radius: var(--radius); margin-bottom: 4px; border: 1px solid var(--border-light);
}
.slc-idx { font-size: 11px; color: var(--text-muted); width: 16px; text-align: center; flex-shrink: 0; }
.inp-s     { width: 120px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius); padding: 4px 7px; color: var(--text-primary); font-size: 12px; outline: none; }
.inp-s:focus { border-color: var(--accent); }
.inp-path-s { flex: 1; min-width: 200px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius); padding: 4px 7px; color: var(--text-primary); font-size: 12px; outline: none; }
.inp-sel-s { width: 130px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius); padding: 4px 7px; color: var(--text-primary); font-size: 12px; outline: none; }
.slc-or { font-size: 11px; color: var(--text-muted); }
.inp-xs   { width: 90px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius); padding: 4px 7px; color: var(--text-primary); font-size: 12px; outline: none; }
.inp-port { width: 50px; background: var(--bg-input); border: 1px solid var(--border); border-radius: var(--radius); padding: 4px 7px; color: var(--text-primary); font-size: 12px; outline: none; }
.btn-remove-xs { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 13px; padding: 2px 4px; }
.btn-remove-xs:hover { color: var(--error); }
.slc-empty { font-size: 12px; color: var(--text-muted); padding: 8px 0; }
.slc-footer { margin-top: 10px; display: flex; justify-content: flex-end; }
.btn-sm { padding: 5px 16px; font-size: 12px; }

/* 右侧 */
.report-detail {
  flex: 1;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: var(--radius); overflow-y: auto; min-height: 0;
}
.report-content { padding: 24px; }

/* 标题栏 */
.report-title-bar {
  display: flex; justify-content: space-between;
  align-items: flex-start; margin-bottom: 20px; gap: 16px;
}
.report-title-bar h2 { font-size: 20px; font-weight: 700; }
.report-date { color: var(--text-muted); font-size: 13px; margin-top: 4px; }

.health-circle {
  text-align: center; padding: 14px 18px;
  border-radius: var(--radius); border: 2px solid; min-width: 100px; flex-shrink: 0;
}
.health-circle.health-good { border-color: var(--success); color: var(--success); background: rgba(63,185,80,.08); }
.health-circle.health-mid  { border-color: var(--warning); color: var(--warning); background: rgba(210,153,34,.08); }
.health-circle.health-bad  { border-color: var(--error);   color: var(--error);   background: rgba(248,81,73,.08); }
.health-num   { font-size: 30px; font-weight: 800; line-height: 1; }
.health-label { font-size: 10px; margin-top: 4px; opacity: .8; }

/* 指标卡片 */
.metrics-row {
  display: grid; grid-template-columns: repeat(5, 1fr);
  gap: 10px; margin-bottom: 24px;
}
.metric-card {
  background: var(--bg-base); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 14px 10px; text-align: center;
}
.metric-icon  { font-size: 20px; margin-bottom: 6px; }
.metric-val   { font-size: 17px; font-weight: 700; color: var(--text-primary); line-height: 1.4; }
.metric-label { font-size: 11px; color: var(--text-muted); margin-top: 4px; }
.inspect-scope-note {
  padding: 12px 14px;
  border-radius: var(--radius);
  border: 1px solid rgba(59,130,246,.22);
  background: rgba(59,130,246,.08);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.7;
}

/* 区块 */
.section { margin-bottom: 24px; }
.section-title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.section-title { font-size: 15px; font-weight: 600; margin-bottom: 14px; }

.analyzing-badge {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 12px; color: var(--accent-hover);
  background: rgba(99,102,241,.12); border: 1px solid rgba(99,102,241,.25);
  padding: 2px 10px; border-radius: 9999px;
}
.analyzing-badge span { animation: pulse 1.2s ease-in-out infinite; }
.dot2 { animation-delay: .2s !important; }
.dot3 { animation-delay: .4s !important; }

/* Top10 */
.top10-list { display: flex; flex-direction: column; gap: 10px; }
.top10-row  { display: flex; align-items: center; gap: 12px; }
.rank { width: 22px; text-align: center; font-size: 12px; color: var(--text-muted); font-weight: 700; flex-shrink: 0; }
.rank-top { color: var(--warning); }
.top10-svc { width: 180px; font-size: 13px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }
.bar-wrap { flex: 1; height: 8px; background: var(--bg-hover); border-radius: 4px; overflow: hidden; }
.bar { height: 100%; background: linear-gradient(90deg, var(--error), #f97316); border-radius: 4px; transition: width .4s ease; }

/* AI 分析框 */
.ai-analysis-box {
  background: var(--bg-base); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 20px; min-height: 80px;
}
.ai-conclusion-section {
  padding: 16px;
  border: 1px solid rgba(99,102,241,.25);
  border-radius: var(--radius);
  background: rgba(99,102,241,.05);
}
.summary-table-wrap, .host-table-wrap { width: 100%; overflow-x: auto; }
.report-table {
  width: 100%; border-collapse: collapse; font-size: 12px;
}
.report-table th {
  background: var(--bg-hover); color: var(--text-secondary); font-weight: 600;
  padding: 9px 10px; text-align: left; border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.report-table td {
  padding: 9px 10px; border-bottom: 1px solid var(--border-light);
  color: var(--text-primary); vertical-align: top; line-height: 1.55;
}
.report-table.compact { max-width: 900px; }
.service-cell { min-width: 150px; font-weight: 600; }
.keyword-chip {
  display: inline-flex; margin: 0 4px 4px 0; padding: 1px 7px;
  border-radius: 999px; color: var(--warning);
  background: rgba(210,153,34,.1); border: 1px solid rgba(210,153,34,.25);
  white-space: nowrap;
}
.status-pill {
  display: inline-flex; align-items: center; justify-content: center;
  padding: 2px 7px; border-radius: 999px; font-size: 11px; white-space: nowrap;
}
.status-pill.critical, .status-critical { color: var(--error); background: rgba(248,81,73,.1); }
.status-pill.warning, .status-warning { color: var(--warning); background: rgba(210,153,34,.1); }
.status-pill.normal, .status-normal { color: var(--success); background: rgba(63,185,80,.1); }
.status-unknown { color: var(--text-muted); }
.host-group-section {
  margin-bottom: 18px; border: 1px solid var(--border); border-radius: var(--radius);
  overflow: hidden; background: var(--bg-base);
}
.host-group-header {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 11px 13px; background: var(--bg-hover); border-bottom: 1px solid var(--border);
}
.group-count { margin-left: 8px; color: var(--text-muted); font-size: 11px; }
.group-status-counts { display: flex; gap: 6px; flex-wrap: wrap; }
.host-detail-table { min-width: 1450px; }
.host-detail-table small { display: block; color: var(--text-muted); white-space: nowrap; }
.host-row-critical td:first-child { border-left: 3px solid var(--error); }
.host-row-warning td:first-child { border-left: 3px solid var(--warning); }
.disk-cell, .process-cell { min-width: 220px; }
.disk-cell span, .process-cell span { display: block; white-space: nowrap; font-size: 11px; }
.group-ai-list { display: flex; flex-direction: column; gap: 14px; }
.group-ai-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}
.group-ai-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.group-ai-name { font-size: 14px; font-weight: 700; color: var(--text-primary); }
.group-ai-meta { font-size: 12px; color: var(--text-muted); margin-top: 4px; }
.ai-text { font-size: 13px; line-height: 2; color: var(--text-secondary); white-space: pre-wrap; word-break: break-word; }
:deep(.ai-warn) { color: var(--warning); }
:deep(.ai-ok)   { color: var(--success); }
:deep(strong)   { color: var(--text-primary); font-weight: 600; }
.ai-placeholder { display: flex; align-items: center; gap: 10px; color: var(--text-muted); font-size: 13px; padding: 8px 0; }

/* 通知按钮 */
.btn-notify { display: inline-flex; align-items: center; gap: 5px; padding: 5px 12px; border-radius: 6px; border: 1px solid; font-size: 12px; font-weight: 500; cursor: pointer; transition: opacity .15s; }
.btn-notify:disabled { opacity: .5; cursor: not-allowed; }
.btn-notify.feishu  { background: rgba(0,195,155,.1); border-color: rgba(0,195,155,.4); color: #00c39b; }
.btn-notify.feishu:hover:not(:disabled)   { background: rgba(0,195,155,.2); }
.btn-notify.dingtalk { background: rgba(255,106,0,.1); border-color: rgba(255,106,0,.4); color: #ff6a00; }
.btn-notify.dingtalk:hover:not(:disabled) { background: rgba(255,106,0,.2); }
.btn-notify.group-push { background: rgba(99,102,241,.1); border-color: rgba(99,102,241,.4); color: #818cf8; }
.btn-notify.group-push:hover:not(:disabled) { background: rgba(99,102,241,.2); }

/* 导出按钮组 */
.export-group {
  display: flex; align-items: center; gap: 4px;
  background: var(--bg-hover); border: 1px solid var(--border);
  border-radius: var(--radius); padding: 4px 8px;
}
.export-label { font-size: 11px; color: var(--text-muted); margin-right: 2px; }
.btn-export-r {
  padding: 3px 9px; font-size: 11px; font-weight: 600;
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 4px; color: var(--text-secondary);
  cursor: pointer; transition: .15s;
}
.btn-export-pdf {
  background: #eff6ff; border-color: #93c5fd; color: #1d4ed8;
}
.btn-export-pdf:hover { background: #dbeafe; }
.btn-export-r:hover { background: var(--accent); color: #fff; border-color: var(--accent); }

/* 慢日志报告专用样式 */
.slowlog-date-range {
  font-size: 13px; color: var(--text-secondary);
  margin-bottom: 16px; padding: 8px 12px;
  background: var(--bg-hover); border-radius: var(--radius);
}
.slowlog-threshold { margin-left: 14px; color: var(--text-muted); font-size: 11px; }
.sl-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.sl-table th { background: var(--bg-hover); padding: 7px 10px; text-align: left; font-weight: 600; border-bottom: 1px solid var(--border); color: var(--text-secondary); }
.sl-table td { padding: 8px 10px; border-bottom: 1px solid var(--border-light); vertical-align: top; color: var(--text-primary); }
.sl-table tr:last-child td { border-bottom: none; }
.sl-clusters { max-width: 300px; }
.cluster-tag { display: block; font-size: 11px; color: var(--text-muted); margin-bottom: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.slowlog-list { display: flex; flex-direction: column; gap: 8px; }
.slowlog-row { display: flex; align-items: flex-start; gap: 10px; padding: 8px 10px; background: var(--bg-hover); border-radius: var(--radius); border: 1px solid var(--border-light); }
.sl-host { font-size: 11px; color: var(--text-muted); width: 120px; flex-shrink: 0; }
.sl-time { font-size: 13px; font-weight: 700; width: 60px; flex-shrink: 0; color: var(--warning); }
.sl-time-alert { color: var(--error); }
.sl-rows { font-size: 11px; color: var(--text-muted); width: 90px; flex-shrink: 0; white-space: nowrap; }
.sl-sql { font-size: 12px; color: var(--text-secondary); font-family: monospace; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.err-row { font-size: 12px; color: var(--error); padding: 4px 0; }
.muted { color: var(--text-muted); font-size: 12px; }
.mono { font-family: monospace; }

/* 异常主机 */
.abnormal-list { display: flex; flex-direction: column; gap: 6px; }
.abnormal-row {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-radius: var(--radius);
  border: 1px solid var(--border); background: var(--bg-card); font-size: 12px;
}
.abnormal-row.row-critical { border-left: 3px solid var(--error); }
.abnormal-row.row-warning  { border-left: 3px solid var(--warning); }
.abnormal-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.abnormal-dot.critical { background: var(--error); }
.abnormal-dot.warning  { background: var(--warning); }
.abnormal-host { font-weight: 600; color: var(--text-primary); min-width: 120px; }
.abnormal-ip   { color: var(--text-muted); min-width: 110px; }
.abnormal-checks { flex: 1; display: flex; flex-wrap: wrap; gap: 4px; }
.check-tag { padding: 1px 7px; border-radius: 2px; font-size: 11px; background: var(--bg-hover); color: var(--text-secondary); border: 1px solid var(--border); }
.check-tag.warning  { background: rgba(255,156,1,.1);  color: var(--warning); border-color: rgba(255,156,1,.3); }
.check-tag.critical { background: rgba(234,54,54,.1);  color: var(--error);   border-color: rgba(234,54,54,.3); }
.extra-prom-list { display: flex; flex-direction: column; gap: 8px; }
.extra-prom-row {
  display: grid;
  grid-template-columns: 150px minmax(180px, 1fr) minmax(120px, 180px) auto;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--bg-card);
  font-size: 12px;
}
.extra-prom-ip { font-family: monospace; color: var(--text-primary); }
.extra-prom-host { color: var(--text-secondary); }
.extra-prom-job { color: var(--text-muted); font-size: 11px; }

@keyframes pulse { 0%,80%,100%{opacity:.2} 40%{opacity:1} }
.fade-enter-active, .fade-leave-active { transition: opacity .3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
