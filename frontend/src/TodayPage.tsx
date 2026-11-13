import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  MEAL_TYPES,
  copyMeal,
  createEntry,
  createQuickEntry,
  deleteMealEntry,
  entryKey,
  describeError,
  fetchEntries,
  fetchFoods,
  fetchRecentFoods,
  fetchSummary,
} from './api'
import type { DailySummary, Food, MealEntry, MealType } from './api'
import { defaultCopyDay } from './copyTarget'
import FoodLogger from './FoodLogger'
import { MEAL_LABELS, entryName, headline, keepOrder, mealForHour } from './logging'
import DayChoice from './DayChoice'
import Toast from './Toast'
import type { ToastMessage } from './Toast'
import { formatDay, formatDecimal, formatKcal, localDateString, shiftDate } from './format'
import { useI18n } from './i18n/context'
import type { MessageKey } from './i18n/i18n'

type DayData = { summary: DailySummary; entries: MealEntry[] }

function DayPicker({ day, onChange }: { day: string; onChange: (day: string) => void }) {
  const { t } = useI18n()
  const today = localDateString()

  return (
    <div className="day-picker">
      <button
        type="button"
        className="icon"
        aria-label={t('today.previousDay')}
        onClick={() => onChange(shiftDate(day, -1))}
      >
        ‹
      </button>
      <DayChoice day={day} onChange={onChange} fieldLabel={t('today.day')} />
      <button
        type="button"
        className="icon"
        aria-label={t('today.nextDay')}
        onClick={() => onChange(shiftDate(day, 1))}
      >
        ›
      </button>
      {day !== today && (
        <button type="button" className="link back-to-today" onClick={() => onChange(today)}>
          {t('today.backToToday')}
        </button>
      )}
    </div>
  )
}

function SummaryCard({ summary }: { summary: DailySummary }) {
  const { t } = useI18n()
  const { totals, daily_calorie_target: target } = summary
  const head = headline(summary)
  const over = head.kind === 'over'
  const percent = target ? Math.min(100, (totals.calories / target) * 100) : 0
  const label: MessageKey =
    head.kind === 'over' ? 'today.kcalOver' : head.kind === 'left' ? 'today.kcalLeft' : 'today.kcalEaten'

  return (
    <section className="card summary">
      <p className={over ? 'calories over' : 'calories'}>
        <span className="big">{formatKcal(head.kcal)}</span> {t(label)}
      </p>
      {target !== null && (
        <p className="muted">
          {t('today.eatenOf', { eaten: formatKcal(totals.calories), target: formatKcal(target) })}
        </p>
      )}

      {target !== null && (
        <div
          // Red only past the target; under it the bar is plain
          className={over ? 'progress over' : 'progress'}
          role="progressbar"
          aria-label={t('today.caloriesEaten')}
          aria-valuemin={0}
          aria-valuemax={target}
          aria-valuenow={Math.round(totals.calories)}
        >
          <div style={{ width: `${percent}%` }} />
        </div>
      )}

      <dl className="macros">
        <div>
          <dt>{t('today.protein')}</dt>
          <dd>{formatDecimal(totals.protein)} g</dd>
        </div>
        <div>
          <dt>{t('today.carbs')}</dt>
          <dd>{formatDecimal(totals.carbs)} g</dd>
        </div>
        <div>
          <dt>{t('today.fat')}</dt>
          <dd>{formatDecimal(totals.fat)} g</dd>
        </div>
      </dl>

    </section>
  )
}

/**
 * Copy one meal of the shown day to another meal or day, then say what
 * was copied where.
 */
function CopyMealForm({
  token,
  day,
  meal,
  onCopied,
  onClose,
}: {
  token: string
  day: string
  meal: MealType
  onCopied: (message: string) => void
  onClose: () => void
}) {
  const { t } = useI18n()
  const [toDay, setToDay] = useState(() => defaultCopyDay(day, localDateString()))
  const [toMeal, setToMeal] = useState<MealType>(meal)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const same = toDay === day && toMeal === meal

  async function handleSubmit() {
    setError(null)
    setBusy(true)
    try {
      const copied = await copyMeal(token, {
        from_day: day,
        from_meal: meal,
        to_day: toDay,
        to_meal: toMeal,
      })
      const where = { meal: t(MEAL_LABELS[toMeal]), day: formatDay(toDay) }
      onCopied(
        copied.length === 0
          ? t('today.nothingToCopy')
          : t('today.copied', { count: copied.length, ...where }),
      )
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      className="copy-form"
      aria-label={t('today.copyTitle', { meal: t(MEAL_LABELS[meal]) })}
      onSubmit={(event) => {
        event.preventDefault()
        void handleSubmit()
      }}
    >
      <label>
        {t('today.copyToDay')}
        <input
          type="date"
          required
          value={toDay}
          // Clearing the field gives an empty string: keep the last day
          onChange={(event) => event.target.value && setToDay(event.target.value)}
        />
      </label>
      <label>
        {t('today.copyToMeal')}
        <select value={toMeal} onChange={(event) => setToMeal(event.target.value as MealType)}>
          {MEAL_TYPES.map((option) => (
            <option key={option} value={option}>
              {t(MEAL_LABELS[option])}
            </option>
          ))}
        </select>
      </label>
      <div className="actions">
        <button type="submit" disabled={busy || same}>
          {busy ? t('today.copying') : t('today.copy')}
        </button>
        <button type="button" className="link" onClick={onClose}>
          {t('common.cancel')}
        </button>
      </div>
      {same && <p className="muted">{t('today.copySame')}</p>}
      {error && <p className="error">{error}</p>}
    </form>
  )
}

/** Optional macro field: empty means 0, as the API's default. */
function optionalGrams(value: string): number | undefined {
  return value === '' ? undefined : Number(value)
}

/**
 * Log something without a food: a restaurant dish, a snack with only a
 * label's kcal. Folded away until asked for; it works with no foods at all.
 */
function QuickAddForm({
  token,
  day,
  onAdded,
}: {
  token: string
  day: string
  onAdded: () => void
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [calories, setCalories] = useState('')
  const [protein, setProtein] = useState('')
  const [carbs, setCarbs] = useState('')
  const [fat, setFat] = useState('')
  const [mealType, setMealType] = useState<MealType>('breakfast')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!open) {
    return (
      <button type="button" className="secondary quick-open" onClick={() => setOpen(true)}>
        {t('quick.open')}
      </button>
    )
  }

  async function handleSubmit() {
    setError(null)
    setBusy(true)
    try {
      await createQuickEntry(token, {
        eaten_on: day,
        meal_type: mealType,
        calories: Number(calories),
        // Empty name: the server's default ("Quick add")
        ...(name.trim() && { name: name.trim() }),
        protein: optionalGrams(protein),
        carbs: optionalGrams(carbs),
        fat: optionalGrams(fat),
      })
      // Keep the meal: the next one is often for the same meal
      setName('')
      setCalories('')
      setProtein('')
      setCarbs('')
      setFat('')
      onAdded()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const macros: [string, string, (value: string) => void][] = [
    [t('today.protein'), protein, setProtein],
    [t('today.carbs'), carbs, setCarbs],
    [t('today.fat'), fat, setFat],
  ]

  return (
    <form
      className="card quick-form"
      aria-label={t('quick.title')}
      onSubmit={(event) => {
        event.preventDefault()
        void handleSubmit()
      }}
    >
      <h2>{t('quick.title')}</h2>
      <p className="muted">{t('quick.optional')}</p>
      <div className="quick-fields">
        <label className="quick-name">
          {t('quick.name')}
          <input
            value={name}
            maxLength={100}
            placeholder={t('quick.namePlaceholder')}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label>
          {t('quick.calories')}
          <input
            type="number"
            inputMode="decimal"
            min={0}
            max={5000}
            step="any"
            required
            value={calories}
            onChange={(event) => setCalories(event.target.value)}
          />
        </label>
        <label>
          {t('today.meal')}
          <select
            value={mealType}
            onChange={(event) => setMealType(event.target.value as MealType)}
          >
            {MEAL_TYPES.map((meal) => (
              <option key={meal} value={meal}>
                {t(MEAL_LABELS[meal])}
              </option>
            ))}
          </select>
        </label>
        {macros.map(([label, value, setValue]) => (
          <label key={label}>
            {t('quick.macro', { macro: label })}
            <input
              type="number"
              inputMode="decimal"
              min={0}
              max={500}
              step="any"
              value={value}
              onChange={(event) => setValue(event.target.value)}
            />
          </label>
        ))}
      </div>
      <div className="actions">
        <button type="submit" disabled={busy}>
          {busy ? t('today.adding') : t('today.add')}
        </button>
        <button type="button" className="link" onClick={() => setOpen(false)}>
          {t('common.cancel')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  )
}

function EntryList({
  token,
  day,
  data,
  openMeal,
  deletingKey,
  onOpen,
  onDelete,
  onCopied,
}: {
  token: string
  day: string
  data: DayData
  // The meal shown in full, the one new entries go to
  openMeal: MealType
  deletingKey: string | null
  onOpen: (meal: MealType) => void
  onDelete: (entry: MealEntry) => void
  onCopied: (message: string) => void
}) {
  const { t, locale } = useI18n()
  const [copying, setCopying] = useState<MealType | null>(null)
  if (data.entries.length === 0) {
    return <p className="muted empty">{t('today.nothing')}</p>
  }

  return (
    <>
      {MEAL_TYPES.map((meal) => {
        const entries = data.entries.filter((entry) => entry.meal_type === meal)
        if (entries.length === 0) return null
        const kcal = formatKcal(data.summary.meals[meal].calories)
        if (meal !== openMeal) {
          return (
            <button
              key={meal}
              type="button"
              className="card meal-line"
              aria-expanded={false}
              aria-label={t('today.openMeal', { meal: t(MEAL_LABELS[meal]) })}
              onClick={() => onOpen(meal)}
            >
              <span>
                {t(MEAL_LABELS[meal])}{' '}
                <span className="muted">· {t('today.items', { count: entries.length })}</span>
              </span>
              <span className="kcal">{kcal}</span>
            </button>
          )
        }
        return (
          <section key={meal} className="card meal">
            <h3>
              {t(MEAL_LABELS[meal])}
              <span className="kcal">{kcal}</span>
            </h3>
            {copying === meal ? (
              <CopyMealForm
                token={token}
                day={day}
                meal={meal}
                onCopied={(message) => {
                  setCopying(null)
                  onCopied(message)
                }}
                onClose={() => setCopying(null)}
              />
            ) : (
              <button
                type="button"
                className="link"
                aria-label={t('today.copyTitle', { meal: t(MEAL_LABELS[meal]) })}
                onClick={() => setCopying(meal)}
              >
                {t('today.copyOpen')}
              </button>
            )}
            <ul className="rows">
              {entries.map((entry) => (
                <li key={entryKey(entry)}>
                  <span className="grow">
                    {entryName(entry, locale)}{' '}
                    <span className="muted">
                      {entry.grams === null ? t('quick.label') : `${formatDecimal(entry.grams)} g`}
                    </span>
                  </span>
                  <span>{formatKcal(entry.calories)} kcal</span>
                  <button
                    type="button"
                    className="icon"
                    aria-label={t('today.deleteEntry', { food: entryName(entry, locale) })}
                    disabled={deletingKey === entryKey(entry)}
                    onClick={() => onDelete(entry)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </>
  )
}

export default function TodayPage({
  token,
  headerSlot,
}: {
  token: string
  // Where the day picker goes: the app header, next to the wordmark
  headerSlot: HTMLElement | null
}) {
  const { t, locale } = useI18n()
  const [day, setDay] = useState(localDateString)
  const [foods, setFoods] = useState<Food[] | null>(null)
  const [recent, setRecent] = useState<Food[]>([])
  const [data, setData] = useState<DayData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deletingKey, setDeletingKey] = useState<string | null>(null)
  // What the last copy did; cleared when the shown day changes
  const [notice, setNotice] = useState<string | null>(null)
  // The meal new entries go to, and the one shown in full
  const [meal, setMeal] = useState<MealType>(() => mealForHour(new Date().getHours()))
  // "Added ... · Undo" after a one-tap or searched entry
  const [toast, setToast] = useState<ToastMessage | null>(null)
  const clearToast = useCallback(() => setToast(null), [])
  // Bumped after every change, to re-run the effect that loads the day
  const [version, setVersion] = useState(0)
  const reload = () => setVersion((v) => v + 1)

  // Reloaded after every change too: a chip shows how much was logged last time
  useEffect(() => {
    let cancelled = false
    fetchFoods(token)
      .then((list) => {
        if (!cancelled) setFoods(list)
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err))
      })
    return () => {
      cancelled = true
    }
  }, [token, version])

  // The chips' order, fixed for this visit and day: a chip just used keeps
  // its place (its quantity updates); new foods go to the end
  const chipOrder = useRef<{ day: string; ids: number[] } | null>(null)

  // Reloaded after every change, for the quantities and new foods
  useEffect(() => {
    let cancelled = false
    fetchRecentFoods(token)
      .then((list) => {
        if (cancelled) return
        const order = chipOrder.current
        const kept = order && order.day === day ? keepOrder(list, order.ids) : list
        chipOrder.current = { day, ids: kept.map((food) => food.id) }
        setRecent(kept)
      })
      // Only a shortcut: without it the form still works, so no error shown
      .catch(() => {
        if (!cancelled) setRecent([])
      })
    return () => {
      cancelled = true
    }
  }, [token, version, day])

  useEffect(() => {
    // If the day changes before the answer arrives, ignore the stale answer
    let cancelled = false
    Promise.all([fetchSummary(token, day), fetchEntries(token, day)])
      .then(([summary, entries]) => {
        if (cancelled) return
        setData({ summary, entries })
        setError(null)
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err))
      })
    return () => {
      cancelled = true
    }
  }, [token, day, version])

  /**
   * Delete at once, no confirm dialog: the message offers Undo, which logs
   * the same entry again (a quick entry with its own kcal and macros).
   */
  async function handleDelete(entry: MealEntry) {
    setDeletingKey(entryKey(entry))
    try {
      await deleteMealEntry(token, entry)
      reload()
      const food = entryName(entry, locale)
      const meal = t(MEAL_LABELS[entry.meal_type])
      setToast({
        id: Date.now(),
        text:
          entry.grams === null
            ? t('log.removedQuick', { food, meal })
            : t('log.removed', { food, grams: formatDecimal(entry.grams), meal }),
        undo: async () => {
          try {
            if (entry.grams === null || entry.food_id === null) {
              await createQuickEntry(token, {
                eaten_on: entry.eaten_on,
                meal_type: entry.meal_type,
                calories: entry.calories,
                name: entry.food_name,
                protein: entry.protein,
                carbs: entry.carbs,
                fat: entry.fat,
              })
            } else {
              await createEntry(token, {
                food_id: entry.food_id,
                eaten_on: entry.eaten_on,
                meal_type: entry.meal_type,
                grams: entry.grams,
              })
            }
          } catch (err) {
            setError(describeError(err))
          }
          reload()
        },
      })
    } catch (err) {
      setError(describeError(err))
    } finally {
      setDeletingKey(null)
    }
  }

  // Data still showing the previous day counts as not loaded yet
  const current = data?.summary.eaten_on === day ? data : null

  return (
    <div className="page">
      {(() => {
        const picker = (
          <DayPicker
            day={day}
            onChange={(next) => {
              setNotice(null)
              setDay(next)
            }}
          />
        )
        return headerSlot ? createPortal(picker, headerSlot) : picker
      })()}
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
      {!current && !error && <p className="muted">{t('app.loading')}</p>}

      {current && (
        <SummaryCard summary={current.summary} />
      )}

      {foods && (
        <FoodLogger
          token={token}
          day={day}
          meal={meal}
          foods={foods}
          recent={recent}
          onMealChange={setMeal}
          onLogged={(entry, name) => {
            reload()
            setToast({
              id: Date.now(),
              text: t('log.added', {
                food: name,
                grams: formatDecimal(entry.grams ?? 0),
                meal: t(MEAL_LABELS[entry.meal_type]),
              }),
              undo: async () => {
                try {
                  await deleteMealEntry(token, entry)
                } catch (err) {
                  setError(describeError(err))
                }
                reload()
              },
            })
          }}
        />
      )}
      <QuickAddForm token={token} day={day} onAdded={reload} />

      {current && (
        <EntryList
          token={token}
          day={day}
          data={current}
          openMeal={meal}
          onOpen={setMeal}
          deletingKey={deletingKey}
          onDelete={(entry) => void handleDelete(entry)}
          onCopied={(message) => {
            setNotice(message)
            // The shown day changes when copied onto it; recents either way
            reload()
          }}
        />
      )}
      <Toast message={toast} onDone={clearToast} />
    </div>
  )
}
