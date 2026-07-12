export const CONTEXT_INITIAL_SIDE = 20
export const CONTEXT_PAGE_STEP = 50
export const CONTEXT_MAX_SIDE = 500

export function nextContextCount(current) {
  const value = Number(current) || 0
  return Math.min(value + CONTEXT_PAGE_STEP, CONTEXT_MAX_SIDE)
}
