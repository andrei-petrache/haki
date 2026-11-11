import { useEffect, useState } from 'react'
import {
  WORKOUTS_PAGE_SIZE,
  deleteWorkout,
  describeError,
  fetchWorkout,
  fetchWorkouts,
} from './api'
import type { Workout, WorkoutSummary } from './api'
import { formatDay, formatSet, shorten } from './format'
import { useI18n } from './i18n/context'
import { HISTORY_LIMIT, loadHistory, recordPositions } from './history'
import WorkoutEditor from './WorkoutEditor'
import type { WeightUnit } from './units'

const NOTE_PREVIEW_LENGTH = 80

type View =
  | { kind: 'list' }
  | { kind: 'detail'; id: number }
  | { kind: 'new' }
  | { kind: 'edit'; workout: Workout }

/**
 * The workouts, newest first, a page at a time.
 *
 * Mounted afresh each time the list is shown, so after a change it reloads
 * from the first page instead of keeping pages whose offsets have shifted.
 */
function WorkoutList({
  token,
  onOpen,
  onNew,
}: {
  token: string
  onOpen: (id: number) => void
  onNew: () => void
}) {
  const { t } = useI18n()
  const [workouts, setWorkouts] = useState<WorkoutSummary[] | null>(null)
  // A full page means there may be more; an empty next page then just ends it
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchWorkouts(token)
      .then((page) => {
        if (cancelled) return
        setWorkouts(page)
        setHasMore(page.length === WORKOUTS_PAGE_SIZE)
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err))
      })
    return () => {
      cancelled = true
    }
  }, [token])

  async function handleLoadMore(loaded: WorkoutSummary[]) {
    setError(null)
    setLoadingMore(true)
    try {
      const page = await fetchWorkouts(token, WORKOUTS_PAGE_SIZE, loaded.length)
      // A workout added elsewhere meanwhile shifts the pages: skip repeats
      const seen = new Set(loaded.map((workout) => workout.id))
      setWorkouts([...loaded, ...page.filter((workout) => !seen.has(workout.id))])
      setHasMore(page.length === WORKOUTS_PAGE_SIZE)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <h2>{t('workouts.yours')}</h2>
        <button type="button" onClick={onNew}>
          {t('workouts.new')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {workouts === null && !error && <p className="muted">{t('app.loading')}</p>}
      {workouts?.length === 0 && <p className="muted empty">{t('workouts.none')}</p>}
      {workouts && workouts.length > 0 && (
        <ul className="workout-list">
          {workouts.map((workout) => (
            <li key={workout.id}>
              <button
                type="button"
                className="workout-card"
                onClick={() => onOpen(workout.id)}
              >
                <strong>{formatDay(workout.performed_on)}</strong>
                {workout.note && <span>{shorten(workout.note, NOTE_PREVIEW_LENGTH)}</span>}
                <span className="muted">
                  {t('count.exercises', { count: workout.exercise_count })} ·{' '}
                  {t('count.sets', { count: workout.set_count })}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {workouts && hasMore && (
        <button
          type="button"
          className="secondary"
          disabled={loadingMore}
          onClick={() => void handleLoadMore(workouts)}
        >
          {loadingMore ? t('app.loading') : t('common.loadMore')}
        </button>
      )}
    </section>
  )
}

function WorkoutDetail({
  token,
  id,
  onBack,
  onEdit,
  weightUnit,
}: {
  token: string
  id: number
  onBack: () => void
  onEdit: (workout: Workout) => void
  weightUnit: WeightUnit
}) {
  const { t } = useI18n()
  const [workout, setWorkout] = useState<Workout | null>(null)
  // The recent workouts, to spot records; nothing is marked until they arrive
  const [history, setHistory] = useState<Workout[]>([])
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchWorkout(token, id)
      .then((loaded) => {
        if (!cancelled) setWorkout(loaded)
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err))
      })
    return () => {
      cancelled = true
    }
  }, [token, id])

  useEffect(() => {
    let cancelled = false
    loadHistory(token)
      .then((loaded) => {
        if (!cancelled) setHistory(loaded)
      })
      // No history, no records: the workout itself still shows
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [token])

  const records = workout ? recordPositions(workout, history) : new Set<string>()

  async function handleDelete(loaded: Workout) {
    if (!window.confirm(t('workouts.deleteConfirm', { day: formatDay(loaded.performed_on) }))) {
      return
    }
    setError(null)
    setDeleting(true)
    try {
      await deleteWorkout(token, loaded.id)
      onBack()
    } catch (err) {
      setError(describeError(err))
      setDeleting(false)
    }
  }

  return (
    <section className="card">
      <button type="button" className="link" onClick={onBack}>
        {t('workouts.back')}
      </button>
      {error && <p className="error">{error}</p>}
      {!workout && !error && <p className="muted">{t('app.loading')}</p>}
      {workout && (
        <>
          <h2>{formatDay(workout.performed_on)}</h2>
          {workout.note && <p className="workout-note">{workout.note}</p>}
          {workout.exercises.length === 0 && <p className="muted">{t('workouts.noExercises')}</p>}
          {workout.exercises.map((item, index) => (
            // The same exercise may appear twice in a workout: the index is the key
            <div key={index} className="workout-exercise">
              <h3>{item.exercise_name}</h3>
              <ol className="sets">
                {item.sets.map((set, setIndex) => (
                  <li key={setIndex}>
                    {formatSet(set.reps, set.weight_kg, weightUnit)}
                    {records.has(`${index}.${setIndex}`) && (
                      <span
                        className="record"
                        title={t('history.recordScope', { count: HISTORY_LIMIT })}
                      >
                        {t('history.record')}
                      </span>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          ))}
          <div className="actions">
            <button
              type="button"
              className="secondary"
              disabled={deleting}
              onClick={() => onEdit(workout)}
            >
              {t('common.edit')}
            </button>
            <button
              type="button"
              className="secondary"
              disabled={deleting}
              onClick={() => void handleDelete(workout)}
            >
              {deleting ? t('common.deleting') : t('common.delete')}
            </button>
          </div>
        </>
      )}
    </section>
  )
}

/** The workouts tab; openWorkoutId opens one workout first, e.g. one just started. */
export default function WorkoutsPage({
  token,
  weightUnit,
  openWorkoutId = null,
}: {
  token: string
  weightUnit: WeightUnit
  openWorkoutId?: number | null
}) {
  const [view, setView] = useState<View>(() =>
    openWorkoutId === null ? { kind: 'list' } : { kind: 'detail', id: openWorkoutId },
  )
  const showList = () => setView({ kind: 'list' })
  const showDetail = (id: number) => setView({ kind: 'detail', id })

  return (
    <div className="page">
      {view.kind === 'list' && (
        <WorkoutList
          token={token}
          onOpen={showDetail}
          onNew={() => setView({ kind: 'new' })}
        />
      )}
      {view.kind === 'detail' && (
        <WorkoutDetail
          token={token}
          id={view.id}
          onBack={showList}
          onEdit={(workout) => setView({ kind: 'edit', workout })}
          weightUnit={weightUnit}
        />
      )}
      {view.kind === 'new' && (
        <WorkoutEditor
          token={token}
          initial={null}
          onSaved={showDetail}
          onCancel={showList}
          weightUnit={weightUnit}
        />
      )}
      {view.kind === 'edit' && (
        <WorkoutEditor
          token={token}
          initial={view.workout}
          onSaved={showDetail}
          onCancel={() => showDetail(view.workout.id)}
          weightUnit={weightUnit}
        />
      )}
    </div>
  )
}
