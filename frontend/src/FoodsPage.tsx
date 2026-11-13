import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createFood,
  deleteFood,
  describeError,
  fetchFoods,
  setFavourite,
  updateFood,
} from './api'
import type { Food, FoodInput } from './api'
import CatalogFoodPicker from './CatalogFoodPicker'
import { formatDecimal } from './format'
import { displayName, matchesFilter } from './logging'
import { useI18n } from './i18n/context'
import type { MessageKey } from './i18n/i18n'
import Toast from './Toast'
import type { ToastMessage } from './Toast'

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

/**
 * Add or edit form. Shows the API's error if onSubmit throws. With
 * onDelete, an edit form also offers Delete (or says why it cannot).
 */
function FoodForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
  onDelete,
  inDiary = false,
}: {
  initial?: FoodInput
  submitLabel: string
  onSubmit: (food: FoodInput) => Promise<void>
  onCancel?: () => void
  onDelete?: () => void
  inDiary?: boolean
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
        {onDelete &&
          (inDiary ? (
            <span className="muted small push-end">{t('foods.inDiary')}</span>
          ) : (
            <button type="button" className="link danger push-end" onClick={onDelete}>
              {t('common.delete')}
            </button>
          ))}
      </div>
    </form>
  )
}

type Panel = 'new' | 'catalog' | null

export default function FoodsPage({ token }: { token: string }) {
  const { t, locale } = useI18n()
  const [foods, setFoods] = useState<Food[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [filter, setFilter] = useState('')
  // At most one of "New food" and "From the catalog" open, above the list
  const [panel, setPanel] = useState<Panel>(null)
  const [version, setVersion] = useState(0)
  const reload = () => setVersion((v) => v + 1)
  const [toast, setToast] = useState<ToastMessage | null>(null)
  // Each message a new id, so the timer restarts even for the same text
  const toastSeq = useRef(0)
  // A deletion waits as long as its Undo shows; the food is hidden meanwhile
  const pending = useRef<Food | null>(null)
  const [hiddenId, setHiddenId] = useState<number | null>(null)

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

  /** Send the deletion that waited, if any (Undo not used). */
  const commitDelete = useCallback(async () => {
    const food = pending.current
    if (!food) return
    pending.current = null
    try {
      await deleteFood(token, food.id)
    } catch (err) {
      setError(`${food.name}: ${describeError(err)}`)
    } finally {
      setHiddenId(null)
      setVersion((v) => v + 1)
    }
  }, [token])

  // Leaving the page does not cancel a deletion: it goes at once
  useEffect(
    () => () => {
      const food = pending.current
      pending.current = null
      if (food) deleteFood(token, food.id).catch(() => {})
    },
    [token],
  )

  const toastDone = useCallback(() => {
    setToast(null)
    void commitDelete()
  }, [commitDelete])

  // A successful change makes an older list error (e.g. a failed delete) stale
  async function handleCreate(food: FoodInput) {
    const created = await createFood(token, food)
    setError(null)
    setPanel(null)
    toastSeq.current += 1
    setToast({ id: toastSeq.current, text: t('foods.added', { name: created.name }) })
    reload()
  }

  async function handleUpdate(id: number, food: FoodInput) {
    await updateFood(token, id, food)
    setError(null)
    setEditingId(null)
    reload()
  }

  async function toggleFavourite(food: Food) {
    setError(null)
    try {
      await setFavourite(token, food.id, !food.favourite)
      reload()
    } catch (err) {
      setError(`${food.name}: ${describeError(err)}`)
    }
  }

  /** No dialog: the food goes from the list, with Undo while the message shows. */
  function handleDelete(food: Food) {
    // An earlier deletion still waiting goes now
    void commitDelete()
    setError(null)
    setEditingId(null)
    pending.current = food
    setHiddenId(food.id)
    toastSeq.current += 1
    setToast({
      id: toastSeq.current,
      text: t('foods.removed', { name: displayName(food, locale) }),
      undo: async () => {
        pending.current = null
        setHiddenId(null)
      },
    })
  }

  function togglePanel(next: Exclude<Panel, null>) {
    setPanel((current) => (current === next ? null : next))
  }

  const shown = foods?.filter((food) => food.id !== hiddenId && matchesFilter(displayName(food, locale), filter)) ?? null

  return (
    <div className="page">
      <section className="card foods-card">
        <div className="card-head">
          <h2>{t('foods.yours')}</h2>
          {foods && foods.length > 0 && <span className="muted kcal">{foods.length}</span>}
        </div>
        <label className="search-field">
          <span className="visually-hidden">{t('foods.filter')}</span>
          <input
            type="search"
            value={filter}
            placeholder={t('foods.filter')}
            onChange={(event) => setFilter(event.target.value)}
          />
        </label>
        <div className="actions">
          <button
            type="button"
            className="secondary"
            aria-expanded={panel === 'new'}
            onClick={() => togglePanel('new')}
          >
            + {t('foods.new')}
          </button>
          <button
            type="button"
            className="secondary"
            aria-expanded={panel === 'catalog'}
            onClick={() => togglePanel('catalog')}
          >
            {t('foods.fromCatalog')}
          </button>
        </div>

        {panel === 'new' && (
          <div className="panel">
            <h3>{t('foods.addTitle')}</h3>
            <FoodForm submitLabel={t('foods.add')} onSubmit={handleCreate} onCancel={() => setPanel(null)} />
          </div>
        )}
        {/* The fastest way in: a food from the catalog, as the user's own copy */}
        {panel === 'catalog' && <CatalogFoodPicker token={token} onAdded={reload} embedded />}

        {error && <p className="error">{error}</p>}
        {foods === null && !error && <p className="muted">{t('app.loading')}</p>}
        {foods?.length === 0 && <p className="muted">{t('foods.none')}</p>}
        {shown && shown.length === 0 && foods && foods.length > 0 && (
          <p className="muted">{t('foods.noMatch', { q: filter.trim() })}</p>
        )}
        {shown && shown.length > 0 && (
          <ul className="rows food-list">
            {shown.map((food) =>
              food.id === editingId ? (
                <li key={food.id} className="food-editing">
                  <FoodForm
                    initial={food}
                    submitLabel={t('common.save')}
                    onSubmit={(input) => handleUpdate(food.id, input)}
                    onCancel={() => setEditingId(null)}
                    onDelete={() => handleDelete(food)}
                    inDiary={Boolean(food.last_logged)}
                  />
                </li>
              ) : (
                <li key={food.id}>
                  {/* The whole row opens the food for editing */}
                  <button type="button" className="food-open" onClick={() => setEditingId(food.id)}>
                    <span className="grow">
                      <span className="visually-hidden">{t('common.edit')}: </span>
                      <strong>{displayName(food, locale)}</strong>
                      <span className="muted small food-macros">
                        {t('foods.macros', {
                          protein: formatDecimal(food.protein_per_100g),
                          carbs: formatDecimal(food.carbs_per_100g),
                          fat: formatDecimal(food.fat_per_100g),
                        })}
                      </span>
                    </span>
                    <span className="food-kcal">
                      <span className="kcal">{formatDecimal(food.calories_per_100g)}</span>
                      <span className="muted small"> kcal</span>
                    </span>
                  </button>
                  <button
                    type="button"
                    className="icon star"
                    aria-label={t('foods.favourite', { name: displayName(food, locale) })}
                    aria-pressed={food.favourite === true}
                    onClick={() => void toggleFavourite(food)}
                  >
                    {food.favourite ? '★' : '☆'}
                  </button>
                </li>
              ),
            )}
          </ul>
        )}
      </section>
      <Toast message={toast} onDone={toastDone} />
    </div>
  )
}
