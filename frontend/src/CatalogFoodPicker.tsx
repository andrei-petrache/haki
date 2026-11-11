import { useEffect, useState } from 'react'
import { ApiError, CATALOG_PAGE_SIZE, copyCatalogFood, describeError, searchCatalogFoods } from './api'
import type { CatalogFood } from './api'
import { catalogLanguage, catalogName, searchText } from './catalog'
import { formatDecimal } from './format'
import { useI18n } from './i18n/context'

/** How long typing must pause before the catalog is asked. */
const SEARCH_DELAY_MS = 250

type Notice = { kind: 'ok' | 'info' | 'error'; text: string }

/**
 * Search the catalog's foods and add one to the user's own list, as their
 * copy (they can edit it there). Results show only for a non-empty search,
 * in the app's language.
 */
export default function CatalogFoodPicker({
  token,
  onAdded,
}: {
  token: string
  onAdded: () => void
}) {
  const { t, locale } = useI18n()
  const [text, setText] = useState('')
  const q = searchText(text)
  // The results and the search they answer: older answers are ignored
  const [found, setFound] = useState<{ q: string; items: CatalogFood[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [addingId, setAddingId] = useState<number | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const language = catalogLanguage(locale)

  useEffect(() => {
    if (q === '') return
    let cancelled = false
    const timer = window.setTimeout(() => {
      searchCatalogFoods(token, q, language)
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
  }, [token, q, language])

  async function handleAdd(item: CatalogFood) {
    const name = catalogName(item, locale)
    setNotice(null)
    setAddingId(item.id)
    try {
      const { item: food, created } = await copyCatalogFood(token, item.id, language)
      setNotice(
        created
          ? { kind: 'ok', text: t('catalog.foodAdded', { name: food.name }) }
          : { kind: 'info', text: t('catalog.foodExisting', { name: food.name }) },
      )
      onAdded()
    } catch (err) {
      setNotice({
        kind: 'error',
        text:
          err instanceof ApiError && err.status === 409
            ? t('catalog.foodTaken', { name })
            : describeError(err),
      })
    } finally {
      setAddingId(null)
    }
  }

  const items = q !== '' && found?.q === q ? found.items : null

  return (
    <section className="card catalog-picker">
      <h2>{t('catalog.foodsTitle')}</h2>
      <label>
        {t('catalog.search')}
        <input
          type="search"
          value={text}
          placeholder={t('catalog.foodsPlaceholder')}
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      {notice && (
        <p className={notice.kind === 'error' ? 'error' : 'notice'} role="status">
          {notice.text}
        </p>
      )}
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
                <span className="muted">
                  {t('catalog.foodRow', {
                    kcal: formatDecimal(item.calories_per_100g),
                    protein: formatDecimal(item.protein_per_100g),
                    carbs: formatDecimal(item.carbs_per_100g),
                    fat: formatDecimal(item.fat_per_100g),
                    source: item.source.name,
                  })}
                </span>
              </span>
              <button
                type="button"
                className="secondary"
                disabled={addingId !== null}
                aria-label={t('catalog.addName', { name: catalogName(item, locale) })}
                onClick={() => void handleAdd(item)}
              >
                {addingId === item.id ? t('catalog.adding') : t('catalog.add')}
              </button>
            </li>
          ))}
        </ul>
      )}
      {items && items.length === CATALOG_PAGE_SIZE && (
        <p className="muted">{t('catalog.more', { count: CATALOG_PAGE_SIZE })}</p>
      )}
    </section>
  )
}
