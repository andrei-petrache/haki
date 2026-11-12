import { describe, expect, it } from 'vitest'
import type { Workout } from './api'
import { beats, historyIds, liveRecordIndex, recordPositions, topSet } from './history'

const BENCH = 1
const SQUAT = 2

function workout(id: number, performedOn: string, ...blocks: [number, [number, number][]][]): Workout {
  return {
    id,
    performed_on: performedOn,
    note: null,
    exercises: blocks.map(([exerciseId, sets]) => ({
      exercise_id: exerciseId,
      exercise_name: `E${exerciseId}`,
      sets: sets.map(([reps, weight]) => ({ reps, weight_kg: weight })),
    })),
  }
}

describe('comparing sets', () => {
  it('ranks heavier first, then more reps at the same weight', () => {
    expect(beats({ reps: 1, weight_kg: 72.5 }, { reps: 8, weight_kg: 70 })).toBe(true)
    expect(beats({ reps: 6, weight_kg: 70 }, { reps: 5, weight_kg: 70 })).toBe(true)
    expect(beats({ reps: 5, weight_kg: 70 }, { reps: 5, weight_kg: 70 })).toBe(false)
    expect(beats({ reps: 20, weight_kg: 0 }, { reps: 15, weight_kg: 0 })).toBe(true)
  })

  it('finds the best set, or none', () => {
    expect(topSet([{ reps: 8, weight_kg: 60 }, { reps: 3, weight_kg: 72.5 }, { reps: 5, weight_kg: 70 }])).toEqual({
      reps: 3,
      weight_kg: 72.5,
    })
    expect(topSet([])).toBeNull()
  })
})

describe('recordPositions', () => {
  const today = workout(9, '2026-11-12', [BENCH, [[5, 70], [3, 75]]], [SQUAT, [[5, 100]]], [BENCH, [[3, 75]]])

  it('marks the first best set of an exercise that beats the best before', () => {
    const bests = new Map([
      [BENCH, { reps: 3, weight_kg: 72.5 }],
      [SQUAT, { reps: 5, weight_kg: 100 }],
    ])

    expect([...recordPositions(today, bests)]).toEqual(['0.1'])
  })

  it('marks nothing for an exercise done for the first time, or not loaded yet', () => {
    expect(recordPositions(today, new Map([[BENCH, null]])).size).toBe(0)
    expect(recordPositions(today, new Map()).size).toBe(0)
  })

  it('compares bodyweight sets by reps', () => {
    const pullUps = workout(9, '2026-11-12', [SQUAT, [[12, 0]]])

    expect([...recordPositions(pullUps, new Map([[SQUAT, { reps: 10, weight_kg: 0 }]]))]).toEqual(['0.0'])
  })
})

describe('liveRecordIndex', () => {
  const best = { reps: 3, weight_kg: 72.5 }

  it('points at the typed set that beats the best before', () => {
    expect(liveRecordIndex([{ reps: 5, weight_kg: 70 }, { reps: 2, weight_kg: 75 }], best)).toBe(1)
  })

  it('skips sets still being typed, and needs something to beat', () => {
    expect(liveRecordIndex([null, { reps: 4, weight_kg: 72.5 }], best)).toBe(1)
    expect(liveRecordIndex([{ reps: 3, weight_kg: 72.5 }], best)).toBeNull()
    expect(liveRecordIndex([{ reps: 10, weight_kg: 100 }], null)).toBeNull()
    expect(liveRecordIndex([null, null], best)).toBeNull()
  })
})

describe('historyIds', () => {
  it('keeps valid ids once, in order: rows not chosen yet are 0 or NaN', () => {
    expect(historyIds([3, 1, 3, 0, Number.NaN, -2, 1.5])).toEqual([1, 3])
  })
})
