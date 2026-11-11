import { useEffect, useState } from 'react'
import { describeError, fetchCatalogSources } from './api'
import type { CatalogSource } from './api'
import { useI18n } from './i18n/context'

/**
 * Where the catalog's foods and exercises come from: each source's name,
 * licence and version, and its attribution where the licence requires it
 * on screen (neither source does today; the screen does not assume so).
 */
export default function Credits({ token, onBack }: { token: string; onBack: () => void }) {
  const { t } = useI18n()
  const [sources, setSources] = useState<CatalogSource[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchCatalogSources(token)
      .then((list) => {
        if (!cancelled) setSources(list)
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err))
      })
    return () => {
      cancelled = true
    }
  }, [token])

  return (
    <section className="card">
      <button type="button" className="link" onClick={onBack}>
        {t('credits.back')}
      </button>
      <h2>{t('credits.title')}</h2>
      <p className="muted">{t('credits.intro')}</p>
      {error && <p className="error">{error}</p>}
      {!sources && !error && <p className="muted">{t('app.loading')}</p>}
      {sources?.map((source) => (
        <div key={source.key} className="workout-exercise credit">
          <h3>
            <a href={source.url} target="_blank" rel="noreferrer">
              {source.name}
            </a>
          </h3>
          <dl className="credit-facts">
            <dt>{t('credits.license')}</dt>
            <dd>{source.license}</dd>
            <dt>{t('credits.version')}</dt>
            <dd>{source.version}</dd>
          </dl>
          {source.attribution_required && <p className="attribution">{source.attribution}</p>}
          {source.share_alike && <p className="muted">{t('credits.shareAlike')}</p>}
        </div>
      ))}
    </section>
  )
}
