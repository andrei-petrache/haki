/**
 * The program editor's state and the pure functions around it: validation,
 * which exercises to create first, and the request body. No React, no fetch.
 */
import type { Exercise, ProgramInput } from './api'
import {
  MAX_NAME_LENGTH,
  MAX_SETS,
  NEW_EXERCISE,
  choiceError,
  exerciseIdOf,
  newExerciseNames,
  setError,
} from './workoutForm'
import { firstChangedRow, withoutKeys, withoutRowsFrom } from './formErrors'
import type { FormErrors } from './formErrors'
import { weightToSend } from './units'
import type { WeightUnit } from './units'

export type { FormErrors } from './formErrors'

// Must match the limits in backend/app/schemas.py
export const MAX_DAYS = 7
export const MAX_EXERCISES_PER_DAY = 20

/** One planned exercise: `sets` sets of `reps` at `weight` (in the chosen unit), all as typed. */
export type PlannedFields = {
  exercise: string // an exercise id, '' (not chosen yet) or NEW_EXERCISE
  newName: string // used only when exercise is NEW_EXERCISE
  sets: string
  reps: string
  weight: string
}

export type DayFields = {
  position: number // the day's place in the plan, 1 to MAX_DAYS
  name: string
  exercises: PlannedFields[]
}

export type ProgramFields = {
  name: string
  days: DayFields[]
}

/** A new planned exercise: with an empty catalog, the only choice is a new name. */
export function emptyPlanned(catalog: Exercise[]): PlannedFields {
  return {
    exercise: catalog.length === 0 ? NEW_EXERCISE : '',
    newName: '',
    sets: '',
    reps: '',
    weight: '',
  }
}

/** The first place in the plan no day has taken yet, or null when all are. */
export function nextFreePosition(days: DayFields[]): number | null {
  const taken = new Set(days.map((day) => day.position))
  for (let position = 1; position <= MAX_DAYS; position++) {
    if (!taken.has(position)) return position
  }
  return null
}

/** A new day at the first free place, or null when the week is full. */
export function newDay(days: DayFields[], catalog: Exercise[]): DayFields | null {
  const position = nextFreePosition(days)
  if (position === null) return null
  return { position, name: '', exercises: [emptyPlanned(catalog)] }
}

export function newProgramFields(catalog: Exercise[]): ProgramFields {
  return { name: '', days: [newDay([], catalog) as DayFields] }
}

// Validation errors are keyed by where they belong in the form (see the
// *Key functions), so each one can be shown next to its field or row.

export const NAME_KEY = 'name'
export const DAYS_KEY = 'days'

export function dayNameKey(day: number): string {
  return `day.${day}.name`
}

export function dayPositionKey(day: number): string {
  return `day.${day}.position`
}

export function dayExercisesKey(day: number): string {
  return `day.${day}.exercises`
}

export function plannedExerciseKey(day: number, index: number): string {
  return `day.${day}.exercise.${index}`
}

export function plannedValuesKey(day: number, index: number): string {
  return `day.${day}.exercise.${index}.values`
}

/** What is wrong with a name (the program's or a day's), or null if nothing is. */
function nameError(name: string, what: string): string | null {
  const trimmed = name.trim()
  if (trimmed === '') return `Enter ${what}`
  if (trimmed.length > MAX_NAME_LENGTH) {
    return `The name can have at most ${MAX_NAME_LENGTH} characters`
  }
  return null
}

/** What is wrong with a planned exercise's numbers, or null if nothing is. */
function valuesError(item: PlannedFields, unit: WeightUnit): string | null {
  const sets = item.sets.trim() === '' ? null : Number(item.sets)
  if (sets === null) return 'Enter the sets'
  if (!Number.isInteger(sets) || sets < 1 || sets > MAX_SETS) {
    return `Sets must be a whole number from 1 to ${MAX_SETS}`
  }
  // Reps and weight follow the same rules as a logged set
  return setError({ reps: item.reps, weight: item.weight }, unit)
}

/** Everything the API would reject, found before sending. Empty means valid. */
export function validateProgram(fields: ProgramFields, unit: WeightUnit = 'kg'): FormErrors {
  const errors: FormErrors = {}

  const name = nameError(fields.name, 'a name for the program')
  if (name) errors[NAME_KEY] = name
  if (fields.days.length === 0) {
    errors[DAYS_KEY] = 'Add at least one day'
  } else if (fields.days.length > MAX_DAYS) {
    errors[DAYS_KEY] = `A program can have at most ${MAX_DAYS} days`
  }

  // Two days on the same place in the plan: the API answers 409, so say it
  // here, next to the later one
  const seen = new Set<number>()
  fields.days.forEach((day, d) => {
    if (!Number.isInteger(day.position) || day.position < 1 || day.position > MAX_DAYS) {
      errors[dayPositionKey(d)] = `Choose a day from 1 to ${MAX_DAYS}`
    } else if (seen.has(day.position)) {
      errors[dayPositionKey(d)] = `Another day is already day ${day.position}`
    }
    seen.add(day.position)

    const dayName = nameError(day.name, 'a name for the day')
    if (dayName) errors[dayNameKey(d)] = dayName

    if (day.exercises.length === 0) {
      errors[dayExercisesKey(d)] = 'Add at least one exercise'
    } else if (day.exercises.length > MAX_EXERCISES_PER_DAY) {
      errors[dayExercisesKey(d)] =
        `A day can have at most ${MAX_EXERCISES_PER_DAY} exercises`
    }
    day.exercises.forEach((item, e) => {
      const choice = choiceError(item)
      if (choice) errors[plannedExerciseKey(d, e)] = choice
      const values = valuesError(item, unit)
      if (values) errors[plannedValuesKey(d, e)] = values
    })
  })

  return errors
}

/** The new exercise names, across all days, that need a POST /exercises first. */
export function programExercisesToCreate(
  fields: ProgramFields,
  catalog: Exercise[],
): string[] {
  return newExerciseNames(
    fields.days.flatMap((day) => day.exercises),
    catalog,
  )
}

/**
 * The request body for POST /programs.
 *
 * Call it on valid fields only, once every name from programExercisesToCreate
 * is in the catalog. Days go in the order shown; the API returns them by
 * position.
 */
export function toProgramInput(
  fields: ProgramFields,
  catalog: Exercise[],
  unit: WeightUnit = 'kg',
): ProgramInput {
  return {
    name: fields.name.trim(),
    days: fields.days.map((day) => ({
      position: day.position,
      name: day.name.trim(),
      exercises: day.exercises.map((item) => ({
        exercise_id: exerciseIdOf(item, catalog),
        sets: Number(item.sets),
        reps: Number(item.reps),
        // A new program only: no saved weight to keep
        weight_kg: weightToSend(item.weight, unit, null),
      })),
    })),
  }
}

/**
 * The errors without any day's position error. Positions depend on each
 * other (two days on one place): moving or removing one day can fix another.
 */
function withoutPositionErrors(errors: FormErrors): FormErrors {
  return withoutKeys(errors, ...Object.keys(errors).filter((key) => /^day\.\d+\.position$/.test(key)))
}

/**
 * The errors left once day index changed from before to after: each field
 * the user changed loses its error, the others keep theirs until the next
 * Save. An exercise added or removed also clears the day's "exercises" error,
 * and a removed one the errors of the exercises after it, which moved up.
 */
export function clearDayErrors(
  errors: FormErrors,
  index: number,
  before: DayFields,
  after: DayFields,
): FormErrors {
  let left = errors
  if (after.name !== before.name) left = withoutKeys(left, dayNameKey(index))
  if (after.position !== before.position) left = withoutPositionErrors(left)
  if (after.exercises.length !== before.exercises.length) {
    left = withoutKeys(left, dayExercisesKey(index))
    return withoutRowsFrom(
      left,
      `day.${index}.exercise`,
      firstChangedRow(before.exercises, after.exercises),
    )
  }
  before.exercises.forEach((item, e) => {
    const changed = after.exercises[e]
    if (changed === item) return
    if (changed.exercise !== item.exercise || changed.newName !== item.newName) {
      left = withoutKeys(left, plannedExerciseKey(index, e))
    }
    if (changed.sets !== item.sets || changed.reps !== item.reps || changed.weight !== item.weight) {
      left = withoutKeys(left, plannedValuesKey(index, e))
    }
  })
  return left
}

/** The errors left once day index is removed (the days after it move up). */
export function clearRemovedDay(errors: FormErrors, index: number): FormErrors {
  return withoutPositionErrors(withoutRowsFrom(withoutKeys(errors, DAYS_KEY), 'day', index))
}
