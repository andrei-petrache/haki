/**
 * The workout editor's set rows in direction A, without React: which plan
 * a block follows, which rows are still the plan untouched, which row is
 * next, and what last time says for each row.
 */
import type { PlannedExercise, ProgramDay, WorkoutSet } from './api'
import { formatSet } from './format'
import type { WeightUnit } from './units'
import { weightFieldText } from './units'
import type { SetFields } from './workoutForm'

/**
 * The planned exercise each block follows: the day's planned exercises,
 * matched by exercise in order, each used once (a day may plan the same
 * exercise twice). Null for a block the plan does not have.
 */
export function plannedForBlocks(
  blocks: { exercise: string }[],
  day: Pick<ProgramDay, 'exercises'> | null,
): (PlannedExercise | null)[] {
  const left = [...(day?.exercises ?? [])]
  return blocks.map((block) => {
    const at = left.findIndex((planned) => String(planned.exercise_id) === block.exercise)
    return at < 0 ? null : left.splice(at, 1)[0]
  })
}

/** Whether a row still holds the plan's values, as the program filled it. */
export function untouchedPlan(
  set: Pick<SetFields, 'reps' | 'weight'>,
  planned: Pick<PlannedExercise, 'reps' | 'weight_kg'> | null,
  unit: WeightUnit,
): boolean {
  return (
    planned !== null &&
    set.reps === String(planned.reps) &&
    set.weight === weightFieldText(planned.weight_kg, unit)
  )
}

/** The first row not ticked as done, or -1 when every row is. */
export function firstOpenRow(done: boolean[], count: number): number {
  for (let i = 0; i < count; i++) if (!done[i]) return i
  return -1
}

/** What a row says beside its values: next, still the plan, or nothing. */
export function rowNote(
  index: number,
  done: boolean,
  firstOpen: number,
  plan: boolean,
): 'next' | 'plan' | null {
  if (done) return null
  if (index === firstOpen) return 'next'
  return plan ? 'plan' : null
}

/** Last time's set in the same place, "5 × 70 kg", or null. */
export function lastSetText(sets: WorkoutSet[] | null | undefined, index: number, unit: WeightUnit): string | null {
  const set = sets?.[index]
  return set ? formatSet(set.reps, set.weight_kg, unit) : null
}
