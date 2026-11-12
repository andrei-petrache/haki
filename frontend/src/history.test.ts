import { afterEach, describe, expect, it, vi } from 'vitest'
import type { Workout } from './api'
import { beats, bestBefore, lastTime, liveRecordIndex, loadHistory, recordPositions, topSet } from './history'

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

// Newest first, as the API lists them
const HISTORY = [
  workout(5, '2026-11-08', [SQUAT, [[5, 100]]]),
  workout(4, '2026-11-06', [BENCH, [[5, 70]]], [BENCH, [[3, 72.5]]]),
  workout(3, '2026-11-06', [BENCH, [[8, 60]]]),
  workout(2, '2026-11-01', [BENCH, [[8, 65], [6, 65]]]),
]

describe('lastTime', () => {
  it('gives every set of the latest workout with the exercise, all its blocks', () => {
    expect(lastTime(HISTORY, BENCH)).toEqual({
      performedOn: '2026-11-06',
      sets: [
        { reps: 5, weight_kg: 70 },
        { reps: 3, weight_kg: 72.5 },
      ],
    })
  })

  it('skips the workout being edited and anything after it', () => {
    expect(lastTime(HISTORY, BENCH, { id: 4, performed_on: '2026-11-06' })).toEqual({
      performedOn: '2026-11-06',
      sets: [{ reps: 8, weight_kg: 60 }],
    })
    expect(lastTime(HISTORY, BENCH, { id: 3, performed_on: '2026-11-06' })?.performedOn).toBe('2026-11-01')
  })

  it('is null for an exercise never done before', () => {
    expect(lastTime(HISTORY, 99)).toBeNull()
    expect(lastTime(HISTORY, BENCH, { id: 2, performed_on: '2026-11-01' })).toBeNull()
  })
})

describe('records', () => {
  it('ranks heavier first, then more reps at the same weight', () => {
    expect(beats({ reps: 1, weight_kg: 72.5 }, { reps: 8, weight_kg: 70 })).toBe(true)
    expect(beats({ reps: 6, weight_kg: 70 }, { reps: 5, weight_kg: 70 })).toBe(true)
    expect(beats({ reps: 5, weight_kg: 70 }, { reps: 5, weight_kg: 70 })).toBe(false)
    // Bodyweight: by reps
    expect(beats({ reps: 12, weight_kg: 0 }, { reps: 10, weight_kg: 0 })).toBe(true)
  })

  it('finds the best set, or none', () => {
    expect(topSet([{ reps: 8, weight_kg: 60 }, { reps: 3, weight_kg: 72.5 }, { reps: 5, weight_kg: 72.5 }])).toEqual({
      reps: 5,
      weight_kg: 72.5,
    })
    expect(topSet([])).toBeNull()
  })

  it('finds the best earlier set, not counting the workout itself', () => {
    expect(bestBefore(HISTORY, BENCH)).toEqual({ reps: 3, weight_kg: 72.5 })
    expect(bestBefore(HISTORY, BENCH, { id: 4, performed_on: '2026-11-06' })).toEqual({ reps: 8, weight_kg: 65 })
    expect(bestBefore(HISTORY, BENCH, { id: 2, performed_on: '2026-11-01' })).toBeNull()
  })
})

describe('loadHistory', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('reads list pages up to the limit, then each workout, in list order', async () => {
    const all = Array.from({ length: 25 }, (_, i) => workout(100 - i, '2026-11-01', [BENCH, [[5, 60]]]))
    const asked: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        asked.push(url)
        const list = /\/workouts\?limit=(\d+)&offset=(\d+)/.exec(url)
        const body = list
          ? all.slice(Number(list[2]), Number(list[2]) + Number(list[1])).map((w) => ({ id: w.id }))
          : all.find((w) => url.endsWith(`/workouts/${w.id}`))
        return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }),
    )

    const history = await loadHistory('a-token', 22, 3)

    expect(history.map((w) => w.id)).toEqual(all.slice(0, 22).map((w) => w.id))
    expect(asked.filter((url) => url.includes('?limit='))).toHaveLength(2)
    expect(asked.filter((url) => !url.includes('?limit='))).toHaveLength(22)
  })
})

describe('recordPositions', () => {
  it('marks the best set of an exercise that beats everything before it', () => {
    const today = workout(9, '2026-11-10', [BENCH, [[5, 72.5], [4, 75]]], [SQUAT, [[5, 100]]])

    // Bench: 75 beats 72.5; squat: 5 x 100 only ties the best before
    expect([...recordPositions(today, [today, ...HISTORY])]).toEqual(['0.1'])
  })

  it('marks nothing for an exercise done for the first time', () => {
    const first = workout(9, '2026-11-10', [77, [[5, 50]]])

    expect(recordPositions(first, [first, ...HISTORY]).size).toBe(0)
  })

  it('does not let a workout beat itself or later workouts', () => {
    expect(recordPositions(HISTORY[3], HISTORY).size).toBe(0)
  })

  it('compares bodyweight sets by reps', () => {
    const before = workout(1, '2026-10-01', [3, [[10, 0]]])
    const today = workout(9, '2026-11-10', [3, [[12, 0], [8, 0]]])

    expect([...recordPositions(today, [today, before])]).toEqual(['0.0'])
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
