/**
 * The workout editor's state and the pure functions around it: validation,
 * which exercises to create first, and the request body. No React, no fetch.
 */
import type { Exercise, Workout, WorkoutInput } from './api'

// Must match the limits in backend/app/schemas.py
export const MAX_EXERCISES = 50
export const MAX_SETS = 50
export const MAX_NAME_LENGTH = 100
export const MAX_NOTE_LENGTH = 500
export const MAX_REPS = 1000
export const MAX_WEIGHT_KG = 1000

/** The select's value for "type a new exercise name". */
export const NEW_EXERCISE = 'new'

// Form inputs hold text; convert to numbers only on submit
export type SetFields = { reps: string; weight: string }

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

/** The editor prefilled with a saved workout. */
export function workoutToFields(workout: Workout): WorkoutFields {
  return {
    performedOn: workout.performed_on,
    note: workout.note ?? '',
    exercises: workout.exercises.map((item) => ({
      exercise: String(item.exercise_id),
      newName: '',
      // String(), not formatWeight(): a number input rejects "22,5"
      sets: item.sets.map((set) => ({
        reps: String(set.reps),
        weight: String(set.weight_kg),
      })),
    })),
  }
}

/**
 * Validation errors, keyed by where they belong in the form (see the *Key
 * functions), so each one can be shown next to its field or row.
 */
export type FormErrors = Record<string, string>

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

/** What is wrong with one set row, or null if nothing is. */
function setError(set: SetFields): string | null {
  const reps = parseNumber(set.reps)
  const weight = parseNumber(set.weight)
  if (reps === null) return 'Enter the reps'
  if (!Number.isInteger(reps) || reps < 1 || reps > MAX_REPS) {
    return `Reps must be a whole number from 1 to ${MAX_REPS}`
  }
  // Blank is not bodyweight: Number('') would silently turn it into 0
  if (weight === null) return 'Enter the weight (0 for bodyweight)'
  if (!Number.isFinite(weight) || weight < 0 || weight > MAX_WEIGHT_KG) {
    return `Weight must be from 0 to ${MAX_WEIGHT_KG} kg`
  }
  return null
}

/** Everything the API would reject, found before sending. Empty means valid. */
export function validateWorkout(fields: WorkoutFields): FormErrors {
  const errors: FormErrors = {}

  if (fields.performedOn === '') errors[DATE_KEY] = 'Choose a date'
  if (fields.note.trim().length > MAX_NOTE_LENGTH) {
    errors[NOTE_KEY] = `The note can have at most ${MAX_NOTE_LENGTH} characters`
  }
  if (fields.exercises.length === 0) {
    errors[EXERCISES_KEY] = 'Add at least one exercise'
  } else if (fields.exercises.length > MAX_EXERCISES) {
    errors[EXERCISES_KEY] = `A workout can have at most ${MAX_EXERCISES} exercises`
  }

  fields.exercises.forEach((item, index) => {
    if (item.exercise === '') {
      errors[exerciseKey(index)] = 'Choose an exercise'
    } else if (item.exercise === NEW_EXERCISE) {
      const name = item.newName.trim()
      if (name === '') {
        errors[exerciseKey(index)] = 'Enter the new exercise name'
      } else if (name.length > MAX_NAME_LENGTH) {
        errors[exerciseKey(index)] =
          `The name can have at most ${MAX_NAME_LENGTH} characters`
      }
    }

    if (item.sets.length === 0) {
      errors[setsKey(index)] = 'Add at least one set'
    } else if (item.sets.length > MAX_SETS) {
      errors[setsKey(index)] = `An exercise can have at most ${MAX_SETS} sets`
    }
    item.sets.forEach((set, setIndex) => {
      const error = setError(set)
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

/**
 * The new exercise names that need a POST /exercises before saving.
 *
 * A name already in the catalog (ignoring spaces around it and case) is
 * reused, and two blocks with the same new name create it once. Exercises
 * created by an earlier, failed save are in the catalog by then, so a retry
 * does not create them again (which would be a 409).
 */
export function exercisesToCreate(fields: WorkoutFields, catalog: Exercise[]): string[] {
  const names = new Map<string, string>()
  for (const item of fields.exercises) {
    if (item.exercise !== NEW_EXERCISE) continue
    const name = item.newName.trim()
    if (!findByName(catalog, name) && !names.has(nameKey(name))) {
      names.set(nameKey(name), name)
    }
  }
  return [...names.values()]
}

/**
 * The request body for POST or PUT /workouts.
 *
 * Call it on valid fields only, once every name from exercisesToCreate is in
 * the catalog.
 */
export function toWorkoutInput(fields: WorkoutFields, catalog: Exercise[]): WorkoutInput {
  return {
    performed_on: fields.performedOn,
    // A blank note is no note
    note: fields.note.trim() || null,
    exercises: fields.exercises.map((item) => {
      let exerciseId = Number(item.exercise)
      if (item.exercise === NEW_EXERCISE) {
        const exercise = findByName(catalog, item.newName)
        if (!exercise) throw new Error(`Exercise not created: ${item.newName}`)
        exerciseId = exercise.id
      }
      return {
        exercise_id: exerciseId,
        sets: item.sets.map((set) => ({
          reps: Number(set.reps),
          weight_kg: Number(set.weight),
        })),
      }
    }),
  }
}
