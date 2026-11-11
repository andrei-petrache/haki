import { useEffect, useState } from 'react'
import { PROGRAMS_PAGE_SIZE, deleteProgram, describeError, fetchProgram, fetchPrograms } from './api'
import type { Program, ProgramSummary } from './api'
import { formatDayCount, formatPlanned } from './format'

type View = { kind: 'list' } | { kind: 'detail'; id: number }

/**
 * The programs, by name, a page at a time.
 *
 * Mounted afresh each time the list is shown, so after a change it reloads
 * from the first page instead of keeping pages whose offsets have shifted
 * (a new name can land anywhere in the order).
 */
function ProgramList({ token, onOpen }: { token: string; onOpen: (id: number) => void }) {
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
        <h2>Your programs</h2>
      </div>
      {error && <p className="error">{error}</p>}
      {programs === null && !error && <p className="muted">Loading…</p>}
      {programs?.length === 0 && <p className="muted empty">No programs yet</p>}
      {programs && programs.length > 0 && (
        <ul className="workout-list">
          {programs.map((program) => (
            <li key={program.id}>
              <button type="button" className="workout-card" onClick={() => onOpen(program.id)}>
                <strong>{program.name}</strong>
                <span className="muted">{formatDayCount(program.day_count)}</span>
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
          {loadingMore ? 'Loading…' : 'Load more'}
        </button>
      )}
    </section>
  )
}

function ProgramDetail({ token, id, onBack }: { token: string; id: number; onBack: () => void }) {
  const [program, setProgram] = useState<Program | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

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
    if (!window.confirm(`Delete the program "${loaded.name}"? Its workouts stay.`)) return
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

  return (
    <section className="card">
      <button type="button" className="link" onClick={onBack}>
        ‹ Back to programs
      </button>
      {error && <p className="error">{error}</p>}
      {!program && !error && <p className="muted">Loading…</p>}
      {program && (
        <>
          <h2>{program.name}</h2>
          {/* By position: the API returns the days in that order */}
          {program.days.map((day) => (
            <div key={day.id} className="workout-exercise">
              <h3>
                Day {day.position} · {day.name}
              </h3>
              <ul className="sets">
                {day.exercises.map((item, index) => (
                  // The same exercise may appear twice in a day: the index is the key
                  <li key={index}>
                    {item.exercise_name}: {formatPlanned(item.sets, item.reps, item.weight_kg)}
                  </li>
                ))}
              </ul>
            </div>
          ))}
          <div className="actions">
            <button
              type="button"
              className="secondary"
              disabled={deleting}
              onClick={() => void handleDelete(program)}
            >
              {deleting ? 'Deleting…' : 'Delete'}
            </button>
          </div>
        </>
      )}
    </section>
  )
}

export default function ProgramsPage({ token }: { token: string }) {
  const [view, setView] = useState<View>({ kind: 'list' })
  const showList = () => setView({ kind: 'list' })

  return (
    <div className="page">
      {view.kind === 'list' && (
        <ProgramList token={token} onOpen={(id) => setView({ kind: 'detail', id })} />
      )}
      {view.kind === 'detail' && <ProgramDetail token={token} id={view.id} onBack={showList} />}
    </div>
  )
}
