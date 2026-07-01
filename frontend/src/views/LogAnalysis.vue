<template>
  <div class="log-layout">
    <!-- 左侧标签过滤 -->
    <aside class="service-panel">
      <div class="panel-header">
        <span class="panel-title">日志标签筛选</span>
        <!-- 时间模式切换 -->
        <div class="time-mode-tabs">
          <button class="tmode-btn" :class="{ active: timeMode === 'relative' }" @click="timeMode = 'relative'; onTimeModeChange()">快速</button>
          <button class="tmode-btn" :class="{ active: timeMode === 'custom' }" @click="timeMode = 'custom'">自定义</button>
        </div>
        <!-- 相对时间选择 -->
        <select v-if="timeMode === 'relative'" v-model="hours" class="time-select" @change="onParamChange">
          <option value="0.016667">最近 1 分钟</option>
          <option value="0.083333">最近 5 分钟</option>
          <option value="0.25">最近 15 分钟</option>
          <option value="0.5">最近 30 分钟</option>
          <option value="1">最近 1 小时</option>
          <option value="6">最近 6 小时</option>
          <option value="24">最近 24 小时</option>
          <option value="72">最近 3 天</option>
        </select>
        <!-- 自定义时间范围 -->
        <div v-else class="custom-time-wrap">
          <input type="datetime-local" v-model="customStart" class="dt-input" @change="onCustomTimeChange" title="开始时间" />
          <span class="dt-sep">→</span>
          <input type="datetime-local" v-model="customEnd"   class="dt-input" @change="onCustomTimeChange" title="结束时间" />
        </div>
        <div class="panel-subsection">
          <span class="panel-subtitle">标签分组</span>
          <select v-model="groupBy" class="time-select" @change="onGroupByChange">
            <option v-for="option in groupByOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </div>
      </div>

      <div class="label-explorer">
        <div class="label-explorer-header" @click="labelExplorerOpen = !labelExplorerOpen">
          <span class="label-explorer-title">Loki 标签</span>
          <span class="label-explorer-toggle">{{ labelExplorerOpen ? '收起' : '展开' }}</span>
        </div>
        <div v-show="labelExplorerOpen" class="label-explorer-body">
          <div v-if="loadingLabelCatalog" class="loading-row label-loading">
            <div class="spinner" style="width:14px;height:14px;border-width:2px"></div>
          </div>
          <template v-else>
            <!-- 已加标签条件（chip 列表，AND 组合） -->
            <div v-if="activeLabelFilters.length" class="active-label-chips" title="所有条件 AND 组合，点 ✕ 单条移除">
              <span
                v-for="(item, idx) in activeLabelFilters"
                :key="item.label + '=' + item.value"
                class="active-label-chip"
              >
                <span class="chip-key">{{ item.label }}</span>
                <span class="chip-eq">=</span>
                <span class="chip-val">{{ item.value }}</span>
                <span class="chip-remove" @click="removeActiveLabel(idx)" title="移除">✕</span>
              </span>
              <button class="active-label-clear" @click="clearAllActiveLabels">清空</button>
            </div>
            <div v-if="labelCatalog.length" class="label-dropdown-panel">
              <!-- 标签名（可搜索 combobox） -->
              <div class="label-select-field">
                <span>标签名</span>
                <div class="combo" :class="{ open: showLabelNameDropdown }">
                  <input
                    class="combo-input"
                    v-model="labelNameQuery"
                    :placeholder="selectedLabelName ? '' : '搜索标签，如 app / namespace'"
                    @focus="showLabelNameDropdown = true"
                    @input="showLabelNameDropdown = true"
                    @keydown.esc="showLabelNameDropdown = false"
                    @blur="hideLabelNameLater"
                  />
                  <span
                    v-if="selectedLabelName || labelNameQuery"
                    class="combo-clear"
                    @mousedown.prevent="clearLabelName"
                    title="清空"
                  >✕</span>
                  <span class="combo-caret" @mousedown.prevent="showLabelNameDropdown = !showLabelNameDropdown">▾</span>
                  <div v-show="showLabelNameDropdown && filteredLabels.length" class="combo-dropdown">
                    <div
                      v-for="item in filteredLabels"
                      :key="item.name"
                      class="combo-item"
                      :class="{ active: item.name === selectedLabelName }"
                      @mousedown.prevent="pickLabelName(item.name)"
                    >
                      <span class="combo-item-text">
                        <mark v-for="(seg, i) in highlight(item.name, labelNameQuery)" :key="i" :class="{ hl: seg.hit }">{{ seg.t }}</mark>
                      </span>
                      <span class="combo-item-meta">{{ labelRoleText(item) }}</span>
                    </div>
                  </div>
                  <div v-show="showLabelNameDropdown && !filteredLabels.length" class="combo-empty">未匹配到标签名</div>
                </div>
              </div>

              <!-- 标签值（可搜索 combobox） -->
              <div class="label-select-field">
                <span>标签值</span>
                <div class="combo" :class="{ open: showLabelValueDropdown, disabled: !selectedLabelName || loadingLabelValueMap[selectedLabelName] }">
                  <input
                    class="combo-input"
                    v-model="labelValueQuery"
                    :placeholder="loadingLabelValueMap[selectedLabelName] ? '加载中...' : (selectedLabelValue ? '' : '搜索标签值')"
                    :disabled="!selectedLabelName || loadingLabelValueMap[selectedLabelName]"
                    @focus="showLabelValueDropdown = true"
                    @input="showLabelValueDropdown = true"
                    @keydown.esc="showLabelValueDropdown = false"
                    @blur="hideLabelValueLater"
                  />
                  <span
                    v-if="selectedLabelValue || labelValueQuery"
                    class="combo-clear"
                    @mousedown.prevent="clearLabelValue"
                    title="清空"
                  >✕</span>
                  <span class="combo-caret" @mousedown.prevent="showLabelValueDropdown = !showLabelValueDropdown">▾</span>
                  <div v-show="showLabelValueDropdown && filteredLabelValues.length" class="combo-dropdown">
                    <div
                      v-for="value in filteredLabelValues"
                      :key="value"
                      class="combo-item"
                      :class="{ active: value === selectedLabelValue }"
                      @mousedown.prevent="pickLabelValue(value)"
                    >
                      <span class="combo-item-text">
                        <mark v-for="(seg, i) in highlight(value, labelValueQuery)" :key="i" :class="{ hl: seg.hit }">{{ seg.t }}</mark>
                      </span>
                    </div>
                  </div>
                  <div v-show="showLabelValueDropdown && !filteredLabelValues.length && !loadingLabelValueMap[selectedLabelName]" class="combo-empty">
                    {{ selectedLabelValues.length ? '未匹配到值' : '当前标签暂无样例值' }}
                  </div>
                </div>
              </div>

              <button
                class="label-dropdown-apply"
                :disabled="!selectedLabelName || !selectedLabelValue"
                @click="addActiveLabel(selectedLabelName, selectedLabelValue)"
              >
                ＋ 添加条件
              </button>
            </div>
            <div v-else class="label-empty">未发现 Loki 标签</div>
          </template>
        </div>
      </div>

    </aside>

    <!-- 右侧内容区 -->
    <div class="log-panel">
      <!-- 工具栏 -->
      <div class="log-toolbar">
        <div class="toolbar-left">
          <!-- Tab 切换 -->
          <div class="tab-group">
            <button class="tab-btn" :class="{ active: activeTab === 'logs' }" @click="switchTab('logs')">
              📋 日志流
              <span class="tab-count">{{ logs.length }}</span>
            </button>
            <button class="tab-btn" :class="{ active: activeTab === 'templates' }" @click="switchTab('templates')">
              🧩 模板聚合
              <span class="tab-count" v-if="templates.length">{{ templates.length }}</span>
            </button>
            <button class="tab-btn" :class="{ active: activeTab === 'trace' }" @click="switchTab('trace')">
              ⏱ 耗时追踪
            </button>
          </div>
        </div>
        <div class="toolbar-right">
          <!-- 关键字搜索（日志流 / 模板聚合 tab 共用） -->
          <div v-if="activeTab !== 'trace'" class="keyword-wrap" title="服务端关键字（重新查询 Loki）">
            <span class="kw-icon">🔍</span>
            <input
              v-model="keyword"
              class="kw-input"
              placeholder="后端关键字（查询 Loki）..."
              @input="onKeywordInput"
              @keyup.enter="onParamChange"
            />
            <button v-if="keyword" class="kw-clear" @click="clearKeyword">✕</button>
          </div>
          <!-- 多服务选择（可跨服务同时查，等价 Loki app=~"a|b|c"） -->
          <div v-if="activeTab !== 'trace'" class="multi-filter-wrap svc-multi" title="多服务筛选：输入服务名回车加入，可选多个跨服务查看总体调用">
            <span class="kw-icon">≡</span>
            <span
              v-for="(svc, i) in selectedServices"
              :key="'svc-'+i"
              class="filter-chip include svc-chip"
              title="点击删除"
            >
              <span class="chip-prefix">◈</span>
              <span class="chip-text">{{ svc }}</span>
              <span class="chip-remove" @click.stop="removeServiceChip(i)" title="删除服务">✕</span>
            </span>
            <input
              v-model="serviceChipInput"
              list="svc-datalist"
              class="kw-input multi-input"
              :placeholder="selectedServices.length ? '再加服务...' : '服务名 (回车加入；可选多个)'"
              @keyup.enter="addServiceChip"
              @keydown.backspace="onServiceChipBackspace"
            />
            <datalist id="svc-datalist">
              <option v-for="s in allServicesList" :key="s" :value="s" />
            </datalist>
            <button v-if="selectedServices.length" class="kw-clear" @click="selectedServices = []; selectedService = ''; onParamChange()" title="清空全部服务">✕</button>
          </div>

          <!-- 多条件关键字过滤（服务端 Loki 查询：AND/OR 可切；- 前缀=排除） -->
          <div v-if="activeTab === 'logs'" class="multi-filter-wrap" title="多关键字：回车加入；- 前缀=排除；点 chip 切包含/排除；同时推到 Loki 服务端查询">
            <span class="kw-icon">⊕</span>
            <!-- AND / OR 切换 -->
            <div class="kw-mode-switch" title="AND=同时命中所有关键字；OR=命中任一即可">
              <button
                class="kw-mode-btn"
                :class="{ active: keywordMode === 'and' }"
                @click="keywordMode = 'and'; onParamChange()"
              >AND</button>
              <button
                class="kw-mode-btn"
                :class="{ active: keywordMode === 'or' }"
                @click="keywordMode = 'or'; onParamChange()"
              >OR</button>
            </div>
            <span
              v-for="(chip, i) in localKeywords"
              :key="i"
              class="filter-chip"
              :class="chip.exclude ? 'exclude' : 'include'"
              @click="toggleChipExclude(i); onParamChange()"
              :title="chip.exclude ? '排除（点击切回包含）' : '包含（点击切为排除）'"
            >
              <span class="chip-prefix">{{ chip.exclude ? '−' : '+' }}</span>
              <span class="chip-text">{{ chip.text }}</span>
              <span class="chip-remove" @click.stop="removeChip(i); onParamChange()" title="删除条件">✕</span>
            </span>
            <input
              v-model="localKeywordInput"
              class="kw-input multi-input"
              :placeholder="localKeywords.length ? '继续加条件...' : '关键字 (回车加入；- 前缀=排除)'"
              @keyup.enter="addChipFromInput"
              @keydown.backspace="onMultiInputBackspace"
            />
            <button v-if="localKeywords.length" class="kw-clear" @click="localKeywords = []; onParamChange()" title="清空全部条件">✕</button>
          </div>

          <!-- 日志流专有控件 -->
          <template v-if="activeTab === 'logs'">
            <select v-model="levelFilter" class="time-select" @change="onLevelChange">
              <option value="">全部级别</option>
              <option value="error">ERROR</option>
              <option value="warn">WARN</option>
              <option value="info">INFO</option>
              <option value="debug">DEBUG</option>
            </select>
            <button
              class="btn"
              :class="incidentOnly ? 'btn-incident-active' : 'btn-outline'"
              @click="toggleIncident"
              title="仅显示 ERROR/WARN 及含 error/exception/timeout 等关键字的日志"
            >⚡ 仅事件</button>
            <button class="btn btn-outline" @click="loadLogs" :disabled="loadingLogs">
              <span v-if="loadingLogs" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🔄</span>查询
            </button>
            <button class="btn btn-primary" @click="startAIAnalysis" :disabled="analyzingAI">
              <span v-if="analyzingAI" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🤖</span>AI 分析
            </button>
          </template>
          <!-- 模板聚合专有控件 -->
          <template v-if="activeTab === 'templates'">
            <span class="meta-info" v-if="templateMeta.total_logs">
              采样 {{ templateMeta.total_logs }} 条 → {{ templates.length }} 个模板
            </span>
            <select v-model="tplLevelFilter" class="time-select" @change="loadTemplates">
              <option value="">全量日志</option>
              <option value="error">仅 ERROR</option>
              <option value="warn">仅 WARN</option>
            </select>
            <button class="btn btn-outline" @click="loadTemplates" :disabled="loadingTemplates">
              <span v-if="loadingTemplates" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🔄</span>重新聚类
            </button>
            <button class="btn btn-primary" @click="startTplAIAnalysis" :disabled="analyzingTplAI || loadingTemplates || !templates.length">
              <span v-if="analyzingTplAI" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
              <span v-else>🤖</span>AI 分析
            </button>
          </template>
        </div>
      </div>

      <!-- AI 分析面板（日志流 tab） -->
      <transition name="fade">
        <div v-if="(aiContent || analyzingAI) && activeTab === 'logs'" class="ai-panel">
          <div class="ai-panel-header">
            <span>🤖 AI 分析结果</span>
            <button class="btn btn-outline btn-xs" @click="aiContent = ''">关闭</button>
          </div>
          <div class="ai-content" v-html="renderedAI"></div>
          <div v-if="analyzingAI" class="ai-typing">
            <span class="dot1">·</span><span class="dot2">·</span><span class="dot3">·</span>
          </div>
        </div>
      </transition>
      <!-- AI 分析面板（模板聚合 tab） -->
      <transition name="fade">
        <div v-if="(tplAiContent || analyzingTplAI) && activeTab === 'templates'" class="ai-panel">
          <div class="ai-panel-header">
            <span>🤖 模板聚类 AI 分析</span>
            <button class="btn btn-outline btn-xs" @click="tplAiContent = ''">关闭</button>
          </div>
          <div class="ai-content" v-html="renderedTplAI"></div>
          <div v-if="analyzingTplAI" class="ai-typing">
            <span class="dot1">·</span><span class="dot2">·</span><span class="dot3">·</span>
          </div>
        </div>
      </transition>

      <!-- ── 日志流 ── -->
      <div v-show="activeTab === 'logs'" class="log-container">
        <div v-if="loadingLogs && !filteredLogs.length" class="empty-state">
          <div class="spinner"></div><p>加载日志中...</p>
        </div>
        <div v-else-if="!filteredLogs.length" class="empty-state">
          <span class="icon">📭</span><p>暂无日志数据</p>
        </div>
        <template v-else>
          <!-- 统计栏 -->
          <div class="log-stats-bar">
            <span class="log-stat-item">
              共 <strong>{{ filteredLogs.length }}</strong> 条
              <span v-if="filteredLogs.length !== logs.length" class="log-stat-filtered">（过滤后）</span>
            </span>
            <span class="log-stat-sep">·</span>
            <span v-for="(cnt, lvl) in levelStats" :key="lvl" class="log-stat-item">
              <span class="lvl-dot" :class="'lvl-' + lvl"></span>{{ lvl.toUpperCase() }} {{ cnt }}
            </span>
          </div>
          <!-- 表格 -->
          <div ref="logScrollWrap" class="log-table-wrap" @scroll.passive="onLogScroll">
            <table class="log-table">
              <colgroup>
              <col style="width:168px">
              <col style="width:72px">
              <col style="width:130px">
              <col style="width:120px">
              <col>
              </colgroup>
              <thead>
                <tr>
                  <th>时间</th>
                  <th>级别</th>
                  <th>服务</th>
                  <th>分组</th>
                  <th>内容</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(log, i) in filteredLogs" :key="i"
                  class="log-row" :class="[logRowClass(log.line), { selected: isSelectedLog(log) }]"
                  @click="openDetail(log)"
                >
                  <td class="col-ts">{{ log.timestamp }}</td>
                  <td class="col-lvl">
                    <span class="lvl-badge" :class="'lvl-badge-' + extractLevel(log.line)">
                      {{ extractLevel(log.line).toUpperCase() }}
                    </span>
                  </td>
                  <td class="col-svc">{{ logServiceName(log) }}</td>
                  <td class="col-group">{{ logGroup(log) }}</td>
                  <td class="col-msg">{{ log.line }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <!-- 加载更多 -->
          <div class="load-more-bar" :class="{ ready: hasMore && !loadingMore }">
            <span v-if="loadingMore" class="load-more-status">
              <span class="spinner" style="width:13px;height:13px;border-width:2px"></span>
              正在继续加载日志...
            </span>
            <span v-else-if="hasMore" class="load-more-status">
              向下滚动到底部自动加载更多，已加载 {{ totalLoaded }} 条
            </span>
            <span v-else class="load-more-status">
              已加载全部日志，共 {{ totalLoaded }} 条
            </span>
          </div>
        </template>
      </div>

      <!-- 日志详情模态框（居中弹出，包含原始记录 + 上下文滚动）-->
      <transition name="modal-fade">
        <div v-if="detailLog" class="log-detail-modal-mask" @click.self="closeDetail" @keyup.esc="closeDetail" tabindex="0">
          <div class="drawer-panel log-detail-modal">
            <div class="drawer-header">
              <span>日志详情 · 上下文</span>
              <button class="drawer-close" @click="closeDetail">✕</button>
            </div>
            <div class="drawer-body">
              <!-- 元数据折叠区（默认收起，header 显示关键摘要，留更多空间给上下文） -->
              <div class="drawer-meta-section" :class="{ open: metaOpen }">
                <div class="drawer-meta-header" @click="metaOpen = !metaOpen">
                  <span class="meta-toggle">{{ metaOpen ? '▼' : '▶' }}</span>
                  <span class="meta-title">元数据</span>
                  <span class="meta-summary">
                    <span class="meta-summary-ts">{{ detailLog.timestamp }}</span>
                    <span class="lvl-badge mini" :class="'lvl-badge-' + extractLevel(detailLog.line)">
                      {{ extractLevel(detailLog.line).toUpperCase() }}
                    </span>
                    <span class="meta-summary-svc">{{ logServiceName(detailLog) }}</span>
                    <span class="meta-summary-ns">{{ logGroup(detailLog) }}</span>
                  </span>
                </div>
                <div v-if="metaOpen" class="drawer-meta-body">
                  <div class="drawer-row">
                    <span class="drawer-label">时间</span>
                    <span class="drawer-val">{{ detailLog.timestamp }}</span>
                  </div>
                  <div class="drawer-row">
                    <span class="drawer-label">级别</span>
                    <span class="lvl-badge" :class="'lvl-badge-' + extractLevel(detailLog.line)">
                      {{ extractLevel(detailLog.line).toUpperCase() }}
                    </span>
                  </div>
                  <div class="drawer-row">
                    <span class="drawer-label">服务</span>
                    <span class="drawer-val">{{ logServiceName(detailLog) }}</span>
                  </div>
                  <div class="drawer-row">
                    <span class="drawer-label">分组</span>
                    <span class="drawer-val">{{ logGroup(detailLog) }}</span>
                  </div>
                  <div v-if="detailLog.labels && Object.keys(detailLog.labels).length" class="drawer-row">
                    <span class="drawer-label">标签</span>
                    <div class="drawer-tags">
                      <span v-for="(v, k) in detailLog.labels" :key="k" class="drawer-tag">{{ k }}=<em>{{ v }}</em></span>
                    </div>
                  </div>
                  <div class="drawer-row drawer-row-full">
                    <span class="drawer-label">内容</span>
                    <pre class="drawer-content">{{ detailLog.line }}</pre>
                  </div>
                </div>
              </div>
              <div class="drawer-row drawer-row-full">
                <div class="drawer-section-header">
                  <span class="drawer-section-title">
                    上下文
                    <span
                      v-if="loadingDetailContext"
                      class="spinner mini-inline"
                      title="后台加载前后上下文中..."
                    ></span>
                  </span>
                  <div class="drawer-section-actions">
                    <span v-if="detailContextBeforeCount || detailContextAfterCount" class="drawer-section-meta">
                      前 {{ detailContextBeforeCount }} / 后 {{ detailContextAfterCount }}
                    </span>
                    <button class="btn btn-outline btn-xs" @click="loadLogContext(detailLog, { reset: true })">刷新</button>
                  </div>
                </div>
                <div v-if="detailContextError" class="drawer-context-state drawer-context-state-error">
                  {{ detailContextError }}
                </div>
                <div
                  v-else-if="detailContextLogs.length"
                  ref="contextScrollWrap"
                  class="drawer-context-list"
                  @scroll.passive="onContextScroll"
                >
                  <div v-if="loadingContextBefore" class="drawer-context-loading-more">
                    <span class="spinner" style="width:12px;height:12px;border-width:2px"></span>
                    正在加载更早的上下文...
                  </div>
                  <div v-else-if="contextBeforeAtLimit" class="drawer-context-hint">已到达可用上下文上限</div>
                  <div
                    v-for="(item, idx) in detailContextLogs"
                    :key="`${item.timestamp_ns}-${idx}`"
                    class="drawer-context-item"
                    :class="[
                      { active: idx === detailContextAnchorIndex },
                      logClass(item.line),
                    ]"
                  >
                    <span v-if="idx === detailContextAnchorIndex" class="anchor-marker" title="当前查询的记录">▶</span>
                    <span class="drawer-context-ts">{{ item.timestamp }}</span>
                    <span class="drawer-context-svc">{{ logServiceName(item) }}</span>
                    <span class="drawer-context-text">{{ item.line }}</span>
                  </div>
                  <div v-if="loadingContextAfter" class="drawer-context-loading-more">
                    <span class="spinner" style="width:12px;height:12px;border-width:2px"></span>
                    正在加载更晚的上下文...
                  </div>
                  <div v-else-if="contextAfterAtLimit" class="drawer-context-hint">已到达可用上下文上限</div>
                  <div v-if="!detailContextAnchorFound" class="drawer-context-hint">
                    未精确定位当前行，已展示同一日志流的邻近上下文。
                  </div>
                  <div class="drawer-context-hint">滚动到顶/底自动加载更多上下文。</div>
                </div>
                <div v-else class="drawer-context-state">未找到可展示的上下文日志。</div>
              </div>
            </div>
          </div>
        </div>
      </transition>

      <!-- ── 模板聚合 ── -->
      <div v-show="activeTab === 'templates'" class="template-container">
        <div v-if="loadingTemplates" class="empty-state">
          <div class="spinner"></div><p>Drain3 聚类中...</p>
        </div>
        <div v-else-if="tplError" class="empty-state">
          <span class="icon">⚠️</span>
          <p style="color:var(--error)">{{ tplError }}</p>
        </div>
        <div v-else-if="!templates.length" class="empty-state">
          <span class="icon">🧩</span>
          <p>当前条件下暂无日志可聚类<br><small style="color:var(--text-muted)">尝试切换「全量日志」或扩大时间范围</small></p>
        </div>
        <div v-else class="template-list">
          <div v-for="(tpl, i) in templates" :key="tpl.cluster_id" class="tpl-card">
            <!-- 头部：排名 + 计数 + 模板 -->
            <div class="tpl-header">
              <span class="tpl-rank" :class="i < 3 ? 'rank-top' : ''">{{ i + 1 }}</span>
              <span class="tpl-count badge badge-error">{{ tpl.count }} 条</span>
              <span class="tpl-pct">{{ tplPct(tpl.count) }}%</span>
              <div class="tpl-bar-wrap">
                <div class="tpl-bar" :style="{ width: tplBarW(tpl.count) + '%' }"></div>
              </div>
            </div>
            <!-- 模板字符串 -->
            <div class="tpl-pattern" v-html="highlightWildcard(tpl.template)"></div>
            <!-- 服务分布 -->
            <div class="tpl-services" v-if="tpl.top_services.length">
              <span class="tpl-label">来源：</span>
              <span
                v-for="s in tpl.top_services" :key="s.name"
                class="svc-chip"
              >{{ s.name }}<em>{{ s.count }}</em></span>
            </div>
            <!-- 示例原文（可展开） -->
            <div class="tpl-example" v-if="tpl.example">
              <span class="tpl-label">示例：</span>
              <span class="tpl-example-text">
                <span class="tpl-example-ts">{{ tpl.example_ts }}</span>
                {{ tpl.example }}
              </span>
            </div>
          </div>
        </div>
      </div>
      <!-- ── 耗时追踪 Tab ── -->
      <div v-show="activeTab === 'trace'" class="trace-tab">
        <!-- 查询表单（单行紧凑工具栏） -->
        <div class="trace-form-bar">
          <!-- 追踪值输入 -->
          <div class="trace-input-wrap trace-input-grow">
            <span class="trace-input-icon">🔍</span>
            <input
              v-model="traceValue"
              class="trace-input"
              placeholder="追踪值：traceId、requestId、关键字..."
              @keyup.enter="runTrace"
            />
            <button v-if="traceValue" class="kw-clear" @click="traceValue = ''">✕</button>
          </div>
          <!-- 时间模式 -->
          <div class="time-mode-tabs" style="width:fit-content;flex-shrink:0">
            <button class="tmode-btn" :class="{ active: traceTimeMode === 'relative' }" @click="traceTimeMode = 'relative'">快速</button>
            <button class="tmode-btn" :class="{ active: traceTimeMode === 'custom' }" @click="switchTraceToCustom">自定义</button>
          </div>
          <select v-if="traceTimeMode === 'relative'" v-model="traceHours" class="time-select" style="width:120px;flex-shrink:0">
            <option value="1">最近 1 小时</option>
            <option value="6">最近 6 小时</option>
            <option value="24">最近 24 小时</option>
            <option value="72">最近 3 天</option>
            <option value="168">最近 7 天</option>
          </select>
          <template v-else>
            <input type="datetime-local" v-model="traceStart" class="dt-input" style="width:152px;flex-shrink:0" title="开始时间" />
            <span class="dt-sep" style="flex-shrink:0">→</span>
            <input type="datetime-local" v-model="traceEnd"   class="dt-input" style="width:152px;flex-shrink:0" title="结束时间" />
          </template>
          <!-- 当前服务提示 -->
          <span v-if="selectedService" class="trace-svc-hint" style="flex-shrink:0;font-size:12px;color:var(--text-muted);white-space:nowrap">
            服务: <em style="color:var(--primary)">{{ selectedService }}</em>
          </span>
          <!-- 分析按钮 -->
          <button
            class="btn btn-trace-primary"
            @click="runTrace"
            :disabled="!traceValue || tracingKeyword"
            style="flex-shrink:0"
          >
            <span v-if="tracingKeyword" class="spinner" style="width:14px;height:14px;border-width:2px"></span>
            <span v-else>⏱</span>
            开始分析
          </button>
        </div>

        <!-- 结果区 -->
        <div v-if="tracingKeyword" class="empty-state">
          <div class="spinner"></div>
          <p>正在全量扫描日志，计算首末耗时...</p>
          <small style="color:var(--text-muted)">最多扫描 50,000 条匹配日志</small>
        </div>
        <div v-else-if="traceResult" class="trace-result">
          <!-- 未找到 / 请求失败 -->
          <div v-if="!traceResult.found" class="trace-not-found">
            <span class="icon" style="font-size:28px">{{ traceResult._error ? '⚠️' : '🔍' }}</span>
            <p v-if="traceResult._error" style="color:var(--error);font-size:13px">
              请求失败：{{ traceResult._error }}
            </p>
            <p v-else>
              在指定时间范围内未找到包含 <em>{{ traceResult.keyword }}</em> 的日志
            </p>
            <small v-if="!traceResult._error" style="color:var(--text-muted)">
              请检查关键字拼写、时间范围或服务选择是否正确
            </small>
          </div>
          <!-- 找到了：子页签 -->
          <template v-else>
            <!-- 子页签切换栏 -->
            <div class="trace-sub-tabs">
              <button
                class="trace-sub-btn"
                :class="{ active: traceResultTab === 'overview' }"
                @click="traceResultTab = 'overview'"
              >
                ⏱ 耗时概览
              </button>
              <button
                class="trace-sub-btn"
                :class="{ active: traceResultTab === 'logs' }"
                @click="traceResultTab = 'logs'"
              >
                📋 匹配日志
                <span class="trace-sub-badge">
                  <span v-if="loadingTraceLogs" class="spinner" style="width:10px;height:10px;border-width:2px"></span>
                  <span v-else>{{ traceLogs.length }}</span>
                </span>
              </button>
            </div>

            <!-- ── 耗时概览页签 ── -->
            <div v-show="traceResultTab === 'overview'" class="trace-overview">
              <!-- 大耗时数字区 -->
              <div class="trace-hero">
                <div class="trace-hero-label">全链路耗时</div>
                <div class="trace-hero-duration">{{ traceResult.duration_str }}</div>
                <div class="trace-hero-meta">
                  关键字 <em>{{ traceResult.keyword }}</em>
                  · 共匹配 <strong>{{ traceResult.log_count }}</strong> 条日志
                  <span v-if="traceResult.log_count >= 50000" class="trace-limit-hint">（已达扫描上限）</span>
                </div>
              </div>
              <!-- 时间线 -->
              <div class="trace-timeline-card">
                <!-- 首次 -->
                <div class="trace-tl-row">
                  <div class="trace-tl-left">
                    <div class="trace-tl-dot dot-first"></div>
                    <div class="trace-tl-connector"></div>
                  </div>
                  <div class="trace-tl-body">
                    <div class="trace-tl-tag">首次出现</div>
                    <div class="trace-tl-ts">{{ traceResult.first_ts }}</div>
                    <span v-if="traceResult.first_service" class="trace-ep-svc">{{ traceResult.first_service }}</span>
                    <div class="trace-tl-log">{{ traceResult.first_log }}</div>
                  </div>
                </div>
                <!-- 耗时标注 -->
                <div class="trace-tl-row dur-row">
                  <div class="trace-tl-left">
                    <div class="trace-tl-line"></div>
                  </div>
                  <div class="trace-tl-dur-badge">{{ traceResult.duration_str }}</div>
                </div>
                <!-- 末次 -->
                <div class="trace-tl-row">
                  <div class="trace-tl-left">
                    <div class="trace-tl-dot dot-last"></div>
                  </div>
                  <div class="trace-tl-body">
                    <div class="trace-tl-tag">末次出现</div>
                    <div class="trace-tl-ts">{{ traceResult.last_ts }}</div>
                    <span v-if="traceResult.last_service" class="trace-ep-svc">{{ traceResult.last_service }}</span>
                    <div class="trace-tl-log">{{ traceResult.last_log }}</div>
                  </div>
                </div>
              </div>

              <!-- 每条耗时列表 -->
              <div class="trace-spans-card">
                <div class="trace-spans-header">
                  <span>每次出现耗时</span>
                  <span v-if="loadingTraceLogs" class="spinner" style="width:11px;height:11px;border-width:2px;flex-shrink:0"></span>
                  <span v-else class="trace-logs-count">{{ traceLogs.length }} 条</span>
                </div>
                <div v-if="loadingTraceLogs && !traceLogs.length" class="empty-state" style="padding:20px">
                  <div class="spinner"></div><p style="font-size:12px">加载中...</p>
                </div>
                <div v-else class="trace-span-list">
                  <div
                    v-for="(log, i) in traceLogs" :key="i"
                    class="trace-span-row"
                    :class="[logClass(log.line), { expanded: expandedSpans.has(i) }]"
                    @click="toggleSpan(i)"
                  >
                    <div class="trace-span-idx">{{ i + 1 }}</div>
                    <div class="trace-span-elapsed">{{ spanElapsed(log) }}</div>
                    <div class="trace-span-bar-wrap">
                      <div class="trace-span-bar" :style="{ width: spanBarW(log) + '%' }"></div>
                    </div>
                    <div class="trace-span-ts">{{ log.timestamp }}</div>
                    <span v-if="log.labels.app || log.labels.job" class="trace-ep-svc">{{ log.labels.app || log.labels.job }}</span>
                    <div class="trace-span-line">{{ log.line }}</div>
                  </div>
                </div>
              </div>
            </div>

            <!-- ── 匹配日志页签 ── -->
            <div v-show="traceResultTab === 'logs'" class="trace-log-panel">
              <div class="trace-logs-header">
                <span>匹配日志（按时间升序）</span>
                <span v-if="loadingTraceLogs" class="spinner" style="width:12px;height:12px;border-width:2px;flex-shrink:0"></span>
                <span v-else class="trace-logs-count">{{ traceLogs.length }} 条</span>
                <span v-if="traceLogs.length >= 2000" class="trace-limit-hint" style="margin-left:4px">（仅展示前 2000 条）</span>
              </div>
              <div class="trace-log-list">
                <div v-if="loadingTraceLogs && !traceLogs.length" class="empty-state" style="padding:24px">
                  <div class="spinner"></div><p style="font-size:12px">加载日志列表...</p>
                </div>
                <div
                  v-for="(log, i) in traceLogs" :key="i"
                  class="log-line" :class="logClass(log.line)"
                >
                  <span class="log-ts">{{ log.timestamp }}</span>
                  <span class="log-svc">{{ log.labels.app || log.labels.job || '?' }}</span>
                  <span class="log-text">{{ log.line }}</span>
                </div>
              </div>
            </div>
          </template>
        </div>
        <!-- 初始提示 -->
        <div v-else class="empty-state" style="flex:1">
          <span class="icon" style="font-size:36px">⏱</span>
          <p>输入追踪值并选择时间范围，分析关键字首次到末次出现的耗时</p>
          <small style="color:var(--text-muted)">支持 traceId、requestId、订单号等任意字符串</small>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { api, streamSSE } from '../api/index.js'

// ── 公共状态 ─────────────────────────────
const selectedService = ref('')
const hours          = ref('0.016667')
const groupBy        = ref('namespace')
const selectedGroupLabel = ref('')
const selectedGroupValue = ref('')
const labelCatalog   = ref([])
const groupOptions   = ref([{ value: 'namespace', label: 'namespace' }])
const loadingLabelCatalog = ref(false)
const labelExplorerOpen = ref(true)
const openLabelGroups = ref(new Set())
const labelValueMap = ref({})
const labelValueTotals = ref({})
const loadingLabelValueMap = ref({})
const selectedLabelName = ref('')
const selectedLabelValue = ref('')
// 可搜索下拉：查询词 + 展开状态
const labelNameQuery = ref('')
const labelValueQuery = ref('')
const showLabelNameDropdown = ref(false)
const showLabelValueDropdown = ref(false)
let hideLabelNameTimer = null
let hideLabelValueTimer = null
// 多标签条件：数组形式 [{label, value}]，同一 label 只保留最新一条
const activeLabelFilters = ref([])

const activeTab      = ref('logs')

// 时间模式：relative（最近N小时） | custom（自定义时间段）
const timeMode    = ref('relative')
const customStart = ref('')
const customEnd   = ref('')

// 关键字搜索
const keyword      = ref('')         // 后端单关键字（旧参数，仍保留）
const localKeywords     = ref([])    // 多条件过滤：[{ text, exclude }] AND/OR，同时推到 Loki 服务端
const localKeywordInput = ref('')    // 多条件输入框临时状态
const keywordMode  = ref('and')      // 多关键字组合模式 and/or
// 多服务：LogAnalysis 支持一次查多个服务的日志（跨服务调用链排障用）
const selectedServices  = ref([])    // 已选服务列表 chip
const serviceChipInput  = ref('')    // 服务 chip 输入临时状态
const allServicesList   = ref([])    // 服务名下拉候选（datalist）
let   searchTimer  = null

function addChipFromInput() {
  const raw = (localKeywordInput.value || '').trim()
  if (!raw) return
  // - 前缀视为排除
  const exclude = raw.startsWith('-') && raw.length > 1
  const text = exclude ? raw.slice(1).trim() : raw
  if (!text) return
  // 同文本去重
  if (localKeywords.value.some(c => c.text === text && c.exclude === exclude)) {
    localKeywordInput.value = ''
    return
  }
  localKeywords.value.push({ text, exclude })
  localKeywordInput.value = ''
  onParamChange()
}

function addServiceChip() {
  const raw = (serviceChipInput.value || '').trim()
  if (!raw) return
  if (selectedServices.value.includes(raw)) { serviceChipInput.value = ''; return }
  selectedServices.value.push(raw)
  serviceChipInput.value = ''
  // 单值 selectedService 保持与首个已选服务同步，便于跳转/URL 兼容
  if (selectedServices.value.length === 1) selectedService.value = raw
  onParamChange()
}

function removeServiceChip(i) {
  selectedServices.value.splice(i, 1)
  if (!selectedServices.value.length && selectedService.value) selectedService.value = ''
  else if (selectedServices.value.length) selectedService.value = selectedServices.value[0]
  onParamChange()
}

function onServiceChipBackspace() {
  if (serviceChipInput.value === '' && selectedServices.value.length) {
    selectedServices.value.pop()
    onParamChange()
  }
}

// 组装本页所有请求都要带的多条件参数（服务/关键字/排除/模式/标签）
function multiFilterParams() {
  const p = {}
  const svcs = selectedServices.value
  if (svcs.length > 1) p.services = svcs.join(',')
  else if (svcs.length === 1) p.service = svcs[0]
  else if (selectedService.value) p.service = selectedService.value

  const inc = localKeywords.value.filter(c => !c.exclude).map(c => c.text)
  const exc = localKeywords.value.filter(c =>  c.exclude).map(c => c.text)
  if (inc.length) {
    p.keywords = inc.join(',')
    if (inc.length > 1) p.keyword_mode = keywordMode.value
  } else if (keyword.value) {
    p.keyword = keyword.value
  }
  if (exc.length) p.exclude_keywords = exc.join(',')

  // 多标签条件：axios 收到数组会自动展开成 labels=a:x&labels=b:y
  if (activeLabelFilters.value.length) {
    p.labels = activeLabelFilters.value.map(x => `${x.label}:${x.value}`)
  }
  return p
}

function toggleChipExclude(i) {
  const c = localKeywords.value[i]
  if (!c) return
  localKeywords.value.splice(i, 1, { ...c, exclude: !c.exclude })
}

function removeChip(i) {
  localKeywords.value.splice(i, 1)
}

// 输入框空时按 backspace：删掉最后一个 chip（IDE / 邮件客户端常见交互）
function onMultiInputBackspace() {
  if (localKeywordInput.value === '' && localKeywords.value.length) {
    localKeywords.value.pop()
  }
}
let   logsAbort = null
let   loadMoreAbort = null
let   templatesAbort = null
let   traceLogsAbort = null
let   detailContextAbort = null
let   logsRequestId = 0
let   loadMoreRequestId = 0
let   templatesRequestId = 0
let   detailContextRequestId = 0

const groupByOptions = computed(() => {
  const options = groupOptions.value.length
    ? [...groupOptions.value]
    : [{ value: 'namespace', label: 'namespace' }]
  if (groupBy.value && !options.some(option => option.value === groupBy.value)) {
    options.unshift({ value: groupBy.value, label: groupBy.value })
  }
  return options
})
const selectedLabelValues = computed(() => (
  selectedLabelName.value ? (labelValueMap.value[selectedLabelName.value] || []) : []
))

// ── 可搜索下拉过滤（大小写不敏感包含匹配） ──
function _fuzzyFilter(items, query, textFn) {
  const q = (query || '').trim().toLowerCase()
  if (!q) return items
  return items.filter(it => textFn(it).toLowerCase().includes(q))
}

const filteredLabels = computed(() => (
  _fuzzyFilter(labelCatalog.value || [], labelNameQuery.value, it => it.name)
))
const filteredLabelValues = computed(() => (
  _fuzzyFilter(selectedLabelValues.value, labelValueQuery.value, v => String(v))
))

// 高亮命中片段，切成 [{t, hit}] 数组供 <mark class="hl"> 渲染
function highlight(text, query) {
  const str = String(text ?? '')
  const q = (query || '').trim()
  if (!q) return [{ t: str, hit: false }]
  const idx = str.toLowerCase().indexOf(q.toLowerCase())
  if (idx < 0) return [{ t: str, hit: false }]
  const out = []
  if (idx > 0) out.push({ t: str.slice(0, idx), hit: false })
  out.push({ t: str.slice(idx, idx + q.length), hit: true })
  if (idx + q.length < str.length) out.push({ t: str.slice(idx + q.length), hit: false })
  return out
}

function pickLabelName(name) {
  selectedLabelName.value = name
  labelNameQuery.value = name
  showLabelNameDropdown.value = false
  // 复位标签值搜索并触发加载
  labelValueQuery.value = ''
  onLabelDropdownChange()
}
function clearLabelName() {
  selectedLabelName.value = ''
  labelNameQuery.value = ''
  labelValueQuery.value = ''
  selectedLabelValue.value = ''
  showLabelNameDropdown.value = true
}
function hideLabelNameLater() {
  clearTimeout(hideLabelNameTimer)
  hideLabelNameTimer = setTimeout(() => { showLabelNameDropdown.value = false }, 120)
}

function pickLabelValue(value) {
  selectedLabelValue.value = value
  labelValueQuery.value = String(value)
  showLabelValueDropdown.value = false
  onLabelValueDropdownChange()
}
function clearLabelValue() {
  selectedLabelValue.value = ''
  labelValueQuery.value = ''
  showLabelValueDropdown.value = true
}
function hideLabelValueLater() {
  clearTimeout(hideLabelValueTimer)
  hideLabelValueTimer = setTimeout(() => { showLabelValueDropdown.value = false }, 120)
}

// selectedLabelName/Value 被其它路径（onGroupByChange / _applyRouteQuery / loadLabelCatalog）
// 修改时，同步输入框显示，避免"值已选但输入框为空"的错觉
watch(selectedLabelName, (v) => {
  if (v && !labelNameQuery.value) labelNameQuery.value = v
  else if (!v) labelNameQuery.value = ''
})
watch(selectedLabelValue, (v) => {
  if (v && !labelValueQuery.value) labelValueQuery.value = String(v)
  else if (!v) labelValueQuery.value = ''
})

function logServiceName(log) {
  return log?.labels?.app || log?.labels?.job || selectedService.value || '—'
}

function logGroup(log) {
  const labels = log?.labels || {}
  if (selectedGroupLabel.value && labels[selectedGroupLabel.value]) return labels[selectedGroupLabel.value]
  if (groupBy.value && labels[groupBy.value]) return labels[groupBy.value]
  return (
    labels.namespace ||
    labels.k8s_namespace_name ||
    labels.kubernetes_namespace ||
    labels.k8s_namespace ||
    labels.ns ||
    '默认'
  )
}

// 返回今天 00:00 ~ 当前时刻的本地时间字符串（datetime-local 格式）
function todayRange() {
  const now = new Date()
  const pad = n => String(n).padStart(2, '0')
  const date = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
  return {
    start: `${date}T00:00`,
    end:   `${date}T${pad(now.getHours())}:${pad(now.getMinutes())}`,
  }
}

// datetime-local 返回本地时间字符串，转成 UTC ISO 再发给后端
function toUtcStr(localStr) {
  if (!localStr) return ''
  return new Date(localStr).toISOString().slice(0, 16)   // "2025-03-25T02:00"
}

// 构建时间参数（relative 或 custom）
function timeParams() {
  if (timeMode.value === 'custom' && customStart.value && customEnd.value) {
    return { start_time: toUtcStr(customStart.value), end_time: toUtcStr(customEnd.value) }
  }
  return { hours: hours.value }
}

function currentGroupParams() {
  if (!selectedGroupLabel.value || !selectedGroupValue.value) {
    return {}
  }
  return {
    group_label: selectedGroupLabel.value,
    group_value: selectedGroupValue.value,
  }
}

// ── 日志流 ───────────────────────────────
const logs         = ref([])
const levelFilter  = ref('')
const loadingLogs  = ref(false)
const loadingMore  = ref(false)
const hasMore      = ref(false)
const nextCursorNs = ref(null)
const totalLoaded  = ref(0)
const logScrollWrap = ref(null)
const analyzingAI  = ref(false)
const aiContent    = ref('')

// 仅事件过滤
const incidentOnly = ref(false)
const INCIDENT_KEYWORDS = ['error', 'exception', 'fail', 'timeout', 'refused', 'panic', 'oom', 'fatal', 'traceback']

// 详情抽屉
const detailLog   = ref(null)
const loadingDetailContext = ref(false)
const detailContextLogs = ref([])
const detailContextAnchorIndex = ref(-1)
const detailContextAnchorFound = ref(true)
const detailContextBeforeCount = ref(0)
const detailContextAfterCount = ref(0)
const detailContextError = ref('')
const contextScrollWrap = ref(null)
const metaOpen = ref(false)   // 元数据折叠状态：默认收起，给上下文留位

// 上下文窗口大小：初始 250 前 + 250 后；每次滚动到边界扩 +200，最大 500（后端 API 限制）
const CONTEXT_INITIAL_BEFORE = 250
const CONTEXT_INITIAL_AFTER  = 250
const CONTEXT_PAGE_STEP      = 200
const CONTEXT_MAX_SIDE       = 500   // 后端 /api/logs/context 的 le=500
const contextWantedBefore = ref(CONTEXT_INITIAL_BEFORE)
const contextWantedAfter  = ref(CONTEXT_INITIAL_AFTER)
const loadingContextBefore = ref(false)
const loadingContextAfter  = ref(false)
// 实际返回数小于请求数时，表示该方向已无更多数据（或到达边界）
const contextBeforeAtLimit = ref(false)
const contextAfterAtLimit  = ref(false)
let contextScrollPending = null   // 用于触底/触顶滚动锚点保留

// 提取日志级别
function extractLevel(line) {
  const l = (line || '').toLowerCase()
  if (/\berror\b|exception|fatal|panic|traceback/.test(l)) return 'error'
  if (/\bwarn(ing)?\b/.test(l))                            return 'warn'
  if (/\binfo\b/.test(l))                                  return 'info'
  if (/\bdebug\b/.test(l))                                 return 'debug'
  return 'other'
}

function logRowClass(line) {
  const lvl = extractLevel(line)
  if (lvl === 'error') return 'row-error'
  if (lvl === 'warn')  return 'row-warn'
  return ''
}

function isSameLog(a, b) {
  if (!a || !b) return false
  const aTs = a.timestamp_ns != null ? String(a.timestamp_ns) : ''
  const bTs = b.timestamp_ns != null ? String(b.timestamp_ns) : ''
  if (aTs && bTs) return aTs === bTs && (a.line || '') === (b.line || '')
  return a === b
}

function isSelectedLog(log) {
  return isSameLog(log, detailLog.value)
}

function scrollContextAnchorIntoView() {
  const anchor = contextScrollWrap.value?.querySelector('.drawer-context-item.active')
  if (!anchor) return false
  anchor.scrollIntoView({ block: 'center', behavior: 'auto' })
  return true
}

const filteredLogs = computed(() => {
  let list = logs.value
  // 前端 incidentOnly 过滤（已从后端拿全量，在前端二次过滤）
  if (incidentOnly.value) {
    list = list.filter(log => {
      const l = (log.line || '').toLowerCase()
      return /\berror\b|exception|fatal|panic|\bwarn\b/.test(l) ||
             INCIDENT_KEYWORDS.some(kw => l.includes(kw))
    })
  }
  // 本地多条件过滤：include 全部命中(AND)；任一 exclude 命中即剔除
  if (localKeywords.value.length) {
    const includes = localKeywords.value.filter(c => !c.exclude).map(c => c.text.toLowerCase())
    const excludes = localKeywords.value.filter(c =>  c.exclude).map(c => c.text.toLowerCase())
    list = list.filter(log => {
      const line = (log.line || '').toLowerCase()
      if (includes.length && !includes.every(t => line.includes(t))) return false
      if (excludes.length &&  excludes.some(t => line.includes(t))) return false
      return true
    })
  }
  return list
})

const levelStats = computed(() => {
  const stats = {}
  for (const log of filteredLogs.value) {
    const lvl = extractLevel(log.line)
    stats[lvl] = (stats[lvl] || 0) + 1
  }
  return stats
})

function toggleIncident() {
  incidentOnly.value = !incidentOnly.value
}

function contextServiceName(log) {
  return log?.labels?.app || log?.labels?.job || selectedService.value || ''
}

function normalizeRequestError(error) {
  if (typeof error === 'string') return error
  if (Array.isArray(error)) {
    return error
      .map(item => item?.msg || item?.message || '')
      .filter(Boolean)
      .join('；') || '请求失败'
  }
  if (error?.detail) return normalizeRequestError(error.detail)
  return error?.message || '请求失败'
}

function closeDetail() {
  detailContextAbort?.abort()
  detailContextAbort = null
  detailLog.value = null
  metaOpen.value = false   // 下次打开重新收起，焦点回到上下文
  loadingDetailContext.value = false
  loadingContextBefore.value = false
  loadingContextAfter.value = false
  detailContextLogs.value = []
  detailContextAnchorIndex.value = -1
  detailContextAnchorFound.value = true
  detailContextBeforeCount.value = 0
  detailContextAfterCount.value = 0
  detailContextError.value = ''
  contextWantedBefore.value = CONTEXT_INITIAL_BEFORE
  contextWantedAfter.value = CONTEXT_INITIAL_AFTER
  contextBeforeAtLimit.value = false
  contextAfterAtLimit.value = false
  contextScrollPending = null
}

/**
 * 加载上下文。统一入口：
 *   - opts.reset: true   重置 wanted before/after 至初始值（默认 false，保留扩展量）
 *   - opts.direction: 'before' | 'after' | null  滚动加载方向，用于保留滚动锚点
 */
async function loadLogContext(log = detailLog.value, opts = {}) {
  if (!log?.timestamp_ns) return

  if (opts.reset) {
    contextWantedBefore.value = CONTEXT_INITIAL_BEFORE
    contextWantedAfter.value = CONTEXT_INITIAL_AFTER
    contextBeforeAtLimit.value = false
    contextAfterAtLimit.value = false
  }

  const requestId = ++detailContextRequestId
  detailContextAbort?.abort()
  const controller = new AbortController()
  detailContextAbort = controller

  const direction = opts.direction || null
  if (!direction) loadingDetailContext.value = true
  if (direction === 'before') loadingContextBefore.value = true
  if (direction === 'after')  loadingContextAfter.value = true
  if (!direction) {
    // 乐观渲染：立即把 detailLog 放进 list 作为锚点，让用户秒看到自己点的那条
    // 不显示"正在加载上下文..."大块文字，后台异步补全前后日志后 merge
    detailContextLogs.value = log ? [{ ...log }] : []
    detailContextAnchorIndex.value = log ? 0 : -1
    detailContextAnchorFound.value = true
    detailContextBeforeCount.value = 0
    detailContextAfterCount.value = 0
    contextScrollPending = null
  }
  detailContextError.value = ''

  // 保留滚动锚点（用于"加载更早"时不让用户跳到顶部）
  const wrap = contextScrollWrap.value
  let savedScroll = null
  if (direction === 'before' && wrap) {
    savedScroll = { prevHeight: wrap.scrollHeight, prevTop: wrap.scrollTop }
  }

  const wantedBefore = Math.min(contextWantedBefore.value, CONTEXT_MAX_SIDE)
  const wantedAfter  = Math.min(contextWantedAfter.value, CONTEXT_MAX_SIDE)

  try {
    const result = await api.getLogContext({
      timestamp_ns: log.timestamp_ns,
      service: contextServiceName(log) || undefined,
      line_prefix: (log.line || '').slice(0, 200) || undefined,
      labels_json: JSON.stringify(log.labels || {}),
      before: wantedBefore,
      after: wantedAfter,
      ...timeParams(),
    }, { signal: controller.signal })

    if (requestId !== detailContextRequestId || detailLog.value !== log) return

    const prevBeforeCount = detailContextBeforeCount.value
    detailContextLogs.value = result.data || []
    detailContextAnchorIndex.value = result.anchor_index ?? -1
    detailContextAnchorFound.value = result.anchor_found !== false
    detailContextBeforeCount.value = result.before_count ?? 0
    detailContextAfterCount.value = result.after_count ?? 0

    // 前端兜底：保证锚点 = 用户实际点击的那条
    //   1) 用 timestamp_ns + line 严格匹配查 anchor index
    //   2) 同 ts 但 line 不同 → 用 detailLog 覆盖那一行
    //   3) 完全找不到 → 按 ts 排序插入 detailLog 作为锚点行
    if (log?.timestamp_ns && detailContextLogs.value.length) {
      const targetTs   = String(log.timestamp_ns)
      const targetLine = log.line || ''

      let exact = detailContextLogs.value.findIndex(
        item => String(item.timestamp_ns) === targetTs && item.line === targetLine,
      )

      if (exact < 0) {
        // 同 ts 但 line 内容不同的位置：用 detailLog 替换那条
        const sameTsIdx = detailContextLogs.value.findIndex(
          item => String(item.timestamp_ns) === targetTs,
        )
        if (sameTsIdx >= 0) {
          detailContextLogs.value.splice(sameTsIdx, 1, { ...log })
          exact = sameTsIdx
        }
      }

      if (exact < 0) {
        // 完全没有同 ts 行 → 按时间戳升序插入
        const targetNum = Number(targetTs)
        let insertAt = detailContextLogs.value.findIndex(
          item => Number(item.timestamp_ns) > targetNum,
        )
        if (insertAt < 0) insertAt = detailContextLogs.value.length
        detailContextLogs.value.splice(insertAt, 0, { ...log })
        exact = insertAt
      }

      detailContextAnchorIndex.value = exact
      detailContextAnchorFound.value = true
    }

    // 判断该方向是否还能继续扩展：
    //  - 返回数 < 请求数 → 该方向已无更多日志
    //  - 已达后端 le=500 上限 → 不能再扩
    if (direction === 'before' || opts.reset || !direction) {
      contextBeforeAtLimit.value = (detailContextBeforeCount.value < wantedBefore) ||
                                   wantedBefore >= CONTEXT_MAX_SIDE
    }
    if (direction === 'after' || opts.reset || !direction) {
      contextAfterAtLimit.value = (detailContextAfterCount.value < wantedAfter) ||
                                  wantedAfter >= CONTEXT_MAX_SIDE
    }

    // 'before' 方向加载完后，把 scrollTop 补到新的同等"上方距离"，避免视野跳变
    if (direction === 'before' && wrap && savedScroll) {
      await nextTick()
      const addedHeight = wrap.scrollHeight - savedScroll.prevHeight
      wrap.scrollTop = savedScroll.prevTop + addedHeight
    }

    // 初始加载或刷新：自动滚到锚点居中
    if (!direction && detailContextAnchorIndex.value >= 0) {
      contextScrollPending = 'anchor'
      await nextTick()
      // 直接在 scroll 容器内查 .active 行，比函数式 ref 可靠
      // (setup script 模板里 ref 自动 unwrap，:ref="el => myRef = el" 写法不会回写)
      const anchor = contextScrollWrap.value?.querySelector('.drawer-context-item.active')
      if (anchor) anchor.scrollIntoView({ block: 'center', behavior: 'auto' })
    }
  } catch (error) {
    if (isCanceled(error)) return
    if (requestId !== detailContextRequestId || detailLog.value !== log) return
    if (!direction) detailContextError.value = normalizeRequestError(error)
  } finally {
    const shouldScrollAnchor = requestId === detailContextRequestId &&
                               !direction &&
                               contextScrollPending === 'anchor'
    if (requestId === detailContextRequestId) {
      if (!direction) loadingDetailContext.value = false
      if (direction === 'before') loadingContextBefore.value = false
      if (direction === 'after')  loadingContextAfter.value = false
    }
    if (detailContextAbort === controller) {
      detailContextAbort = null
    }
    if (shouldScrollAnchor) {
      await nextTick()
      if (requestId === detailContextRequestId && detailLog.value === log) {
        scrollContextAnchorIntoView()
        contextScrollPending = null
      }
    }
  }
}

function loadMoreContextBefore() {
  if (loadingDetailContext.value || loadingContextBefore.value) return
  if (contextBeforeAtLimit.value) return
  if (contextWantedBefore.value >= CONTEXT_MAX_SIDE) {
    contextBeforeAtLimit.value = true
    return
  }
  contextWantedBefore.value = Math.min(contextWantedBefore.value + CONTEXT_PAGE_STEP, CONTEXT_MAX_SIDE)
  loadLogContext(detailLog.value, { direction: 'before' })
}

function loadMoreContextAfter() {
  if (loadingDetailContext.value || loadingContextAfter.value) return
  if (contextAfterAtLimit.value) return
  if (contextWantedAfter.value >= CONTEXT_MAX_SIDE) {
    contextAfterAtLimit.value = true
    return
  }
  contextWantedAfter.value = Math.min(contextWantedAfter.value + CONTEXT_PAGE_STEP, CONTEXT_MAX_SIDE)
  loadLogContext(detailLog.value, { direction: 'after' })
}

function onContextScroll(event) {
  const t = event?.target
  if (!t) return
  if (loadingDetailContext.value) return
  // 距顶部 < 80px → 加载更早；距底部 < 80px → 加载更晚
  if (t.scrollTop < 80 && !loadingContextBefore.value) {
    loadMoreContextBefore()
  }
  const distBottom = t.scrollHeight - t.scrollTop - t.clientHeight
  if (distBottom < 80 && !loadingContextAfter.value) {
    loadMoreContextAfter()
  }
}

function openDetail(log) {
  detailLog.value = log
  loadLogContext(log, { reset: true })   // 切换日志时重置窗口
}

function onLevelChange() {
  loadLogs()
}

function onLogScroll(event) {
  const target = event?.target
  if (!target || loadingLogs.value || loadingMore.value || !hasMore.value) return
  const remaining = target.scrollHeight - target.scrollTop - target.clientHeight
  if (remaining <= 160) {
    loadMore()
  }
}

async function ensureLogViewportFilled() {
  await nextTick()
  const el = logScrollWrap.value
  if (!el || loadingLogs.value || loadingMore.value || !hasMore.value) return
  const remaining = el.scrollHeight - el.scrollTop - el.clientHeight
  if (remaining <= 40) {
    loadMore()
  }
}

// ── 模板聚合 AI ───────────────────────────
function isCanceled(error) {
  return error?.name === 'CanceledError' ||
         error?.code === 'ERR_CANCELED' ||
         error === 'canceled' ||
         (typeof error === 'string' && error.toLowerCase() === 'canceled')
}

const tplAiContent  = ref('')
const analyzingTplAI = ref(false)

// ── 耗时追踪 Tab ──────────────────────────
const traceValue     = ref('')
const traceTimeMode  = ref('relative')   // 默认快速模式，避免空 custom 字段误导
const traceHours     = ref('24')
const traceStart     = ref('')
const traceEnd       = ref('')
const traceResult      = ref(null)
const traceLogs        = ref([])
const tracingKeyword   = ref(false)   // trace API 请求中
const loadingTraceLogs = ref(false)   // 日志列表加载中（独立状态）
const traceResultTab   = ref('overview')  // 结果子页签：overview | logs
const expandedSpans    = ref(new Set())   // 已展开的行索引

const renderedAI = computed(() =>
  aiContent.value
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
)
const renderedTplAI = computed(() =>
  tplAiContent.value
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
)

function logClass(line) {
  const l = line.toLowerCase()
  if (/\berror\b|exception|fatal|panic/.test(l)) return 'level-error'
  if (/\bwarn(ing)?\b/.test(l))                  return 'level-warn'
  return ''
}

// ── 模板聚合 ─────────────────────────────
const templates        = ref([])
const loadingTemplates = ref(false)
const templateMeta     = ref({ total_logs: 0, total_templates: 0 })
const tplLevelFilter   = ref('')
const tplError         = ref('')

const maxTplCount = computed(() =>
  templates.value[0]?.count || 1
)
const totalTplLogs = computed(() =>
  templates.value.reduce((s, t) => s + t.count, 0) || 1
)
function tplBarW(cnt) {
  return Math.round(cnt / maxTplCount.value * 100)
}
function tplPct(cnt) {
  return (cnt / totalTplLogs.value * 100).toFixed(1)
}
function highlightWildcard(tpl) {
  return tpl.replace(/<\*>/g, '<span class="wildcard">&lt;*&gt;</span>')
}

async function loadLabelCatalog() {
  loadingLabelCatalog.value = true
  try {
    const result = await api.getLogLabels()
    labelCatalog.value = result.data || []
    groupOptions.value = result.group_options?.length
      ? result.group_options
      : [{ value: 'namespace', label: 'namespace' }]
    if (result.default_group_by) {
      groupBy.value = result.default_group_by
    }
    const preferredLabel = result.default_group_by || result.service_label || labelCatalog.value[0]?.name || ''
    if (preferredLabel) {
      selectedLabelName.value = preferredLabel
      selectedLabelValue.value = ''
      openLabelGroups.value = new Set([preferredLabel])
      await ensureLabelValues(preferredLabel)
    }
  } catch (error) {
    labelCatalog.value = []
    groupOptions.value = [{ value: 'namespace', label: 'namespace' }]
    openLabelGroups.value = new Set()
    selectedLabelName.value = ''
    selectedLabelValue.value = ''
  } finally {
    loadingLabelCatalog.value = false
  }
}

function labelRoleText(item) {
  if (item?.role === 'service') return '服务'
  if (item?.role === 'namespace') return '命名空间'
  if (item?.role === 'group') return '分组'
  return '标签'
}

function setLabelLoading(labelName, value) {
  loadingLabelValueMap.value = { ...loadingLabelValueMap.value, [labelName]: value }
}

async function ensureLabelValues(labelName) {
  if (!labelName || labelValueMap.value[labelName]) return
  setLabelLoading(labelName, true)
  try {
    const result = await api.getLogLabelValues(labelName, { limit: 80 })
    labelValueMap.value = { ...labelValueMap.value, [labelName]: result.data || [] }
    labelValueTotals.value = { ...labelValueTotals.value, [labelName]: result.total || 0 }
  } catch (error) {
    labelValueMap.value = { ...labelValueMap.value, [labelName]: [] }
    labelValueTotals.value = { ...labelValueTotals.value, [labelName]: 0 }
  } finally {
    setLabelLoading(labelName, false)
  }
}

async function toggleLabelGroup(labelName) {
  if (!labelName) return
  const next = new Set(openLabelGroups.value)
  if (next.has(labelName)) {
    next.delete(labelName)
  } else {
    next.add(labelName)
    ensureLabelValues(labelName)
  }
  openLabelGroups.value = next
}

async function onLabelDropdownChange() {
  selectedLabelValue.value = ''
  if (selectedLabelName.value) {
    await ensureLabelValues(selectedLabelName.value)
  }
}

function onLabelValueDropdownChange() {
  if (selectedLabelName.value && selectedLabelValue.value) {
    applyLabelFilter(selectedLabelName.value, selectedLabelValue.value)
  }
}

function isSelectedLabelFilter(labelName, value) {
  return selectedGroupLabel.value === labelName && selectedGroupValue.value === value
}

function refreshActiveData() {
  if (activeTab.value === 'logs') {
    loadLogs()
  } else if (activeTab.value === 'templates') {
    loadTemplates()
  }
}

function applyLabelFilter(labelName, value) {
  // 兼容旧调用：直接以一条 chip 的形式生效
  selectedLabelName.value = labelName
  selectedLabelValue.value = value
  labelNameQuery.value = labelName
  labelValueQuery.value = String(value ?? '')
  showLabelNameDropdown.value = false
  showLabelValueDropdown.value = false
  addActiveLabel(labelName, value, { skipRefresh: false })
}

function addActiveLabel(labelName, value, opts = {}) {
  if (!labelName || value === '' || value == null) return
  const val = String(value)
  const list = activeLabelFilters.value
  // 同 label+value 才去重；同 label 不同 value 累加（生成 label=~"a|b|c" regex）
  if (list.some(x => x.label === labelName && x.value === val)) {
    // 已存在则不重复添加，仅清值输入方便再挑
    labelValueQuery.value = ''
    selectedLabelValue.value = ''
    showLabelValueDropdown.value = false
    return
  }
  list.push({ label: labelName, value: val })
  // 单条 groupBy 联动（保持原有分组统计能力）
  selectedGroupLabel.value = labelName
  selectedGroupValue.value = val
  if (groupBy.value !== labelName) groupBy.value = labelName
  // 关下拉 + 清值输入，让用户能继续加下一条（保留标签名，方便同 label 多值连加）
  showLabelNameDropdown.value = false
  showLabelValueDropdown.value = false
  labelValueQuery.value = ''
  selectedLabelValue.value = ''
  if (!opts.skipRefresh) refreshActiveData()
}

function removeActiveLabel(idx) {
  activeLabelFilters.value.splice(idx, 1)
  if (activeLabelFilters.value.length) {
    const last = activeLabelFilters.value[activeLabelFilters.value.length - 1]
    selectedGroupLabel.value = last.label
    selectedGroupValue.value = last.value
  } else {
    selectedGroupLabel.value = ''
    selectedGroupValue.value = ''
  }
  refreshActiveData()
}

function clearAllActiveLabels() {
  activeLabelFilters.value = []
  selectedGroupLabel.value = ''
  selectedGroupValue.value = ''
  refreshActiveData()
}

function clearLabelFilter() {
  clearAllActiveLabels()
}

function onGroupByChange() {
  selectedGroupLabel.value = ''
  selectedGroupValue.value = ''
  selectedLabelName.value = groupBy.value || selectedLabelName.value
  selectedLabelValue.value = ''
  if (selectedLabelName.value) ensureLabelValues(selectedLabelName.value)
  if (activeTab.value === 'logs') {
    loadLogs()
  } else if (activeTab.value === 'templates') {
    loadTemplates()
  }
}

async function loadLogs() {
  const requestId = ++logsRequestId
  logsAbort?.abort()
  loadMoreAbort?.abort()
  const controller = new AbortController()
  logsAbort = controller
  loadingLogs.value = true
  logs.value = []
  hasMore.value = false
  nextCursorNs.value = null
  totalLoaded.value = 0
  try {
    const r = await api.getLogs({
      level:    levelFilter.value || undefined,
      limit:    200,
      ...multiFilterParams(),
      ...currentGroupParams(),
      ...timeParams(),
    }, { signal: controller.signal })
    if (requestId !== logsRequestId) return
    logs.value = r.data
    hasMore.value      = r.has_more ?? false
    nextCursorNs.value = r.next_cursor_ns ?? null
    totalLoaded.value  = r.data?.length ?? 0
    await ensureLogViewportFilled()
  } catch (error) {
    if (!isCanceled(error)) {
      logs.value = []
      hasMore.value = false
      nextCursorNs.value = null
      totalLoaded.value = 0
    }
  } finally {
    if (requestId === logsRequestId) {
      loadingLogs.value = false
    }
    if (logsAbort === controller) {
      logsAbort = null
    }
  }
}

async function loadMore() {
  if (!hasMore.value || !nextCursorNs.value || loadingMore.value) return
  const requestId = ++loadMoreRequestId
  const baseLogsRequestId = logsRequestId
  loadMoreAbort?.abort()
  const controller = new AbortController()
  loadMoreAbort = controller
  loadingMore.value = true
  try {
    const r = await api.getLogs({
      level:      levelFilter.value || undefined,
      limit:      200,
      cursor_ns:  nextCursorNs.value,
      ...multiFilterParams(),
      ...currentGroupParams(),
      ...timeParams(),
    }, { signal: controller.signal })
    if (requestId !== loadMoreRequestId || baseLogsRequestId !== logsRequestId) return
    logs.value = [...logs.value, ...(r.data || [])]
    hasMore.value      = r.has_more ?? false
    nextCursorNs.value = r.next_cursor_ns ?? null
    totalLoaded.value  = logs.value.length
    await ensureLogViewportFilled()
  } catch (error) {
    if (!isCanceled(error)) {
      hasMore.value = false
    }
  } finally {
    if (requestId === loadMoreRequestId) {
      loadingMore.value = false
    }
    if (loadMoreAbort === controller) {
      loadMoreAbort = null
    }
  }
}

async function loadTemplates() {
  const requestId = ++templatesRequestId
  templatesAbort?.abort()
  const controller = new AbortController()
  templatesAbort = controller
  loadingTemplates.value = true
  templates.value = []
  tplError.value = ''
  try {
    const r = await api.getTemplates({
      limit:    10000,
      top_n:    100,
      level:    tplLevelFilter.value || undefined,
      ...multiFilterParams(),
      ...currentGroupParams(),
      ...timeParams(),
    }, { signal: controller.signal })
    if (requestId !== templatesRequestId) return
    templates.value = r.data
    templateMeta.value = { total_logs: r.total_logs, total_templates: r.total_templates }
  } catch (error) {
    if (isCanceled(error)) return
    tplError.value = typeof error === 'string' ? error : (error?.message || '聚类请求失败，请检查后端连接')
  } finally {
    if (requestId === templatesRequestId) {
      loadingTemplates.value = false
    }
    if (templatesAbort === controller) {
      templatesAbort = null
    }
  }
}

function onParamChange() {
  if (activeTab.value === 'logs')      loadLogs()
  else                                 loadTemplates()
}

function onTimeModeChange() {
  if (timeMode.value === 'relative') {
    customStart.value = ''
    customEnd.value   = ''
    onParamChange()
  } else {
    const r = todayRange()
    if (!customStart.value) customStart.value = r.start
    if (!customEnd.value)   customEnd.value   = r.end
  }
}

function onCustomTimeChange() {
  if (customStart.value && customEnd.value) onParamChange()
}

function onKeywordInput() {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(onParamChange, 500)
}

function clearKeyword() {
  keyword.value = ''
  onParamChange()
}

function traceTimeParams() {
  if (traceTimeMode.value === 'custom' && traceStart.value && traceEnd.value) {
    if (traceEnd.value < traceStart.value) {
      alert('结束时间不能早于开始时间')
      throw new Error('invalid time range')
    }
    // 本地时间 → UTC，避免服务端按 UTC 错误解析
    return { start_time: toUtcStr(traceStart.value), end_time: toUtcStr(traceEnd.value) }
  }
  return { hours: traceHours.value }
}

async function runTrace() {
  if (!traceValue.value) return

  // 验证自定义时间范围
  if (traceTimeMode.value === 'custom' && (!traceStart.value || !traceEnd.value)) {
    alert('请填写完整的开始时间和结束时间')
    return
  }

  tracingKeyword.value = true
  loadingTraceLogs.value = false
  traceResult.value = null
  traceLogs.value = []
  traceResultTab.value = 'overview'
  expandedSpans.value = new Set()

  let tp
  try { tp = traceTimeParams() } catch { tracingKeyword.value = false; return }

  // ── 第一步：计算首末耗时 ──────────────────
  let traceData = null
  try {
    traceData = await api.traceKeyword({
      keyword: traceValue.value,
      service: selectedService.value || undefined,
      ...currentGroupParams(),
      ...tp,
    })
    traceResult.value = traceData
  } catch (e) {
    traceResult.value = { found: false, keyword: traceValue.value, log_count: 0, _error: String(e) }
    tracingKeyword.value = false
    return
  }
  tracingKeyword.value = false   // 耗时计算完成，立即解除主加载状态

  // ── 第二步：加载匹配日志列表（独立加载，不影响结果展示）──
  if (traceData.found) {
    traceLogsAbort?.abort()
    const controller = new AbortController()
    traceLogsAbort = controller
    loadingTraceLogs.value = true
    try {
      const logsR = await api.getLogs({
        keyword: traceValue.value,
        service: selectedService.value || undefined,
        limit: 2000,
        ...currentGroupParams(),
        ...tp,
      }, { signal: controller.signal })
      traceLogs.value = [...(logsR.data || [])].reverse()  // 升序展示
    } catch (error) {
      if (isCanceled(error)) return
      traceLogs.value = []  // 日志列表加载失败不影响耗时结果
    } finally {
      loadingTraceLogs.value = false
      if (traceLogsAbort === controller) {
        traceLogsAbort = null
      }
    }
  }
}

function switchTraceToCustom() {
  traceTimeMode.value = 'custom'
  const r = todayRange()
  if (!traceStart.value) traceStart.value = r.start
  if (!traceEnd.value)   traceEnd.value   = r.end
}

function toggleSpan(i) {
  const s = new Set(expandedSpans.value)
  s.has(i) ? s.delete(i) : s.add(i)
  expandedSpans.value = s
}

function spanElapsed(log) {
  const firstNs = traceResult.value?.first_ts_ns
  if (!firstNs) return ''
  const ms = (parseInt(log.timestamp_ns) - firstNs) / 1_000_000
  if (ms <= 0) return '+0'
  if (ms < 1)       return `+${(ms * 1000).toFixed(0)} µs`
  if (ms < 1000)    return `+${ms.toFixed(1)} ms`
  if (ms < 60000)   return `+${(ms / 1000).toFixed(3)} s`
  return `+${Math.floor(ms / 60000)}m ${((ms % 60000) / 1000).toFixed(1)}s`
}

function spanBarW(log) {
  const firstNs = traceResult.value?.first_ts_ns
  const totalMs = traceResult.value?.duration_ms
  if (!firstNs || !totalMs) return 0
  const ms = (parseInt(log.timestamp_ns) - firstNs) / 1_000_000
  return Math.min(100, Math.max(0, (ms / totalMs) * 100))
}

function startTplAIAnalysis() {
  if (analyzingTplAI.value) return
  tplAiContent.value = ''
  analyzingTplAI.value = true
  const params = new URLSearchParams({
    ...multiFilterParams(),
    ...(tplLevelFilter.value ? { level: tplLevelFilter.value } : {}),
    ...currentGroupParams(),
  })
  if (timeMode.value === 'custom' && customStart.value && customEnd.value) {
    params.set('start_time', toUtcStr(customStart.value))
    params.set('end_time',   toUtcStr(customEnd.value))
  } else {
    params.set('hours', hours.value)
  }
  streamSSE(
    `/api/analyze/templates/stream?${params}`,
    chunk => { try { tplAiContent.value += JSON.parse(chunk) } catch { tplAiContent.value += chunk } },
    () => { analyzingTplAI.value = false },
    () => { analyzingTplAI.value = false },
  )
}

function switchTab(tab) {
  activeTab.value = tab
  if (tab === 'templates' && !templates.value.length) loadTemplates()
  // trace tab 不自动加载，等用户输入后手动触发
}

function startAIAnalysis() {
  aiContent.value = ''
  analyzingAI.value = true
  const params = new URLSearchParams({
    ...timeParams(),
    ...multiFilterParams(),
    ...(levelFilter.value ? { level: levelFilter.value } : {}),
    ...currentGroupParams(),
  })
  streamSSE(
    `/api/analyze/stream?${params}`,
    (chunk) => { try { aiContent.value += JSON.parse(chunk) } catch { aiContent.value += chunk } },
    () => { analyzingAI.value = false },
    () => { analyzingAI.value = false },
  )
}

// 钻取入口：从 URL ?service=&level=&hours=&q= 预填查询条件（指标→日志）
function _applyRouteQuery() {
  const q = (typeof window !== 'undefined' && window.location.hash.includes('?'))
    ? Object.fromEntries(new URLSearchParams(window.location.hash.split('?')[1]))
    : {}
  if (q.service) selectedService.value = q.service
  if (q.level)   levelFilter.value = q.level
  if (q.hours)   hours.value = String(q.hours)
  if (q.q)       keyword.value = q.q
}

onMounted(async () => {
  _applyRouteQuery()
  // 已有 URL ?service=xxx 兼容进 chip
  if (selectedService.value && !selectedServices.value.length) {
    selectedServices.value.push(selectedService.value)
  }
  await loadLabelCatalog()
  // 预取服务名（供 chip datalist 提示）
  try {
    const r = await api.getServices({})
    const data = r?.data ?? r
    if (Array.isArray(data)) {
      allServicesList.value = data.map(s => typeof s === 'string' ? s : (s.name || s.service || '')).filter(Boolean)
    }
  } catch {}
  loadLogs()
})

onBeforeUnmount(() => {
  clearTimeout(searchTimer)
  logsAbort?.abort()
  loadMoreAbort?.abort()
  templatesAbort?.abort()
  traceLogsAbort?.abort()
  detailContextAbort?.abort()
})
</script>

<style scoped>
.log-layout { display: flex; height: 100%; overflow: hidden; }

/* 左侧服务面板 */
.service-panel {
  width: 340px; min-width: 320px;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; overflow: hidden;
}
.panel-header { padding: 12px 12px 10px; border-bottom: 1px solid var(--border); }
.panel-title {
  display: block; font-size: 12px; font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.time-select {
  width: 100%; background: var(--bg-hover);
  border: 1px solid var(--border); color: var(--text-primary);
  padding: 5px 8px; border-radius: 5px; font-size: 12px; cursor: pointer;
}
/* 时间模式切换 */
.time-mode-tabs {
  display: flex; margin-bottom: 6px;
  background: var(--bg-base); border-radius: 5px; padding: 2px;
}
.tmode-btn {
  flex: 1; padding: 3px 0; font-size: 11px; border: none;
  background: transparent; color: var(--text-muted);
  border-radius: 4px; cursor: pointer; transition: all .12s;
}
.tmode-btn.active { background: var(--bg-active); color: var(--text-primary); }

/* 自定义时间输入 */
.custom-time-wrap {
  display: flex; flex-direction: column; gap: 4px; margin-top: 2px;
}
.dt-input {
  width: 100%; background: var(--bg-hover);
  border: 1px solid var(--border); color: var(--text-primary);
  padding: 4px 6px; border-radius: 5px; font-size: 11px;
}
.dt-sep {
  text-align: center; font-size: 10px; color: var(--text-muted); line-height: 1;
}
.panel-subsection { margin-top: 10px; }
.panel-subtitle {
  display: block;
  margin-bottom: 6px;
  font-size: 11px;
  color: var(--text-muted);
}

.label-explorer {
  background: var(--bg-card);
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.label-explorer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 8px;
  cursor: pointer;
}
.label-explorer-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}
.label-explorer-toggle {
  font-size: 11px;
  color: var(--text-muted);
}
.label-explorer-body {
  padding: 0 12px 12px;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.label-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.label-chip {
  border: 1px solid var(--border);
  background: var(--bg-base);
  color: var(--text-secondary);
  border-radius: 9999px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
  max-width: 100%;
}
.label-chip:hover {
  border-color: var(--border-accent);
  color: var(--text-primary);
}
.label-chip.active {
  background: var(--accent-dim);
  border-color: var(--border-accent);
  color: var(--accent);
}
.label-chip.groupable::after {
  content: ' *';
  opacity: .7;
}
.active-label-filter {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  padding: 6px 8px;
  border: 1px solid rgba(99,102,241,.35);
  border-radius: 8px;
  background: rgba(99,102,241,.1);
  color: var(--text-secondary);
  font-size: 11px;
}
.active-label-filter em {
  color: var(--accent-hover);
  font-style: normal;
  word-break: break-all;
}
.active-label-filter button {
  flex-shrink: 0;
  border: none;
  background: transparent;
  color: var(--accent);
  cursor: pointer;
  font-size: 11px;
}
.label-dropdown-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.label-select-field {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 11px;
  color: var(--text-muted);
}
.label-select-field select {
  width: 100%;
  min-width: 0;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-base);
  color: var(--text-primary);
  padding: 7px 8px;
  font-size: 12px;
}
.label-dropdown-apply {
  border: 1px solid var(--border-accent);
  border-radius: 7px;
  background: var(--accent-dim);
  color: var(--accent);
  padding: 7px 8px;
  cursor: pointer;
  font-size: 12px;
}
.label-dropdown-apply:disabled {
  opacity: .5;
  cursor: not-allowed;
}

/* 可搜索下拉 combobox */
.combo {
  position: relative;
  display: flex;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: 7px;
  background: var(--bg-base);
  transition: border-color .12s, box-shadow .12s;
}
.combo.open { border-color: var(--accent, #818cf8); box-shadow: 0 0 0 2px rgba(129,140,248,.15); }
.combo.disabled { opacity: .5; pointer-events: none; }
.combo-input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  padding: 7px 8px;
  font-size: 12px;
  outline: none;
}
.combo-input::placeholder { color: var(--text-muted); }
.combo-clear, .combo-caret {
  padding: 0 6px;
  font-size: 11px;
  color: var(--text-muted);
  cursor: pointer;
  user-select: none;
  transition: color .12s;
}
.combo-clear:hover, .combo-caret:hover { color: var(--text-primary); }
.combo-caret { padding-right: 8px; font-size: 10px; }
.combo-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0; right: 0;
  z-index: 20;
  max-height: 260px;
  overflow-y: auto;
  background: var(--bg-card, #1a1a1a);
  border: 1px solid var(--border);
  border-radius: 7px;
  box-shadow: 0 4px 16px rgba(0,0,0,.28);
  padding: 4px;
}
.combo-item {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 5px;
  font-size: 12px;
  color: var(--text-primary);
  cursor: pointer;
  transition: background .1s;
}
.combo-item:hover { background: var(--bg-hover, rgba(255,255,255,.06)); }
.combo-item.active {
  background: rgba(129,140,248,.14);
  color: var(--accent, #818cf8);
}
.combo-item-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.combo-item-text mark {
  background: transparent;
  color: inherit;
  padding: 0;
}
.combo-item-text mark.hl {
  background: rgba(129,140,248,.28);
  color: #fff;
  font-weight: 600;
  border-radius: 2px;
  padding: 0 1px;
}
.combo-item-meta {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--text-muted);
  opacity: .8;
}
.combo-empty {
  position: absolute;
  top: calc(100% + 4px);
  left: 0; right: 0;
  z-index: 20;
  padding: 12px 10px;
  background: var(--bg-card, #1a1a1a);
  border: 1px solid var(--border);
  border-radius: 7px;
  font-size: 11px;
  color: var(--text-muted);
  text-align: center;
}

/* 多标签条件 chip 列表（已加的过滤条件） */
.active-label-chips {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 6px;
  margin-bottom: 6px;
  background: var(--bg-hover, rgba(255,255,255,.03));
  border: 1px dashed var(--border);
  border-radius: 7px;
}
.active-label-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 7px;
  border-radius: 999px;
  background: rgba(129,140,248,.14);
  border: 1px solid rgba(129,140,248,.36);
  color: var(--accent, #818cf8);
  font-size: 11px;
  font-family: 'Cascadia Code','Consolas',monospace;
  line-height: 1.4;
}
.active-label-chip .chip-key { font-weight: 600; }
.active-label-chip .chip-eq  { opacity: .6; }
.active-label-chip .chip-val { color: var(--text-primary); }
.active-label-chip .chip-remove {
  margin-left: 3px;
  padding: 0 3px;
  font-size: 10px;
  opacity: .55;
  cursor: pointer;
}
.active-label-chip .chip-remove:hover { opacity: 1; }
.active-label-clear {
  background: transparent;
  border: 0;
  color: var(--text-muted);
  font-size: 11px;
  cursor: pointer;
  margin-left: auto;
}
.active-label-clear:hover { color: var(--error, #f85149); }
.label-group-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
}
.label-group-card {
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-base);
  overflow: hidden;
}
.label-group-card.active {
  border-color: rgba(99,102,241,.45);
}
.label-group-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  padding: 7px 8px;
  cursor: pointer;
  text-align: left;
}
.label-group-header:hover {
  background: var(--bg-hover);
}
.label-group-main {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.label-group-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono, 'Consolas', monospace);
  font-size: 11.5px;
  color: var(--text-primary);
}
.label-group-role {
  flex-shrink: 0;
  border-radius: 9999px;
  background: var(--bg-hover);
  color: var(--text-muted);
  padding: 1px 6px;
  font-size: 10px;
}
.label-group-card.groupable .label-group-role {
  color: var(--accent);
  background: rgba(99,102,241,.13);
}
.label-group-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-muted);
  font-size: 11px;
}
.label-total {
  min-width: 18px;
  text-align: right;
}
.label-values-card {
  padding: 0 8px 8px;
  background: transparent;
  border: 0;
}
.label-values-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.label-values-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}
.label-values-meta {
  font-size: 11px;
  color: var(--text-muted);
}
.label-values-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.label-value-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  border: 1px solid var(--border);
  padding: 3px 8px;
  border-radius: 9999px;
  background: var(--bg-hover);
  color: var(--text-secondary);
  font-size: 11px;
  word-break: break-all;
  cursor: pointer;
}
.label-value-chip:hover,
.label-value-chip.active {
  border-color: var(--border-accent);
  color: var(--accent);
  background: var(--accent-dim);
}
.label-empty {
  font-size: 11px;
  color: var(--text-muted);
  padding: 4px 0;
}
.label-loading {
  padding: 8px 0;
}

/* 关键字搜索框 */
.keyword-wrap {
  display: flex; align-items: center;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 6px; padding: 0 8px; gap: 5px;
  min-width: 160px; max-width: 240px;
}
.kw-icon { font-size: 12px; flex-shrink: 0; }
.kw-input {
  flex: 1; background: transparent; border: none;
  color: var(--text-primary); font-size: 12px;
  padding: 5px 0; outline: none;
}
.kw-input::placeholder { color: var(--text-muted); }
.kw-clear {
  background: none; border: none; color: var(--text-muted);
  font-size: 11px; cursor: pointer; padding: 2px;
  line-height: 1; flex-shrink: 0;
}
.kw-clear:hover { color: var(--text-primary); }

/* 二次本地过滤框：次要色调，与服务端 keyword 视觉区分 */
.keyword-wrap.secondary {
  border-color: rgba(99,102,241,.35);
  background: rgba(99,102,241,.06);
  min-width: 150px; max-width: 200px;
}
.keyword-wrap.secondary .kw-icon { color: var(--accent, #818cf8); }

/* 多条件本地过滤 */
.multi-filter-wrap {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px;
  padding: 3px 6px;
  border: 1px solid rgba(99,102,241,.35);
  background: rgba(99,102,241,.06);
  border-radius: 6px;
  min-width: 220px;
  max-width: 460px;
}
.multi-filter-wrap .kw-icon { color: var(--accent, #818cf8); flex-shrink: 0; margin-right: 2px; }
.multi-filter-wrap .multi-input {
  flex: 1;
  min-width: 90px;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 12px;
  padding: 4px 0;
  outline: none;
}
.multi-filter-wrap .multi-input::placeholder { color: var(--text-muted); }

.filter-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-family: monospace;
  cursor: pointer;
  border: 1px solid transparent;
  white-space: nowrap;
  user-select: none;
  transition: background .12s, border-color .12s;
}
.filter-chip.include {
  background: rgba(63,185,80,.15);
  border-color: rgba(63,185,80,.35);
  color: #3fb950;
}
.filter-chip.exclude {
  background: rgba(248,81,73,.15);
  border-color: rgba(248,81,73,.35);
  color: var(--error, #f85149);
  text-decoration: line-through;
}
.filter-chip:hover { filter: brightness(1.15); }
.chip-prefix { font-weight: 700; opacity: .8; }
.chip-text { font-weight: 500; }
.chip-remove {
  margin-left: 2px;
  padding: 0 2px;
  font-size: 10px;
  opacity: .6;
  cursor: pointer;
}
.chip-remove:hover { opacity: 1; }

/* 服务多选 chip 蓝色系，与关键字 chip 区分 */
.multi-filter-wrap.svc-multi .kw-icon { color: #38bdf8; }
.filter-chip.svc-chip {
  background: rgba(56,189,248,.14);
  border: 1px solid rgba(56,189,248,.36);
  color: #38bdf8;
}
.filter-chip.svc-chip .chip-prefix { color: #38bdf8; }

/* AND / OR 切换 pill */
.kw-mode-switch {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 4px;
  overflow: hidden;
  margin-right: 4px;
  flex-shrink: 0;
}
.kw-mode-btn {
  background: transparent;
  color: var(--text-muted);
  border: 0;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: background .12s, color .12s;
}
.kw-mode-btn:hover { color: var(--text-primary); }
.kw-mode-btn.active {
  background: var(--accent, #818cf8);
  color: #fff;
}

.svc-ns-arrow { font-size: 8px; transition: transform .2s; display: inline-block; }
.svc-ns-arrow.open { transform: rotate(90deg); }
.loading-row { display: flex; justify-content: center; padding: 12px; }

/* 右侧 */
.log-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* 工具栏 */
.log-toolbar {
  padding: 8px 14px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center;
  justify-content: space-between; gap: 12px;
  flex-shrink: 0;
}
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }

/* Tab */
.tab-group { display: flex; gap: 2px; background: var(--bg-base); padding: 3px; border-radius: 8px; }
.tab-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 14px; border-radius: 6px;
  border: none; background: transparent;
  color: var(--text-muted); font-size: 13px;
  cursor: pointer; transition: all .15s;
}
.tab-btn:hover  { color: var(--text-primary); }
.tab-btn.active { background: var(--bg-active); color: var(--text-primary); }
.tab-count {
  background: var(--bg-hover);
  color: var(--text-muted);
  font-size: 11px; padding: 0 6px;
  border-radius: 9999px; font-weight: 600;
}
.tab-btn.active .tab-count { background: var(--accent-dim); color: var(--accent); }
.meta-info { font-size: 12px; color: var(--text-muted); }

/* AI 面板 */
.ai-panel {
  margin: 10px 14px; padding: 14px 16px;
  background: rgba(99,102,241,.07);
  border: 1px solid rgba(99,102,241,.25);
  border-radius: var(--radius);
  flex-shrink: 0;
}
.ai-panel-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px; font-size: 13px; font-weight: 600;
  color: var(--accent-hover);
}
.btn-xs { padding: 2px 8px; font-size: 11px; }
.ai-content {
  font-size: 13px; line-height: 1.8; color: var(--text-secondary);
  max-height: 200px; overflow-y: auto; white-space: pre-wrap; word-break: break-word;
}
.ai-typing { display: flex; gap: 4px; margin-top: 8px; }
.ai-typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: pulse 1.2s ease-in-out infinite; }
.dot2 { animation-delay: .2s !important; }
.dot3 { animation-delay: .4s !important; }

/* 日志列表容器 */
.log-container { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

/* 统计栏 */
.log-stats-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 6px 16px; font-size: 12px; color: var(--text-muted);
  background: var(--bg-base); border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.log-stat-sep { opacity: .4; }
.log-stat-filtered { color: var(--accent); margin-left: 3px; }
.log-stat-item { display: flex; align-items: center; gap: 4px; }
.lvl-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
}
.lvl-error { background: #f87171; }
.lvl-warn  { background: #fb923c; }
.lvl-info  { background: #60a5fa; }
.lvl-debug { background: #6b7280; }
.lvl-other { background: #6b7280; }

/* 表格区 */
.log-table-wrap {
  flex: 1; overflow-y: auto;
  font-family: 'Consolas', 'Cascadia Code', 'Consolas', monospace; font-size: 12px;
}
.log-table {
  width: 100%; border-collapse: collapse; table-layout: fixed;
}
.log-table thead {
  position: sticky; top: 0; z-index: 1;
  background: var(--bg-card);
}
.log-table th {
  padding: 7px 12px; text-align: left;
  font-size: 11px; font-weight: 600; letter-spacing: .04em;
  color: var(--text-muted); border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.log-row {
  cursor: pointer; transition: background .1s;
  border-bottom: 1px solid rgba(46,49,80,.35);
}
.log-row:hover    { background: var(--bg-hover); }
.log-row.row-error { background: var(--log-error); }
.log-row.row-warn  { background: var(--log-warn); }
.log-row td { padding: 5px 12px; vertical-align: top; }
.col-ts  { color: var(--text-muted); white-space: nowrap; font-size: 11px; }
.col-svc { color: var(--accent-hover); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.col-group { color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.col-msg { color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.row-error .col-msg { color: #fca5a5; }
.row-warn  .col-msg { color: #fcd34d; }
.log-row.selected,
.log-row.selected:hover {
  background: rgba(250,204,21,.18);
}
.log-row.selected td {
  background: rgba(250,204,21,.16);
  border-top: 1px solid rgba(250,204,21,.75);
  border-bottom: 1px solid rgba(250,204,21,.75);
}
.log-row.selected td:first-child {
  box-shadow: inset 4px 0 0 #facc15;
}
.log-row.selected .col-ts,
.log-row.selected .col-svc,
.log-row.selected .col-group {
  color: #fde68a;
}
.log-row.selected .col-msg {
  color: #fff7ed;
  font-weight: 600;
}

/* 级别徽章 */
.lvl-badge {
  display: inline-block; padding: 1px 7px; border-radius: 4px;
  font-size: 10px; font-weight: 700; letter-spacing: .04em;
  white-space: nowrap;
}
.lvl-badge-error { background: rgba(248,113,113,.15); color: #f87171; border: 1px solid rgba(248,113,113,.3); }
.lvl-badge-warn  { background: rgba(251,146,60,.15);  color: #fb923c; border: 1px solid rgba(251,146,60,.3); }
.lvl-badge-info  { background: rgba(96,165,250,.15);  color: #60a5fa; border: 1px solid rgba(96,165,250,.3); }
.lvl-badge-debug { background: rgba(107,114,128,.15); color: #9ca3af; border: 1px solid rgba(107,114,128,.3); }
.lvl-badge-other { background: rgba(107,114,128,.12); color: #9ca3af; border: 1px solid rgba(107,114,128,.2); }

/* 仅事件按钮 */
.btn-incident-active {
  background: rgba(251,191,36,.15);
  border: 1px solid rgba(251,191,36,.5);
  color: #fbbf24;
  padding: 5px 12px; border-radius: 6px; font-size: 12px;
  cursor: pointer; display: inline-flex; align-items: center; gap: 5px;
}

/* 加载更多 */
.load-more-bar {
  display: flex; justify-content: center;
  padding: 10px 14px; border-top: 1px solid var(--border);
  background: var(--bg-card);
}
.load-more-bar.ready {
  background: linear-gradient(180deg, rgba(99,102,241,.04), transparent);
}
.load-more-status {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 12px; color: var(--text-muted);
}

/* 日志详情居中模态框 */
.log-detail-modal-mask {
  position: fixed; inset: 0; z-index: 300;
  background: rgba(0,0,0,.55); backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center;
  padding: 32px;
  outline: none;
}
.drawer-panel.log-detail-modal {
  width: min(880px, 96vw); max-height: 92vh; height: auto;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  display: flex; flex-direction: column;
  box-shadow: 0 24px 80px rgba(0,0,0,.55);
  overflow: hidden;
}
.drawer-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 14px 18px; border-bottom: 1px solid var(--border);
  font-size: 14px; font-weight: 600; color: var(--text-primary);
  flex-shrink: 0;
}
.drawer-close {
  background: none; border: none; color: var(--text-muted);
  font-size: 14px; cursor: pointer; padding: 4px;
}
.drawer-close:hover { color: var(--text-primary); }
.drawer-body { flex: 1; overflow-y: auto; padding: 14px 18px; display: flex; flex-direction: column; gap: 10px; }

/* 元数据折叠区 */
.drawer-meta-section {
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-base);
  overflow: hidden;
  flex-shrink: 0;
}
.drawer-meta-header {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  font-size: 12px;
  transition: background .15s;
}
.drawer-meta-header:hover { background: var(--bg-hover); }
.drawer-meta-section.open .drawer-meta-header {
  border-bottom: 1px solid var(--border);
}
.meta-toggle {
  display: inline-block;
  width: 10px;
  font-size: 9px;
  color: var(--text-muted);
}
.meta-title { font-weight: 600; color: var(--text-secondary); }
.meta-summary {
  flex: 1; min-width: 0;
  display: flex; align-items: center; gap: 8px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  font-size: 11px;
}
.meta-summary-ts { color: var(--text-muted); font-family: monospace; }
.meta-summary-svc { color: var(--accent); font-weight: 500; }
.meta-summary-ns  { color: var(--text-muted); }
.lvl-badge.mini { font-size: 9px; padding: 0 5px; line-height: 1.4; }
.drawer-meta-body {
  padding: 12px 14px;
  display: flex; flex-direction: column; gap: 12px;
  background: var(--bg-card);
}
.drawer-row { display: flex; align-items: flex-start; gap: 12px; }
.drawer-row-full { flex-direction: column; gap: 6px; }
.drawer-label {
  width: 44px; flex-shrink: 0; font-size: 11px; font-weight: 600;
  color: var(--text-muted); padding-top: 2px; text-align: right;
}
.drawer-val { font-size: 13px; color: var(--text-primary); word-break: break-all; }
.drawer-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.drawer-tag {
  font-size: 11px; padding: 2px 8px;
  background: var(--bg-base); border: 1px solid var(--border);
  border-radius: 9999px; color: var(--text-muted);
}
.drawer-tag em { color: var(--accent-hover); font-style: normal; }
.drawer-content {
  margin: 0; padding: 12px 14px;
  background: var(--bg-base); border: 1px solid var(--border);
  border-radius: 6px; font-size: 12px; font-family: 'Consolas', monospace;
  color: var(--text-secondary); line-height: 1.7;
  word-break: break-all; white-space: pre-wrap;
  max-height: 60vh; overflow-y: auto;
}

/* 抽屉动画 */
.drawer-section-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin-bottom: 8px;
}
.drawer-section-title {
  font-size: 12px; font-weight: 600; color: var(--text-primary);
  display: inline-flex; align-items: center; gap: 6px;
}
/* 标题旁的小内联 spinner：弱化加载感知 */
.spinner.mini-inline {
  width: 10px;
  height: 10px;
  border-width: 1.5px;
  border-color: var(--text-muted);
  border-top-color: transparent;
  opacity: .65;
  vertical-align: middle;
}
.drawer-section-actions {
  display: flex; align-items: center; gap: 8px;
}
.drawer-section-meta {
  font-size: 11px; color: var(--text-muted);
}
.drawer-context-state {
  display: flex; align-items: center; gap: 8px;
  min-height: 42px; padding: 0 2px;
  font-size: 12px; color: var(--text-muted);
}
.drawer-context-state-error { color: var(--error); }
.drawer-context-list {
  display: flex; flex-direction: column; gap: 6px;
  max-height: 76vh; overflow-y: auto;
  padding: 4px 4px 4px 28px;   /* 左侧 28px 给锚点 ▶ 标记预留 */
}
.drawer-context-loading-more {
  display: flex; align-items: center; justify-content: center;
  gap: 8px; padding: 8px;
  font-size: 11px; color: var(--text-muted);
  background: var(--bg-base);
  border: 1px dashed var(--border);
  border-radius: 6px;
}
.drawer-context-item {
  width: 100%; display: grid;
  grid-template-columns: 138px 120px minmax(0, 1fr);
  gap: 10px; align-items: start;
  padding: 10px 12px;
  background: var(--bg-base); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text-secondary);
  font-family: 'Consolas', monospace; font-size: 12px; line-height: 1.6;
  text-align: left; cursor: default;
  position: relative;
}
.drawer-context-item.level-error { background: var(--log-error); }
.drawer-context-item.level-warn  { background: var(--log-warn); }

/* 锚点行（开始查看的日志）— 实色高反差 */
.drawer-context-item.active {
  background: #facc15;            /* 实色亮黄 */
  border-color: #facc15;
  color: #1f2937;                  /* 深字 */
  font-weight: 600;
  box-shadow:
    inset 5px 0 0 0 #ea580c,       /* 左侧橙色实色条 */
    0 0 0 2px #facc15,
    0 8px 22px rgba(250,204,21,.45);
  z-index: 2;
}
.drawer-context-item.active .drawer-context-ts,
.drawer-context-item.active .drawer-context-svc,
.drawer-context-item.active .drawer-context-text {
  color: #1f2937;
}
/* 锚点是 error/warn 时：用红色实色加重，因为问题日志更要突出 */
.drawer-context-item.active.level-error,
.drawer-context-item.active.level-warn {
  background: #f85149;
  border-color: #f85149;
  color: #fff;
  box-shadow:
    inset 5px 0 0 0 #7f1d1d,
    0 0 0 2px #f85149,
    0 8px 22px rgba(248,81,73,.5);
}
.drawer-context-item.active.level-error .drawer-context-ts,
.drawer-context-item.active.level-warn  .drawer-context-ts,
.drawer-context-item.active.level-error .drawer-context-svc,
.drawer-context-item.active.level-warn  .drawer-context-svc,
.drawer-context-item.active.level-error .drawer-context-text,
.drawer-context-item.active.level-warn  .drawer-context-text {
  color: #fff;
}

.anchor-marker {
  position: absolute;
  left: -22px;
  top: 50%;
  transform: translateY(-50%);
  color: #ea580c;
  font-size: 14px;
  font-weight: 900;
  pointer-events: none;
  animation: anchor-pulse 1.2s ease-in-out infinite;
}
.drawer-context-item.active.level-error .anchor-marker,
.drawer-context-item.active.level-warn  .anchor-marker { color: #f85149; }
@keyframes anchor-pulse {
  0%, 100% { opacity: 1; transform: translateY(-50%) translateX(0); }
  50%      { opacity: .55; transform: translateY(-50%) translateX(3px); }
}
.drawer-context-ts,
.drawer-context-svc { color: var(--text-muted); white-space: nowrap; }
.drawer-context-svc {
  color: var(--accent-hover); overflow: hidden; text-overflow: ellipsis;
}
.drawer-context-text {
  min-width: 0; word-break: break-all;
}
.drawer-context-hint {
  font-size: 11px; color: var(--text-muted); padding: 0 2px;
}

@media (max-width: 720px) {
  .drawer-context-item {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}

/* 模态淡入 + 卡片轻微上推 */
.modal-fade-enter-active, .modal-fade-leave-active {
  transition: opacity .18s ease, background .18s ease;
}
.modal-fade-enter-from, .modal-fade-leave-to { opacity: 0; background: transparent; }
.modal-fade-enter-active .drawer-panel.log-detail-modal,
.modal-fade-leave-active .drawer-panel.log-detail-modal {
  transition: transform .18s ease, opacity .18s ease;
}
.modal-fade-enter-from .drawer-panel.log-detail-modal,
.modal-fade-leave-to   .drawer-panel.log-detail-modal {
  transform: translateY(12px) scale(.985); opacity: 0;
}

/* ── 模板聚合 ── */
.template-container { flex: 1; overflow-y: auto; padding: 12px 16px; }
.template-list { display: flex; flex-direction: column; gap: 10px; }

.tpl-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  transition: border-color .15s;
}
.tpl-card:hover { border-color: rgba(99,102,241,.4); }

.tpl-header {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 10px;
}
.tpl-rank {
  width: 22px; text-align: center;
  font-size: 12px; font-weight: 700;
  color: var(--text-muted); flex-shrink: 0;
}
.tpl-rank.rank-top { color: var(--warning); }
.tpl-count { flex-shrink: 0; }
.tpl-pct { font-size: 11px; color: var(--text-muted); flex-shrink: 0; width: 44px; }
.tpl-bar-wrap { flex: 1; height: 6px; background: var(--bg-hover); border-radius: 3px; overflow: hidden; }
.tpl-bar { height: 100%; background: linear-gradient(90deg, var(--error), #f97316); border-radius: 3px; transition: width .4s; }

.tpl-pattern {
  font-family: 'Consolas', 'Cascadia Code', 'Consolas', monospace;
  font-size: 13px;
  color: var(--text-primary);
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 8px 12px;
  word-break: break-all;
  line-height: 1.7;
  margin-bottom: 10px;
}
:deep(.wildcard) {
  color: var(--accent-hover);
  background: rgba(99,102,241,.15);
  border-radius: 3px;
  padding: 0 3px;
  font-weight: 600;
}

.tpl-services { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.tpl-label { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }
.svc-chip {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; padding: 2px 8px;
  background: rgba(59,130,246,.1);
  border: 1px solid rgba(59,130,246,.25);
  color: var(--info); border-radius: 9999px;
}
.svc-chip em { font-style: normal; opacity: .7; }

.tpl-example {
  display: flex; align-items: flex-start; gap: 6px;
  font-size: 11px;
}
.tpl-example-text {
  color: var(--text-muted);
  font-family: 'Consolas', monospace;
  overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; flex: 1;
}
.tpl-example-ts { color: var(--text-muted); opacity: .6; margin-right: 6px; }

@keyframes pulse { 0%,80%,100%{opacity:.2} 40%{opacity:1} }

/* ═══════════════════════════════════════
   耗时追踪 Tab
═══════════════════════════════════════ */
.trace-tab {
  flex: 1; display: flex; flex-direction: column;
  overflow: hidden; padding: 10px 16px; gap: 10px;
}

/* 查询工具栏（单行） */
.trace-form-bar {
  display: flex; align-items: center; gap: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 12px;
  flex-shrink: 0;
}
.trace-input-grow { flex: 1; min-width: 0; }
.trace-bar-select { width: 130px; flex-shrink: 0; }
.trace-input-wrap {
  display: flex; align-items: center;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 6px; padding: 0 10px; gap: 6px;
  transition: border-color .15s;
}
.trace-input-wrap:focus-within {
  border-color: rgba(234,179,8,.5);
  box-shadow: 0 0 0 2px rgba(234,179,8,.08);
}
.trace-input-icon { font-size: 13px; flex-shrink: 0; }
.trace-input {
  flex: 1; background: transparent; border: none;
  color: var(--text-primary); font-size: 13px;
  padding: 6px 0; outline: none;
}
.trace-input::placeholder { color: var(--text-muted); }

/* 开始分析按钮 */
.btn-trace-primary {
  background: linear-gradient(135deg, rgba(234,179,8,.2), rgba(234,179,8,.1));
  border: 1px solid rgba(234,179,8,.45);
  color: #fbbf24; padding: 7px 20px;
  border-radius: 6px; font-size: 13px; font-weight: 600;
  cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
  transition: all .15s; white-space: nowrap;
}
.btn-trace-primary:hover:not(:disabled) {
  background: linear-gradient(135deg, rgba(234,179,8,.3), rgba(234,179,8,.18));
  border-color: rgba(234,179,8,.7);
}
.btn-trace-primary:disabled { opacity: .4; cursor: not-allowed; }

/* 结果区域 */
.trace-result {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
  min-height: 0;
}

/* 未找到 */
.trace-not-found {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; padding: 40px;
  color: var(--text-muted); font-size: 13px; gap: 8px;
}
.trace-not-found em { color: var(--text-primary); font-style: normal; font-weight: 500; }

/* ── 子页签切换栏 ── */
.trace-sub-tabs {
  display: flex; gap: 2px;
  background: var(--bg-base);
  border: 1px solid var(--border);
  border-radius: 8px; padding: 3px;
  flex-shrink: 0; margin-bottom: 10px;
  width: fit-content;
}
.trace-sub-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 16px; border-radius: 6px;
  border: none; background: transparent;
  color: var(--text-muted); font-size: 13px;
  cursor: pointer; transition: all .15s;
}
.trace-sub-btn:hover { color: var(--text-primary); }
.trace-sub-btn.active {
  background: var(--bg-active); color: var(--text-primary);
}
.trace-sub-badge {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 20px; height: 18px; padding: 0 5px;
  background: var(--bg-hover); border-radius: 9999px;
  font-size: 11px; color: var(--text-muted); font-weight: 600;
}
.trace-sub-btn.active .trace-sub-badge {
  background: rgba(234,179,8,.15); color: #fbbf24;
}

/* ── 耗时概览页签 ── */
.trace-overview {
  flex: 1; overflow-y: auto;
  display: flex; flex-direction: column; gap: 16px;
}

/* 大数字英雄区 */
.trace-hero {
  background: var(--bg-card);
  border: 1px solid rgba(234,179,8,.3);
  border-radius: var(--radius);
  padding: 28px 32px;
  display: flex; flex-direction: column; gap: 6px;
  align-items: flex-start;
}
.trace-hero-label {
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .6px; color: var(--text-muted);
}
.trace-hero-duration {
  font-size: 56px; font-weight: 700; color: #fbbf24;
  font-variant-numeric: tabular-nums; line-height: 1;
  letter-spacing: -2px;
}
.trace-hero-meta {
  font-size: 13px; color: var(--text-muted); margin-top: 4px;
}
.trace-hero-meta em { color: var(--text-primary); font-style: normal; font-weight: 500; }
.trace-hero-meta strong { color: var(--text-primary); }
.trace-limit-hint { font-size: 11px; color: var(--warning); }

/* 时间线卡片 */
.trace-timeline-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px 24px;
}
.trace-tl-row {
  display: flex; align-items: stretch; gap: 16px;
}
.trace-tl-left {
  display: flex; flex-direction: column; align-items: center;
  width: 20px; flex-shrink: 0;
}
.trace-tl-dot {
  width: 14px; height: 14px; border-radius: 50%;
  flex-shrink: 0;
}
.dot-first { background: #34d399; box-shadow: 0 0 8px rgba(52,211,153,.6); }
.dot-last  { background: #f87171; box-shadow: 0 0 8px rgba(248,113,113,.6); }
.trace-tl-connector {
  flex: 1; width: 2px;
  background: repeating-linear-gradient(
    180deg, rgba(234,179,8,.4) 0 4px, transparent 4px 8px
  );
  margin: 4px 0;
}
.trace-tl-line {
  flex: 1; width: 2px;
  background: repeating-linear-gradient(
    180deg, rgba(234,179,8,.4) 0 4px, transparent 4px 8px
  );
}
.trace-tl-body {
  flex: 1; display: flex; flex-direction: column; gap: 4px;
  padding: 0 0 20px;
}
.dur-row .trace-tl-body { padding: 0; justify-content: center; }
.trace-tl-tag {
  font-size: 10px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .5px; color: var(--text-muted);
}
.trace-tl-ts {
  font-size: 15px; font-weight: 600; color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}
.trace-ep-svc {
  display: inline-block; font-size: 10px; padding: 1px 7px;
  background: rgba(99,102,241,.15); border: 1px solid rgba(99,102,241,.3);
  color: var(--accent-hover); border-radius: 9999px; width: fit-content;
}
.trace-tl-log {
  font-size: 12px; color: var(--text-muted);
  font-family: 'Consolas', monospace;
  word-break: break-all; line-height: 1.5;
}
.trace-tl-dur-badge {
  font-size: 13px; font-weight: 700; color: #fbbf24;
  background: rgba(234,179,8,.1);
  border: 1px solid rgba(234,179,8,.3);
  border-radius: 6px; padding: 3px 12px;
  font-variant-numeric: tabular-nums;
  align-self: flex-start;
}

/* ── 匹配日志页签 ── */
.trace-log-panel {
  flex: 1; display: flex; flex-direction: column; gap: 8px;
  overflow: hidden; min-height: 0;
}
.trace-logs-header {
  display: flex; align-items: center; gap: 10px;
  font-size: 12px; font-weight: 500; color: var(--text-muted);
  flex-shrink: 0;
}
.trace-logs-count {
  font-size: 11px; padding: 1px 7px;
  background: var(--bg-hover); border-radius: 9999px;
  color: var(--text-muted);
}
.trace-log-list {
  flex: 1; overflow-y: auto;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  font-family: 'Consolas', 'Cascadia Code', 'Consolas', monospace;
  font-size: 12px;
}

/* ── 每条耗时列表 ── */
.trace-spans-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  flex-shrink: 0;
}
.trace-spans-header {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 16px;
  font-size: 12px; font-weight: 500; color: var(--text-muted);
  border-bottom: 1px solid var(--border);
  background: var(--bg-base);
}
.trace-span-list {
  max-height: 400px; overflow-y: auto;
  font-family: 'Consolas', 'Cascadia Code', 'Consolas', monospace; font-size: 11px;
}
.trace-span-row {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 5px 14px;
  border-bottom: 1px solid rgba(46,49,80,.35);
  transition: background .1s;
  cursor: pointer;
}
.trace-span-row:hover { background: var(--bg-hover); }
.trace-span-row.level-error { background: var(--log-error); }
.trace-span-row.level-warn  { background: var(--log-warn); }
.trace-span-idx {
  width: 30px; text-align: right; flex-shrink: 0;
  color: var(--text-muted); font-size: 10px;
}
.trace-span-elapsed {
  width: 90px; flex-shrink: 0;
  color: #fbbf24; font-weight: 600; font-size: 11px;
  font-variant-numeric: tabular-nums; text-align: right;
}
.trace-span-bar-wrap {
  width: 80px; flex-shrink: 0;
  height: 4px; background: rgba(255,255,255,.07);
  border-radius: 2px; overflow: hidden;
}
.trace-span-bar {
  height: 100%;
  background: linear-gradient(90deg, #34d399, #fbbf24);
  border-radius: 2px; transition: width .2s;
  min-width: 2px;
}
.trace-span-ts {
  width: 138px; flex-shrink: 0;
  color: var(--text-muted); font-size: 10px;
  white-space: nowrap;
}
.trace-span-line {
  flex: 1; color: var(--text-secondary);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  line-height: 1.5; padding-top: 1px;
}
.trace-span-row.expanded .trace-span-line {
  white-space: pre-wrap; word-break: break-all;
  text-overflow: unset; overflow: visible;
}
.trace-span-idx,
.trace-span-elapsed,
.trace-span-bar-wrap,
.trace-span-ts,
.trace-ep-svc {
  flex-shrink: 0; margin-top: 2px;
}
</style>
