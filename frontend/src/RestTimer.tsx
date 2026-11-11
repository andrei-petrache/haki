import { useEffect, useRef, useSyncExternalStore } from 'react'
import { useI18n } from './i18n/context'
import { REST_PRESETS, formatClock, remainingSeconds, restStore } from './restTimer'

function useRest() {
  return useSyncExternalStore(restStore.subscribe, restStore.get)
}

const TICK_MS = 250

function subscribeTicks(onTick: () => void): () => void {
  const id = window.setInterval(onTick, TICK_MS)
  return () => window.clearInterval(id)
}

const noTicks = () => () => {}

/** Now, to a quarter of a second, refreshed only while a rest runs. */
function useNow(running: boolean): number {
  return useSyncExternalStore(running ? subscribeTicks : noTicks, () =>
    running ? Math.floor(Date.now() / TICK_MS) * TICK_MS : 0,
  )
}

/**
 * The running rest, under the header on every screen: time left and Stop,
 * then "Rest over" until dismissed. Nothing when no rest was started.
 */
export function RestBar() {
  const { t } = useI18n()
  const rest = useRest()
  const now = useNow(rest !== null)
  const left = rest ? remainingSeconds(rest, now) : 0
  const buzzed = useRef<number | null>(null)

  // One short buzz when it ends, where phones allow it
  useEffect(() => {
    if (rest && left === 0 && buzzed.current !== rest.endsAt) {
      buzzed.current = rest.endsAt
      navigator.vibrate?.(300)
    }
  }, [rest, left])

  if (!rest) return null
  const over = left === 0
  return (
    <section className={over ? 'rest-bar over' : 'rest-bar'} aria-label={t('rest.title')}>
      <span role="timer" aria-live={over ? 'assertive' : 'off'}>
        {over ? t('rest.over') : t('rest.left', { time: formatClock(left) })}
      </span>
      <button type="button" className="secondary" onClick={() => restStore.stop()}>
        {over ? t('rest.dismiss') : t('rest.stop')}
      </button>
    </section>
  )
}

/** The buttons that start a rest, in the workout editor. */
export function RestStart() {
  const { t } = useI18n()
  return (
    <div className="rest-start">
      <span className="muted">{t('rest.startLabel')}</span>
      {REST_PRESETS.map((seconds) => (
        <button
          key={seconds}
          type="button"
          className="secondary"
          aria-label={t('rest.startPreset', { time: formatClock(seconds) })}
          onClick={() => restStore.start(seconds)}
        >
          {formatClock(seconds)}
        </button>
      ))}
    </div>
  )
}
