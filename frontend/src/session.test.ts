import { describe, expect, it } from 'vitest'
import { TOKEN_KEY, afterRejected } from './session'

function storage(value: string | null) {
  const data = new Map<string, string>()
  if (value !== null) data.set(TOKEN_KEY, value)
  return {
    getItem: (key: string) => data.get(key) ?? null,
    removeItem: (key: string) => void data.delete(key),
    value: () => data.get(TOKEN_KEY) ?? null,
  }
}

describe('afterRejected', () => {
  it('logs out and forgets the token when it is the one rejected', () => {
    const s = storage('old')
    expect(afterRejected(s, 'old')).toBeNull()
    expect(s.value()).toBeNull()
  })

  it('carries on with a newer token another tab stored, and keeps it', () => {
    const s = storage('new')
    expect(afterRejected(s, 'old')).toBe('new')
    expect(s.value()).toBe('new')
  })

  it('logs out when nothing is stored', () => {
    const s = storage(null)
    expect(afterRejected(s, 'old')).toBeNull()
    expect(s.value()).toBeNull()
  })
})
