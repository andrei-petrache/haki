/**
 * Small pure helpers for the catalog pickers. No React, no fetch.
 */
import type { CatalogLanguage } from './api'
import type { Locale } from './i18n/i18n'

/** The catalog's language for the app's: the two are the same today. */
export function catalogLanguage(locale: Locale): CatalogLanguage {
  return locale === 'ro' ? 'ro' : 'en'
}

/** An item's name in the language, English where it has no Romanian one. */
export function catalogName(item: { name: string; name_ro: string | null }, locale: Locale): string {
  return locale === 'ro' && item.name_ro ? item.name_ro : item.name
}

/** A search box's text as the API's q: spaces around and between words tidied. */
export function searchText(text: string): string {
  return text.trim().replace(/\s+/g, ' ')
}
