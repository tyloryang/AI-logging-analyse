function uniqueAvailableNames(names, availableNames) {
  const available = new Set((availableNames || []).map(String))
  const seen = new Set()
  const result = []
  for (const raw of names || []) {
    const name = String(raw || '').trim()
    if (!name || seen.has(name) || !available.has(name)) continue
    seen.add(name)
    result.push(name)
  }
  return result
}


export function resolveDefaultLabelNames(savedNames, availableNames, fallbackNames = []) {
  const source = Array.isArray(savedNames) ? savedNames : fallbackNames
  return uniqueAvailableNames(source, availableNames)
}


export function toggleDefaultLabelName(currentNames, labelName) {
  const name = String(labelName || '').trim()
  if (!name) return [...(currentNames || [])]
  const current = [...(currentNames || [])]
  const index = current.indexOf(name)
  if (index >= 0) current.splice(index, 1)
  else current.push(name)
  return current
}
