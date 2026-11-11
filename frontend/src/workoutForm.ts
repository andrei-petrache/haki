/**
 * The workout editor's state and the pure functions around it: validation,
 * which exercises to create first, and the request body. No React, no fetch.
 */
import type { Exercise, Workout, WorkoutInput } from './api'
import { localDateString, shiftDate } from './format'
import { firstChangedRow, withoutKeys, withoutRowsFrom } from './formErrors'
import { tActive } from './i18n/i18n'
import type { FormErrors } from './formErrors'
import { weightError, weightFieldText, weightToSend } from './units'
import type { WeightUnit } from './units'

export type { FormErrors } from './formErrors'

// Must match the limits in backend/app/schemas.py
export const EARLIEST_WORKOUT_DATE = '2000-01-01'
export const MAX_EXERCISES = 50
export const MAX_SETS = 50
export const MAX_NAME_LENGTH = 100
export const MAX_NOTE_LENGTH = 500
export const MAX_REPS = 1000
// One limit for the whole app, kept with the unit conversion
export { MAX_WEIGHT_KG } from './units'

/** The select's value for "type a new exercise name". */
export const NEW_EXERCISE = 'new'

// Form inputs hold text; convert to numbers only on submit
export type SetFields = {
  reps: string
  weight: string // in the chosen unit
  // The kilograms the row was filled with, when editing a saved workout:
  // sent back unchanged unless the weight is edited (see weightToSend)
  savedKg?: number | null
}

export type ExerciseFields = {
  exercise: string // an exercise id, '' (not chosen yet) or NEW_EXERCISE
  newName: string // used only when exercise is NEW_EXERCISE
  sets: SetFields[]
}

export type WorkoutFields = {
  performedOn: string
  note: string
  exercises: ExerciseFields[]
}

export function emptySet(): SetFields {
  return { reps: '', weight: '' }
}

/** A new exercise block: with an empty catalog, the only choice is a new name. */
export function emptyExercise(catalog: Exercise[]): ExerciseFields {
  return {
    exercise: catalog.length === 0 ? NEW_EXERCISE : '',
    newName: '',
    sets: [emptySet()],
  }
}

export function newWorkoutFields(today: string, catalog: Exercise[]): WorkoutFields {
  return { performedOn: today, note: '', exercises: [emptyExercise(catalog)] }
}

/** The editor prefilled with a saved workout, its weights shown in the unit. */
export function workoutToFields(workout: Workout, unit: WeightUnit = 'kg'): WorkoutFields {
  return {
    performedOn: workout.performed_on,
    note: workout.note ?? '',
    exercises: workout.exercises.map((item) => ({
      exercise: String(item.exercise_id),
      newName: '',
      // Plain text, not formatWeight(): a number input rejects "22,5"
      sets: item.sets.map((set) => ({
        reps: String(set.reps),
        weight: weightFieldText(set.weight_kg, unit),
        savedKg: set.weight_kg,
      })),
    })),
  }
}

// Validation errors are keyed by where they belong in the form (see the
// *Key functions), so each one can be shown next to its field or row.

export const DATE_KEY = 'performedOn'
export const NOTE_KEY = 'note'
export const EXERCISES_KEY = 'exercises'

export function exerciseKey(index: number): string {
  return `exercise.${index}`
}

export function setsKey(index: number): string {
  return `exercise.${index}.sets`
}

export function setKey(index: number, setIndex: number): string {
  return `exercise.${index}.set.${setIndex}`
}

/** The number in a field, or null when it is blank. */
function parseNumber(text: string): number | null {
  return text.trim() === '' ? null : Number(text)
}

/** What is wrong with one set row (reps and weight), or null if nothing is. */
export function setError(set: SetFields, unit: WeightUnit = 'kg'): string | null {
  const reps = parseNumber(set.reps)
  if (reps === null) return tActive('form.enterReps')
  if (!Number.isInteger(reps) || reps < 1 || reps > MAX_REPS) {
    return tActive('form.repsRange', { max: MAX_REPS })
  }
  // Blank is not bodyweight; the limit is checked in kg, as the API does
  return weightError(set.weight, unit)
}

/**
 * What is wrong with a workout's date, or null if nothing is.
 *
 * Also used when a workout is started from a program day.
 */
export function dateError(day: string, today: string = localDateString()): string | null {
  // A cleared date input gives ''; anything not YYYY-MM-DD counts as cleared
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day)) return tActive('form.chooseDate')
  // Tomorrow, as the API allows: the user's local day can be ahead of its own
  const latest = shiftDate(today, 1)
  // YYYY-MM-DD strings sort like the dates they stand for
  if (day < EARLIEST_WORKOUT_DATE || day > latest) {
    return tActive('form.dateRange', { from: EARLIEST_WORKOUT_DATE, to: latest })
  }
  return null
}

/**
 * Everything the API would reject, found before sending. Empty means valid.
 *
 * today is the user's local day, as YYYY-MM-DD.
 */
export function validateWorkout(
  fields: WorkoutFields,
  today: string = localDateString(),
  unit: WeightUnit = 'kg',
): FormErrors {
  const errors: FormErrors = {}

  const date = dateError(fields.performedOn, today)
  if (date) errors[DATE_KEY] = date
  if (fields.note.trim().length > MAX_NOTE_LENGTH) {
    errors[NOTE_KEY] = tActive('form.noteTooLong', { max: MAX_NOTE_LENGTH })
  }
  if (fields.exercises.length === 0) {
    errors[EXERCISES_KEY] = tActive('form.addExercise')
  } else if (fields.exercises.length > MAX_EXERCISES) {
    errors[EXERCISES_KEY] = tActive('form.tooManyExercises', { max: MAX_EXERCISES })
  }

  fields.exercises.forEach((item, index) => {
    const choice = choiceError(item)
    if (choice) errors[exerciseKey(index)] = choice

    if (item.sets.length === 0) {
      errors[setsKey(index)] = tActive('form.addSet')
    } else if (item.sets.length > MAX_SETS) {
      errors[setsKey(index)] = tActive('form.tooManySets', { max: MAX_SETS })
    }
    item.sets.forEach((set, setIndex) => {
      const error = setError(set, unit)
      if (error) errors[setKey(index, setIndex)] = error
    })
  })

  return errors
}

/** How names are compared: the API trims them and ignores case. */
function nameKey(name: string): string {
  return name.trim().toLowerCase()
}

function findByName(catalog: Exercise[], name: string): Exercise | undefined {
  return catalog.find((exercise) => nameKey(exercise.name) === nameKey(name))
}

/** An exercise as a form picks it: from the catalog, or by a new name. */
export type ExerciseChoice = { exercise: string; newName: string }

/** What is wrong with an exercise choice, or null if nothing is. */
export function choiceError(item: ExerciseChoice): string | null {
  if (item.exercise === '') return tActive('form.chooseExercise')
  if (item.exercise !== NEW_EXERCISE) return null
  const name = item.newName.trim()
  if (name === '') return tActive('form.enterExerciseName')
  if (name.length > MAX_NAME_LENGTH) {
    return tActive('form.nameTooLong', { max: MAX_NAME_LENGTH })
  }
  return null
}

/**
 * The new exercise names that need a POST /exercises before saving.
 *
 * A name already in the catalog (ignoring spaces around it and case) is
 * reused, and two blocks with the same new name create it once. Exercises
 * created by an earlier, failed save are in the catalog by then, so a retry
 * does not create them again (which would be a 409).
 */
export function newExerciseNames(items: ExerciseChoice[], catalog: Exercise[]): string[] {
  const names = new Map<string, string>()
  for (const item of items) {
    if (item.exercise !== NEW_EXERCISE) continue
    const name = item.newName.trim()
    if (!findByName(catalog, name) && !names.has(nameKey(name))) {
      names.set(nameKey(name), name)
    }
  }
  return [...names.values()]
}

export function exercisesToCreate(fields: WorkoutFields, catalog: Exercise[]): string[] {
  return newExerciseNames(fields.exercises, catalog)
}

/**
 * The id of the chosen exercise, a new name resolved through the catalog.
 *
 * Call it only once every name from newExerciseNames is in the catalog.
 */
export function exerciseIdOf(item: ExerciseChoice, catalog: Exercise[]): number {
  if (item.exercise !== NEW_EXERCISE) return Number(item.exercise)
  const exercise = findByName(catalog, item.newName)
  if (!exercise) throw new Error(`Exercise not created: ${item.newName}`)
  return exercise.id
}

/**
 * The request body for POST or PUT /workouts.
 *
 * Call it on valid fields only, once every name from exercisesToCreate is in
 * the catalog.
 */
export function toWorkoutInput(
  fields: WorkoutFields,
  catalog: Exercise[],
  unit: WeightUnit = 'kg',
): WorkoutInput {
  return {
    performed_on: fields.performedOn,
    // A blank note is no note
    note: fields.note.trim() || null,
    exercises: fields.exercises.map((item) => ({
      exercise_id: exerciseIdOf(item, catalog),
      sets: item.sets.map((set) => ({
        reps: Number(set.reps),
        weight_kg: weightToSend(set.weight, unit, set.savedKg),
      })),
    })),
  }
}

/**
 * The errors left once exercise block index changed from before to after:
 * each field the user changed loses its error, the others keep theirs until
 * the next Save. A set added or removed also clears the "sets" error, and a
 * removed set the errors of the sets after it, which moved up a row.
 */
export function clearExerciseErrors(
  errors: FormErrors,
  index: number,
  before: ExerciseFields,
  after: ExerciseFields,
): FormErrors {
  let left = errors
  if (after.exercise !== before.exercise || after.newName !== before.newName) {
    left = withoutKeys(left, exerciseKey(index))
  }
  if (after.sets.length !== before.sets.length) {
    left = withoutKeys(left, setsKey(index))
    return withoutRowsFrom(left, `exercise.${index}.set`, firstChangedRow(before.sets, after.sets))
  }
  before.sets.forEach((set, setIndex) => {
    if (after.sets[setIndex] !== set) left = withoutKeys(left, setKey(index, setIndex))
  })
  return left
}

/** The errors left once exercise block index is removed (the blocks after it move up). */
export function clearRemovedExercise(errors: FormErrors, index: number): FormErrors {
  return withoutRowsFrom(withoutKeys(errors, EXERCISES_KEY), 'exercise', index)
}
