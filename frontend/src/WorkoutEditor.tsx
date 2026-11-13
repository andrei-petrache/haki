import { useEffect, useRef, useState } from 'react'
import {
  ApiError,
  createExercise,
  createWorkout,
  describeError,
  fetchExercises,
  fetchProgram,
  updateWorkout,
} from './api'
import type { Exercise, PlannedExercise, ProgramDay, Workout, WorkoutSet } from './api'
import { formatDay, formatSet, localDateString } from './format'
import { liveRecordIndex, useExerciseHistory } from './history'
import DayChoice from './DayChoice'
import { withoutKeys } from './formErrors'
import { useI18n } from './i18n/context'
import { weightToSend } from './units'
import type { WeightUnit } from './units'
import CatalogExercisePicker from './CatalogExercisePicker'
import { RestStart } from './RestTimer'
import { restStore } from './restTimer'
import { firstOpenRow, lastSetText, plannedForBlocks, rowNote, untouchedPlan } from './workoutRows'
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
  setError,
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
  last,
  record,
  token,
  onPickFromCatalog,
  lastSets,
  planned,
  done,
  onToggleDone,
}: {
  index: number
  item: ExerciseFields
  catalog: Exercise[]
  errors: FormErrors
  onChange: (item: ExerciseFields) => void
  onRemove: () => void
  unit: WeightUnit
  /** What the history says about last time, ready to show; null for nothing */
  last: string | null
  /** The set that would be a new record, as typed so far; null for none */
  record: number | null
  token: string
  /** The row now uses this exercise, picked from the catalog */
  onPickFromCatalog: (exercise: Exercise) => void
  /** Last time's sets of this exercise, for the "last time" column */
  lastSets: WorkoutSet[] | null
  /** What the program day plans for this block, if it was started from one */
  planned: PlannedExercise | null
  /** Which rows are ticked as done (this visit only) */
  done: boolean[]
  onToggleDone: (setIndex: number) => void
}) {
  const { t } = useI18n()
  const firstOpen = firstOpenRow(done, item.sets.length)

  function setSet(setIndex: number, change: Partial<SetFields>) {
    onChange({
      ...item,
      sets: item.sets.map((set, i) => (i === setIndex ? { ...set, ...change } : set)),
    })
  }

  return (
    <fieldset className="exercise-block">
      <legend className="muted">{t('workouts.exerciseN', { n: index + 1 })}</legend>
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
        <button type="button" className="icon remove-block" aria-label={t('workouts.removeExercise')} title={t('workouts.removeExercise')} onClick={onRemove}>
          ×
        </button>
      </div>
      <FieldError errors={errors} field={exerciseKey(index)} />
      <CatalogExercisePicker token={token} own={catalog} onPick={onPickFromCatalog} />
      {last && <p className="muted last-time">{last}</p>}

      {item.sets.length > 0 && (
        <div className="set-table-head" aria-hidden="true">
          <span>{t('workouts.colSet')}</span>
          <span>{t('workouts.colLast')}</span>
          <span>{unit}</span>
          <span>{t('workouts.colReps')}</span>
          <span />
        </div>
      )}
      {item.sets.map((set, setIndex) => {
        const isDone = done[setIndex] ?? false
        const note = rowNote(setIndex, isDone, firstOpen, untouchedPlan(set, planned, unit))
        const lastText = lastSetText(lastSets, setIndex, unit)
        return (
          // Rows have no state of their own (the inputs are controlled), so the
          // index is a safe key even when a row in the middle is removed
          <div key={setIndex} className="set-row-wrap">
            <div className={`set-row${isDone ? ' done' : ''}${note === 'plan' ? ' plan' : ''}`}>
              <span className="set-n">{setIndex + 1}</span>
              <span className="set-last">
                {lastText ?? '—'}
                {note && <span className={`set-note ${note}`}>{t(note === 'next' ? 'workouts.next' : 'workouts.fromPlan')}</span>}
              </span>
              <WeightInput
                compact
                value={set.weight}
                unit={unit}
                of={t('workouts.setOf', { set: setIndex + 1, exercise: index + 1 })}
                onChange={(weight) => setSet(setIndex, { weight })}
              />
              <label className="set-reps">
                <span className="visually-hidden">{t('workouts.reps')}</span>
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
              <button
                type="button"
                className="tick"
                aria-pressed={isDone}
                aria-label={t('workouts.done', { set: setIndex + 1, exercise: index + 1 })}
                onClick={() => onToggleDone(setIndex)}
              >
                ✓
              </button>
              <button
                type="button"
                className="icon set-remove"
                aria-label={t('workouts.removeSet', { set: setIndex + 1, exercise: index + 1 })}
                onClick={() =>
                  onChange({ ...item, sets: item.sets.filter((_, i) => i !== setIndex) })
                }
              >
                ×
              </button>
            </div>
            <FieldError errors={errors} field={setKey(index, setIndex)} />
            {record === setIndex && (
              <p className="record-line">
                <span className="record">{t('history.record')}</span>
              </p>
            )}
          </div>
        )
      })}
      <FieldError errors={errors} field={setsKey(index)} />
      <button
        type="button"
        className="link"
        disabled={item.sets.length >= MAX_SETS}
        onClick={() => onChange({ ...item, sets: [...item.sets, emptySet()] })}
      >
        {t('workouts.addSet')}
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
  const { t } = useI18n()
  const [catalog, setCatalog] = useState<Exercise[] | null>(null)
  const [fields, setFields] = useState<WorkoutFields | null>(() =>
    initial ? workoutToFields(initial, weightUnit) : null,
  )
  const [errors, setErrors] = useState<FormErrors>({})
  const [saveError, setSaveError] = useState<string | null>(null)
  // Sets ticked as done, by block: this visit only, not saved
  const [done, setDone] = useState<boolean[][]>([])
  // The program day this workout was started from, for its plan
  const [planDay, setPlanDay] = useState<ProgramDay | null>(null)
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

  // Alongside the form, never in its way: a failure only hides "last time".
  // The workout being edited is not its own "last time": only earlier ones count.
  const histories = useExerciseHistory(
    token,
    fields ? fields.exercises.map((item) => Number(item.exercise)) : [],
    initial ? initial.id : null,
  )

  // Started from a program: its day, to show the plan beside what was done
  useEffect(() => {
    const programId = initial?.program_id
    const dayId = initial?.program_day_id
    if (!programId || !dayId) return
    let cancelled = false
    fetchProgram(token, programId)
      .then((program) => {
        if (!cancelled) setPlanDay(program.days.find((day) => day.id === dayId) ?? null)
      })
      // No plan shown, the workout itself still works
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [token, initial])

  function toggleDone(block: number, setIndex: number) {
    const now = !(done[block]?.[setIndex] ?? false)
    // A set done: the rest between sets starts, as long as last time
    if (now) restStore.startLast()
    setDone((old) => {
      const next = old.map((row) => [...row])
      while (next.length <= block) next.push([])
      next[block][setIndex] = now
      return next
    })
  }

  function lastSetsOf(item: ExerciseFields): WorkoutSet[] | null {
    return histories.get(Number(item.exercise))?.last?.sets ?? null
  }

  function lastText(item: ExerciseFields): string | null {
    const last = histories.get(Number(item.exercise))?.last
    if (!last) return null
    return t('history.lastTime', {
      day: formatDay(last.performed_on),
      sets: last.sets.map((set) => formatSet(set.reps, set.weight_kg, weightUnit)).join(', '),
    })
  }

  /** A catalog pick: the user's copy joins the choices, and the row uses it. */
  function pickFromCatalog(index: number, exercise: Exercise) {
    setCatalog((current) =>
      current && current.some((known) => known.id === exercise.id)
        ? current
        : [...(current ?? []), exercise].sort(byName),
    )
    if (fields) setExercise(index, { ...fields.exercises[index], exercise: String(exercise.id), newName: '' })
  }

  /**
   * Which set of a row, as typed, would beat the history's best: live, while
   * typing. A set still as the program planned it counts only once ticked
   * done: the plan alone is not a record.
   */
  function recordIndex(item: ExerciseFields, planned: PlannedExercise | null, doneRows: boolean[]): number | null {
    const history = histories.get(Number(item.exercise))
    if (!history) return null
    const typed = item.sets.map((set, setIndex) =>
      setError(set, weightUnit) === null &&
      ((doneRows[setIndex] ?? false) || !untouchedPlan(set, planned, weightUnit))
        ? { reps: Number(set.reps), weight_kg: weightToSend(set.weight, weightUnit, set.savedKg) }
        : null,
    )
    return liveRecordIndex(typed, history.best)
  }

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
    setDone((old) => old.filter((_, i) => i !== index))
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
          setSaveError(t('exercise.exists', { name }))
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

  const title = initial ? t('workouts.edit') : t('workouts.new')

  if (!fields || !catalog) {
    return (
      <section className="card">
        <h2>{title}</h2>
        {saveError ? (
          <p className="error">{saveError}</p>
        ) : (
          <p className="muted">{t('app.loading')}</p>
        )}
        <button type="button" className="link" onClick={onCancel}>
          {t('common.cancel')}
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
      <div className="editor-head">
        <div>
          <h2>{planDay ? planDay.name || t('programs.dayTitle', { position: planDay.position, name: '' }) : title}</h2>
          {/* The day as words, under the title: a tap opens the date picker */}
          <DayChoice
            day={fields.performedOn}
            fieldLabel={t('workouts.date')}
            onChange={(day) => {
              setErrors((old) => withoutKeys(old, DATE_KEY))
              setFields({ ...fields, performedOn: day })
            }}
          />
        </div>
        <button type="submit" disabled={busy}>
          {busy ? t('common.saving') : t('common.save')}
        </button>
      </div>
      <FieldError errors={errors} field={DATE_KEY} />
      <label>
        {t('workouts.note')}
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

      {(() => {
        const plans = plannedForBlocks(fields.exercises, planDay)
        return fields.exercises.map((item, index) => (
        <ExerciseBlock
          key={index}
          lastSets={lastSetsOf(item)}
          planned={plans[index]}
          done={done[index] ?? []}
          onToggleDone={(setIndex) => toggleDone(index, setIndex)}
          index={index}
          item={item}
          catalog={catalog}
          errors={errors}
          onChange={(changed) => setExercise(index, changed)}
          onRemove={() => removeExercise(index)}
          unit={weightUnit}
          last={lastText(item)}
          record={recordIndex(item, plans[index], done[index] ?? [])}
          token={token}
          onPickFromCatalog={(exercise) => pickFromCatalog(index, exercise)}
        />
        ))
      })()}
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
        {t('workouts.addExercise')}
      </button>

      {saveError && <p className="error">{saveError}</p>}
      <RestStart />

      <div className="actions">
        <button type="button" className="link" onClick={onCancel}>
          {t('common.cancel')}
        </button>
      </div>
    </form>
  )
}
