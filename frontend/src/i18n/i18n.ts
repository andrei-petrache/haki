/**
 * Translations without a library: typed dictionaries, {name} parameters and
 * Intl.PluralRules. The language comes from an explicit choice in Profile,
 * else from the browser (Romanian or English), else English. No React here.
 */
import { en } from './en'
import { isPlural } from './plural'
import type { Plural } from './plural'
import { ro } from './ro'

export type MessageKey = keyof typeof en

/** What every other language must provide: the same keys, the same kinds of entry. */
export type Dictionary = {
  [K in MessageKey]: (typeof en)[K] extends string ? string : Plural
}

export const LOCALES = ['en', 'ro'] as const
export type Locale = (typeof LOCALES)[number]

/** What the user picked in Profile: a language, or the browser's. */
export type LocaleChoice = Locale | 'auto'

/** Each language's name in itself, as a language picker shows it. */
export const LOCALE_NAMES: Record<Locale, string> = { en: 'English', ro: 'Română' }

export const DICTIONARIES: Record<Locale, Dictionary> = { en, ro }

export type Params = Record<string, string | number>

/**
 * The text for key in the dictionary, with its {parameters} filled in.
 *
 * A plural entry takes its form from params.count, by the language's rules;
 * a form the entry lacks falls back to other. An unknown {parameter} is left
 * as it is, so a missing value shows instead of vanishing.
 */
export function translate(
  dictionary: Dictionary,
  locale: Locale,
  key: MessageKey,
  params: Params = {},
): string {
  const entry: string | Plural = dictionary[key]
  let text: string
  if (isPlural(entry)) {
    const form = new Intl.PluralRules(locale).select(Number(params.count))
    text = entry[form] ?? entry.other
  } else {
    text = entry
  }
  return text.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in params ? String(params[name]) : whole,
  )
}

/** A translator for one language, as components use it: t('nav.today'). */
export function translator(locale: Locale): (key: MessageKey, params?: Params) => string {
  const dictionary = DICTIONARIES[locale]
  return (key, params) => translate(dictionary, locale, key, params)
}

/**
 * The first of the browser's languages we have (by its main part: "ro-RO"
 * is Romanian, "en-GB" English), or English.
 */
export function detectLocale(languages: readonly string[]): Locale {
  for (const language of languages) {
    const main = language.toLowerCase().split('-')[0]
    const found = LOCALES.find((locale) => locale === main)
    if (found) return found
  }
  return 'en'
}

/** The language to show: the explicit choice, or the browser's. */
export function resolveLocale(choice: LocaleChoice, languages: readonly string[]): Locale {
  return choice === 'auto' ? detectLocale(languages) : choice
}

/** The browser's languages, most preferred first; none outside a browser. */
export function browserLanguages(): readonly string[] {
  if (typeof navigator === 'undefined') return []
  return navigator.languages?.length ? navigator.languages : [navigator.language]
}

/** Where the choice is kept: on this device, like the weight unit. */
export const LOCALE_KEY = 'haki_locale'

type ChoiceStorage = Pick<Storage, 'getItem' | 'setItem'>

function browserStorage(): ChoiceStorage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    // Some browsers throw on access when site data is blocked
    return null
  }
}

/** A choice read back from storage; anything unknown (or nothing) is 'auto'. */
export function parseLocaleChoice(value: string | null): LocaleChoice {
  return LOCALES.find((locale) => locale === value) ?? 'auto'
}

/**
 * The choice an account's language makes on this device: its language when
 * it has one, else null, so the device keeps its own choice (an account
 * from before languages were kept has none).
 */
export function accountLocaleChoice(language: string | null | undefined): LocaleChoice | null {
  return LOCALES.find((locale) => locale === language) ?? null
}

/** What to keep with the account for a choice made here: 'auto' is none. */
export function accountLanguageOf(choice: LocaleChoice): Locale | null {
  return choice === 'auto' ? null : choice
}

export function loadLocaleChoice(storage: ChoiceStorage | null = browserStorage()): LocaleChoice {
  try {
    return parseLocaleChoice(storage?.getItem(LOCALE_KEY) ?? null)
  } catch {
    return 'auto'
  }
}

/** Keep the choice on this device. Not being able to is no error: it lasts this visit. */
export function saveLocaleChoice(
  choice: LocaleChoice,
  storage: ChoiceStorage | null = browserStorage(),
): void {
  try {
    storage?.setItem(LOCALE_KEY, choice)
  } catch {
    // Storage full or blocked: the choice still holds until the page reloads
  }
}

/**
 * The language for texts made outside components: form validation, number
 * and date formats, the API client's own messages. App sets it while it
 * renders, so everything rendered after it follows. English until then,
 * and in unit tests, which therefore keep their English texts.
 */
let active: Locale = 'en'

export function setActiveLocale(locale: Locale): void {
  active = locale
}

export function activeLocale(): Locale {
  return active
}

/** t() for the active language, where there is no component to ask. */
export function tActive(key: MessageKey, params?: Params): string {
  return translate(DICTIONARIES[active], active, key, params)
}

/** A plain number for a message in the active language: "2204.62", "2204,62" (no grouping). */
export function formatNumber(value: number): string {
  return new Intl.NumberFormat(active, { maximumFractionDigits: 2, useGrouping: false }).format(value)
}
