/**
 * The Romanian translation is complete, checked in CI (the frontend job
 * runs these with the unit tests):
 * - every key exists in both languages: ro.ts is typed Dictionary, so a
 *   missing key already fails the build; here, no value is empty;
 * - each text keeps the same {placeholders} in both languages;
 * - no text is left in English by mistake (a short allowlist holds the
 *   words that are the same in Romanian);
 * - every error code the backend can send (backend/app/errors.py) has a
 *   message, so the server's English never reaches a Romanian screen.
 */
// The backend's error codes, from the repository: a new code there without a
// message here fails CI
import errorsPy from '../../../backend/app/errors.py?raw'
import { describe, expect, it } from 'vitest'
import { en } from './en'
import { ro } from './ro'

type Entry = string | Record<string, string>

// The same word in both languages, on purpose
const SAME_IN_BOTH = new Set([
  'auth.email',
  'profile.email',
  'log.catalog',
  'quick.macro',
  'workouts.colSet',
  'rest.dismiss',
])

function texts(entry: Entry): string[] {
  return typeof entry === 'string' ? [entry] : Object.values(entry)
}

function placeholders(text: string): string[] {
  return [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]).sort()
}

const keys = Object.keys(en) as (keyof typeof en)[]

describe('the Romanian translation', () => {
  it('has no empty text', () => {
    const empty = keys.filter((key) => texts(ro[key] as Entry).some((text) => text.trim() === ''))
    expect(empty).toEqual([])
  })

  it('keeps the same placeholders as English', () => {
    const differ = keys.filter((key) => {
      const english = new Set(texts(en[key] as Entry).flatMap(placeholders))
      const romanian = new Set(texts(ro[key] as Entry).flatMap(placeholders))
      return [...english].sort().join() !== [...romanian].sort().join()
    })
    expect(differ).toEqual([])
  })

  it('leaves nothing in English by mistake', () => {
    const same = keys.filter((key) => !SAME_IN_BOTH.has(key) && JSON.stringify(en[key]) === JSON.stringify(ro[key]))
    expect(same).toEqual([])
  })

  it('has a message for every error code the backend sends', () => {
    const source = errorsPy
    const enumBody = source.slice(source.indexOf('class ErrorCode'), source.indexOf('\n\n\n', source.indexOf('class ErrorCode')))
    const codes = [...enumBody.matchAll(/^\s+[A-Z_]+ = "([a-z_]+)"$/gm)].map((match) => match[1])
    expect(codes.length).toBeGreaterThan(30)
    const missing = codes.filter((code) => !(`error.${code}` in en))
    expect(missing).toEqual([])
  })
})
