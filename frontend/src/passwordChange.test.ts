import { describe, expect, it } from 'vitest'
import { passwordChangeError } from './passwordChange'

describe('passwordChangeError', () => {
  it('accepts a new password of 8 or more that matches its confirmation', () => {
    expect(passwordChangeError('old-secret', 'new-secret', 'new-secret')).toBeNull()
    expect(passwordChangeError('old', '12345678', '12345678')).toBeNull()
  })

  it('refuses one that is too short or too long, as the server would', () => {
    expect(passwordChangeError('old', '1234567', '1234567')).toBe('password.tooShort')
    const long = 'x'.repeat(129)
    expect(passwordChangeError('old', long, long)).toBe('password.tooLong')
  })

  it('refuses a confirmation that differs, then a password that does not change', () => {
    expect(passwordChangeError('old-secret', 'new-secret', 'new-secreT')).toBe('password.mismatch')
    expect(passwordChangeError('same-secret', 'same-secret', 'same-secret')).toBe('password.same')
  })
})
