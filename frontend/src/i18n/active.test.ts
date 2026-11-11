import { afterEach, describe, expect, it } from 'vitest'
import { describeError } from '../api'
import { formatDay, formatSet, formatWeight } from '../format'
import { validateProgram } from '../programForm'
import { weightError } from '../units'
import { NEW_EXERCISE, validateWorkout } from '../workoutForm'
import { activeLocale, formatNumber, setActiveLocale } from './i18n'

afterEach(() => setActiveLocale('en'))

const blankSet = {
  performedOn: '2026-11-02',
  note: '',
  exercises: [{ exercise: '1', newName: '', sets: [{ reps: '', weight: '60' }] }],
}

describe('texts made outside components', () => {
  it('are English until App sets the language', () => {
    expect(activeLocale()).toBe('en')
    expect(validateWorkout(blankSet, '2026-11-02')).toEqual({ 'exercise.0.set.0': 'Enter the reps' })
    expect(formatSet(8, 0)).toBe('8 × bodyweight')
  })

  it('follow Romanian once it is active', () => {
    setActiveLocale('ro')

    expect(validateWorkout(blankSet, '2026-11-02')).toEqual({ 'exercise.0.set.0': 'Scrie repetările' })
    expect(weightError('', 'kg')).toBe('Scrie greutatea (0 pentru greutatea corpului)')
    expect(weightError('3000', 'lb')).toBe('Greutatea trebuie să fie între 0 și 2204,62 lb')
    expect(formatSet(8, 0)).toBe('8 × greutatea corpului')
    expect(formatWeight(61.25)).toBe('61,25')
    expect(formatDay('2026-11-02')).toMatch(/2026/)
    expect(describeError(new Error('network'))).toBe('Serverul nu răspunde')
  })

  it('give program errors in Romanian, "de" from 20 on', () => {
    setActiveLocale('ro')
    const tooMany = {
      name: 'P',
      days: [
        {
          position: 1,
          name: 'Zi',
          exercises: Array.from({ length: 21 }, () => ({
            exercise: NEW_EXERCISE,
            newName: 'X',
            sets: '3',
            reps: '5',
            weight: '0',
          })),
        },
      ],
    }

    expect(validateProgram(tooMany)['day.0.exercises']).toBe('O zi poate avea cel mult 20 de exerciții')
    expect(validateProgram({ name: ' ', days: [] })).toEqual({
      name: 'Scrie un nume pentru program',
      days: 'Adaugă cel puțin o zi',
    })
  })

  it('format numbers for messages without grouping', () => {
    expect(formatNumber(2204.62)).toBe('2204.62')
    setActiveLocale('ro')
    expect(formatNumber(2204.62)).toBe('2204,62')
  })
})
