import { describe, expect, it } from 'vitest'
import {
  DEFAULT_WEIGHT_UNIT,
  KG_PER_LB,
  WEIGHT_UNIT_KEY,
  MAX_WEIGHT_KG,
  fieldToKg,
  kgToUnit,
  loadWeightUnit,
  maxWeightIn,
  parseWeightUnit,
  saveWeightUnit,
  stepWeight,
  unitToKg,
  weightError,
  weightFieldText,
  weightStep,
  weightToSend,
} from './units'
import { MAX_WEIGHT_KG as WORKOUT_MAX_WEIGHT_KG } from './workoutForm'

describe('conversion', () => {
  it('keeps kilograms as they are', () => {
    expect(kgToUnit(61.25, 'kg')).toBe(61.25)
    expect(unitToKg(61.25, 'kg')).toBe(61.25)
  })

  it('converts pounds with the exact factor', () => {
    expect(KG_PER_LB).toBe(0.45359237)
    expect(kgToUnit(KG_PER_LB, 'lb')).toBe(1)
  })

  it('rounds pounds to the gram when converting to kilograms', () => {
    expect(unitToKg(132.28, 'lb')).toBe(60.001)
    expect(unitToKg(135, 'lb')).toBe(61.235)
    expect(unitToKg(61, 'lb')).toBe(27.669)
  })

  it('keeps 0 exactly 0 both ways: a bodyweight set', () => {
    expect(unitToKg(0, 'lb')).toBe(0)
    expect(kgToUnit(0, 'lb')).toBe(0)
    expect(weightFieldText(0, 'lb')).toBe('0')
  })

  it('brings every pound value with up to 2 decimals back unchanged', () => {
    // 0.00 to 2204.62 lb, in steps of 0.01: what is typed is what shows again
    const changed: string[] = []
    for (let hundredths = 0; hundredths <= 220462; hundredths++) {
      const typed = String(hundredths / 100)
      if (weightFieldText(unitToKg(Number(typed), 'lb'), 'lb') !== typed) changed.push(typed)
    }

    expect(changed).toEqual([])
  })
})

describe('editor fields', () => {
  it('starts with plain text a number input accepts, 2 decimals at most in pounds', () => {
    expect(weightFieldText(60, 'kg')).toBe('60')
    expect(weightFieldText(22.5, 'kg')).toBe('22.5')
    expect(weightFieldText(60, 'lb')).toBe('132.28')
    expect(weightFieldText(1000, 'lb')).toBe('2204.62')
  })

  it('sends the saved kilograms when the field was not changed', () => {
    const saved = 60
    const text = weightFieldText(saved, 'lb') // "132.28", which alone would be 60.001 kg

    expect(fieldToKg(text, 'lb', saved, text)).toBe(60)
  })

  it('converts what was typed when the field changed, or is new', () => {
    expect(fieldToKg('135', 'lb', 60, '132.28')).toBe(61.235)
    expect(fieldToKg('135', 'lb')).toBe(61.235)
    expect(fieldToKg('22.5', 'kg')).toBe(22.5)
  })

  it('treats a field typed back to its first text as unchanged', () => {
    expect(fieldToKg('132.28', 'lb', 60, '132.28')).toBe(60)
  })
})

describe('weightError', () => {
  it('uses the same limit as the API and the workout form', () => {
    expect(MAX_WEIGHT_KG).toBe(1000)
    expect(MAX_WEIGHT_KG).toBe(WORKOUT_MAX_WEIGHT_KG)
  })

  it('allows 0 to 1000 kg, or 0 to 2204.62 lb', () => {
    expect(maxWeightIn('kg')).toBe(1000)
    expect(maxWeightIn('lb')).toBe(2204.62)
    for (const [text, unit] of [['0', 'kg'], ['1000', 'kg'], ['0', 'lb'], ['61', 'lb'], ['2204.62', 'lb']] as const) {
      expect(weightError(text, unit), `${text} ${unit}`).toBeNull()
    }
  })

  it('accepts 2204.62 lb, which is under 1000 kg', () => {
    expect(weightError('2204.62', 'lb')).toBeNull()
    expect(unitToKg(2204.62, 'lb')).toBeLessThanOrEqual(MAX_WEIGHT_KG)
  })

  it('rejects 2204.623 lb, above the limit shown, though it rounds to 1000 kg', () => {
    // Rounded to the gram it is 1000 kg: the check must come before rounding
    expect(unitToKg(2204.623, 'lb')).toBe(1000)

    expect(weightError('2204.623', 'lb')).toBe('Weight must be from 0 to 2204.62 lb')
  })

  it('rejects a blank weight instead of treating it as bodyweight', () => {
    for (const text of ['', '  ']) {
      expect(weightError(text, 'lb')).toBe('Enter the weight (0 for bodyweight)')
    }
  })

  it('rejects weights outside the range or not a number, in the unit shown', () => {
    for (const text of ['-1', '2205', 'abc']) {
      expect(weightError(text, 'lb'), text).toBe('Weight must be from 0 to 2204.62 lb')
    }
    expect(weightError('1000.5', 'kg')).toBe('Weight must be from 0 to 1000 kg')
  })
})

describe('parseWeightUnit', () => {
  it('reads a known unit back, and falls back to kilograms otherwise', () => {
    expect(DEFAULT_WEIGHT_UNIT).toBe('kg')
    expect(parseWeightUnit('lb')).toBe('lb')
    expect(parseWeightUnit('kg')).toBe('kg')
    expect(parseWeightUnit('stone')).toBe('kg')
    expect(parseWeightUnit(null)).toBe('kg')
  })
})

describe('stepWeight', () => {
  it('moves by the smallest plate pair: 2.5 lb or 1.25 kg', () => {
    expect(weightStep('lb')).toBe(2.5)
    expect(weightStep('kg')).toBe(1.25)
    expect(stepWeight('61', 'lb', 1)).toBe('63.5')
    expect(stepWeight('61', 'lb', -1)).toBe('58.5')
    expect(stepWeight('22.5', 'kg', -1)).toBe('21.25')
    expect(stepWeight('60', 'kg', 1)).toBe('61.25')
  })

  it('starts a blank field from 0', () => {
    expect(stepWeight('', 'lb', 1)).toBe('2.5')
    expect(stepWeight(' ', 'kg', 1)).toBe('1.25')
  })

  it('never goes below 0 or above the limit', () => {
    expect(stepWeight('1', 'lb', -1)).toBe('0')
    expect(stepWeight('0', 'kg', -1)).toBe('0')
    expect(stepWeight('', 'lb', -1)).toBe('0')
    expect(stepWeight('2203', 'lb', 1)).toBe('2204.62')
    expect(stepWeight('999.5', 'kg', 1)).toBe('1000')
  })

  it('drops float noise and keeps 2 decimals at most', () => {
    expect(stepWeight('132.28', 'lb', 1)).toBe('134.78')
    expect(stepWeight('0.1', 'kg', 1)).toBe('1.35')
  })

  it('leaves text that is not a number for validation to report', () => {
    expect(stepWeight('abc', 'lb', 1)).toBe('abc')
  })

  it('gives back the first text after + then −, so the saved kilograms are sent', () => {
    const saved = weightFieldText(60, 'lb')

    const back = stepWeight(stepWeight(saved, 'lb', 1), 'lb', -1)

    expect(back).toBe(saved)
    expect(fieldToKg(back, 'lb', 60, saved)).toBe(60)
  })
})

describe('the unit kept on this device', () => {
  function memoryStorage() {
    const items = new Map<string, string>()
    return {
      getItem: (key: string) => items.get(key) ?? null,
      setItem: (key: string, value: string) => void items.set(key, value),
    }
  }

  it('is kilograms until something else is saved', () => {
    const storage = memoryStorage()

    expect(loadWeightUnit(storage)).toBe('kg')
    saveWeightUnit('lb', storage)
    expect(storage.getItem(WEIGHT_UNIT_KEY)).toBe('lb')
    expect(loadWeightUnit(storage)).toBe('lb')
  })

  it('falls back to kilograms when there is no storage or it is refused', () => {
    const refusing = {
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
    }

    expect(loadWeightUnit(null)).toBe('kg')
    expect(loadWeightUnit(refusing)).toBe('kg')
    expect(() => saveWeightUnit('lb', refusing)).not.toThrow()
    expect(() => saveWeightUnit('lb', null)).not.toThrow()
  })
})

describe('weightToSend', () => {
  it('sends a saved weight unchanged while its field shows what it was filled with', () => {
    expect(weightToSend('132.28', 'lb', 60)).toBe(60)
    expect(weightToSend('60', 'kg', 60)).toBe(60)
  })

  it('converts a changed field, or a new row', () => {
    expect(weightToSend('135', 'lb', 60)).toBe(61.235)
    expect(weightToSend('135', 'lb', null)).toBe(61.235)
    expect(weightToSend('135', 'lb', undefined)).toBe(61.235)
  })
})
