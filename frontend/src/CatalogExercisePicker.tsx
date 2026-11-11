import { useEffect, useState } from 'react'
import {
  ApiError,
  CATALOG_PAGE_SIZE,
  copyCatalogExercise,
  describeError,
  fetchExercises,
  searchCatalogExercises,
} from './api'
import type { CatalogExercise, Exercise } from './api'
import { catalogLanguage, catalogName, searchText } from './catalog'
import { useI18n } from './i18n/context'

const SEARCH_DELAY_MS = 250

/** The user's exercise with this name, as the API compares names: trimmed, any case. */
function ownByName(own: Exercise[], name: string): Exercise | undefined {
  const key = name.trim().toLowerCase()
  return own.find((exercise) => exercise.name.trim().toLowerCase() === key)
}

/** What a catalog exercise is, in a few words: its main muscles and its equipment. */
function details(item: CatalogExercise): string {
  return [item.primary_muscles.join(', '), item.equipment].filter(Boolean).join(' · ')
}

/**
 * "From the catalog", under an exercise choice in the workout and program
 * editors: search the catalog's exercises, pick one, and the row uses the
 * user's own copy of it. A copy they already had is reused (200); one of
 * their own exercises with that name (409) is used instead, and said so.
 */
export default function CatalogExercisePicker({
  token,
  own,
  onPick,
}: {
  token: string
  /** The user's own exercises, as the editor knows them */
  own: Exercise[]
  /** The row now uses this exercise of the user's */
  onPick: (exercise: Exercise) => void
}) {
  const { t, locale } = useI18n()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const q = searchText(text)
  const [found, setFound] = useState<{ q: string; items: CatalogExercise[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [picking, setPicking] = useState(false)
  const [notice, setNotice] = useState<{ error: boolean; text: string } | null>(null)
  const language = catalogLanguage(locale)

  useEffect(() => {
    if (!open || q === '') return
    let cancelled = false
    const timer = window.setTimeout(() => {
      searchCatalogExercises(token, q, language)
        .then((items) => {
          if (cancelled) return
          setFound({ q, items })
          setError(null)
        })
        .catch((err) => {
          if (!cancelled) setError(describeError(err))
        })
    }, SEARCH_DELAY_MS)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [token, q, language, open])

  async function handlePick(item: CatalogExercise) {
    const name = catalogName(item, locale)
    setNotice(null)
    setPicking(true)
    try {
      const { item: exercise, created } = await copyCatalogExercise(token, item.id, language)
      onPick(exercise)
      setNotice({
        error: false,
        text: t(created ? 'catalog.exerciseAdded' : 'catalog.exerciseExisting', { name: exercise.name }),
      })
      setOpen(false)
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        // Theirs has the name: use it. Look again if the editor's list is older.
        const mine = ownByName(own, name) ?? ownByName(await fetchExercises(token).catch(() => []), name)
        if (mine) {
          onPick(mine)
          setNotice({ error: false, text: t('catalog.exerciseTaken', { name: mine.name }) })
          setOpen(false)
          return
        }
      }
      setNotice({ error: true, text: describeError(err) })
    } finally {
      setPicking(false)
    }
  }

  const items = open && q !== '' && found?.q === q ? found.items : null

  return (
    <div className="catalog-inline">
      <button
        type="button"
        className="link"
        aria-expanded={open}
        onClick={() => {
          setOpen(!open)
          setNotice(null)
        }}
      >
        {open ? t('catalog.exercisesClose') : t('catalog.exercisesOpen')}
      </button>
      {notice && (
        <p className={notice.error ? 'error' : 'notice'} role="status">
          {notice.text}
        </p>
      )}
      {open && (
        <div className="catalog-panel">
          <label>
            {t('catalog.search')}
            <input
              type="search"
              value={text}
              placeholder={t('catalog.exercisesPlaceholder')}
              onChange={(event) => setText(event.target.value)}
            />
          </label>
          {q !== '' && error && <p className="error">{error}</p>}
          {q !== '' && !items && !error && <p className="muted">{t('catalog.searching')}</p>}
          {items?.length === 0 && <p className="muted">{t('catalog.none', { q })}</p>}
          {items && items.length > 0 && (
            <ul className="rows">
              {items.map((item) => (
                <li key={item.id}>
                  <span className="grow">
                    <strong>{catalogName(item, locale)}</strong>
                    <br />
                    <span className="muted">{details(item)}</span>
                  </span>
                  <button
                    type="button"
                    className="secondary"
                    disabled={picking}
                    aria-label={t('catalog.useName', { name: catalogName(item, locale) })}
                    onClick={() => void handlePick(item)}
                  >
                    {t('catalog.use')}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {items && items.length === CATALOG_PAGE_SIZE && (
            <p className="muted">{t('catalog.more', { count: CATALOG_PAGE_SIZE })}</p>
          )}
        </div>
      )}
    </div>
  )
}
