const countFormatter = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })


export function formatLogCount(value) {
  const count = Number(value)
  return countFormatter.format(Number.isFinite(count) ? count : 0)
}


export function countLoadedPods(rows, podLabel) {
  if (!podLabel) return 0
  return new Set(
    (rows || [])
      .map(row => row?.labels?.[podLabel])
      .filter(Boolean),
  ).size
}


export function buildCoverageSummary({ totalLogs, loadedCount, loadedPods, totalPods, hasMore }) {
  const matched = Number(totalLogs) || 0
  const loaded = Number(loadedCount) || 0
  const covered = Number(loadedPods) || 0
  const pods = Number(totalPods) || 0
  return {
    text: `匹配 ${formatLogCount(matched)} 条 · 已加载 ${formatLogCount(loaded)} 条 · 覆盖 ${covered}/${pods} 个 Pod`,
    truncated: Boolean(hasMore) || matched > loaded,
  }
}


export function replacePodFilters(filters, { namespaceLabel, namespace, podLabel, pod }) {
  const replacedLabels = new Set([namespaceLabel, podLabel].filter(Boolean))
  const next = (filters || []).filter(item => !replacedLabels.has(item.label))
  if (namespaceLabel && namespace) next.push({ label: namespaceLabel, value: String(namespace) })
  if (podLabel && pod) next.push({ label: podLabel, value: String(pod) })
  return next
}
