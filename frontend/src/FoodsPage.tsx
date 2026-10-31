import { useEffect, useState } from 'react'
import { createFood, deleteFood, describeError, fetchFoods, updateFood } from './api'
import type { Food, FoodInput } from './api'
import { formatDecimal } from './format'

// Form inputs hold text; convert to numbers only on submit
type FoodFields = Record<keyof FoodInput, string>
type NutrientKey = Exclude<keyof FoodInput, 'name'>

const NUTRIENT_FIELDS: { key: NutrientKey; label: string; max: number }[] = [
  { key: 'calories_per_100g', label: 'Calories (kcal)', max: 900 },
  { key: 'protein_per_100g', label: 'Protein (g)', max: 100 },
  { key: 'carbs_per_100g', label: 'Carbs (g)', max: 100 },
  { key: 'fat_per_100g', label: 'Fat (g)', max: 100 },
]

function toFields(food?: FoodInput): FoodFields {
  return {
    name: food?.name ?? '',
    calories_per_100g: food ? String(food.calories_per_100g) : '',
    protein_per_100g: food ? String(food.protein_per_100g) : '',
    carbs_per_100g: food ? String(food.carbs_per_100g) : '',
    fat_per_100g: food ? String(food.fat_per_100g) : '',
  }
}

function toInput(fields: FoodFields): FoodInput {
  return {
    name: fields.name,
    calories_per_100g: Number(fields.calories_per_100g),
    protein_per_100g: Number(fields.protein_per_100g),
    carbs_per_100g: Number(fields.carbs_per_100g),
    fat_per_100g: Number(fields.fat_per_100g),
  }
}

/** Add or edit form. Shows the API's error if onSubmit throws. */
function FoodForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: FoodInput
  submitLabel: string
  onSubmit: (food: FoodInput) => Promise<void>
  onCancel?: () => void
}) {
  const [fields, setFields] = useState(() => toFields(initial))
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function setField(key: keyof FoodInput, value: string) {
    setFields((current) => ({ ...current, [key]: value }))
  }

  async function handleSubmit() {
    setError(null)
    setBusy(true)
    try {
      await onSubmit(toInput(fields))
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      className="food-form"
      onSubmit={(event) => {
        event.preventDefault()
        void handleSubmit()
      }}
    >
      <label>
        Name
        <input
          value={fields.name}
          onChange={(event) => setField('name', event.target.value)}
          required
          maxLength={100}
        />
      </label>
      <fieldset className="nutrients">
        <legend className="muted">Per 100 g</legend>
        {NUTRIENT_FIELDS.map(({ key, label, max }) => (
          <label key={key}>
            {label}
            <input
              type="number"
              inputMode="decimal"
              min={0}
              max={max}
              step="any"
              required
              value={fields[key]}
              onChange={(event) => setField(key, event.target.value)}
            />
          </label>
        ))}
      </fieldset>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={busy}>
          {busy ? 'Saving…' : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="link" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  )
}

export default function FoodsPage({ token }: { token: string }) {
  const [foods, setFoods] = useState<Food[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  // A new key gives a fresh, empty add form after each successful add
  const [addFormKey, setAddFormKey] = useState(0)
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
  }, [token, version])

  async function handleCreate(food: FoodInput) {
    await createFood(token, food)
    setAddFormKey((key) => key + 1)
    reload()
  }

  async function handleUpdate(id: number, food: FoodInput) {
    await updateFood(token, id, food)
    setEditingId(null)
    reload()
  }

  async function handleDelete(food: Food) {
    if (!window.confirm(`Delete "${food.name}"?`)) return
    setError(null)
    try {
      await deleteFood(token, food.id)
      reload()
    } catch (err) {
      setError(`${food.name}: ${describeError(err)}`)
    }
  }

  return (
    <div className="page">
      <section className="card">
        <h2>Add a food</h2>
        <FoodForm key={addFormKey} submitLabel="Add food" onSubmit={handleCreate} />
      </section>

      <section className="card">
        <h2>Your foods</h2>
        {error && <p className="error">{error}</p>}
        {foods === null && !error && <p className="muted">Loading…</p>}
        {foods?.length === 0 && (
          <p className="muted">No foods yet. Add the first one above.</p>
        )}
        {foods && foods.length > 0 && (
          <ul className="rows">
            {foods.map((food) =>
              food.id === editingId ? (
                <li key={food.id}>
                  <FoodForm
                    initial={food}
                    submitLabel="Save"
                    onSubmit={(input) => handleUpdate(food.id, input)}
                    onCancel={() => setEditingId(null)}
                  />
                </li>
              ) : (
                <li key={food.id}>
                  <span className="grow">
                    <strong>{food.name}</strong>
                    <br />
                    <span className="muted">
                      {formatDecimal(food.calories_per_100g)} kcal · P{' '}
                      {formatDecimal(food.protein_per_100g)} · C{' '}
                      {formatDecimal(food.carbs_per_100g)} · F{' '}
                      {formatDecimal(food.fat_per_100g)} per 100 g
                    </span>
                  </span>
                  <span className="actions">
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setEditingId(food.id)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => void handleDelete(food)}
                    >
                      Delete
                    </button>
                  </span>
                </li>
              ),
            )}
          </ul>
        )}
      </section>
    </div>
  )
}
