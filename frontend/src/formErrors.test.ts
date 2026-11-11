import { describe, expect, it } from 'vitest'
import { firstChangedRow, withoutKeys, withoutRowsFrom } from './formErrors'

describe('withoutKeys', () => {
  it('drops the given keys and keeps the rest', () => {
    const errors = { name: 'Enter a name', 'day.0.name': 'Enter a name for the day' }

    expect(withoutKeys(errors, 'name', 'missing')).toEqual({
      'day.0.name': 'Enter a name for the day',
    })
    expect(errors).toHaveProperty('name')
  })

  it('returns the same object when there is nothing to drop', () => {
    const errors = { name: 'Enter a name' }

    expect(withoutKeys(errors, 'note')).toBe(errors)
  })
})

describe('withoutRowsFrom', () => {
  const errors = {
    exercises: 'Add at least one exercise',
    'exercise.1': 'Choose an exercise',
    'exercise.2': 'Choose an exercise',
    'exercise.2.set.0': 'Enter the reps',
    'exercise.10.sets': 'Add at least one set',
  }

  it('drops the rows from the index on, with what is inside them', () => {
    expect(withoutRowsFrom(errors, 'exercise', 2)).toEqual({
      exercises: 'Add at least one exercise',
      'exercise.1': 'Choose an exercise',
    })
  })

  it('works on rows nested in a row', () => {
    const nested = { 'day.0.exercise.0': 'a', 'day.0.exercise.1.values': 'b', 'day.1.exercise.1': 'c' }

    expect(withoutRowsFrom(nested, 'day.0.exercise', 1)).toEqual({
      'day.0.exercise.0': 'a',
      'day.1.exercise.1': 'c',
    })
  })
})

describe('firstChangedRow', () => {
  const a = { n: 1 }
  const b = { n: 2 }
  const c = { n: 3 }

  it('finds a replaced or removed row', () => {
    expect(firstChangedRow([a, b, c], [a, { n: 2 }, c])).toBe(1)
    expect(firstChangedRow([a, b, c], [a, c])).toBe(1)
  })

  it('gives the old length when rows were only added at the end', () => {
    expect(firstChangedRow([a, b], [a, b, c])).toBe(2)
    expect(firstChangedRow([a, b], [a, b])).toBe(2)
  })
})
