import { useEffect, useState } from 'react'
import { ApiError, describeError, fetchCurrentTarget, setGoal } from './api'
import type { CurrentTarget, TargetMode, User } from './api'
import { GOAL_OPTIONS, goalAmount, knownReasons } from './bodyWeight'
import { formatKcal, localDateString } from './format'
import { useI18n } from './i18n/context'
import { formatNumber } from './i18n/i18n'
import type { MessageKey } from './i18n/i18n'
import { kgToUnit } from './units'
import type { WeightUnit } from './units'

type Loaded =
  | { kind: 'loading' }
  | { kind: 'off' }
  | { kind: 'error'; message: string }
  | { kind: 'ok'; target: CurrentTarget }

/**
 * Today's target as the server works it out. A 404 means body weight is
 * switched off on the server; a 422 (date_out_of_range) a device clock
 * more than a day off: said in one short line, nothing else breaks.
 */
function useCurrentTarget(token: string, version: number): Loaded {
  const [loaded, setLoaded] = useState<Loaded>({ kind: 'loading' })
  useEffect(() => {
    let cancelled = false
    fetchCurrentTarget(token, localDateString())
      .then((target) => {
        if (!cancelled) setLoaded({ kind: 'ok', target })
      })
      .catch((err) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 404) setLoaded({ kind: 'off' })
        else if (err instanceof ApiError && err.status === 422) setLoaded({ kind: 'error', message: 'clock' })
        else setLoaded({ kind: 'error', message: describeError(err) })
      })
    return () => {
      cancelled = true
    }
  }, [token, version])
  return loaded
}

function goalLabel(t: (key: MessageKey, params?: Record<string, string>) => string, kg: number, unit: WeightUnit): string {
  if (kg === 0) return t('goal.maintain')
  return t(kg < 0 ? 'goal.lose' : 'goal.gain', { amount: goalAmount(kg, unit) })
}

/**
 * In Profile, under the daily target: whether it stays as typed or follows
 * the weight, and the weekly goal. Shown only when the server has body
 * weight switched on.
 */
export function GoalEditor({
  token,
  user,
  unit,
  onSaved,
}: {
  token: string
  user: User
  unit: WeightUnit
  onSaved: (user: User) => void
}) {
  const { t } = useI18n()
  const loaded = useCurrentTarget(token, 0)
  const [mode, setMode] = useState<TargetMode>(user.target_mode ?? 'manual')
  const [goal, setGoalValue] = useState<number>(user.goal_kg_per_week ?? 0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  if (loaded.kind !== 'ok' && loaded.kind !== 'error') return null

  async function save() {
    setError(null)
    setSaved(false)
    setBusy(true)
    try {
      onSaved(await setGoal(token, mode, goal))
      setSaved(true)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      className="goal-form"
      onSubmit={(event) => {
        event.preventDefault()
        void save()
      }}
    >
      <h3>{t('goal.title')}</h3>
      <fieldset className="segmented mode-choice">
        <legend className="visually-hidden">{t('goal.mode')}</legend>
        {(['manual', 'adaptive'] as const).map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={mode === value}
            onClick={() => {
              setMode(value)
              setSaved(false)
            }}
          >
            {t(value === 'manual' ? 'goal.manual' : 'goal.adaptive')}
          </button>
        ))}
      </fieldset>
      {mode === 'adaptive' && (
        <>
          <label className="pref-field">
            {t('goal.goal')}
            <select
              value={String(goal)}
              onChange={(event) => {
                setGoalValue(Number(event.target.value))
                setSaved(false)
              }}
            >
              {GOAL_OPTIONS.map((option) => (
                <option key={option} value={String(option)}>
                  {goalLabel(t, option, unit)}
                </option>
              ))}
            </select>
          </label>
          <p className="muted small">{t('goal.adaptiveNote')}</p>
        </>
      )}
      <div className="actions">
        <button type="submit" disabled={busy}>
          {busy ? t('common.saving') : t('goal.save')}
        </button>
        {saved && (
          <span className="notice" role="status">
            {t('goal.saved')}
          </span>
        )}
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  )
}

/**
 * In Today's weight card, for the adaptive mode: the target from the trend,
 * or what it still waits for; a warning when the floor set it.
 */
export function TargetStatus({ token, unit, version }: { token: string; unit: WeightUnit; version: number }) {
  const { t } = useI18n()
  const loaded = useCurrentTarget(token, version)
  if (loaded.kind === 'error') {
    return <p className="error small">{loaded.message === 'clock' ? t('target.clock') : loaded.message}</p>
  }
  if (loaded.kind !== 'ok' || loaded.target.target_mode !== 'adaptive') return null
  const target = loaded.target

  if (target.status === 'collecting') {
    const what = knownReasons(target.reasons)
      .map((reason) => t(`target.reason.${reason}` as MessageKey))
      .join(', ')
    return (
      <div className="target-status">
        <p>
          <strong>{t('target.collecting')}</strong>
        </p>
        {what && <p className="muted small">{t('target.collectingDetail', { what })}</p>}
      </div>
    )
  }

  const trend = target.trend_kg_per_week
  const trendText =
    trend === null ? '' : `${trend > 0 ? '+' : trend < 0 ? '−' : ''}${formatNumber(Math.round(Math.abs(kgToUnit(trend, unit)) * 10) / 10)} ${unit}`
  return (
    <div className="target-status">
      <p>
        <strong>
          {target.target_kcal === null ? t('target.none') : t('target.adaptive', { kcal: formatKcal(target.target_kcal) })}
        </strong>
      </p>
      {target.tdee_kcal !== null && (
        <p className="muted small">
          {t('target.adaptiveDetail', { tdee: formatKcal(target.tdee_kcal), trend: trendText })}
        </p>
      )}
      {target.floor_applied && (
        <p className="warning small" role="note">
          <span aria-hidden="true">⚠ </span>
          {t('target.floor')}
        </p>
      )}
    </div>
  )
}
