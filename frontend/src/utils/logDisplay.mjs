const MESSAGE_KEYS = ['log', 'message', 'msg', 'content', 'body', 'event']
const METADATA_KEYS = new Set(['stream', 'time', 'timestamp', 'ts'])


function fallbackObjectText(value) {
  return Object.entries(value)
    .filter(([key]) => !METADATA_KEYS.has(key))
    .map(([key, item]) => {
      if (item == null) return `${key}=`
      if (typeof item === 'object') return `${key}=[data]`
      return `${key}=${String(item)}`
    })
    .join(' ')
}


export function displayLogLine(line) {
  const original = String(line ?? '')
  let current = original

  for (let depth = 0; depth < 4; depth += 1) {
    const trimmed = current.trim()
    if (!trimmed || !['{', '[', '"'].includes(trimmed[0])) return current.trimEnd()

    let parsed
    try {
      parsed = JSON.parse(trimmed)
    } catch {
      return current.trimEnd()
    }

    if (typeof parsed === 'string') {
      current = parsed
      continue
    }
    if (Array.isArray(parsed)) {
      return parsed.map(item => typeof item === 'object' ? '[data]' : String(item)).join(' ')
    }
    if (!parsed || typeof parsed !== 'object') return String(parsed ?? '')

    const messageKey = MESSAGE_KEYS.find(key => Object.prototype.hasOwnProperty.call(parsed, key))
    if (!messageKey) return fallbackObjectText(parsed) || original.trimEnd()
    const message = parsed[messageKey]
    if (message && typeof message === 'object') return fallbackObjectText(message)
    current = String(message ?? '')
  }

  return current.trimEnd()
}
