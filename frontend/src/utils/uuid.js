export function safeRandomUUID() {
  const cryptoObj = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined

  if (cryptoObj && typeof cryptoObj.randomUUID === 'function') {
    try {
      return cryptoObj.randomUUID()
    } catch {
      // ignore and fall through
    }
  }

  if (cryptoObj && typeof cryptoObj.getRandomValues === 'function') {
    try {
      const bytes = new Uint8Array(16)
      cryptoObj.getRandomValues(bytes)
      bytes[6] = (bytes[6] & 0x0f) | 0x40
      bytes[8] = (bytes[8] & 0x3f) | 0x80

      const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0'))
      return [
        hex.slice(0, 4).join(''),
        hex.slice(4, 6).join(''),
        hex.slice(6, 8).join(''),
        hex.slice(8, 10).join(''),
        hex.slice(10, 16).join(''),
      ].join('-')
    } catch {
      // ignore and fall through
    }
  }

  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, ch => {
    const r = Math.random() * 16 | 0
    return (ch === 'x' ? r : (r & 0x3 | 0x8)).toString(16)
  })
}
