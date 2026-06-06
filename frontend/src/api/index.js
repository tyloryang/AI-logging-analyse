import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 120000 })

http.interceptors.response.use(
  r => r.data,
  e => {
    if (axios.isCancel(e)) {
      return Promise.reject(e)
    }
    if (e?.response?.status === 401 && !window.location.hash.includes('/login')) {
      window.location.href = '/#/login'
    }
    return Promise.reject(e?.response?.data?.detail || e.message || '请求失败')
  },
)

export const api = {
  // 服务列表
  getServices:        (config = {}) => http.get('/services', config),
  getServicesGrouped: (params = {}, config = {}) => http.get('/services/grouped', { ...config, params }),
  getLogLabels:       (config = {}) => http.get('/logs/labels', config),
  getLogLabelValues:  (label, params = {}, config = {}) => http.get(`/logs/labels/${encodeURIComponent(label)}/values`, { ...config, params }),
  // 日志
  getLogs:        (params, config = {}) => http.get('/logs', { ...config, params }),
  getLogContext:  (params, config = {}) => http.get('/logs/context', { ...config, params }),
  getErrorLogs:   (params) => http.get('/logs/errors', { params }),
  // 指标
  getErrorMetrics: (hours = 24) => http.get('/metrics/errors', { params: { hours } }),
  // 日志模板聚合
  getTemplates:   (params, config = {}) => http.get('/logs/templates', { ...config, params }),
  // 链路耗时分析
  traceKeyword:   (params, config = {}) => http.get('/logs/trace', { ...config, params }),
  // 报告
  listReports:    () => http.get('/report/list'),
  getReport:      (id) => http.get(`/report/${id}`),
  notifyReport:   (id, channels) => http.post(`/report/${id}/notify`, { channels }),
  // CMDB / 主机（手动录入）
  getHosts:       () => http.get('/hosts'),
  createHost:     (data) => http.post('/hosts', data),
  updateHost:     (id, data) => http.put(`/hosts/${id}`, data),
  deleteHost:     (id) => http.delete(`/hosts/${id}`),
  syncHost:       (id) => http.post(`/hosts/${id}/sync`),
  syncAllHosts:   ()   => `/api/hosts/sync-all`,
  getHostProcesses: (id) => http.get(`/hosts/${id}/processes`),
  javaDiagArthas: (hostId, data) => http.post(`/hosts/${hostId}/java-diagnostics/arthas`, data),
  javaDiagFlamegraph: (hostId, data) => http.post(`/hosts/${hostId}/java-diagnostics/flamegraph`, data),
  exportHosts:    ()   => `/api/hosts/export`,
  importHosts:    (file, conflict = 'skip') => {
    const fd = new FormData(); fd.append('file', file)
    return http.post(`/hosts/import?conflict=${conflict}`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  inspectHosts:   (groupId) => http.get('/hosts/inspect', { params: groupId ? { group_id: groupId } : {} }),
  inspectHost:    (id) => http.get(`/hosts/${id}/inspect`),
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
  healthCheck:    (config = {}) => http.get('/health', config),
  // 系统配置（管理员）
  getSettings:    () => http.get('/settings'),
  saveSettings:   (data) => http.put('/settings', data),
  testPrometheus: (data) => http.post('/settings/test/prometheus', data),
  testLoki:       (data) => http.post('/settings/test/loki', data),
  testAlertmanager: (data) => http.post('/settings/test/alertmanager', data),
  testK8s:        ()     => http.get('/settings/test/k8s'),
  testAI:         (data) => http.post('/settings/test/ai', data),
  // Agent 工作台
  getAgentConfig:          () => http.get('/agent-config'),
  saveAgentConfig:         (data) => http.put('/agent-config', data),
  listAgentModels:         () => http.get('/agent-config/models'),
  createAgentModel:        (data) => http.post('/agent-config/models', data),
  updateAgentModel:        (id, data) => http.put(`/agent-config/models/${id}`, data),
  deleteAgentModel:        (id) => http.delete(`/agent-config/models/${id}`),
  setAgentActiveModel:     (modelId) => http.put('/agent-config/models/active', { model_id: modelId }),
  discoverAgentWorkspace:  () => http.get('/agent-config/workspace/discover'),
  updateAgentMcp:          (id, data) => http.put(`/agent-config/mcps/${id}`, data),
  pingAgentMcp:            (id) => http.post(`/agent-config/mcps/${id}/ping`),
  updateAgentSkill:        (id, data) => http.put(`/agent-config/skills/${id}`, data),
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
  adminDisableUser: (id) => http.post(`/admin/users/${id}/disable`),
  adminDeleteUser:  (id) => http.delete(`/admin/users/${id}`),
  adminGetPermissions: (id) => http.get(`/admin/users/${id}/permissions`),
  adminSetPermissions: (id, data) => http.put(`/admin/users/${id}/permissions`, data),
  adminListModules: () => http.get('/admin/modules'),
  adminAuditLogs:  (params) => http.get('/admin/audit-logs', { params }),
  adminGetUserCmdbGroups: (id)       => http.get(`/admin/users/${id}/cmdb-groups`),
  adminSetUserCmdbGroups: (id, data) => http.put(`/admin/users/${id}/cmdb-groups`, data),
  adminGetUserK8sClusters: (id)       => http.get(`/admin/users/${id}/k8s-clusters`),
  adminSetUserK8sClusters: (id, data) => http.put(`/admin/users/${id}/k8s-clusters`, data),
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
  observabilityOverview: (params, config = {}) => http.get('/observability/overview', { ...config, params }),
  // 知识拓扑
  topologyKnowledge: () => http.get('/topology/knowledge'),
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
  // K8s 证书管理
  k8sInspectKubeconfig: (path)         => http.post('/k8s/inspect-kubeconfig', { path }),
  // Agent git 工具
  // cc-haha 集成
  ccHahaStatus:  ()                      => http.get('/cc-haha/status'),
  ccHahaStart:   ()                      => http.post('/cc-haha/start'),
  ccHahaStop:    ()                      => http.post('/cc-haha/stop'),
  ccHahaProxy:   (method, path, data)    => http.request({ method, url: '/cc-haha/proxy/' + path, data }),
  agentClaudeMd:       (path)          => http.get('/agent/claude-md',    { params: { path } }),
  agentSaveClaudeMd:   (path, content) => http.put('/agent/claude-md',    { path, content }),
  agentContextPreview: (path)          => http.get('/agent/context-preview', { params: { path } }),
  agentGitStatus:      (path)          => http.get('/agent/git/status',   { params: { path } }),
  agentGitDiff:        (path, file)    => http.get('/agent/git/diff',     { params: { path, file } }),
  agentDetectExecutors:()              => http.get('/agent/executors/detect'),
  k8sListCerts:     ()                 => http.get('/k8s/certs'),
  k8sUploadCert:    (file, certType)   => {
    const fd = new FormData(); fd.append('file', file)
    return http.post(`/k8s/certs/upload?cert_type=${certType}`, fd, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  k8sGenerateKubeconfig: (data)        => http.post('/k8s/generate-kubeconfig', data),
  k8sUploadKubeconfigText: (name, content) => http.post('/k8s/kubeconfigs/upload-text', { name, content }),
  // K8s 集群管理
  k8sClusters:      ()                 => http.get('/k8s/clusters'),
  k8sAddCluster:    (data)             => http.post('/k8s/clusters', data),
  k8sUpdateCluster: (id, data)         => http.put(`/k8s/clusters/${id}`, data),
  k8sDeleteCluster: (id)               => http.delete(`/k8s/clusters/${id}`),
  k8sSetDefaultCluster: (id)           => http.post(`/k8s/clusters/${id}/default`),
  k8sTestCluster:   (id)               => http.get(`/k8s/clusters/${id}/test`),
  k8sSummary:       (clusterId)        => http.get('/k8s/summary',     { params: clusterId ? { cluster_id: clusterId } : {} }),
  k8sNodes:         (clusterId)        => http.get('/k8s/nodes',       { params: clusterId ? { cluster_id: clusterId } : {} }),
  k8sPods:          (clusterId, ns)    => http.get('/k8s/pods',        { params: { ...(clusterId ? { cluster_id: clusterId } : {}), ...(ns ? { namespace: ns } : {}) } }),
  k8sDeployments:   (clusterId, ns)    => http.get('/k8s/deployments', { params: { ...(clusterId ? { cluster_id: clusterId } : {}), ...(ns ? { namespace: ns } : {}) } }),
  k8sDaemonSets:    (clusterId, ns)    => http.get('/k8s/daemonsets',  { params: { ...(clusterId ? { cluster_id: clusterId } : {}), ...(ns ? { namespace: ns } : {}) } }),
  k8sStatefulSets:  (clusterId, ns)    => http.get('/k8s/statefulsets',{ params: { ...(clusterId ? { cluster_id: clusterId } : {}), ...(ns ? { namespace: ns } : {}) } }),
  k8sJobs:          (clusterId, ns)    => http.get('/k8s/jobs',        { params: { ...(clusterId ? { cluster_id: clusterId } : {}), ...(ns ? { namespace: ns } : {}) } }),
  k8sCronJobs:      (clusterId, ns)    => http.get('/k8s/cronjobs',    { params: { ...(clusterId ? { cluster_id: clusterId } : {}), ...(ns ? { namespace: ns } : {}) } }),
  k8sServices:      (clusterId, ns)    => http.get('/k8s/services',    { params: { ...(clusterId ? { cluster_id: clusterId } : {}), ...(ns ? { namespace: ns } : {}) } }),
  k8sNamespaces:    (clusterId)        => http.get('/k8s/namespaces',  { params: clusterId ? { cluster_id: clusterId } : {} }),
  k8sResourceDetail:(clusterId, kind, name, namespace = '') => http.get('/k8s/resource-detail', { params: { ...(clusterId ? { cluster_id: clusterId } : {}), kind, name, namespace } }),
  k8sResourcePods:  (clusterId, kind, name, namespace = '') => http.get('/k8s/resource-pods',   { params: { ...(clusterId ? { cluster_id: clusterId } : {}), kind, name, namespace } }),
  k8sUpdateResourceYaml: (clusterId, kind, name, namespace, yamlText) =>
    http.put('/k8s/resource-yaml',
      { yaml_text: yamlText },
      { params: { ...(clusterId ? { cluster_id: clusterId } : {}), kind, name, namespace } }),
  k8sScaleResource: (clusterId, kind, name, namespace, replicas) =>
    http.post('/k8s/resource-scale',
      { replicas },
      { params: { ...(clusterId ? { cluster_id: clusterId } : {}), kind, name, namespace } }),
  k8sBatchOperate: (clusterId, action, items) =>
    http.post('/k8s/resource-batch',
      { action, items },
      { params: clusterId ? { cluster_id: clusterId } : {} }),
  k8sUpdateResourceImage: (clusterId, kind, name, namespace, containers) =>
    http.post('/k8s/resource-image',
      { containers },
      { params: { ...(clusterId ? { cluster_id: clusterId } : {}), kind, name, namespace } }),
  k8sResourceEvents: (clusterId, kind, name, namespace = '') =>
    http.get('/k8s/resource-events',
      { params: { ...(clusterId ? { cluster_id: clusterId } : {}), kind, name, namespace } }),
  k8sPodLogs:       (clusterId, namespace, podName, container = '', tailLines = 200) => http.get('/k8s/pod-logs', { params: { ...(clusterId ? { cluster_id: clusterId } : {}), namespace, pod_name: podName, container, tail_lines: tailLines } }),
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
  redisClusters:       ()        => http.get('/redis/clusters'),
  redisAddCluster:     (data)    => http.post('/redis/clusters', data),
  redisUpdateCluster:  (id, data)=> http.put(`/redis/clusters/${id}`, data),
  redisDeleteCluster:  (id)      => http.delete(`/redis/clusters/${id}`),
  redisTestCluster:    (id)      => http.get(`/redis/clusters/${id}/test`),
  redisTestConfig:     (data)    => http.post('/redis/clusters/test-config', data),
  redisOverview:       (id)      => http.get(`/redis/clusters/${id}/overview`),
  // Redis Key 浏览
  redisScanKeys:       (id, p)   => http.get(`/redis/clusters/${id}/keys`,    { params: p }),
  redisGetKey:         (id, p)   => http.get(`/redis/clusters/${id}/key`,     { params: p }),
  redisDeleteKey:      (id, key, db) => http.delete(`/redis/clusters/${id}/key`, { params: { key, db } }),
  redisSetKeyTTL:      (id, key, ttl, db) => http.put(`/redis/clusters/${id}/key/ttl`, { ttl }, { params: { key, db } }),
  // Redis 监控
  redisInfo:           (id, db)  => http.get(`/redis/clusters/${id}/info`,    { params: { db } }),
  redisSlowlog:        (id, n, db) => http.get(`/redis/clusters/${id}/slowlog`, { params: { count: n, db } }),
  // Redis 命令台
  redisCommand:        (id, data) => http.post(`/redis/clusters/${id}/command`, data),
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
  // 根因分析
  rcaStream:       (data)  => `/api/rca/analyze/stream`,
  rcaTrigger:      (data)  => http.post('/rca/analyze', data),
  rcaResults:      (limit) => http.get('/rca/results', { params: { limit } }),
  rcaResult:       (id)    => http.get(`/rca/results/${id}`),
  rcaConfirm:      (id, data) => http.post(`/rca/results/${id}/confirm`, data),
  rcaExpertCases:  (limit = 50) => http.get('/rca/expert-cases', { params: { limit } }),
  rcaFeedback:     ()      => http.get('/rca/feedback'),
  rcaAnomalies:    (limit) => http.get('/rca/anomalies', { params: { limit } }),
  rcaDetect:       ()      => http.post('/rca/anomalies/detect'),
  // 告警中心
  alertWebhook:       (data)  => http.post('/alerts/webhook', data),
  alertGroups:        (params) => http.get('/alerts/groups', { params }),
  alertFilters:       ()       => http.get('/alerts/filters'),
  alertGroup:         (id)    => http.get(`/alerts/groups/${id}`),
  alertTriggerRca:    (id, data = {}) => http.post(`/alerts/groups/${id}/rca`, data),
  alertUpdateStatus:  (id, data) => http.put(`/alerts/groups/${id}/status`, data),
  alertStats:         ()      => http.get('/alerts/stats'),
  // Jenkins CI/CD — 多实例
  jenkinsListInstances:   ()           => http.get('/jenkins/instances'),
  jenkinsCreateInstance:  (data)       => http.post('/jenkins/instances', data),
  jenkinsUpdateInstance:  (id, data)   => http.put(`/jenkins/instances/${id}`, data),
  jenkinsDeleteInstance:  (id)         => http.delete(`/jenkins/instances/${id}`),
  jenkinsSetDefault:      (id)         => http.post(`/jenkins/instances/${id}/default`),
  jenkinsTestInstance:    (id)         => http.get(`/jenkins/instances/${id}/test`),
  jenkinsGetViews:        (id)         => http.get(`/jenkins/instances/${id}/views`),
  jenkinsGetJobs:         (id, view)   => http.get(`/jenkins/instances/${id}/jobs`, { params: view ? { view } : {} }),
  jenkinsSearchJobs:      (id, q)      => http.get(`/jenkins/instances/${id}/jobs/search`, { params: { q } }),
  jenkinsGetJobBuilds:    (id, job, limit = 15) => http.get(`/jenkins/instances/${id}/builds`, { params: { job, limit } }),
  jenkinsGetBuildInfo:    (id, job, build) => http.get(`/jenkins/instances/${id}/jobs/${encodeURIComponent(job)}/builds/${build}`),
  jenkinsGetBuildLogs:    (id, job, build, lines) => http.get(`/jenkins/instances/${id}/jobs/${encodeURIComponent(job)}/builds/${build}/logs`, { params: { lines } }),
  jenkinsGetRunning:      (id)         => http.get(`/jenkins/instances/${id}/running`),
  jenkinsGetQueue:        (id)         => http.get(`/jenkins/instances/${id}/queue`),
  jenkinsBuild:           (id, data)   => http.post(`/jenkins/instances/${id}/build`, data),
  jenkinsCancelQueue:     (id, qid)    => http.post(`/jenkins/instances/${id}/queue/cancel`, { queue_id: qid }),
  // 兼容旧接口
  jenkinsGetConfig:     ()           => http.get('/jenkins/config'),
  jenkinsTest:          ()           => http.get('/jenkins/test'),
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

  // Agent 历史会话
  listConversations:   (params)        => http.get('/agent/conversations', { params }),
  getConversation:     (convId)        => http.get(`/agent/conversations/${convId}`),
  saveConversation:    (convId, data)  => http.put(`/agent/conversations/${convId}`, data),
  deleteConversation:  (convId)        => http.delete(`/agent/conversations/${convId}`),
}

export { http }

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
