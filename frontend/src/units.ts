/**
 * Weight units in the UI. The API always stores kilograms: conversion
 * happens only here, when a weight is shown or typed. No React, no fetch.
 */
import { formatNumber, tActive } from './i18n/i18n'

export const WEIGHT_UNITS = ['kg', 'lb'] as const
export type WeightUnit = (typeof WEIGHT_UNITS)[number]

/** Kilograms for everyone until the beta tells us otherwise. */
export const DEFAULT_WEIGHT_UNIT: WeightUnit = 'kg'

/** Kilograms in one pound, exact by definition. */
export const KG_PER_LB = 0.45359237

/** Must match the limit in backend/app/schemas.py (WeightKg). */
export const MAX_WEIGHT_KG = 1000

/** A rounding to this many decimals, without float noise (61.2349999 -> 61.235). */
function roundTo(value: number, decimals: number): number {
  const factor = 10 ** decimals
  return Math.round(value * factor) / factor
}

/** A weight in kilograms as a number in the given unit, not rounded. */
export function kgToUnit(kg: number, unit: WeightUnit): number {
  return unit === 'kg' ? kg : kg / KG_PER_LB
}

/**
 * A typed weight in the given unit, as kilograms for the API.
 *
 * Pounds are rounded to the gram (3 decimals): any pound value with up to 2
 * decimals then comes back the same when shown again. Rounding to 2 decimals
 * of a kilogram (10 g, about 0.02 lb) would not. Kilograms are kept as typed.
 */
export function unitToKg(value: number, unit: WeightUnit): number {
  return unit === 'kg' ? value : roundTo(value * KG_PER_LB, 3)
}

/**
 * The heaviest weight that can be typed in the unit: 1000 kg, or 2204.62 lb.
 *
 * In pounds, 1000 kg is 2204.6226..., cut down to 2 decimals: 2204.63 lb
 * would be over 1000 kg. weightError checks typed weights against this very
 * number, so the limit in the message, the input's max and the check agree.
 */
export function maxWeightIn(unit: WeightUnit): number {
  return unit === 'kg' ? MAX_WEIGHT_KG : Math.floor(kgToUnit(MAX_WEIGHT_KG, unit) * 100) / 100
}

/**
 * A saved weight as the text an editor's number input starts with.
 *
 * Plain digits with a "." (String(), not formatWeight()): a number input
 * rejects "22,5". Pounds get 2 decimals at most: 60 kg is "132.28".
 */
export function weightFieldText(kg: number, unit: WeightUnit): string {
  return unit === 'kg' ? String(kg) : String(roundTo(kgToUnit(kg, unit), 2))
}

/**
 * The kilograms to send for a weight field.
 *
 * A field still showing the text it was filled with (savedText, from
 * weightFieldText) sends the saved kilograms unchanged: opening a workout in
 * pounds and saving it must not turn 60 kg into 60.001. A new field
 * (savedKg null) or a changed one is converted from what was typed.
 *
 * Call it on valid text only (see weightError).
 */
export function fieldToKg(
  text: string,
  unit: WeightUnit,
  savedKg: number | null = null,
  savedText: string | null = null,
): number {
  if (savedKg !== null && text === savedText) return savedKg
  return unitToKg(Number(text), unit)
}

/**
 * What is wrong with a typed weight in the unit, or null if nothing is.
 *
 * Blank is not bodyweight (Number('') would silently be 0). The limit is
 * the typed value against maxWeightIn, before any conversion: after rounding
 * to the gram, 2204.621 to 2204.6237 lb would all become 1000 kg and pass,
 * above the 2204.62 lb the message and the input's max show.
 */
export function weightError(text: string, unit: WeightUnit): string | null {
  if (text.trim() === '') return tActive('form.enterWeight')
  const value = Number(text)
  if (!Number.isFinite(value) || value < 0 || value > maxWeightIn(unit)) {
    return tActive('form.weightRange', { max: formatNumber(maxWeightIn(unit)), unit })
  }
  return null
}

/** A unit read back from storage; anything unknown (or nothing) is the default. */
export function parseWeightUnit(value: string | null): WeightUnit {
  return WEIGHT_UNITS.find((unit) => unit === value) ?? DEFAULT_WEIGHT_UNIT
}

/**
 * What the − / + buttons next to a weight field add or take away: the
 * smallest plate pair, 2.5 lb or 1.25 kg. The input itself keeps step="any",
 * so that any typed weight (61 lb, or 132.28 lb for a saved 60 kg) stays
 * valid: with step="2.5" the browser marks those :invalid.
 */
export function weightStep(unit: WeightUnit): number {
  return unit === 'kg' ? 1.25 : 2.5
}

/**
 * The field's text after one press of − (direction -1) or + (1).
 *
 * A blank field counts as 0. The result stays between 0 and the unit's
 * limit, rounded to 2 decimals to drop float noise. Text that is not a
 * number is left as it is, for validation to report.
 */
export function stepWeight(text: string, unit: WeightUnit, direction: -1 | 1): string {
  const current = text.trim() === '' ? 0 : Number(text)
  if (!Number.isFinite(current)) return text
  const next = roundTo(current + direction * weightStep(unit), 2)
  return String(Math.min(Math.max(next, 0), maxWeightIn(unit)))
}

/** Where the unit is kept: on this device only, until accounts have a setting. */
export const WEIGHT_UNIT_KEY = 'haki_weight_unit'

type UnitStorage = Pick<Storage, 'getItem' | 'setItem'>

/** The browser's storage, or null where there is none or it is refused. */
function browserStorage(): UnitStorage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    // Some browsers throw on access when site data is blocked
    return null
  }
}

/** The unit chosen on this device, or the default when none is saved or readable. */
export function loadWeightUnit(storage: UnitStorage | null = browserStorage()): WeightUnit {
  try {
    return parseWeightUnit(storage?.getItem(WEIGHT_UNIT_KEY) ?? null)
  } catch {
    return DEFAULT_WEIGHT_UNIT
  }
}

/** Keep the unit on this device. Not being able to is no error: it lasts this visit. */
export function saveWeightUnit(
  unit: WeightUnit,
  storage: UnitStorage | null = browserStorage(),
): void {
  try {
    storage?.setItem(WEIGHT_UNIT_KEY, unit)
  } catch {
    // Storage full or blocked: the choice still holds until the page reloads
  }
}

/**
 * The kilograms to send for a weight field that may have been filled from a
 * saved weight (savedKg; null or undefined for a new row): fieldToKg, with
 * the text that saved weight was shown as.
 */
export function weightToSend(
  text: string,
  unit: WeightUnit,
  savedKg: number | null | undefined,
): number {
  return savedKg == null
    ? fieldToKg(text, unit)
    : fieldToKg(text, unit, savedKg, weightFieldText(savedKg, unit))
}
