import { api } from '../api/index.js'

const HEALTH_CACHE_TTL_MS = 10_000

let cachedHealth = null
let cacheExpiresAt = 0
let inflightHealthPromise = null

export function getAiModelShort(provider = '') {
  if (!provider) return 'AI'
  if (provider.startsWith('Anthropic')) return 'Claude'

  const match = provider.match(/\((.+)\)/)
  return match ? match[1].slice(0, 10) : (provider.slice(0, 10) || 'AI')
}

export async function fetchHealthStatus({ force = false } = {}) {
  const now = Date.now()
  if (!force && cachedHealth && now < cacheExpiresAt) {
    return cachedHealth
  }

  if (inflightHealthPromise) {
    return inflightHealthPromise
  }

  inflightHealthPromise = api.healthCheck()
    .then((data) => {
      cachedHealth = { ...data }
      cacheExpiresAt = Date.now() + HEALTH_CACHE_TTL_MS
      return cachedHealth
    })
    .finally(() => {
      inflightHealthPromise = null
    })

  return inflightHealthPromise
}

export function clearHealthStatusCache() {
  cachedHealth = null
  cacheExpiresAt = 0
}
