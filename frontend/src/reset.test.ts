import { describe, expect, it, vi } from 'vitest'
import { exportFileName, exportIsComplete } from './api'
import { parseResetFragment, takeResetToken } from './reset'

describe('the reset link', () => {
  it('reads the token from the fragment only', () => {
    expect(parseResetFragment('#token=abc-123')).toBe('abc-123')
    expect(parseResetFragment('token=abc')).toBe('abc')
    expect(parseResetFragment('#token=')).toBeNull()
    expect(parseResetFragment('')).toBeNull()
  })

  it('on /reset clears the token from the address and the history entry', () => {
    const history = { replaceState: vi.fn() }
    expect(takeResetToken({ pathname: '/reset', hash: '#token=secret' }, history)).toBe('secret')
    expect(history.replaceState).toHaveBeenCalledWith(null, '', '/reset')
  })

  it('leaves any other address alone', () => {
    const history = { replaceState: vi.fn() }
    expect(takeResetToken({ pathname: '/', hash: '#token=secret' }, history)).toBeUndefined()
    expect(history.replaceState).not.toHaveBeenCalled()
  })
})

describe('the data export', () => {
  it('takes the server file name, and only a plain one', () => {
    expect(exportFileName('attachment; filename="haki-export-2026-11-13.json"', '2026-11-13')).toBe(
      'haki-export-2026-11-13.json',
    )
    expect(exportFileName('attachment; filename="../../etc/passwd"', '2026-11-13')).toBe('haki-export-2026-11-13.json')
    expect(exportFileName(null, '2026-11-13')).toBe('haki-export-2026-11-13.json')
  })

  it('is whole only with "complete": true at its end', () => {
    expect(exportIsComplete('{"user": {}, "complete": true}')).toBe(true)
    expect(exportIsComplete('{"user": {}, "complete": false}')).toBe(false)
    expect(exportIsComplete('{"user": {}, "foods": [')).toBe(false)
    expect(exportIsComplete('')).toBe(false)
  })
})
