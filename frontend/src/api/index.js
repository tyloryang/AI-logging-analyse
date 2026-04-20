import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 120000 })

http.interceptors.response.use(
  r => r.data,
  e => {
    if (e?.response?.status === 401 && !window.location.hash.includes('/login')) {
      window.location.href = '/#/login'
    }
    return Promise.reject(e?.response?.data?.detail || e.message || '请求失败')
  },
)

export const api = {
  // 服务列表
  getServices:    () => http.get('/services'),
  // 日志
  getLogs:        (params) => http.get('/logs', { params }),
  getErrorLogs:   (params) => http.get('/logs/errors', { params }),
  // 指标
  getErrorMetrics: (hours = 24) => http.get('/metrics/errors', { params: { hours } }),
  // 日志模板聚合
  getTemplates:   (params) => http.get('/logs/templates', { params }),
  // 链路耗时分析
  traceKeyword:   (params) => http.get('/logs/trace', { params }),
  // 报告
  listReports:    () => http.get('/report/list'),
  getReport:      (id) => http.get(`/report/${id}`),
  notifyReport:   (id, channels) => http.post(`/report/${id}/notify`, { channels }),
  // CMDB / 主机
  getHosts:       () => http.get('/hosts'),
  updateHost:     (instance, data) => http.put(`/hosts/${instance}`, data),
  inspectHosts:   () => http.get('/hosts/inspect'),
  inspectHost:    (instance) => http.get(`/hosts/${instance}/inspect`),
  notifyInspectGroups: (data) => http.post('/hosts/inspect/notify-groups', data),
  // SSH 凭证库
  listCredentials:   () => http.get('/ssh/credentials'),
  createCredential:  (data) => http.post('/ssh/credentials', data),
  updateCredential:  (id, data) => http.put(`/ssh/credentials/${id}`, data),
  deleteCredential:  (id) => http.delete(`/ssh/credentials/${id}`),
  // 慢日志分析
  slowlogHosts:   () => http.get('/slowlog/hosts'),
  slowlogFetch:   (data) => http.post('/slowlog/fetch', data),
  // 慢日志报告
  getSlowlogTargets:  () => http.get('/report/slowlog/targets'),
  saveSlowlogTargets: (data) => http.put('/report/slowlog/targets', data),
  // 健康检查
  healthCheck:    () => http.get('/health'),
  // 系统配置（管理员）
  getSettings:    () => http.get('/settings'),
  saveSettings:   (data) => http.put('/settings', data),
  testPrometheus: (data) => http.post('/settings/test/prometheus', data),
  testLoki:       (data) => http.post('/settings/test/loki', data),
  testK8s:        ()     => http.get('/settings/test/k8s'),
  // 认证
  getMe:        () => http.get('/auth/me'),
  login:        (data) => http.post('/auth/login', data),
  logout:       () => http.post('/auth/logout'),
  changePassword: (data) => http.put('/auth/password', data),
  register:     (data) => http.post('/auth/register', data),
  // 管理员
  adminListUsers:   (params) => http.get('/admin/users', { params }),
  adminCreateUser:  (data) => http.post('/admin/users', data),
  adminUpdateUser:  (id, data) => http.put(`/admin/users/${id}`, data),
  adminApproveUser: (id) => http.post(`/admin/users/${id}/approve`),
  adminUnlockUser:  (id) => http.post(`/admin/users/${id}/unlock`),
  adminDisableUser: (id) => http.delete(`/admin/users/${id}`),
  adminGetPermissions: (id) => http.get(`/admin/users/${id}/permissions`),
  adminSetPermissions: (id, data) => http.put(`/admin/users/${id}/permissions`, data),
  adminListModules: () => http.get('/admin/modules'),
  adminAuditLogs:  (params) => http.get('/admin/audit-logs', { params }),
  // SkyWalking APM
  swGetServices:    (params)              => http.get('/sw/services', { params }),
  swGetInstances:   (params)              => http.get('/sw/instances', { params }),
  swGetEndpoints:   (params)             => http.get('/sw/endpoints', { params }),
  swGetTraces:      (params)             => http.get('/sw/traces', { params }),
  swGetTraceDetail: (traceId)            => http.get(`/sw/traces/${traceId}`),
  swGetTopology:    (params)             => http.get('/sw/topology', { params }),
  swGetMetrics:     (params)             => http.get('/sw/metrics', { params }),
  swGetEndpointTopN:(params)             => http.get('/sw/endpoint-topn', { params }),
  swTest:           ()                   => http.get('/sw/test'),
  // 可观测性总览
  observabilityOverview: (params) => http.get('/observability/overview', { params }),
  // Grafana 看板管理
  observabilityGrafanaBoards: () => http.get('/observability/grafana/boards'),
  discoverGrafanaBoards: () => http.get('/observability/grafana/discover'),
  testGrafanaConnection: () => http.get('/observability/grafana/test'),
  addGrafanaBoard: (data) => http.post('/observability/grafana/boards', data),
  deleteGrafanaBoard: (id) => http.delete(`/observability/grafana/boards/${id}`),
  // 主机分组
  listGroups:    ()         => http.get('/groups'),
  createGroup:   (data)     => http.post('/groups', data),
  updateGroup:   (id, data) => http.put(`/groups/${id}`, data),
  deleteGroup:   (id)       => http.delete(`/groups/${id}`),
  // 报告通知（分组推送）
  notifyReportGroups:        (id, groupId) => {
    const q = groupId ? `?group_id=${encodeURIComponent(groupId)}` : ''
    return http.post(`/report/${id}/notify-groups${q}`)
  },
  generateInspectGroups:     ()        => http.post('/report/inspect/generate-groups'),
  downloadInspectExcel:      (id)      => `/api/report/inspect/${id}/excel`,
  // Kubernetes
  k8sSummary:       ()           => http.get('/k8s/summary'),
  k8sNodes:         ()           => http.get('/k8s/nodes'),
  k8sPods:          (ns)         => http.get('/k8s/pods',        { params: ns ? { namespace: ns } : {} }),
  k8sDeployments:   (ns)         => http.get('/k8s/deployments', { params: ns ? { namespace: ns } : {} }),
  k8sServices:      (ns)         => http.get('/k8s/services',    { params: ns ? { namespace: ns } : {} }),
  k8sNamespaces:    ()           => http.get('/k8s/namespaces'),
  // Ansible 任务中心
  ansibleTasks:     ()           => http.get('/ansible/tasks'),
  ansibleCreateTask:(data)       => http.post('/ansible/tasks', data),
  ansibleGetTask:   (id)         => http.get(`/ansible/tasks/${id}`),
  ansibleDeleteTask:(id)         => http.delete(`/ansible/tasks/${id}`),
  ansibleCrons:     ()           => http.get('/ansible/crons'),
  ansibleCreateCron:(data)       => http.post('/ansible/crons', data),
  ansibleUpdateCron:(id, data)   => http.put(`/ansible/crons/${id}`, data),
  ansibleDeleteCron:(id)         => http.delete(`/ansible/crons/${id}`),
  ansibleRunCron:   (id)         => http.post(`/ansible/crons/${id}/run`),
  ansiblePlaybooks: ()           => http.get('/ansible/playbooks'),
  // 事件墙
  listEvents:       (params)     => http.get('/events',       { params }),
  eventStats:       ()           => http.get('/events/stats'),
  // 中间件
  middlewareSummary:   ()        => http.get('/middleware/summary'),
  middlewareInstances: ()        => http.get('/middleware/instances'),
  middlewareMetrics:   (type)    => http.get(`/middleware/metrics/${type}`),
  // 工单系统
  listTickets:      (params)     => http.get('/tickets',              { params }),
  createTicket:     (data)       => http.post('/tickets', data),
  getTicket:        (id)         => http.get(`/tickets/${id}`),
  updateTicket:     (id, data)   => http.put(`/tickets/${id}`, data),
  deleteTicket:     (id)         => http.delete(`/tickets/${id}`),
  approveTicket:    (id, comment) => http.post(`/tickets/${id}/approve`, null, { params: { comment } }),
  rejectTicket:     (id, comment) => http.post(`/tickets/${id}/reject`,  null, { params: { comment } }),
  doneTicket:       (id, comment) => http.post(`/tickets/${id}/done`,    null, { params: { comment } }),
  ticketStats:      ()           => http.get('/tickets/stats/summary'),
  // 告警中心
  alertWebhook:       (data)  => http.post('/alerts/webhook', data),
  alertGroups:        (params) => http.get('/alerts/groups', { params }),
  alertGroup:         (id)    => http.get(`/alerts/groups/${id}`),
  alertUpdateStatus:  (id, data) => http.put(`/alerts/groups/${id}/status`, data),
  alertStats:         ()      => http.get('/alerts/stats'),
  // Elasticsearch
  esClusters:       ()           => http.get('/es/clusters'),
  esAddCluster:     (data)       => http.post('/es/clusters', data),
  esUpdateCluster:  (id, data)   => http.put(`/es/clusters/${id}`, data),
  esDeleteCluster:  (id)         => http.delete(`/es/clusters/${id}`),
  esTestCluster:    (id)         => http.get(`/es/clusters/${id}/test`),
  esOverview:       (id)         => http.get(`/es/clusters/${id}/overview`),
  esIndices:        (id)         => http.get(`/es/clusters/${id}/indices`),
  esNodes:          (id)         => http.get(`/es/clusters/${id}/nodes`),
  esShards:         (id, idx)    => http.get(`/es/clusters/${id}/shards`, { params: idx ? { index: idx } : {} }),
  esProxy:          (id, method, path, body) => http.request({ method, url: `/es/clusters/${id}/proxy/${path}`, data: body }),
}

/** 流式 SSE 工具 */
export function streamSSE(url, onChunk, onDone, onError) {
  const es = new EventSource(url)
  es.onmessage = (e) => {
    if (e.data === '[DONE]') { es.close(); onDone?.() }
    else { onChunk(e.data) }
  }
  es.onerror = (e) => { es.close(); onError?.(e) }
  return () => es.close()
}
