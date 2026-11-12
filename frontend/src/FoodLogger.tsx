import { useEffect, useState } from 'react'
import {
  MEAL_TYPES,
  copyCatalogFood,
  createEntry,
  describeError,
  fetchCatalogSources,
  searchFoods,
} from './api'
import type { Food, FoodSearchResult, MealEntry, MealType } from './api'
import { catalogLanguage } from './catalog'
import { foodPicks } from './foodPicks'
import { formatDecimal, formatKcal } from './format'
import { useI18n } from './i18n/context'
import { MAX_GRAMS, MEAL_LABELS, displayName, kcalFor, startGrams, stepGrams } from './logging'

/** A food to log, from the user's own or from the catalog. */
type Candidate =
  | { origin: 'own'; food: Food | Extract<FoodSearchResult, { origin: 'own' }> }
  | { origin: 'catalog'; food: Extract<FoodSearchResult, { origin: 'catalog' }> }

function candidateKey(c: Candidate): string {
  return `${c.origin}-${c.food.id}`
}

/** Which meal new entries go to: four buttons, one pressed. */
function MealPicker({ meal, onChange }: { meal: MealType; onChange: (meal: MealType) => void }) {
  const { t } = useI18n()
  return (
    <div className="segmented" role="group" aria-label={t('log.mealGroup')}>
      {MEAL_TYPES.map((option) => (
        <button
          key={option}
          type="button"
          aria-pressed={option === meal}
          onClick={() => onChange(option)}
        >
          {t(MEAL_LABELS[option])}
        </button>
      ))}
    </div>
  )
}

/**
 * The stepper and Add for one food: grams start as last time (else 100),
 * move by 10 g, and Add says how many kcal it logs.
 */
function LogRow({
  candidate,
  busy,
  onAdd,
}: {
  candidate: Candidate
  busy: boolean
  onAdd: (grams: number) => void
}) {
  const { t, locale } = useI18n()
  const last = candidate.origin === 'own' ? candidate.food.last_logged : null
  const [grams, setGrams] = useState(() => startGrams(last))
  const name = candidate.origin === 'own' ? displayName(candidate.food, locale) : candidate.food.name
  const valid = Number.isFinite(grams) && grams > 0 && grams <= MAX_GRAMS

  return (
    <div className="log-row">
      <div className="stepper">
        <button
          type="button"
          className="icon"
          aria-label={t('log.less', { name })}
          onClick={() => setGrams((g) => stepGrams(g, -1))}
        >
          −
        </button>
        <label>
          <span className="visually-hidden">{t('log.grams', { name })}</span>
          <input
            type="number"
            inputMode="decimal"
            min={0.1}
            max={MAX_GRAMS}
            step="any"
            value={Number.isFinite(grams) ? grams : ''}
            onChange={(event) => setGrams(Number(event.target.value))}
          />
        </label>
        <span className="muted">g</span>
        <button
          type="button"
          className="icon"
          aria-label={t('log.more', { name })}
          onClick={() => setGrams((g) => stepGrams(g, 1))}
        >
          +
        </button>
      </div>
      <button type="button" disabled={busy || !valid} onClick={() => onAdd(grams)}>
        {t('log.add', { kcal: formatKcal(kcalFor(candidate.food.calories_per_100g, valid ? grams : 0)) })}
      </button>
    </div>
  )
}

/**
 * Logging on Today: the meal new entries go to, one-tap chips for the
 * favourites and the recent foods (as much as last time), and one search
 * over the user's foods and the catalog (GET /foods/search). Every entry
 * made here is reported through onLogged, which offers Undo.
 */
export default function FoodLogger({
  token,
  day,
  meal,
  foods,
  recent,
  onMealChange,
  onLogged,
}: {
  token: string
  day: string
  meal: MealType
  foods: Food[]
  recent: Food[]
  onMealChange: (meal: MealType) => void
  onLogged: (entry: MealEntry, name: string) => void
}) {
  const { t, locale } = useI18n()
  const language = catalogLanguage(locale)
  const [q, setQ] = useState('')
  const [results, setResults] = useState<FoodSearchResult[] | null>(null)
  const [open, setOpen] = useState<Candidate | null>(null)
  const [sources, setSources] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const picks = foodPicks(foods, recent)

  // Search as the user types, a moment after they stop
  useEffect(() => {
    const query = q.trim()
    if (query === '') return
    let cancelled = false
    const timer = window.setTimeout(() => {
      searchFoods(token, query, language)
        .then((list) => {
          if (!cancelled) setResults(list)
        })
        .catch((err) => {
          if (!cancelled) setError(describeError(err))
        })
    }, 250)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [token, q, language])

  // Source names for the credit line under catalog results
  useEffect(() => {
    let cancelled = false
    fetchCatalogSources(token)
      .then((list) => {
        if (!cancelled) setSources(Object.fromEntries(list.map((s) => [s.key, s.name])))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [token])

  async function log(candidate: Candidate, grams: number) {
    setError(null)
    setBusy(true)
    try {
      const foodId =
        candidate.origin === 'own'
          ? candidate.food.id
          : (await copyCatalogFood(token, candidate.food.id, language)).item.id
      const entry = await createEntry(token, { food_id: foodId, eaten_on: day, meal_type: meal, grams })
      const name = candidate.origin === 'own' ? displayName(candidate.food, locale) : candidate.food.name
      setOpen(null)
      onLogged(entry, name)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  /** A chip: logs at once when there is a last time, else opens its stepper. */
  function chip(food: Food) {
    const name = displayName(food, locale)
    const last = food.last_logged
    return (
      <button
        key={food.id}
        type="button"
        className="chip"
        aria-label={last ? t('log.chipLog', { name, grams: formatDecimal(last.grams) }) : name}
        disabled={busy}
        onClick={() =>
          last ? void log({ origin: 'own', food }, last.grams) : setOpen({ origin: 'own', food })
        }
      >
        {name}
        {last && <span className="chip-grams"> {formatDecimal(last.grams)} g</span>}
      </button>
    )
  }

  const query = q.trim()
  const shown = query === '' ? null : results
  const own = shown?.filter((r): r is Extract<FoodSearchResult, { origin: 'own' }> => r.origin === 'own') ?? []
  const catalog =
    shown?.filter((r): r is Extract<FoodSearchResult, { origin: 'catalog' }> => r.origin === 'catalog') ?? []
  const credit = [...new Set(catalog.map((r) => sources[r.source_key] ?? r.source_key))].join(', ')

  function resultRow(candidate: Candidate) {
    const key = candidateKey(candidate)
    const food = candidate.food
    const name = candidate.origin === 'own' ? displayName(food as Food, locale) : food.name
    const last = candidate.origin === 'own' ? candidate.food.last_logged : null
    const isOpen = open !== null && candidateKey(open) === key
    return (
      <li key={key} className={isOpen ? 'result open' : 'result'}>
        <button
          type="button"
          className="result-head"
          aria-expanded={isOpen}
          onClick={() => setOpen(isOpen ? null : candidate)}
        >
          <strong>{name}</strong>
          <span className="muted">
            {last
              ? t('log.lastTime', {
                  grams: formatDecimal(last.grams),
                  kcal: formatKcal(kcalFor(food.calories_per_100g, last.grams)),
                })
              : t('foods.row', {
                  kcal: formatDecimal(food.calories_per_100g),
                  protein: formatDecimal(food.protein_per_100g),
                  carbs: formatDecimal(food.carbs_per_100g),
                  fat: formatDecimal(food.fat_per_100g),
                })}
          </span>
        </button>
        {isOpen && <LogRow candidate={candidate} busy={busy} onAdd={(grams) => void log(candidate, grams)} />}
      </li>
    )
  }

  // A chip without a last time opens here, above the search
  const openPick = open && open.origin === 'own' && !own.some((r) => r.id === open.food.id) ? open : null

  return (
    <section className="card logger" aria-label={t('log.title', { meal: t(MEAL_LABELS[meal]) })}>
      <MealPicker meal={meal} onChange={onMealChange} />

      {picks.favourites.length > 0 && (
        <div className="quick-picks" role="group" aria-label={t('today.favouriteFoods')}>
          {picks.favourites.map(chip)}
        </div>
      )}
      {picks.recent.length > 0 && (
        <div className="quick-picks" role="group" aria-label={t('today.recentFoods')}>
          {picks.recent.map(chip)}
        </div>
      )}
      {openPick && <ul className="results">{resultRow(openPick)}</ul>}

      <label className="search-field">
        <span className="visually-hidden">{t('log.search')}</span>
        <input
          type="search"
          placeholder={t('log.search')}
          value={q}
          onChange={(event) => {
            setQ(event.target.value)
            setOpen(null)
            if (event.target.value.trim() === '') setResults(null)
          }}
        />
      </label>
      {error && <p className="error">{error}</p>}

      {query !== '' && shown === null && !error && <p className="muted">{t('catalog.searching')}</p>}
      {shown !== null && shown.length === 0 && <p className="muted">{t('log.none', { q: query })}</p>}
      {own.length > 0 && (
        <>
          <h3 className="results-title">{t('log.yours')}</h3>
          <ul className="results">{own.map((food) => resultRow({ origin: 'own', food }))}</ul>
        </>
      )}
      {catalog.length > 0 && (
        <>
          <h3 className="results-title">{t('log.catalog')}</h3>
          <ul className="results">{catalog.map((food) => resultRow({ origin: 'catalog', food }))}</ul>
          {credit && <p className="muted small">{t('log.source', { source: credit })}</p>}
        </>
      )}
    </section>
  )
}
