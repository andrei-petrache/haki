import { useEffect, useRef, useState } from 'react'
import {
  ApiError,
  createExercise,
  createWorkout,
  describeError,
  fetchExercises,
  updateWorkout,
} from './api'
import type { Exercise, Workout } from './api'
import { localDateString } from './format'
import { withoutKeys } from './formErrors'
import type { WeightUnit } from './units'
import WeightInput from './WeightInput'
import {
  DATE_KEY,
  EXERCISES_KEY,
  MAX_EXERCISES,
  MAX_NAME_LENGTH,
  MAX_NOTE_LENGTH,
  MAX_REPS,
  MAX_SETS,
  NEW_EXERCISE,
  NOTE_KEY,
  clearExerciseErrors,
  clearRemovedExercise,
  emptyExercise,
  emptySet,
  exerciseKey,
  exercisesToCreate,
  newWorkoutFields,
  setKey,
  setsKey,
  toWorkoutInput,
  validateWorkout,
  workoutToFields,
} from './workoutForm'
import type { ExerciseFields, FormErrors, SetFields, WorkoutFields } from './workoutForm'

function byName(a: Exercise, b: Exercise): number {
  return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
}

function FieldError({ errors, field }: { errors: FormErrors; field: string }) {
  return errors[field] ? <p className="error">{errors[field]}</p> : null
}

function ExerciseBlock({
  index,
  item,
  catalog,
  errors,
  onChange,
  onRemove,
  unit,
}: {
  index: number
  item: ExerciseFields
  catalog: Exercise[]
  errors: FormErrors
  onChange: (item: ExerciseFields) => void
  onRemove: () => void
  unit: WeightUnit
}) {
  function setSet(setIndex: number, change: Partial<SetFields>) {
    onChange({
      ...item,
      sets: item.sets.map((set, i) => (i === setIndex ? { ...set, ...change } : set)),
    })
  }

  return (
    <fieldset className="exercise-block">
      <legend className="muted">Exercise {index + 1}</legend>
      <div className="exercise-head">
        <label className="grow">
          Exercise
          <select
            value={item.exercise}
            onChange={(event) => onChange({ ...item, exercise: event.target.value })}
          >
            <option value="" disabled>
              Choose an exercise…
            </option>
            {catalog.map((exercise) => (
              <option key={exercise.id} value={exercise.id}>
                {exercise.name}
              </option>
            ))}
            <option value={NEW_EXERCISE}>New exercise…</option>
          </select>
        </label>
        {item.exercise === NEW_EXERCISE && (
          <label className="grow">
            New exercise name
            <input
              value={item.newName}
              maxLength={MAX_NAME_LENGTH}
              onChange={(event) => onChange({ ...item, newName: event.target.value })}
            />
          </label>
        )}
        <button type="button" className="secondary" onClick={onRemove}>
          Remove exercise
        </button>
      </div>
      <FieldError errors={errors} field={exerciseKey(index)} />

      {item.sets.map((set, setIndex) => (
        // Rows have no state of their own (the inputs are controlled), so the
        // index is a safe key even when a row in the middle is removed
        <div key={setIndex} className="set-row-wrap">
          <div className="set-row">
            <span className="muted">{setIndex + 1}</span>
            <label>
              Reps
              <input
                type="number"
                inputMode="numeric"
                min={1}
                max={MAX_REPS}
                step={1}
                value={set.reps}
                onChange={(event) => setSet(setIndex, { reps: event.target.value })}
              />
            </label>
            <WeightInput
              value={set.weight}
              unit={unit}
              of={`set ${setIndex + 1} of exercise ${index + 1}`}
              onChange={(weight) => setSet(setIndex, { weight })}
            />
            <button
              type="button"
              className="icon"
              aria-label={`Remove set ${setIndex + 1} of exercise ${index + 1}`}
              onClick={() =>
                onChange({ ...item, sets: item.sets.filter((_, i) => i !== setIndex) })
              }
            >
              ×
            </button>
          </div>
          <FieldError errors={errors} field={setKey(index, setIndex)} />
        </div>
      ))}
      <FieldError errors={errors} field={setsKey(index)} />
      <button
        type="button"
        className="link"
        disabled={item.sets.length >= MAX_SETS}
        onClick={() => onChange({ ...item, sets: [...item.sets, emptySet()] })}
      >
        + Add set
      </button>
    </fieldset>
  )
}

/**
 * New workout (initial is null) or edit of a saved one.
 *
 * Save validates first and sends nothing if anything is wrong. Only then does
 * it create the new exercises, one at a time, and finally the workout.
 */
export default function WorkoutEditor({
  token,
  initial,
  onSaved,
  onCancel,
  weightUnit,
}: {
  token: string
  initial: Workout | null
  onSaved: (id: number) => void
  onCancel: () => void
  weightUnit: WeightUnit
}) {
  const [catalog, setCatalog] = useState<Exercise[] | null>(null)
  const [fields, setFields] = useState<WorkoutFields | null>(() =>
    initial ? workoutToFields(initial, weightUnit) : null,
  )
  const [errors, setErrors] = useState<FormErrors>({})
  const [saveError, setSaveError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Set synchronously, unlike busy: a double click must not save twice
  const saving = useRef(false)

  useEffect(() => {
    let cancelled = false
    fetchExercises(token)
      .then((list) => {
        if (cancelled) return
        setCatalog(list)
        // A new workout needs the catalog to know its first block's default
        setFields((current) => current ?? newWorkoutFields(localDateString(), list))
      })
      .catch((err) => {
        if (!cancelled) setSaveError(describeError(err))
      })
    return () => {
      cancelled = true
    }
  }, [token])

  function setExercise(index: number, item: ExerciseFields) {
    // The error of what changed goes away; the rest wait for the next Save
    if (fields) setErrors((old) => clearExerciseErrors(old, index, fields.exercises[index], item))
    setFields(
      (current) =>
        current && {
          ...current,
          exercises: current.exercises.map((old, i) => (i === index ? item : old)),
        },
    )
  }

  function removeExercise(index: number) {
    setErrors((old) => clearRemovedExercise(old, index))
    setFields(
      (current) =>
        current && {
          ...current,
          exercises: current.exercises.filter((_, i) => i !== index),
        },
    )
  }

  async function handleSave(current: WorkoutFields, loaded: Exercise[]) {
    if (saving.current) return
    let known = loaded
    const found = validateWorkout(current, undefined, weightUnit)
    setErrors(found)
    setSaveError(null)
    if (Object.keys(found).length > 0) return

    saving.current = true
    setBusy(true)
    try {
      for (const name of exercisesToCreate(current, known)) {
        try {
          const created = await createExercise(token, name)
          // Into the catalog right away: if a later step fails, a retry
          // reuses it instead of creating it again (a 409)
          known = [...known, created].sort(byName)
          setCatalog(known)
        } catch (err) {
          if (!(err instanceof ApiError && err.status === 409)) throw err
          // Created meanwhile elsewhere (e.g. another tab): once reloaded,
          // the next Save matches the name to it
          setCatalog(await fetchExercises(token))
          setSaveError(`"${name}" already exists. Save again to use it.`)
          return
        }
      }
      const input = toWorkoutInput(current, known, weightUnit)
      const saved = initial
        ? await updateWorkout(token, initial.id, input)
        : await createWorkout(token, input)
      onSaved(saved.id)
    } catch (err) {
      setSaveError(describeError(err))
    } finally {
      saving.current = false
      setBusy(false)
    }
  }

  const title = initial ? 'Edit workout' : 'New workout'

  if (!fields || !catalog) {
    return (
      <section className="card">
        <h2>{title}</h2>
        {saveError ? (
          <p className="error">{saveError}</p>
        ) : (
          <p className="muted">Loading…</p>
        )}
        <button type="button" className="link" onClick={onCancel}>
          Cancel
        </button>
      </section>
    )
  }

  return (
    <form
      className="card"
      // Our own validation shows each error next to its row
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        void handleSave(fields, catalog)
      }}
    >
      <h2>{title}</h2>
      <label className="date-field">
        Date
        <input
          type="date"
          value={fields.performedOn}
          onChange={(event) => {
            setErrors((old) => withoutKeys(old, DATE_KEY))
            setFields({ ...fields, performedOn: event.target.value })
          }}
        />
      </label>
      <FieldError errors={errors} field={DATE_KEY} />
      <label>
        Note
        <textarea
          rows={3}
          maxLength={MAX_NOTE_LENGTH}
          value={fields.note}
          onChange={(event) => {
            setErrors((old) => withoutKeys(old, NOTE_KEY))
            setFields({ ...fields, note: event.target.value })
          }}
        />
      </label>
      <FieldError errors={errors} field={NOTE_KEY} />

      {fields.exercises.map((item, index) => (
        <ExerciseBlock
          key={index}
          index={index}
          item={item}
          catalog={catalog}
          errors={errors}
          onChange={(changed) => setExercise(index, changed)}
          onRemove={() => removeExercise(index)}
          unit={weightUnit}
        />
      ))}
      <FieldError errors={errors} field={EXERCISES_KEY} />
      <button
        type="button"
        className="secondary add-exercise"
        disabled={fields.exercises.length >= MAX_EXERCISES}
        onClick={() => {
          setErrors((old) => withoutKeys(old, EXERCISES_KEY))
          setFields({ ...fields, exercises: [...fields.exercises, emptyExercise(catalog)] })
        }}
      >
        Add exercise
      </button>

      {saveError && <p className="error">{saveError}</p>}
      <div className="actions">
        <button type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Save'}
        </button>
        <button type="button" className="link" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}
