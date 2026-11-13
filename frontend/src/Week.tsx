import { useEffect, useState } from 'react'
import { describeError, fetchWeek } from './api'
import type { Week, WeekDay } from './api'
import { formatBodyWeight } from './bodyWeight'
import { formatKcal, formatShortDay, localDateString, shiftDate } from './format'
import { useI18n } from './i18n/context'
import { formatNumber } from './i18n/i18n'
import { kgToUnit } from './units'
import type { WeightUnit } from './units'
import { MUSCLE_KEYS, change, mondayOf, muscleRows, weekLabel, weekdayShort } from './week'

type Loaded = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ok'; week: Week }

function useWeek(token: string, monday: string): Loaded {
  const [loaded, setLoaded] = useState<{ monday: string; value: Loaded } | null>(null)
  useEffect(() => {
    let cancelled = false
    fetchWeek(token, monday)
      .then((week) => {
        if (!cancelled) setLoaded({ monday, value: { kind: 'ok', week } })
      })
      .catch((err) => {
        if (!cancelled) setLoaded({ monday, value: { kind: 'error', message: describeError(err) } })
      })
    return () => {
      cancelled = true
    }
  }, [token, monday])
  return loaded && loaded.monday === monday ? loaded.value : { kind: 'loading' }
}

/** A signed whole number with a real minus sign: "+120", "−80", "0". */
function signed(value: number): string {
  const rounded = Math.round(value)
  if (rounded === 0) return '0'
  return `${rounded > 0 ? '+' : '−'}${formatKcal(Math.abs(rounded))}`
}

/**
 * On Today, above the weight: the week so far in one line, which opens the
 * whole week. Says nothing while it loads or when it fails (a shortcut).
 */
export function WeekSummary({ token, onOpen }: { token: string; onOpen: () => void }) {
  const { t } = useI18n()
  const loaded = useWeek(token, mondayOf(localDateString()))
  if (loaded.kind !== 'ok') return null
  const { totals } = loaded.week
  return (
    <button type="button" className="card week-summary" onClick={onOpen}>
      <span className="grow">
        <span className="muted small">{t('week.thisWeek')}</span>
        <span>
          {totals.avg_kcal === null
            ? t('week.nothingYet')
            : t('week.summary', { kcal: formatKcal(totals.avg_kcal), workouts: String(totals.workouts) })}
        </span>
      </span>
      <span aria-hidden="true" className="muted">
        ›
      </span>
    </button>
  )
}

/** The week: calories a day against the target, training, body weight. */
export function WeekView({ token, unit, onBack }: { token: string; unit: WeightUnit; onBack: () => void }) {
  const { t } = useI18n()
  const thisMonday = mondayOf(localDateString())
  const [monday, setMonday] = useState(thisMonday)
  const loaded = useWeek(token, monday)

  return (
    <div className="page week-page">
      <section className="card">
        <button type="button" className="link" onClick={onBack}>
          {t('weight.back')}
        </button>
        <div className="week-head">
          <button
            type="button"
            className="icon"
            aria-label={t('week.previous')}
            onClick={() => setMonday((m) => shiftDate(m, -7))}
          >
            ‹
          </button>
          <h2>{monday === thisMonday ? t('week.thisWeek') : weekLabel(monday)}</h2>
          <button
            type="button"
            className="icon"
            aria-label={t('week.next')}
            disabled={monday >= thisMonday}
            onClick={() => setMonday((m) => shiftDate(m, 7))}
          >
            ›
          </button>
        </div>
        <p className="muted small">{weekLabel(monday)}</p>
        {loaded.kind === 'loading' && <p className="muted">{t('app.loading')}</p>}
        {loaded.kind === 'error' && <p className="error">{loaded.message}</p>}
      </section>
      {loaded.kind === 'ok' && <WeekBody week={loaded.week} unit={unit} />}
    </div>
  )
}

function WeekBody({ week, unit }: { week: Week; unit: WeightUnit }) {
  const { t } = useI18n()
  const { totals, previous_week: before } = week
  const kcalChange = change(totals.avg_kcal, before.avg_kcal)
  // Whole numbers with the language's thousands separator, like the kcal
  const volume = (kg: number) => `${formatKcal(Math.round(kgToUnit(kg, unit)))} ${unit}`
  const muscles = muscleRows(totals.volume_by_muscle)
  const topMuscle = muscles.length > 0 ? Math.max(...muscles.map((m) => m.volume)) : 0

  return (
    <>
      <section className="card" aria-labelledby="week-food">
        <h3 id="week-food">{t('week.food')}</h3>
        <p className="week-hero">
          <span className="kcal big">{totals.avg_kcal === null ? '—' : formatKcal(totals.avg_kcal)}</span>{' '}
          <span className="muted">{t('week.kcalPerDay')}</span>
        </p>
        <p className="muted small">
          {t('week.daysLogged', { days: String(totals.days_logged) })}
          {kcalChange !== null && ` · ${t('week.vsLast', { change: signed(kcalChange) })}`}
        </p>
        <KcalBars days={week.days} />
        {totals.days_logged > 0 && (
          <p className="muted small">
            {t('week.macros', {
              protein: formatNumber(Math.round(totals.protein / totals.days_logged)),
              carbs: formatNumber(Math.round(totals.carbs / totals.days_logged)),
              fat: formatNumber(Math.round(totals.fat / totals.days_logged)),
            })}
          </p>
        )}
      </section>

      <section className="card" aria-labelledby="week-training">
        <h3 id="week-training">{t('week.training')}</h3>
        <dl className="week-stats">
          <div>
            <dt>{t('week.workouts')}</dt>
            <dd className="kcal">{totals.workouts}</dd>
          </div>
          <div>
            <dt>{t('week.sets')}</dt>
            <dd className="kcal">{totals.sets}</dd>
          </div>
          <div>
            <dt>{t('week.volume')}</dt>
            <dd className="kcal">{volume(totals.volume_kg)}</dd>
          </div>
        </dl>
        <p className="muted small">
          {t('week.trainingBefore', { workouts: String(before.workouts), volume: volume(before.volume_kg) })}
        </p>
        {muscles.length > 0 && (
          <ul className="muscle-bars" aria-label={t('week.byMuscle')}>
            {muscles.map(({ muscle, volume: kg }) => (
              <li key={muscle}>
                <span className="muscle-name">{MUSCLE_KEYS[muscle] ? t(MUSCLE_KEYS[muscle]) : muscle}</span>
                <span className="muscle-track" aria-hidden="true">
                  <span className="muscle-fill" style={{ width: `${Math.max(2, (kg / topMuscle) * 100)}%` }} />
                </span>
                <span className="muscle-value">{volume(kg)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {week.body_weight && (
        <section className="card" aria-labelledby="week-weight">
          <h3 id="week-weight">{t('weight.title')}</h3>
          {week.body_weight.end_trend_kg === null ? (
            <p className="muted">{t('week.noWeighIns')}</p>
          ) : (
            <p>
              <span className="kcal">{formatBodyWeight(week.body_weight.end_trend_kg, unit)}</span>{' '}
              <span className="muted">
                {t('weight.legendTrend').toLowerCase()}
                {week.body_weight.change_kg !== null &&
                  ` · ${t('week.weightChange', {
                    change: `${week.body_weight.change_kg > 0 ? '+' : week.body_weight.change_kg < 0 ? '−' : ''}${formatBodyWeight(Math.abs(week.body_weight.change_kg), unit)}`,
                  })}`}
              </span>
            </p>
          )}
        </section>
      )}

      <section className="card" aria-labelledby="week-days">
        <h3 id="week-days">{t('week.days')}</h3>
        <ul className="rows week-days">
          {week.days.map((day) => (
            <li key={day.date}>
              <span className="grow">{formatShortDay(day.date)}</span>
              <span className="kcal">{day.logged ? formatKcal(day.kcal) : '—'}</span>
              <span className="muted small week-day-workouts">
                {day.workouts > 0 ? t('week.workoutsShort', { count: String(day.workouts) }) : ''}
              </span>
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}

const BAR_HEIGHT = 120

/**
 * Calories a day as columns from one baseline, the day's target as a mark
 * across its column; a column over the target is red, as on Today, under
 * it neutral. A day with nothing logged has no column. The values are in
 * the list of days below (the table view).
 */
function KcalBars({ days }: { days: WeekDay[] }) {
  const { t } = useI18n()
  const top = Math.max(1, ...days.map((d) => Math.max(d.kcal, d.target_kcal ?? 0))) * 1.1
  const anyOver = days.some((d) => d.target_kcal !== null && d.kcal > d.target_kcal)
  return (
    <div className="kcal-bars">
      <div className="kcal-columns" role="img" aria-label={t('week.barsLabel')}>
        {days.map((day) => {
          const over = day.target_kcal !== null && day.kcal > day.target_kcal
          return (
            <div key={day.date} className="kcal-column" title={`${formatShortDay(day.date)}: ${formatKcal(day.kcal)} kcal`}>
              <div className="kcal-track" style={{ height: BAR_HEIGHT }}>
                {day.logged && (
                  <div className={over ? 'kcal-bar over' : 'kcal-bar'} style={{ height: `${(day.kcal / top) * 100}%` }} />
                )}
                {day.target_kcal !== null && (
                  <div className="kcal-target" style={{ bottom: `${(day.target_kcal / top) * 100}%` }} />
                )}
              </div>
              <span className="muted small">{weekdayShort(day.date)}</span>
            </div>
          )
        })}
      </div>
      <ul className="chart-legend">
        <li>
          <span className="swatch target" aria-hidden="true" />
          {t('week.legendTarget')}
        </li>
        {anyOver && (
          <li>
            <span className="swatch over" aria-hidden="true" />
            {t('week.legendOver')}
          </li>
        )}
      </ul>
    </div>
  )
}
