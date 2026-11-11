/**
 * The current language for components: const { t, locale } = useI18n().
 * App provides it; without a provider (e.g. a component in a unit test)
 * everything is in English.
 */
import { createContext, useContext } from 'react'
import { translator } from './i18n'
import type { Locale, MessageKey, Params } from './i18n'

export type I18n = {
  locale: Locale
  t: (key: MessageKey, params?: Params) => string
}

export const I18nContext = createContext<I18n>({ locale: 'en', t: translator('en') })

export function useI18n(): I18n {
  return useContext(I18nContext)
}
