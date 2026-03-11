import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 120000 })

http.interceptors.response.use(
  r => r.data,
  e => Promise.reject(e?.response?.data?.detail || e.message || '请求失败'),
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
  // 健康检查
  healthCheck:    () => http.get('/health'),
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
