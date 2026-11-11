import { useEffect, useRef, useState } from 'react'
import { ApiError, createExercise, createProgram, describeError, fetchExercises } from './api'
import type { Exercise } from './api'
import { withoutKeys } from './formErrors'
import {
  DAYS_KEY,
  MAX_DAYS,
  MAX_EXERCISES_PER_DAY,
  NAME_KEY,
  clearDayErrors,
  clearRemovedDay,
  dayExercisesKey,
  dayNameKey,
  dayPositionKey,
  emptyPlanned,
  newDay,
  newProgramFields,
  plannedExerciseKey,
  plannedValuesKey,
  programExercisesToCreate,
  toProgramInput,
  validateProgram,
} from './programForm'
import type { DayFields, FormErrors, PlannedFields, ProgramFields } from './programForm'
import { MAX_NAME_LENGTH, MAX_REPS, MAX_SETS, MAX_WEIGHT_KG, NEW_EXERCISE } from './workoutForm'

const POSITIONS = Array.from({ length: MAX_DAYS }, (_, i) => i + 1)

function byName(a: Exercise, b: Exercise): number {
  return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
}

function FieldError({ errors, field }: { errors: FormErrors; field: string }) {
  return errors[field] ? <p className="error">{errors[field]}</p> : null
}

function PlannedRow({
  day,
  index,
  item,
  catalog,
  errors,
  onChange,
  onRemove,
}: {
  day: number
  index: number
  item: PlannedFields
  catalog: Exercise[]
  errors: FormErrors
  onChange: (item: PlannedFields) => void
  onRemove: () => void
}) {
  const label = `exercise ${index + 1} of day ${day + 1}`
  return (
    <div className="planned">
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
      </div>
      <FieldError errors={errors} field={plannedExerciseKey(day, index)} />
      <div className="planned-row">
        <label>
          Sets
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={MAX_SETS}
            step={1}
            value={item.sets}
            onChange={(event) => onChange({ ...item, sets: event.target.value })}
          />
        </label>
        <label>
          Reps
          <input
            type="number"
            inputMode="numeric"
            min={1}
            max={MAX_REPS}
            step={1}
            value={item.reps}
            onChange={(event) => onChange({ ...item, reps: event.target.value })}
          />
        </label>
        <label>
          Weight (kg)
          <input
            type="number"
            inputMode="decimal"
            min={0}
            max={MAX_WEIGHT_KG}
            // "any": with the default step of 1 the browser rejects 22.5
            step="any"
            value={item.weight}
            onChange={(event) => onChange({ ...item, weight: event.target.value })}
          />
        </label>
        <button
          type="button"
          className="icon"
          aria-label={`Remove ${label}`}
          onClick={onRemove}
        >
          ×
        </button>
      </div>
      <FieldError errors={errors} field={plannedValuesKey(day, index)} />
    </div>
  )
}

function DayBlock({
  index,
  day,
  catalog,
  errors,
  onChange,
  onRemove,
}: {
  index: number
  day: DayFields
  catalog: Exercise[]
  errors: FormErrors
  onChange: (day: DayFields) => void
  onRemove: () => void
}) {
  function setPlanned(i: number, item: PlannedFields) {
    onChange({ ...day, exercises: day.exercises.map((old, j) => (j === i ? item : old)) })
  }

  return (
    <fieldset className="exercise-block">
      <legend className="muted">Day {index + 1}</legend>
      <div className="exercise-head">
        <label>
          Day
          <select
            value={day.position}
            onChange={(event) => onChange({ ...day, position: Number(event.target.value) })}
          >
            {POSITIONS.map((position) => (
              <option key={position} value={position}>
                Day {position}
              </option>
            ))}
          </select>
        </label>
        <label className="grow">
          Name
          <input
            value={day.name}
            maxLength={MAX_NAME_LENGTH}
            placeholder="e.g. Push"
            onChange={(event) => onChange({ ...day, name: event.target.value })}
          />
        </label>
        <button type="button" className="secondary" onClick={onRemove}>
          Remove day
        </button>
      </div>
      <FieldError errors={errors} field={dayPositionKey(index)} />
      <FieldError errors={errors} field={dayNameKey(index)} />

      {day.exercises.map((item, i) => (
        // Rows have no state of their own (the inputs are controlled), so the
        // index is a safe key even when a row in the middle is removed
        <PlannedRow
          key={i}
          day={index}
          index={i}
          item={item}
          catalog={catalog}
          errors={errors}
          onChange={(changed) => setPlanned(i, changed)}
          onRemove={() =>
            onChange({ ...day, exercises: day.exercises.filter((_, j) => j !== i) })
          }
        />
      ))}
      <FieldError errors={errors} field={dayExercisesKey(index)} />
      <button
        type="button"
        className="link"
        disabled={day.exercises.length >= MAX_EXERCISES_PER_DAY}
        onClick={() => onChange({ ...day, exercises: [...day.exercises, emptyPlanned(catalog)] })}
      >
        + Add exercise
      </button>
    </fieldset>
  )
}

/**
 * A new program. There is no editing yet: the API has no PUT for programs.
 *
 * Save validates first and sends nothing if anything is wrong. Only then does
 * it create the new exercises, one at a time, and finally the whole program.
 */
export default function ProgramEditor({
  token,
  onSaved,
  onCancel,
}: {
  token: string
  onSaved: (id: number) => void
  onCancel: () => void
}) {
  const [catalog, setCatalog] = useState<Exercise[] | null>(null)
  const [fields, setFields] = useState<ProgramFields | null>(null)
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
        // The first exercise's default depends on whether the catalog is empty
        setFields((current) => current ?? newProgramFields(list))
      })
      .catch((err) => {
        if (!cancelled) setSaveError(describeError(err))
      })
    return () => {
      cancelled = true
    }
  }, [token])

  function setDay(index: number, day: DayFields) {
    // The error of what changed goes away; the rest wait for the next Save
    if (fields) setErrors((old) => clearDayErrors(old, index, fields.days[index], day))
    setFields(
      (current) =>
        current && { ...current, days: current.days.map((old, i) => (i === index ? day : old)) },
    )
  }

  function removeDay(index: number) {
    setErrors((old) => clearRemovedDay(old, index))
    setFields(
      (current) => current && { ...current, days: current.days.filter((_, i) => i !== index) },
    )
  }

  async function handleSave(current: ProgramFields, loaded: Exercise[]) {
    if (saving.current) return
    let known = loaded
    const found = validateProgram(current)
    setErrors(found)
    setSaveError(null)
    if (Object.keys(found).length > 0) return

    saving.current = true
    setBusy(true)
    try {
      for (const name of programExercisesToCreate(current, known)) {
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
      const saved = await createProgram(token, toProgramInput(current, known))
      onSaved(saved.id)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Days on the same place are caught above, so this is the name
        setErrors({ [NAME_KEY]: 'You already have a program with this name' })
      } else if (err instanceof ApiError && err.status === 404) {
        // An exercise was deleted meanwhile (e.g. in another tab)
        setCatalog(await fetchExercises(token).catch(() => known))
        setSaveError('An exercise in this program no longer exists. Choose it again.')
      } else {
        setSaveError(describeError(err))
      }
    } finally {
      saving.current = false
      setBusy(false)
    }
  }

  if (!fields || !catalog) {
    return (
      <section className="card">
        <h2>New program</h2>
        {saveError ? <p className="error">{saveError}</p> : <p className="muted">Loading…</p>}
        <button type="button" className="link" onClick={onCancel}>
          Cancel
        </button>
      </section>
    )
  }

  const nextDay = newDay(fields.days, catalog)

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
      <h2>New program</h2>
      <label>
        Name
        <input
          value={fields.name}
          maxLength={MAX_NAME_LENGTH}
          placeholder="e.g. Push/Pull/Legs"
          onChange={(event) => {
            setErrors((old) => withoutKeys(old, NAME_KEY))
            setFields({ ...fields, name: event.target.value })
          }}
        />
      </label>
      <FieldError errors={errors} field={NAME_KEY} />

      {fields.days.map((day, index) => (
        <DayBlock
          key={index}
          index={index}
          day={day}
          catalog={catalog}
          errors={errors}
          onChange={(changed) => setDay(index, changed)}
          onRemove={() => removeDay(index)}
        />
      ))}
      <FieldError errors={errors} field={DAYS_KEY} />
      <button
        type="button"
        className="secondary add-exercise"
        disabled={nextDay === null}
        onClick={() => {
          if (!nextDay) return
          setErrors((old) => withoutKeys(old, DAYS_KEY))
          setFields({ ...fields, days: [...fields.days, nextDay] })
        }}
      >
        Add day
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
