import { useEffect, useRef, useState } from 'react'
import {
  ApiError,
  createExercise,
  createProgram,
  describeError,
  fetchExercises,
  updateProgram,
} from './api'
import type { Exercise, Program } from './api'
import { withoutKeys } from './formErrors'
import { useI18n } from './i18n/context'
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
  programToFields,
} from './programForm'
import type { DayFields, FormErrors, PlannedFields, ProgramFields } from './programForm'
import type { WeightUnit } from './units'
import CatalogExercisePicker from './CatalogExercisePicker'
import WeightInput from './WeightInput'
import { MAX_NAME_LENGTH, MAX_REPS, MAX_SETS, NEW_EXERCISE } from './workoutForm'

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
  unit,
  token,
  onPickFromCatalog,
}: {
  day: number
  index: number
  item: PlannedFields
  catalog: Exercise[]
  errors: FormErrors
  onChange: (item: PlannedFields) => void
  onRemove: () => void
  unit: WeightUnit
  token: string
  onPickFromCatalog: (exercise: Exercise) => void
}) {
  const { t } = useI18n()
  const label = t('programs.plannedOf', { exercise: index + 1, day: day + 1 })
  return (
    <div className="planned">
      <div className="exercise-head">
        <label className="grow">
          {t('exercise.label')}
          <select
            value={item.exercise}
            onChange={(event) => onChange({ ...item, exercise: event.target.value })}
          >
            <option value="" disabled>
              {t('exercise.choose')}
            </option>
            {catalog.map((exercise) => (
              <option key={exercise.id} value={exercise.id}>
                {exercise.name}
              </option>
            ))}
            <option value={NEW_EXERCISE}>{t('exercise.new')}</option>
          </select>
        </label>
        {item.exercise === NEW_EXERCISE && (
          <label className="grow">
            {t('exercise.newName')}
            <input
              value={item.newName}
              maxLength={MAX_NAME_LENGTH}
              onChange={(event) => onChange({ ...item, newName: event.target.value })}
            />
          </label>
        )}
      </div>
      <FieldError errors={errors} field={plannedExerciseKey(day, index)} />
      <CatalogExercisePicker token={token} own={catalog} onPick={onPickFromCatalog} />
      <div className="planned-row">
        <label>
          {t('programs.sets')}
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
          {t('workouts.reps')}
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
        <WeightInput
          value={item.weight}
          unit={unit}
          of={label}
          onChange={(weight) => onChange({ ...item, weight })}
        />
        <button
          type="button"
          className="icon"
          aria-label={t('programs.removePlanned', { what: label })}
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
  unit,
  token,
  onPickFromCatalog,
}: {
  index: number
  day: DayFields
  catalog: Exercise[]
  errors: FormErrors
  onChange: (day: DayFields) => void
  onRemove: () => void
  unit: WeightUnit
  token: string
  onPickFromCatalog: (exerciseIndex: number, exercise: Exercise) => void
}) {
  const { t } = useI18n()

  function setPlanned(i: number, item: PlannedFields) {
    onChange({ ...day, exercises: day.exercises.map((old, j) => (j === i ? item : old)) })
  }

  return (
    <fieldset className="exercise-block">
      <legend className="muted">{t('programs.dayN', { n: index + 1 })}</legend>
      <div className="exercise-head">
        <label>
          {t('programs.day')}
          <select
            value={day.position}
            onChange={(event) => onChange({ ...day, position: Number(event.target.value) })}
          >
            {POSITIONS.map((position) => (
              <option key={position} value={position}>
                {t('programs.dayN', { n: position })}
              </option>
            ))}
          </select>
        </label>
        <label className="grow">
          {t('programs.name')}
          <input
            value={day.name}
            maxLength={MAX_NAME_LENGTH}
            placeholder={t('programs.dayNamePlaceholder')}
            onChange={(event) => onChange({ ...day, name: event.target.value })}
          />
        </label>
        <button type="button" className="icon remove-block" aria-label={t('programs.removeDay')} title={t('programs.removeDay')} onClick={onRemove}>
          ×
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
          unit={unit}
          token={token}
          onPickFromCatalog={(exercise) => onPickFromCatalog(i, exercise)}
        />
      ))}
      <FieldError errors={errors} field={dayExercisesKey(index)} />
      <button
        type="button"
        className="link"
        disabled={day.exercises.length >= MAX_EXERCISES_PER_DAY}
        onClick={() => onChange({ ...day, exercises: [...day.exercises, emptyPlanned(catalog)] })}
      >
        {t('programs.addExercise')}
      </button>
    </fieldset>
  )
}

/**
 * A new program, or a saved one (initial) to edit: Save then replaces it
 * whole (PUT), and its days come back as new rows.
 *
 * Save validates first and sends nothing if anything is wrong. Only then does
 * it create the new exercises, one at a time, and finally the whole program.
 */
export default function ProgramEditor({
  token,
  initial = null,
  onSaved,
  onCancel,
  weightUnit,
}: {
  token: string
  initial?: Program | null
  onSaved: (id: number) => void
  onCancel: () => void
  weightUnit: WeightUnit
}) {
  const { t } = useI18n()
  const [catalog, setCatalog] = useState<Exercise[] | null>(null)
  const [fields, setFields] = useState<ProgramFields | null>(() =>
    initial ? programToFields(initial, weightUnit) : null,
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

  /** A catalog pick: the user's copy joins the choices, and the row uses it. */
  function pickFromCatalog(dayIndex: number, exerciseIndex: number, exercise: Exercise) {
    setCatalog((current) =>
      current && current.some((known) => known.id === exercise.id)
        ? current
        : [...(current ?? []), exercise].sort(byName),
    )
    if (!fields) return
    const day = fields.days[dayIndex]
    setDay(dayIndex, {
      ...day,
      exercises: day.exercises.map((item, j) =>
        j === exerciseIndex ? { ...item, exercise: String(exercise.id), newName: '' } : item,
      ),
    })
  }

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
    const found = validateProgram(current, weightUnit)
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
          setSaveError(t('exercise.exists', { name }))
          return
        }
      }
      const input = toProgramInput(current, known, weightUnit)
      const saved = initial
        ? await updateProgram(token, initial.id, input)
        : await createProgram(token, input)
      onSaved(saved.id)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Days on the same place are caught above, so this is the name
        setErrors({ [NAME_KEY]: t('programs.duplicateName') })
      } else if (err instanceof ApiError && err.status === 404) {
        // An exercise was deleted meanwhile (e.g. in another tab)
        setCatalog(await fetchExercises(token).catch(() => known))
        setSaveError(t('programs.exerciseGone'))
      } else {
        setSaveError(describeError(err))
      }
    } finally {
      saving.current = false
      setBusy(false)
    }
  }

  const title = initial ? t('programs.editTitle', { name: initial.name }) : t('programs.new')

  if (!fields || !catalog) {
    return (
      <section className="card">
        <h2>{title}</h2>
        {saveError ? <p className="error">{saveError}</p> : <p className="muted">{t('app.loading')}</p>}
        <button type="button" className="link" onClick={onCancel}>
          {t('common.cancel')}
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
      <h2>{title}</h2>
      <label>
        {t('programs.name')}
        <input
          value={fields.name}
          maxLength={MAX_NAME_LENGTH}
          placeholder={t('programs.namePlaceholder')}
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
          unit={weightUnit}
          token={token}
          onPickFromCatalog={(exerciseIndex, exercise) =>
            pickFromCatalog(index, exerciseIndex, exercise)
          }
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
        {t('programs.addDay')}
      </button>

      {saveError && <p className="error">{saveError}</p>}
      <div className="actions">
        <button type="submit" disabled={busy}>
          {busy ? t('common.saving') : t('common.save')}
        </button>
        <button type="button" className="link" onClick={onCancel}>
          {t('common.cancel')}
        </button>
      </div>
    </form>
  )
}
