import { describe, expect, it } from 'vitest'
import { TOKEN_KEY, afterRejected, tokenSubject } from './session'

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

describe('tokenSubject', () => {
  const jwt = (payload: object) =>
    `x.${btoa(JSON.stringify(payload)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')}.y`

  it('reads the account from the payload, without verifying', () => {
    expect(tokenSubject(jwt({ sub: '42', exp: 1 }))).toBe('42')
    expect(tokenSubject(jwt({ sub: 7 }))).toBe('7')
  })

  it('is null for anything that is not a token with a subject', () => {
    expect(tokenSubject('not-a-token')).toBeNull()
    expect(tokenSubject(jwt({ exp: 1 }))).toBeNull()
    expect(tokenSubject('x.%%%.y')).toBeNull()
  })
})
