/**
 * What the workout history says about an exercise: the sets of last time
 * and the best set so far, from GET /exercises/{id}/last and /best over
 * all of the user's workouts, and the rules that compare sets.
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchBestSet, fetchLastSession } from './api'
import type { BestSet, LastSession, Workout, WorkoutSet } from './api'

export type ExerciseHistory = { last: LastSession | null; best: BestSet | null }

/**
 * Whether set a is better than set b: heavier, or as heavy with more reps.
 * Bodyweight sets (0 kg) therefore compare by reps. The server's /best
 * uses the same rule.
 */
export function beats(a: WorkoutSet, b: WorkoutSet): boolean {
  return a.weight_kg > b.weight_kg || (a.weight_kg === b.weight_kg && a.reps > b.reps)
}

/** The best of some sets, or null when there are none. */
export function topSet(sets: WorkoutSet[]): WorkoutSet | null {
  return sets.reduce<WorkoutSet | null>((best, set) => (best === null || beats(set, best) ? set : best), null)
}

/** Every set of an exercise in one workout (it may appear in several blocks). */
function setsOf(workout: Workout, exerciseId: number): WorkoutSet[] {
  return workout.exercises
    .filter((item) => item.exercise_id === exerciseId)
    .flatMap((item) => item.sets)
}

/**
 * Where the records of a workout are: for each exercise, its best set in
 * this workout, when it beats the best set before this workout (bests,
 * by exercise id). An exercise done for the first time (null) has nothing
 * to beat, and one not loaded yet (missing) is not judged.
 * Keys are "block.set" positions, the first one for a set that appears twice.
 */
export function recordPositions(
  workout: Workout,
  bests: ReadonlyMap<number, WorkoutSet | null>,
): Set<string> {
  const positions = new Set<string>()
  const exerciseIds = new Set(workout.exercises.map((item) => item.exercise_id))
  for (const exerciseId of exerciseIds) {
    const best = bests.get(exerciseId)
    const top = topSet(setsOf(workout, exerciseId))
    if (!best || !top || !beats(top, best)) continue
    const at = workout.exercises.flatMap((item, block) =>
      item.exercise_id === exerciseId
        ? item.sets.map((set, index) => ({ set, key: `${block}.${index}` }))
        : [],
    )
    const first = at.find(({ set }) => set.reps === top.reps && set.weight_kg === top.weight_kg)
    if (first) positions.add(first.key)
  }
  return positions
}

/**
 * The set of a row being typed that would be a record: its best valid set,
 * when it beats the best earlier set (null: never done before, no record).
 * Sets still invalid are given as null and skipped. Returns its index, or
 * null when none would be.
 */
export function liveRecordIndex(sets: (WorkoutSet | null)[], best: WorkoutSet | null): number | null {
  if (!best) return null
  const top = topSet(sets.filter((set): set is WorkoutSet => set !== null))
  if (!top || !beats(top, best)) return null
  return sets.findIndex((set) => set !== null && set.reps === top.reps && set.weight_kg === top.weight_kg)
}

/** The exercise ids worth asking about: valid ones, each once, in order. */
export function historyIds(exerciseIds: number[]): number[] {
  return [...new Set(exerciseIds.filter((id) => Number.isInteger(id) && id > 0))].sort((a, b) => a - b)
}

/**
 * The history of each exercise listed, loaded once per exercise (two small
 * requests) and kept while the list changes. before: the workout being
 * edited or shown, so only workouts before it count; null for a new
 * workout. Exercises still loading are missing from the map. A failed
 * load counts as no history: nothing is shown, the form still works.
 */
export function useExerciseHistory(
  token: string,
  exerciseIds: number[],
  before: number | null,
): ReadonlyMap<number, ExerciseHistory> {
  const [loaded, setLoaded] = useState<ReadonlyMap<string, ExerciseHistory>>(() => new Map())
  // Keys already asked for, so a re-render never asks twice
  const requested = useRef(new Set<string>())
  const ids = historyIds(exerciseIds).join(',')
  const keyOf = (id: number) => `${before ?? 'new'}:${id}`

  useEffect(() => {
    for (const id of ids ? ids.split(',').map(Number) : []) {
      const key = `${before ?? 'new'}:${id}`
      if (requested.current.has(key)) continue
      requested.current.add(key)
      const store = (history: ExerciseHistory) =>
        setLoaded((old) => new Map(old).set(key, history))
      Promise.all([fetchLastSession(token, id, before), fetchBestSet(token, id, before)])
        .then(([last, best]) => store({ last, best }))
        .catch(() => store({ last: null, best: null }))
    }
  }, [token, ids, before])

  return useMemo(() => {
    const result = new Map<number, ExerciseHistory>()
    for (const id of ids ? ids.split(',').map(Number) : []) {
      const history = loaded.get(keyOf(id))
      if (history) result.set(id, history)
    }
    return result
    // keyOf only reads before, which is listed
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded, ids, before])
}
