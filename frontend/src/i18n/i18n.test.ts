import { describe, expect, it } from 'vitest'
import { en } from './en'
import {
  DICTIONARIES,
  LOCALE_KEY,
  accountLanguageOf,
  accountLocaleChoice,
  detectLocale,
  loadLocaleChoice,
  resolveLocale,
  saveLocaleChoice,
  translate,
  translator,
} from './i18n'
import type { Dictionary, MessageKey } from './i18n'
import type { Plural } from './plural'
import { ro } from './ro'

/** The {parameters} a text, or every form of a plural, uses. */
function parameters(entry: string | Plural): string[] {
  const texts = typeof entry === 'string' ? [entry] : Object.values(entry)
  const names = texts.flatMap((text) => [...(text ?? '').matchAll(/\{(\w+)\}/g)].map((m) => m[1]))
  return [...new Set(names)].sort()
}

describe('the dictionaries', () => {
  it('give Romanian the same parameters as English, for every key', () => {
    for (const key of Object.keys(en) as MessageKey[]) {
      expect(parameters(ro[key]), key).toEqual(parameters(en[key]))
    }
  })

  it('leave no Romanian text empty', () => {
    for (const [key, entry] of Object.entries(ro) as [string, string | Plural][]) {
      const texts = typeof entry === 'string' ? [entry] : Object.values(entry)
      for (const text of texts) expect(text?.trim(), key).not.toBe('')
    }
  })
})

describe('translate', () => {
  // A small dictionary of its own, so plurals are tested before any screen uses one
  const sample = {
    hello: 'Hello, {name}',
    sets: { one: '{count} set', other: '{count} sets' },
    seturi: { one: '{count} set', few: '{count} seturi', other: '{count} de seturi' },
  } as unknown as Dictionary
  const t = (key: string, locale: 'en' | 'ro', params?: Record<string, number | string>) =>
    translate(sample, locale, key as MessageKey, params)

  it('fills in parameters, and leaves an unknown one visible', () => {
    expect(t('hello', 'en', { name: 'Andrei' })).toBe('Hello, Andrei')
    expect(t('hello', 'en')).toBe('Hello, {name}')
  })

  it('picks the English plural form', () => {
    expect(t('sets', 'en', { count: 1 })).toBe('1 set')
    expect(t('sets', 'en', { count: 0 })).toBe('0 sets')
    expect(t('sets', 'en', { count: 3 })).toBe('3 sets')
  })

  it('picks the Romanian plural form, "de" from 20 on', () => {
    expect(t('seturi', 'ro', { count: 1 })).toBe('1 set')
    expect(t('seturi', 'ro', { count: 3 })).toBe('3 seturi')
    expect(t('seturi', 'ro', { count: 19 })).toBe('19 seturi')
    expect(t('seturi', 'ro', { count: 20 })).toBe('20 de seturi')
    expect(t('seturi', 'ro', { count: 101 })).toBe('101 seturi')
  })

  it('falls back to other when a form is missing', () => {
    expect(t('sets', 'ro', { count: 3 })).toBe('3 sets')
  })

  it('translates real keys in both languages', () => {
    expect(translator('en')('nav.today')).toBe('Today')
    expect(translator('ro')('nav.today')).toBe('Azi')
    expect(translator('ro')('profile.languageAuto', { language: 'Română' })).toBe(
      'Ca în browser (Română)',
    )
    expect(Object.keys(DICTIONARIES)).toEqual(['en', 'ro'])
  })
})

describe('choosing the language', () => {
  it('takes the first browser language we have, by its main part', () => {
    expect(detectLocale(['ro-RO', 'en-US'])).toBe('ro')
    expect(detectLocale(['de-DE', 'en-GB'])).toBe('en')
    expect(detectLocale(['RO'])).toBe('ro')
  })

  it('falls back to English for any other language, or none', () => {
    expect(detectLocale(['de-DE', 'fr'])).toBe('en')
    expect(detectLocale([])).toBe('en')
  })

  it('lets an explicit choice win over the browser', () => {
    expect(resolveLocale('en', ['ro-RO'])).toBe('en')
    expect(resolveLocale('ro', ['en-US'])).toBe('ro')
    expect(resolveLocale('auto', ['ro-RO'])).toBe('ro')
  })

  it('keeps the choice on this device, and is auto otherwise', () => {
    const items = new Map<string, string>()
    const storage = {
      getItem: (key: string) => items.get(key) ?? null,
      setItem: (key: string, value: string) => void items.set(key, value),
    }

    expect(loadLocaleChoice(storage)).toBe('auto')
    saveLocaleChoice('ro', storage)
    expect(items.get(LOCALE_KEY)).toBe('ro')
    expect(loadLocaleChoice(storage)).toBe('ro')
    saveLocaleChoice('auto', storage)
    expect(loadLocaleChoice(storage)).toBe('auto')
  })

  it('reads an unknown value, no storage or a refusing one as auto', () => {
    const refusing = {
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
    }

    expect(loadLocaleChoice({ getItem: () => 'de', setItem: () => {} })).toBe('auto')
    expect(loadLocaleChoice(null)).toBe('auto')
    expect(loadLocaleChoice(refusing)).toBe('auto')
    expect(() => saveLocaleChoice('ro', refusing)).not.toThrow()
  })
})

describe('the account language', () => {
  it('wins when the account has one, and leaves the device alone when not', () => {
    expect(accountLocaleChoice('ro')).toBe('ro')
    expect(accountLocaleChoice('en')).toBe('en')
    expect(accountLocaleChoice(null)).toBeNull()
    expect(accountLocaleChoice(undefined)).toBeNull()
    expect(accountLocaleChoice('de')).toBeNull()
  })

  it('keeps an explicit choice, and none for following the browser', () => {
    expect(accountLanguageOf('ro')).toBe('ro')
    expect(accountLanguageOf('auto')).toBeNull()
  })
})
