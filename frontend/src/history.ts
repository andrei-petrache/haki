/**
 * What the workout history says about an exercise: the sets of last time
 * and the best set so far. Built in the browser from the existing workout
 * endpoints, over the most recent workouts only (HISTORY_LIMIT): beyond
 * those, it says nothing rather than something wrong. An endpoint per
 * exercise would cover all of it in one call (see the backend list).
 */
import { WORKOUTS_PAGE_SIZE, fetchWorkout, fetchWorkouts } from './api'
import type { Workout, WorkoutSet } from './api'

/** How many recent workouts are read: 2 list pages, then their details. */
export const HISTORY_LIMIT = 40

/** The most recent workouts with everything in them, newest first. */
export async function loadHistory(
  token: string,
  limit: number = HISTORY_LIMIT,
  concurrency: number = 4,
): Promise<Workout[]> {
  const ids: number[] = []
  while (ids.length < limit) {
    const page = await fetchWorkouts(token, WORKOUTS_PAGE_SIZE, ids.length)
    ids.push(...page.map((workout) => workout.id))
    if (page.length < WORKOUTS_PAGE_SIZE) break
  }
  const wanted = ids.slice(0, limit)
  const details: Workout[] = new Array(wanted.length)
  let next = 0
  // A few at a time: fast enough, without a burst of 40 requests
  async function worker() {
    while (next < wanted.length) {
      const index = next++
      details[index] = await fetchWorkout(token, wanted[index])
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, wanted.length) }, worker))
  return details
}

/** The workout being edited, which history must not count: null for a new one. */
export type Current = { id: number; performed_on: string } | null

/** Newest first, as the list: by day, then by id for workouts on the same day. */
function newestFirst(a: Workout, b: Workout): number {
  return a.performed_on === b.performed_on ? b.id - a.id : a.performed_on < b.performed_on ? 1 : -1
}

/** Workouts before the current one (all of them for a new workout). */
function earlier(history: Workout[], current: Current): Workout[] {
  return history.filter(
    (workout) =>
      current === null ||
      workout.performed_on < current.performed_on ||
      (workout.performed_on === current.performed_on && workout.id < current.id),
  )
}

/** Every set of an exercise in one workout (it may appear in several blocks). */
function setsOf(workout: Workout, exerciseId: number): WorkoutSet[] {
  return workout.exercises
    .filter((item) => item.exercise_id === exerciseId)
    .flatMap((item) => item.sets)
}

/** The sets of the latest earlier workout with this exercise, or null. */
export function lastTime(
  history: Workout[],
  exerciseId: number,
  current: Current = null,
): { performedOn: string; sets: WorkoutSet[] } | null {
  const workout = [...earlier(history, current)]
    .sort(newestFirst)
    .find((candidate) => setsOf(candidate, exerciseId).length > 0)
  return workout ? { performedOn: workout.performed_on, sets: setsOf(workout, exerciseId) } : null
}

/**
 * Whether set a is better than set b: heavier, or as heavy with more reps.
 * Bodyweight sets (0 kg) therefore compare by reps.
 */
export function beats(a: WorkoutSet, b: WorkoutSet): boolean {
  return a.weight_kg > b.weight_kg || (a.weight_kg === b.weight_kg && a.reps > b.reps)
}

/** The best of some sets, or null when there are none. */
export function topSet(sets: WorkoutSet[]): WorkoutSet | null {
  return sets.reduce<WorkoutSet | null>((best, set) => (best === null || beats(set, best) ? set : best), null)
}

/** The best earlier set of an exercise, or null when it was never done before. */
export function bestBefore(history: Workout[], exerciseId: number, current: Current = null): WorkoutSet | null {
  return topSet(earlier(history, current).flatMap((workout) => setsOf(workout, exerciseId)))
}

/**
 * Where the records of a workout are: for each exercise, its best set in
 * this workout, when it beats every earlier set in the history. An
 * exercise done for the first time has nothing to beat, so no record.
 * Keys are "block.set" positions, the first one for a set that appears twice.
 */
export function recordPositions(workout: Workout, history: Workout[]): Set<string> {
  const current: Current = { id: workout.id, performed_on: workout.performed_on }
  const positions = new Set<string>()
  const exerciseIds = new Set(workout.exercises.map((item) => item.exercise_id))
  for (const exerciseId of exerciseIds) {
    const best = bestBefore(history, exerciseId, current)
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
