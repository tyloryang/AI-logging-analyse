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
  // 主机分组
  listGroups:    ()         => http.get('/groups'),
  createGroup:   (data)     => http.post('/groups', data),
  updateGroup:   (id, data) => http.put(`/groups/${id}`, data),
  deleteGroup:   (id)       => http.delete(`/groups/${id}`),
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
