import { useEffect, useState } from 'react'
import {
  WORKOUTS_PAGE_SIZE,
  deleteWorkout,
  describeError,
  fetchWorkout,
  fetchWorkouts,
} from './api'
import type { Workout, WorkoutSummary } from './api'
import { formatCounts, formatDay, formatSet, shorten } from './format'

const NOTE_PREVIEW_LENGTH = 80

type View = { kind: 'list' } | { kind: 'detail'; id: number }

/**
 * The workouts, newest first, a page at a time.
 *
 * Mounted afresh each time the list is shown, so after a change it reloads
 * from the first page instead of keeping pages whose offsets have shifted.
 */
function WorkoutList({
  token,
  onOpen,
}: {
  token: string
  onOpen: (id: number) => void
}) {
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
      <h2>Your workouts</h2>
      {error && <p className="error">{error}</p>}
      {workouts === null && !error && <p className="muted">Loading…</p>}
      {workouts?.length === 0 && <p className="muted empty">No workouts yet</p>}
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
                  {formatCounts(workout.exercise_count, workout.set_count)}
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
          {loadingMore ? 'Loading…' : 'Load more'}
        </button>
      )}
    </section>
  )
}

function WorkoutDetail({
  token,
  id,
  onBack,
}: {
  token: string
  id: number
  onBack: () => void
}) {
  const [workout, setWorkout] = useState<Workout | null>(null)
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

  async function handleDelete(loaded: Workout) {
    if (!window.confirm(`Delete the workout of ${formatDay(loaded.performed_on)}?`)) {
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
        ‹ Back to workouts
      </button>
      {error && <p className="error">{error}</p>}
      {!workout && !error && <p className="muted">Loading…</p>}
      {workout && (
        <>
          <h2>{formatDay(workout.performed_on)}</h2>
          {workout.note && <p className="workout-note">{workout.note}</p>}
          {workout.exercises.length === 0 && <p className="muted">No exercises</p>}
          {workout.exercises.map((item, index) => (
            // The same exercise may appear twice in a workout: the index is the key
            <div key={index} className="workout-exercise">
              <h3>{item.exercise_name}</h3>
              <ol className="sets">
                {item.sets.map((set, setIndex) => (
                  <li key={setIndex}>{formatSet(set.reps, set.weight_kg)}</li>
                ))}
              </ol>
            </div>
          ))}
          <div className="actions">
            <button
              type="button"
              className="secondary"
              disabled={deleting}
              onClick={() => void handleDelete(workout)}
            >
              {deleting ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </>
      )}
    </section>
  )
}

export default function WorkoutsPage({ token }: { token: string }) {
  const [view, setView] = useState<View>({ kind: 'list' })
  const showList = () => setView({ kind: 'list' })

  return (
    <div className="page">
      {view.kind === 'list' && (
        <WorkoutList token={token} onOpen={(id) => setView({ kind: 'detail', id })} />
      )}
      {view.kind === 'detail' && (
        <WorkoutDetail token={token} id={view.id} onBack={showList} />
      )}
    </div>
  )
}
