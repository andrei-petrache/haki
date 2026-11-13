import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, deleteWeight, describeError, fetchWeights, putWeight } from './api'
import type { WeightPoint } from './api'
import {
  bodyFieldText,
  bodyLimits,
  bodyWeightError,
  bodyWeightToKg,
  chartScale,
  formatBodyWeight,
  rangeStart,
  weeklyChange,
} from './bodyWeight'
import type { ChartBox } from './bodyWeight'
import { formatDayLabel, formatShortDay, localDateString, parseDay } from './format'
import { useI18n } from './i18n/context'
import { formatNumber } from './i18n/i18n'
import type { MessageKey } from './i18n/i18n'
import { ConsentCard } from './Consent'
import { TargetStatus } from './Goal'
import { useConsent } from './useConsent'
import Toast from './Toast'
import type { ToastMessage } from './Toast'
import { kgToUnit } from './units'
import type { WeightUnit } from './units'

/** The card's own period: enough for the trend and its weekly change. */
const CARD_DAYS = 90

type Loaded = { kind: 'loading' } | { kind: 'off' } | { kind: 'error'; message: string } | { kind: 'ok'; points: WeightPoint[] }

/**
 * Load the weigh-ins of a period. A 404 means the server has body weight
 * switched off (BODY_WEIGHT_ENABLED): then nothing of it shows.
 */
function useWeights(token: string, from: string, to: string, version: number): Loaded {
  const [loaded, setLoaded] = useState<{ range: string; value: Loaded } | null>(null)
  const range = `${from}/${to}`
  useEffect(() => {
    let cancelled = false
    fetchWeights(token, from, to)
      .then((points) => {
        if (!cancelled) setLoaded({ range, value: { kind: 'ok', points } })
      })
      .catch((err) => {
        if (cancelled) return
        const value: Loaded =
          err instanceof ApiError && err.status === 404 ? { kind: 'off' } : { kind: 'error', message: describeError(err) }
        setLoaded({ range, value })
      })
    return () => {
      cancelled = true
    }
  }, [token, from, to, range, version])
  // While the same period reloads (after a save), its last answer stays on
  // screen; an answer for another period is not this one's
  return loaded && loaded.range === range ? loaded.value : { kind: 'loading' }
}

/** "−0.4 kg a week", "+0.2 lb a week" or "steady" (under 0.05 a week). */
function changeText(t: (key: MessageKey, params?: Record<string, string>) => string, kgPerWeek: number, unit: WeightUnit) {
  const value = kgToUnit(kgPerWeek, unit)
  if (Math.abs(value) < 0.05) return t('weight.steady')
  const sign = value > 0 ? '+' : '−'
  return t('weight.perWeek', { change: `${sign}${formatNumber(Math.round(Math.abs(value) * 10) / 10)} ${unit}` })
}

function dayWords(t: (key: MessageKey) => string, day: string): string {
  return formatDayLabel(day, localDateString(), {
    today: t('today.today'),
    yesterday: t('today.yesterday'),
    tomorrow: t('today.tomorrow'),
  })
}

/**
 * On Today, under the meals: body weight only with a valid health data
 * consent. Without one, the consent's text to agree to (or "Not now", which
 * folds it to one line for this visit); off on the server (404), nothing.
 */
export function WeightCard(props: { token: string; day: string; unit: WeightUnit; onOpen: () => void }) {
  const { t } = useI18n()
  const [version, setVersion] = useState(0)
  const consent = useConsent(props.token, version)
  const [later, setLater] = useState(false)
  if (consent.kind === 'off' || consent.kind === 'loading') return null
  if (consent.kind === 'error') return <p className="error">{consent.message}</p>
  if (!consent.status.valid) {
    if (later) {
      return (
        <section className="card weight-later">
          <span className="grow">{t('weight.title')}</span>
          <button type="button" className="link" onClick={() => setLater(false)}>
            {t('consent.show')}
          </button>
        </section>
      )
    }
    return (
      <ConsentCard
        token={props.token}
        status={consent.status}
        onGiven={() => setVersion((v) => v + 1)}
        onLater={() => setLater(true)}
      />
    )
  }
  return <WeightCardBody {...props} />
}

/** The shown day's weigh-in, typed in the user's unit, and where the trend is going; "Trend ›" opens the chart. */
function WeightCardBody({
  token,
  day,
  unit,
  onOpen,
}: {
  token: string
  day: string
  unit: WeightUnit
  onOpen: () => void
}) {
  const { t } = useI18n()
  const today = localDateString()
  const [version, setVersion] = useState(0)
  const loaded = useWeights(token, rangeStart(today, CARD_DAYS), today, version)

  if (loaded.kind === 'off' || loaded.kind === 'loading') return null

  const points = loaded.kind === 'ok' ? loaded.points : []
  const saved = points.find((point) => point.measured_on === day) ?? null
  const latest = points.length > 0 ? points[points.length - 1] : null
  const change = weeklyChange(points)

  return (
    <section className="card weight-card" aria-labelledby="weight-title">
      <div className="card-head">
        <h2 id="weight-title">{t('weight.title')}</h2>
        <button type="button" className="link" onClick={onOpen}>
          {t('weight.openTrend')}
        </button>
      </div>
      {loaded.kind === 'error' && <p className="error">{loaded.message}</p>}
      <TargetStatus token={token} unit={unit} version={version} />
      {latest && (
        <p className="weight-trend">
          <span className="kcal">{formatBodyWeight(latest.trend_kg, unit)}</span>{' '}
          <span className="muted">
            {t('weight.legendTrend').toLowerCase()}
            {change !== null && ` · ${changeText(t, change, unit)}`}
          </span>
        </p>
      )}
      <WeighInForm
        // A fresh form per day and unit: it starts from what is saved
        key={`${day}/${unit}`}
        token={token}
        day={day}
        unit={unit}
        savedKg={saved?.weight_kg ?? null}
        onSaved={() => setVersion((v) => v + 1)}
      />
    </section>
  )
}

function WeighInForm({
  token,
  day,
  unit,
  savedKg,
  onSaved,
}: {
  token: string
  day: string
  unit: WeightUnit
  savedKg: number | null
  onSaved: () => void
}) {
  const { t } = useI18n()
  const savedText = savedKg === null ? '' : bodyFieldText(savedKg, unit)
  const [text, setText] = useState(savedText)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const { min, max } = bodyLimits(unit)

  async function handleSave() {
    const problem = bodyWeightError(text, unit)
    setError(problem)
    setNotice(null)
    if (problem) return
    setBusy(true)
    try {
      // Unchanged from what is saved: the same kilograms, not a rounded copy
      const kg = text === savedText && savedKg !== null ? savedKg : bodyWeightToKg(text, unit)
      const weight = await putWeight(token, day, kg)
      setNotice(t('weight.saved', { weight: formatBodyWeight(weight.weight_kg, unit), day: dayWords(t, day) }))
      onSaved()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      className="weigh-in"
      noValidate
      onSubmit={(event) => {
        event.preventDefault()
        void handleSave()
      }}
    >
      <label>
        {t('weight.field', { unit })}
        <input
          type="number"
          inputMode="decimal"
          step="any"
          min={min}
          max={max}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      <button type="submit" disabled={busy}>
        {busy ? t('common.saving') : t('weight.save')}
      </button>
      {error && <p className="error">{error}</p>}
      {notice && <p className="notice" role="status">{notice}</p>}
    </form>
  )
}

const RANGES: { days: number; label: MessageKey }[] = [
  { days: 30, label: 'weight.range30' },
  { days: 90, label: 'weight.range90' },
  { days: 365, label: 'weight.range365' },
]

/** The trend: a period, the chart, and every weigh-in in it, newest first. */
export function WeightView({ token, unit, onBack }: { token: string; unit: WeightUnit; onBack: () => void }) {
  const { t } = useI18n()
  const today = localDateString()
  const [days, setDays] = useState(90)
  const [version, setVersion] = useState(0)
  const from = rangeStart(today, days)
  const loaded = useWeights(token, from, today, version)
  const [toast, setToast] = useState<ToastMessage | null>(null)
  const clearToast = useCallback(() => setToast(null), [])
  const toastSeq = useRef(0)
  const [error, setError] = useState<string | null>(null)

  async function handleDelete(point: WeightPoint) {
    setError(null)
    try {
      await deleteWeight(token, point.measured_on)
      setVersion((v) => v + 1)
      toastSeq.current += 1
      setToast({
        id: toastSeq.current,
        text: t('weight.deleted', { day: formatShortDay(point.measured_on) }),
        // Undo puts the same kilograms back on the same day
        undo: async () => {
          try {
            await putWeight(token, point.measured_on, point.weight_kg)
          } catch (err) {
            setError(describeError(err))
          }
          setVersion((v) => v + 1)
        },
      })
    } catch (err) {
      setError(describeError(err))
    }
  }

  const points = loaded.kind === 'ok' ? loaded.points : []

  return (
    <div className="page">
      <section className="card weight-view">
        <button type="button" className="link" onClick={onBack}>
          {t('weight.back')}
        </button>
        <h2>{t('weight.chartTitle')}</h2>
        <div className="segmented range-choice" role="group" aria-label={t('weight.rangeLabel')}>
          {RANGES.map((range) => (
            <button
              key={range.days}
              type="button"
              aria-pressed={days === range.days}
              onClick={() => setDays(range.days)}
            >
              {t(range.label)}
            </button>
          ))}
        </div>
        {loaded.kind === 'loading' && <p className="muted">{t('app.loading')}</p>}
        {loaded.kind === 'error' && <p className="error">{loaded.message}</p>}
        {error && <p className="error">{error}</p>}
        {loaded.kind === 'ok' && points.length === 0 && <p className="muted">{t('weight.none')}</p>}
        {points.length > 0 && <WeightChart points={points} from={from} to={today} unit={unit} />}
      </section>

      {points.length > 0 && (
        <section className="card">
          <h3>{t('weight.list')}</h3>
          <ul className="rows weight-list">
            {[...points].reverse().map((point) => (
              <li key={point.measured_on}>
                <span className="grow">{formatShortDay(point.measured_on)}</span>
                <span className="kcal">{formatBodyWeight(point.weight_kg, unit)}</span>
                <span className="muted small weight-list-trend">{formatBodyWeight(point.trend_kg, unit)}</span>
                <button
                  type="button"
                  className="icon remove-block"
                  aria-label={t('weight.delete', { day: formatShortDay(point.measured_on) })}
                  onClick={() => void handleDelete(point)}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      <Toast message={toast} onDone={clearToast} />
    </div>
  )
}

// Room on top for the unit, at the left for the ticks, below for the days
const BOX: ChartBox = { width: 340, height: 210, left: 38, right: 10, top: 24, bottom: 26 }

/** A day as "13 Nov" for the axis. */
function axisDay(day: string, locale: string): string {
  return parseDay(day).toLocaleDateString(locale === 'en' ? 'en-GB' : locale, { day: 'numeric', month: 'short' })
}

/**
 * Weigh-ins as dots and the trend as a line, one axis in the user's unit.
 * Neutral inks (red is for actions): the line in the text colour, the dots
 * muted with a ring of the card's colour; a weigh-in far from the trend is
 * a hollow dot. A pointer or a finger anywhere on it shows the nearest
 * weigh-in. The list under the chart carries every value as text.
 */
function WeightChart({ points, from, to, unit }: { points: WeightPoint[]; from: string; to: string; unit: WeightUnit }) {
  const { t, locale } = useI18n()
  const scale = chartScale(points, from, to, unit, BOX)
  const [active, setActive] = useState<WeightPoint | null>(null)
  const svg = useRef<SVGSVGElement>(null)
  const inUnit = (kg: number) => kgToUnit(kg, unit)
  const trendPath = points
    .map((point, i) => `${i === 0 ? 'M' : 'L'}${scale.x(point.measured_on).toFixed(1)},${scale.y(inUnit(point.trend_kg)).toFixed(1)}`)
    .join(' ')
  const anyOutlier = points.some((point) => point.outlier)
  const first = points[0]
  const last = points[points.length - 1]

  function pick(clientX: number) {
    const element = svg.current
    if (!element) return
    const rect = element.getBoundingClientRect()
    const x = ((clientX - rect.left) / rect.width) * BOX.width
    let best: WeightPoint | null = null
    let distance = Infinity
    for (const point of points) {
      const d = Math.abs(scale.x(point.measured_on) - x)
      if (d < distance) {
        best = point
        distance = d
      }
    }
    setActive(best)
  }

  const activeX = active ? scale.x(active.measured_on) : 0
  return (
    <div className="weight-chart">
      <ul className="chart-legend">
        <li>
          <svg width="12" height="12" aria-hidden="true">
            <circle cx="6" cy="6" r="4" className="dot" />
          </svg>
          {t('weight.legendWeighIn')}
        </li>
        <li>
          <svg width="18" height="12" aria-hidden="true">
            <line x1="1" y1="6" x2="17" y2="6" className="trend" />
          </svg>
          {t('weight.legendTrend')}
        </li>
        {anyOutlier && (
          <li>
            <svg width="12" height="12" aria-hidden="true">
              <circle cx="6" cy="6" r="4" className="dot outlier" />
            </svg>
            {t('weight.legendOutlier')}
          </li>
        )}
      </ul>
      <div className="chart-frame">
        <svg
          ref={svg}
          viewBox={`0 0 ${BOX.width} ${BOX.height}`}
          role="img"
          aria-label={t('weight.chartSummary', {
            from: formatShortDay(from),
            to: formatShortDay(to),
            count: String(points.length),
            start: formatBodyWeight(first.trend_kg, unit),
            end: formatBodyWeight(last.trend_kg, unit),
          })}
          onPointerMove={(event) => pick(event.clientX)}
          onPointerDown={(event) => pick(event.clientX)}
          // A mouse leaving hides it; a finger lifting does not: the
          // tooltip stays until the next tap
          onPointerLeave={(event) => {
            if (event.pointerType === 'mouse') setActive(null)
          }}
        >
          {scale.ticks.map((tick) => (
            <g key={tick}>
              <line x1={BOX.left} x2={BOX.width - BOX.right} y1={scale.y(tick)} y2={scale.y(tick)} className="grid" />
              <text x={BOX.left - 6} y={scale.y(tick)} className="tick" textAnchor="end" dominantBaseline="middle">
                {formatNumber(tick)}
              </text>
            </g>
          ))}
          <text x={BOX.left} y={BOX.height - 6} className="tick" textAnchor="start">
            {axisDay(from, locale)}
          </text>
          <text x={BOX.width - BOX.right} y={BOX.height - 6} className="tick" textAnchor="end">
            {axisDay(to, locale)}
          </text>
          {active && <line x1={activeX} x2={activeX} y1={BOX.top} y2={BOX.height - BOX.bottom} className="crosshair" />}
          <path d={trendPath} className="trend" />
          {points.map((point) => (
            <circle
              key={point.measured_on}
              cx={scale.x(point.measured_on)}
              cy={scale.y(inUnit(point.weight_kg))}
              r={active === point ? 6 : 4}
              className={point.outlier ? 'dot outlier' : 'dot'}
            />
          ))}
          {/* Unit beside the axis, once */}
          <text x={BOX.left - 6} y={10} className="tick" textAnchor="end">
            {unit}
          </text>
        </svg>
        {active && (
          <p
            className="chart-tooltip"
            // The list under the chart says the same to a screen reader
            aria-hidden="true"
            // Over the chart, kept inside it near the edges
            style={{ left: `${Math.min(70, Math.max(30, (activeX / BOX.width) * 100))}%` }}
          >
            {t('weight.tooltip', {
              day: formatShortDay(active.measured_on),
              weight: formatBodyWeight(active.weight_kg, unit),
              trend: formatBodyWeight(active.trend_kg, unit),
            })}
          </p>
        )}
      </div>
    </div>
  )
}
