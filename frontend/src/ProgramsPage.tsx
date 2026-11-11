import { useEffect, useRef, useState } from 'react'
import {
  PROGRAMS_PAGE_SIZE,
  deleteProgram,
  describeError,
  fetchProgram,
  fetchPrograms,
  startWorkout,
} from './api'
import type { Program, ProgramSummary } from './api'
import { formatPlanned, localDateString } from './format'
import { useI18n } from './i18n/context'
import ProgramEditor from './ProgramEditor'
import { dateError } from './workoutForm'
import type { WeightUnit } from './units'

type View = { kind: 'list' } | { kind: 'detail'; id: number } | { kind: 'new' }

/**
 * The programs, by name, a page at a time.
 *
 * Mounted afresh each time the list is shown, so after a change it reloads
 * from the first page instead of keeping pages whose offsets have shifted
 * (a new name can land anywhere in the order).
 */
function ProgramList({
  token,
  onOpen,
  onNew,
}: {
  token: string
  onOpen: (id: number) => void
  onNew: () => void
}) {
  const { t } = useI18n()
  const [programs, setPrograms] = useState<ProgramSummary[] | null>(null)
  // A full page means there may be more; an empty next page then just ends it
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchPrograms(token)
      .then((page) => {
        if (cancelled) return
        setPrograms(page)
        setHasMore(page.length === PROGRAMS_PAGE_SIZE)
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err))
      })
    return () => {
      cancelled = true
    }
  }, [token])

  async function handleLoadMore(loaded: ProgramSummary[]) {
    setError(null)
    setLoadingMore(true)
    try {
      const page = await fetchPrograms(token, PROGRAMS_PAGE_SIZE, loaded.length)
      // A program added elsewhere meanwhile shifts the pages: skip repeats
      const seen = new Set(loaded.map((program) => program.id))
      setPrograms([...loaded, ...page.filter((program) => !seen.has(program.id))])
      setHasMore(page.length === PROGRAMS_PAGE_SIZE)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setLoadingMore(false)
    }
  }

  return (
    <section className="card">
      <div className="card-head">
        <h2>{t('programs.yours')}</h2>
        <button type="button" onClick={onNew}>
          {t('programs.new')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {programs === null && !error && <p className="muted">{t('app.loading')}</p>}
      {programs?.length === 0 && <p className="muted empty">{t('programs.none')}</p>}
      {programs && programs.length > 0 && (
        <ul className="workout-list">
          {programs.map((program) => (
            <li key={program.id}>
              <button type="button" className="workout-card" onClick={() => onOpen(program.id)}>
                <strong>{program.name}</strong>
                <span className="muted">{t('count.days', { count: program.day_count })}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {programs && hasMore && (
        <button
          type="button"
          className="secondary"
          disabled={loadingMore}
          onClick={() => void handleLoadMore(programs)}
        >
          {loadingMore ? t('app.loading') : t('common.loadMore')}
        </button>
      )}
    </section>
  )
}

function ProgramDetail({
  token,
  id,
  onBack,
  onWorkoutStarted,
  weightUnit,
}: {
  token: string
  id: number
  onBack: () => void
  onWorkoutStarted: (workoutId: number) => void
  weightUnit: WeightUnit
}) {
  const { t } = useI18n()
  const [program, setProgram] = useState<Program | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  // The day a workout started from this program is for, the user's local day
  const [performedOn, setPerformedOn] = useState(localDateString)
  const [dateProblem, setDateProblem] = useState<string | null>(null)
  // The day being started, for its button's label
  const [startingDay, setStartingDay] = useState<number | null>(null)
  // Set synchronously, unlike startingDay: a double click must not start twice
  const starting = useRef(false)

  useEffect(() => {
    let cancelled = false
    fetchProgram(token, id)
      .then((loaded) => {
        if (!cancelled) setProgram(loaded)
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err))
      })
    return () => {
      cancelled = true
    }
  }, [token, id])

  async function handleDelete(loaded: Program) {
    // Workouts already started from it stay: they are copies
    if (!window.confirm(t('programs.deleteConfirm', { name: loaded.name }))) return
    setError(null)
    setDeleting(true)
    try {
      await deleteProgram(token, loaded.id)
      onBack()
    } catch (err) {
      setError(describeError(err))
      setDeleting(false)
    }
  }

  async function handleStart(loaded: Program, dayId: number) {
    if (starting.current) return
    const problem = dateError(performedOn)
    setDateProblem(problem)
    setError(null)
    if (problem) return

    starting.current = true
    setStartingDay(dayId)
    try {
      const workout = await startWorkout(token, loaded.id, dayId, performedOn)
      onWorkoutStarted(workout.id)
    } catch (err) {
      setError(describeError(err))
    } finally {
      starting.current = false
      setStartingDay(null)
    }
  }

  const busy = deleting || startingDay !== null

  return (
    <section className="card">
      <button type="button" className="link" onClick={onBack}>
        {t('programs.back')}
      </button>
      {error && <p className="error">{error}</p>}
      {!program && !error && <p className="muted">{t('app.loading')}</p>}
      {program && (
        <>
          <h2>{program.name}</h2>
          <label className="date-field">
            {t('programs.workoutDate')}
            <input
              type="date"
              value={performedOn}
              onChange={(event) => setPerformedOn(event.target.value)}
            />
          </label>
          {dateProblem && <p className="error">{dateProblem}</p>}
          <p className="muted">
            {t('programs.copyNote')}
          </p>
          {/* By position: the API returns the days in that order */}
          {program.days.map((day) => (
            <div key={day.id} className="workout-exercise">
              <h3>
                {t('programs.dayTitle', { position: day.position, name: day.name })}
              </h3>
              <ul className="sets">
                {day.exercises.map((item, index) => (
                  // The same exercise may appear twice in a day: the index is the key
                  <li key={index}>
                    {item.exercise_name}: {formatPlanned(item.sets, item.reps, item.weight_kg, weightUnit)}
                  </li>
                ))}
              </ul>
              <div className="actions">
                <button
                  type="button"
                  disabled={busy}
                  aria-label={t('programs.startDay', { position: day.position, name: day.name })}
                  onClick={() => void handleStart(program, day.id)}
                >
                  {startingDay === day.id ? t('programs.starting') : t('programs.start')}
                </button>
              </div>
            </div>
          ))}
          <div className="actions">
            <button
              type="button"
              className="secondary"
              disabled={busy}
              onClick={() => void handleDelete(program)}
            >
              {deleting ? t('common.deleting') : t('common.delete')}
            </button>
          </div>
        </>
      )}
    </section>
  )
}

export default function ProgramsPage({
  token,
  weightUnit,
  onWorkoutStarted,
}: {
  token: string
  weightUnit: WeightUnit
  onWorkoutStarted: (workoutId: number) => void
}) {
  const [view, setView] = useState<View>({ kind: 'list' })
  const showList = () => setView({ kind: 'list' })
  const showDetail = (id: number) => setView({ kind: 'detail', id })

  return (
    <div className="page">
      {view.kind === 'list' && (
        <ProgramList
          token={token}
          onOpen={showDetail}
          onNew={() => setView({ kind: 'new' })}
        />
      )}
      {view.kind === 'detail' && (
        <ProgramDetail
          token={token}
          id={view.id}
          onBack={showList}
          onWorkoutStarted={onWorkoutStarted}
          weightUnit={weightUnit}
        />
      )}
      {view.kind === 'new' && (
        <ProgramEditor
          token={token}
          onSaved={showDetail}
          onCancel={showList}
          weightUnit={weightUnit}
        />
      )}
    </div>
  )
}
