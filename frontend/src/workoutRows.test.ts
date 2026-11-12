import { describe, expect, it } from 'vitest'
import { firstOpenRow, lastSetText, plannedForBlocks, rowNote, untouchedPlan } from './workoutRows'

const bench = { exercise_id: 1, exercise_name: 'Bench', sets: 4, reps: 6, weight_kg: 72.5 }
const squat = { exercise_id: 2, exercise_name: 'Squat', sets: 5, reps: 5, weight_kg: 100 }

describe('plannedForBlocks', () => {
  it('matches each block to its planned exercise, in order, each once', () => {
    const day = { exercises: [bench, squat, { ...bench, reps: 10, weight_kg: 50 }] }
    const blocks = [{ exercise: '2' }, { exercise: '1' }, { exercise: '1' }, { exercise: '1' }, { exercise: '' }]

    const planned = plannedForBlocks(blocks, day)

    expect(planned.map((p) => p && `${p.exercise_id}:${p.reps}`)).toEqual(['2:5', '1:6', '1:10', null, null])
  })

  it('has nothing to match without a plan', () => {
    expect(plannedForBlocks([{ exercise: '1' }], null)).toEqual([null])
  })
})

describe('the rows', () => {
  it('knows a row still holding the plan, in kg or in lb', () => {
    expect(untouchedPlan({ reps: '6', weight: '72.5' }, bench, 'kg')).toBe(true)
    expect(untouchedPlan({ reps: '7', weight: '72.5' }, bench, 'kg')).toBe(false)
    expect(untouchedPlan({ reps: '6', weight: '159.84' }, bench, 'lb')).toBe(true)
    expect(untouchedPlan({ reps: '6', weight: '72.5' }, null, 'kg')).toBe(false)
  })

  it('finds the first row not done, and says next, plan or nothing', () => {
    expect(firstOpenRow([true, false, false], 3)).toBe(1)
    expect(firstOpenRow([true, true], 2)).toBe(-1)
    expect(firstOpenRow([], 2)).toBe(0)
    expect(rowNote(1, false, 1, true)).toBe('next')
    expect(rowNote(2, false, 1, true)).toBe('plan')
    expect(rowNote(2, false, 1, false)).toBeNull()
    expect(rowNote(0, true, 1, true)).toBeNull()
  })

  it('reads last time row by row', () => {
    const last = [
      { reps: 5, weight_kg: 70 },
      { reps: 12, weight_kg: 0 },
    ]
    expect(lastSetText(last, 0, 'kg')).toBe('5 × 70 kg')
    expect(lastSetText(last, 1, 'kg')).toBe('12 × bodyweight')
    expect(lastSetText(last, 2, 'kg')).toBeNull()
    expect(lastSetText(null, 0, 'kg')).toBeNull()
  })
})
