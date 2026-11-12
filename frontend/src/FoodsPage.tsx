import { useEffect, useState } from 'react'
import { createFood, deleteFood, describeError, fetchFoods, updateFood } from './api'
import type { Food, FoodInput } from './api'
import CatalogFoodPicker from './CatalogFoodPicker'
import { formatDecimal } from './format'
import { useI18n } from './i18n/context'
import type { MessageKey } from './i18n/i18n'

// Form inputs hold text; convert to numbers only on submit
type FoodFields = Record<keyof FoodInput, string>
type NutrientKey = Exclude<keyof FoodInput, 'name'>

// The backend's MAX_CALORIES_PER_100G (app/schemas.py). Pure fat is about
// 900, but USDA rounds per food: lard is 902, and a copy of it from the
// catalog must stay editable (the browser blocks a submit over max).
const MAX_CALORIES_PER_100G = 950

const NUTRIENT_FIELDS: { key: NutrientKey; label: MessageKey; max: number }[] = [
  { key: 'calories_per_100g', label: 'foods.calories', max: MAX_CALORIES_PER_100G },
  { key: 'protein_per_100g', label: 'foods.protein', max: 100 },
  { key: 'carbs_per_100g', label: 'foods.carbs', max: 100 },
  { key: 'fat_per_100g', label: 'foods.fat', max: 100 },
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
  const { t } = useI18n()
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
        {t('foods.name')}
        <input
          value={fields.name}
          onChange={(event) => setField('name', event.target.value)}
          required
          maxLength={100}
        />
      </label>
      <fieldset className="nutrients">
        <legend className="muted">{t('foods.per100g')}</legend>
        {NUTRIENT_FIELDS.map(({ key, label, max }) => (
          <label key={key}>
            {t(label)}
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
          {busy ? t('common.saving') : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="link" onClick={onCancel}>
            {t('common.cancel')}
          </button>
        )}
      </div>
    </form>
  )
}

export default function FoodsPage({ token }: { token: string }) {
  const { t } = useI18n()
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

  // A successful change makes an older list error (e.g. a failed delete) stale
  async function handleCreate(food: FoodInput) {
    await createFood(token, food)
    setError(null)
    setAddFormKey((key) => key + 1)
    reload()
  }

  async function handleUpdate(id: number, food: FoodInput) {
    await updateFood(token, id, food)
    setError(null)
    setEditingId(null)
    reload()
  }

  async function handleDelete(food: Food) {
    if (!window.confirm(t('foods.deleteConfirm', { name: food.name }))) return
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
      {/* The fastest way in: a food from the catalog, as the user's own copy */}
      <CatalogFoodPicker token={token} onAdded={reload} />

      <section className="card">
        <h2>{t('foods.addTitle')}</h2>
        <FoodForm key={addFormKey} submitLabel={t('foods.add')} onSubmit={handleCreate} />
      </section>

      <section className="card">
        <h2>{t('foods.yours')}</h2>
        {error && <p className="error">{error}</p>}
        {foods === null && !error && <p className="muted">{t('app.loading')}</p>}
        {foods?.length === 0 && (
          <p className="muted">{t('foods.none')}</p>
        )}
        {foods && foods.length > 0 && (
          <ul className="rows">
            {foods.map((food) =>
              food.id === editingId ? (
                <li key={food.id}>
                  <FoodForm
                    initial={food}
                    submitLabel={t('common.save')}
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
                      {t('foods.row', {
                        kcal: formatDecimal(food.calories_per_100g),
                        protein: formatDecimal(food.protein_per_100g),
                        carbs: formatDecimal(food.carbs_per_100g),
                        fat: formatDecimal(food.fat_per_100g),
                      })}
                    </span>
                  </span>
                  <span className="actions">
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => setEditingId(food.id)}
                    >
                      {t('common.edit')}
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => void handleDelete(food)}
                    >
                      {t('common.delete')}
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
