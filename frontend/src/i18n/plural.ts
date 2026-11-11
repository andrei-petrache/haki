/**
 * A text with plural forms, as Intl.PluralRules names them. English needs
 * one and other; Romanian also few ("3 seturi"), while other is "20 de
 * seturi". A form a language never selects can be left out.
 */
export type Plural = {
  zero?: string
  one?: string
  two?: string
  few?: string
  many?: string
  other: string
}

export function isPlural(entry: string | Plural): entry is Plural {
  return typeof entry !== 'string'
}
