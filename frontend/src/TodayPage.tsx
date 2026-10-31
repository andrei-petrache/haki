import { useEffect, useState } from 'react'
import {
  MEAL_TYPES,
  createEntry,
  deleteEntry,
  describeError,
  fetchEntries,
  fetchFoods,
  fetchSummary,
  setCalorieTarget,
} from './api'
import type { DailySummary, Food, MealEntry, MealType } from './api'
import { formatDecimal, formatKcal, localDateString, shiftDate } from './format'

const MEAL_LABELS: Record<MealType, string> = {
  breakfast: 'Breakfast',
  lunch: 'Lunch',
  dinner: 'Dinner',
  snack: 'Snacks',
}

type DayData = { summary: DailySummary; entries: MealEntry[] }

function DayPicker({ day, onChange }: { day: string; onChange: (day: string) => void }) {
  const today = localDateString()

  return (
    <div className="day-picker">
      <button
        type="button"
        className="icon"
        aria-label="Previous day"
        onClick={() => onChange(shiftDate(day, -1))}
      >
        ‹
      </button>
      <input
        type="date"
        aria-label="Day"
        value={day}
        // Clearing the field gives an empty string: keep the current day
        onChange={(event) => event.target.value && onChange(event.target.value)}
      />
      <button
        type="button"
        className="icon"
        aria-label="Next day"
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
        Back to today
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
        {target === null ? 'Set a daily calorie target' : 'Change target'}
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
        Daily target (kcal)
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
          Save
        </button>
        {target !== null && (
          <button
            type="button"
            className="secondary"
            disabled={busy}
            onClick={() => void save(null)}
          >
            Clear target
          </button>
        )}
        <button type="button" className="link" onClick={() => setEditing(false)}>
          Cancel
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
  const { totals, daily_calorie_target: target, calories_remaining: remaining } =
    summary
  const over = remaining !== null && remaining < 0
  const percent = target ? Math.min(100, (totals.calories / target) * 100) : 0

  return (
    <section className="card summary">
      <p className="calories">
        <span className="big">{formatKcal(totals.calories)}</span>
        {target === null ? ' kcal eaten' : ` / ${formatKcal(target)} kcal`}
      </p>

      {target !== null && (
        <div
          className={over ? 'progress over' : 'progress'}
          role="progressbar"
          aria-label="Calories eaten"
          aria-valuemin={0}
          aria-valuemax={target}
          aria-valuenow={Math.round(totals.calories)}
        >
          <div style={{ width: `${percent}%` }} />
        </div>
      )}

      {remaining !== null &&
        (remaining < 0 ? (
          <p className="over-text">{formatKcal(-remaining)} kcal over target</p>
        ) : (
          <p className="muted">{formatKcal(remaining)} kcal left</p>
        ))}

      <dl className="macros">
        <div>
          <dt>Protein</dt>
          <dd>{formatDecimal(totals.protein)} g</dd>
        </div>
        <div>
          <dt>Carbs</dt>
          <dd>{formatDecimal(totals.carbs)} g</dd>
        </div>
        <div>
          <dt>Fat</dt>
          <dd>{formatDecimal(totals.fat)} g</dd>
        </div>
      </dl>

      <TargetEditor token={token} target={target} onSaved={onTargetChanged} />
    </section>
  )
}

function AddEntryForm({
  token,
  day,
  foods,
  onAdded,
}: {
  token: string
  day: string
  foods: Food[]
  onAdded: () => void
}) {
  const [foodId, setFoodId] = useState(String(foods[0].id))
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
      <h2>Add to this day</h2>
      <div className="entry-fields">
        <label className="food-field">
          Food
          <select value={foodId} onChange={(event) => setFoodId(event.target.value)}>
            {foods.map((food) => (
              <option key={food.id} value={food.id}>
                {food.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Grams
          <input
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
          Meal
          <select
            value={mealType}
            onChange={(event) => setMealType(event.target.value as MealType)}
          >
            {MEAL_TYPES.map((meal) => (
              <option key={meal} value={meal}>
                {MEAL_LABELS[meal]}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={busy}>
          {busy ? 'Adding…' : 'Add'}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  )
}

function EntryList({
  data,
  deletingId,
  onDelete,
}: {
  data: DayData
  deletingId: number | null
  onDelete: (entry: MealEntry) => void
}) {
  if (data.entries.length === 0) {
    return <p className="muted empty">Nothing logged for this day yet.</p>
  }

  return (
    <>
      {MEAL_TYPES.map((meal) => {
        const entries = data.entries.filter((entry) => entry.meal_type === meal)
        if (entries.length === 0) return null
        return (
          <section key={meal} className="card meal">
            <h3>
              {MEAL_LABELS[meal]}
              <span className="muted">
                {formatKcal(data.summary.meals[meal].calories)} kcal
              </span>
            </h3>
            <ul className="rows">
              {entries.map((entry) => (
                <li key={entry.id}>
                  <span className="grow">
                    {entry.food_name}{' '}
                    <span className="muted">{formatDecimal(entry.grams)} g</span>
                  </span>
                  <span>{formatKcal(entry.calories)} kcal</span>
                  <button
                    type="button"
                    className="icon"
                    aria-label={`Delete ${entry.food_name}`}
                    disabled={deletingId === entry.id}
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
  const [day, setDay] = useState(localDateString)
  const [foods, setFoods] = useState<Food[] | null>(null)
  const [data, setData] = useState<DayData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<number | null>(null)
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
    const what = `${entry.food_name} (${formatDecimal(entry.grams)} g)`
    if (!window.confirm(`Remove ${what} from ${MEAL_LABELS[entry.meal_type]}?`)) return
    setDeletingId(entry.id)
    try {
      await deleteEntry(token, entry.id)
      reload()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setDeletingId(null)
    }
  }

  // Data still showing the previous day counts as not loaded yet
  const current = data?.summary.eaten_on === day ? data : null

  return (
    <div className="page">
      <DayPicker day={day} onChange={setDay} />
      {error && <p className="error">{error}</p>}
      {!current && !error && <p className="muted">Loading…</p>}

      {current && (
        <SummaryCard
          token={token}
          summary={current.summary}
          onTargetChanged={reload}
        />
      )}

      {foods?.length === 0 && (
        <section className="card">
          <p>You have no foods yet. Add the foods you eat first, then log them here.</p>
          <button type="button" onClick={onGoToFoods}>
            Go to Foods
          </button>
        </section>
      )}
      {foods && foods.length > 0 && (
        <AddEntryForm token={token} day={day} foods={foods} onAdded={reload} />
      )}

      {current && (
        <EntryList
          data={current}
          deletingId={deletingId}
          onDelete={(entry) => void handleDelete(entry)}
        />
      )}
    </div>
  )
}
