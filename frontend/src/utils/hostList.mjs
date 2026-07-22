function normalizedText(value) {
  return String(value ?? '').trim()
}

export function getOwnerOptions(hosts) {
  const owners = hosts
    .map(host => normalizedText(host.owner))
    .filter(Boolean)

  return [...new Set(owners)].sort((left, right) => left.localeCompare(right, 'zh-CN'))
}

export function filterHostsByOwner(hosts, owner) {
  const selectedOwner = normalizedText(owner)
  if (!selectedOwner) return hosts
  return hosts.filter(host => normalizedText(host.owner) === selectedOwner)
}

export function sortHosts(hosts, key, ascending) {
  return [...hosts].sort((left, right) => {
    const leftValue = normalizedText(left[key]).toLocaleLowerCase('zh-CN')
    const rightValue = normalizedText(right[key]).toLocaleLowerCase('zh-CN')
    return ascending
      ? leftValue.localeCompare(rightValue, 'zh-CN')
      : rightValue.localeCompare(leftValue, 'zh-CN')
  })
}
