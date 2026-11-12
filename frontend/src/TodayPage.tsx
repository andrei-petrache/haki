import { useEffect, useRef, useState } from 'react'
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
  setCalorieTarget,
} from './api'
import type { DailySummary, Food, MealEntry, MealType } from './api'
import { defaultCopyDay } from './copyTarget'
import { foodPicks } from './foodPicks'
import { formatDay, formatDecimal, formatKcal, localDateString, shiftDate } from './format'
import { useI18n } from './i18n/context'
import type { MessageKey } from './i18n/i18n'

const MEAL_LABELS: Record<MealType, MessageKey> = {
  breakfast: 'meal.breakfast',
  lunch: 'meal.lunch',
  dinner: 'meal.dinner',
  snack: 'meal.snack',
}

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
      <input
        type="date"
        aria-label={t('today.day')}
        value={day}
        // Clearing the field gives an empty string: keep the current day
        onChange={(event) => event.target.value && onChange(event.target.value)}
      />
      <button
        type="button"
        className="icon"
        aria-label={t('today.nextDay')}
        onClick={() => onChange(shiftDate(day, 1))}
      >
        ›
      </button>
      {/* Always rendered, only hidden on today: keeps its space, so the
          arrow buttons never move under the cursor */}
      <button
        type="button"
        className={day === today ? 'link invisible' : 'link'}
        disabled={day === today}
        onClick={() => onChange(today)}
      >
        {t('today.backToToday')}
      </button>
    </div>
  )
}

function TargetEditor({
  token,
  target,
  onSaved,
}: {
  token: string
  target: number | null
  onSaved: () => void
}) {
  const { t } = useI18n()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function save(newTarget: number | null) {
    setError(null)
    setBusy(true)
    try {
      await setCalorieTarget(token, newTarget)
      setEditing(false)
      onSaved()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  if (!editing) {
    return (
      <button
        type="button"
        className="link"
        onClick={() => {
          setValue(target === null ? '' : String(target))
          setError(null)
          setEditing(true)
        }}
      >
        {target === null ? t('today.setTarget') : t('today.changeTarget')}
      </button>
    )
  }

  return (
    <form
      className="target-form"
      onSubmit={(event) => {
        event.preventDefault()
        void save(Number(value))
      }}
    >
      <label>
        {t('today.dailyTarget')}
        <input
          type="number"
          inputMode="numeric"
          min={500}
          max={10000}
          step={1}
          required
          autoFocus
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      </label>
      <div className="actions">
        <button type="submit" disabled={busy}>
          {t('common.save')}
        </button>
        {target !== null && (
          <button
            type="button"
            className="secondary"
            disabled={busy}
            onClick={() => void save(null)}
          >
            {t('today.clearTarget')}
          </button>
        )}
        <button type="button" className="link" onClick={() => setEditing(false)}>
          {t('common.cancel')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  )
}

function SummaryCard({
  token,
  summary,
  onTargetChanged,
}: {
  token: string
  summary: DailySummary
  onTargetChanged: () => void
}) {
  const { t } = useI18n()
  const { totals, daily_calorie_target: target, calories_remaining: remaining } =
    summary
  const over = remaining !== null && remaining < 0
  const percent = target ? Math.min(100, (totals.calories / target) * 100) : 0

  return (
    <section className="card summary">
      <p className="calories">
        <span className="big">{formatKcal(totals.calories)}</span>
        {target === null ? ` ${t('today.kcalEaten')}` : ` / ${formatKcal(target)} kcal`}
      </p>

      {target !== null && (
        <div
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

      {remaining !== null &&
        (remaining < 0 ? (
          <p className="over-text">{t('today.over', { kcal: formatKcal(-remaining) })}</p>
        ) : (
          <p className="muted">{t('today.left', { kcal: formatKcal(remaining) })}</p>
        ))}

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

      <TargetEditor token={token} target={target} onSaved={onTargetChanged} />
    </section>
  )
}

/**
 * One tap per food (a favourite, or one logged recently): picks it in the
 * form and moves on to the grams, the only field that usually changes.
 */
function PickRow({
  label,
  groupLabel,
  foods,
  foodId,
  onPick,
}: {
  label: string
  groupLabel: string
  foods: Food[]
  foodId: string
  onPick: (food: Food) => void
}) {
  if (foods.length === 0) return null

  return (
    <div className="quick-picks" role="group" aria-label={groupLabel}>
      <span className="muted">{label}</span>
      {foods.map((food) => (
        <button
          key={food.id}
          type="button"
          className="chip"
          aria-pressed={String(food.id) === foodId}
          onClick={() => onPick(food)}
        >
          {food.name}
        </button>
      ))}
    </div>
  )
}

function AddEntryForm({
  token,
  day,
  foods,
  recent,
  onAdded,
}: {
  token: string
  day: string
  foods: Food[]
  recent: Food[]
  onAdded: () => void
}) {
  const { t } = useI18n()
  const [foodId, setFoodId] = useState(String(foods[0].id))
  const gramsRef = useRef<HTMLInputElement>(null)
  const picks = foodPicks(foods, recent)
  function pick(food: Food) {
    setFoodId(String(food.id))
    gramsRef.current?.focus()
  }
  const [grams, setGrams] = useState('')
  const [mealType, setMealType] = useState<MealType>('breakfast')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function handleSubmit() {
    setError(null)
    setBusy(true)
    try {
      await createEntry(token, {
        food_id: Number(foodId),
        eaten_on: day,
        meal_type: mealType,
        grams: Number(grams),
      })
      // Keep food and meal: the next entry is often for the same meal
      setGrams('')
      onAdded()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      className="card entry-form"
      onSubmit={(event) => {
        event.preventDefault()
        void handleSubmit()
      }}
    >
      <h2>{t('today.addTitle')}</h2>
      <PickRow
        label={t('today.favourites')}
        groupLabel={t('today.favouriteFoods')}
        foods={picks.favourites}
        foodId={foodId}
        onPick={pick}
      />
      <PickRow
        label={t('today.recent')}
        groupLabel={t('today.recentFoods')}
        foods={picks.recent}
        foodId={foodId}
        onPick={pick}
      />
      <div className="entry-fields">
        <label className="food-field">
          {t('today.food')}
          <select value={foodId} onChange={(event) => setFoodId(event.target.value)}>
            {foods.map((food) => (
              <option key={food.id} value={food.id}>
                {food.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('today.grams')}
          <input
            ref={gramsRef}
            type="number"
            inputMode="decimal"
            min={0.1}
            max={5000}
            step="any"
            required
            value={grams}
            onChange={(event) => setGrams(event.target.value)}
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
        <button type="submit" disabled={busy}>
          {busy ? t('today.adding') : t('today.add')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
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
  deletingKey,
  onDelete,
  onCopied,
}: {
  token: string
  day: string
  data: DayData
  deletingKey: string | null
  onDelete: (entry: MealEntry) => void
  onCopied: (message: string) => void
}) {
  const { t } = useI18n()
  const [copying, setCopying] = useState<MealType | null>(null)
  if (data.entries.length === 0) {
    return <p className="muted empty">{t('today.nothing')}</p>
  }

  return (
    <>
      {MEAL_TYPES.map((meal) => {
        const entries = data.entries.filter((entry) => entry.meal_type === meal)
        if (entries.length === 0) return null
        return (
          <section key={meal} className="card meal">
            <h3>
              {t(MEAL_LABELS[meal])}
              <span className="muted">
                {formatKcal(data.summary.meals[meal].calories)} kcal
              </span>
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
                    {entry.food_name}{' '}
                    <span className="muted">
                      {entry.grams === null ? t('quick.label') : `${formatDecimal(entry.grams)} g`}
                    </span>
                  </span>
                  <span>{formatKcal(entry.calories)} kcal</span>
                  <button
                    type="button"
                    className="icon"
                    aria-label={t('today.deleteEntry', { food: entry.food_name })}
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
  onGoToFoods,
}: {
  token: string
  onGoToFoods: () => void
}) {
  const { t } = useI18n()
  const [day, setDay] = useState(localDateString)
  const [foods, setFoods] = useState<Food[] | null>(null)
  const [recent, setRecent] = useState<Food[]>([])
  const [data, setData] = useState<DayData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deletingKey, setDeletingKey] = useState<string | null>(null)
  // What the last copy did; cleared when the shown day changes
  const [notice, setNotice] = useState<string | null>(null)
  // Bumped after every change, to re-run the effect that loads the day
  const [version, setVersion] = useState(0)
  const reload = () => setVersion((v) => v + 1)

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
  }, [token])

  // Reloaded after every change: a food just logged moves to the front
  useEffect(() => {
    let cancelled = false
    fetchRecentFoods(token)
      .then((list) => {
        if (!cancelled) setRecent(list)
      })
      // Only a shortcut: without it the form still works, so no error shown
      .catch(() => {
        if (!cancelled) setRecent([])
      })
    return () => {
      cancelled = true
    }
  }, [token, version])

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

  async function handleDelete(entry: MealEntry) {
    const meal = t(MEAL_LABELS[entry.meal_type])
    const question =
      entry.grams === null
        ? t('quick.removeConfirm', { food: entry.food_name, meal })
        : t('today.removeConfirm', {
            food: entry.food_name,
            grams: formatDecimal(entry.grams),
            meal,
          })
    if (!window.confirm(question)) return
    setDeletingKey(entryKey(entry))
    try {
      await deleteMealEntry(token, entry)
      reload()
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
      <DayPicker
        day={day}
        onChange={(next) => {
          setNotice(null)
          setDay(next)
        }}
      />
      {notice && <p role="status">{notice}</p>}
      {error && <p className="error">{error}</p>}
      {!current && !error && <p className="muted">{t('app.loading')}</p>}

      {current && (
        <SummaryCard
          token={token}
          summary={current.summary}
          onTargetChanged={reload}
        />
      )}

      {foods?.length === 0 && (
        <section className="card">
          <p>{t('today.noFoods')}</p>
          <button type="button" onClick={onGoToFoods}>
            {t('today.goToFoods')}
          </button>
        </section>
      )}
      {foods && foods.length > 0 && (
        <AddEntryForm
          token={token}
          day={day}
          foods={foods}
          recent={recent}
          onAdded={reload}
        />
      )}
      <QuickAddForm token={token} day={day} onAdded={reload} />

      {current && (
        <EntryList
          token={token}
          day={day}
          data={current}
          deletingKey={deletingKey}
          onDelete={(entry) => void handleDelete(entry)}
          onCopied={(message) => {
            setNotice(message)
            // The shown day changes when copied onto it; recents either way
            reload()
          }}
        />
      )}
    </div>
  )
}
