/**
 * The rest timer between sets, client only. It keeps the moment the rest
 * ends, never a countdown: the time left is always that moment minus now,
 * so it stays right when the screen changes, the tab sleeps or the page
 * reloads. Kept on this device (localStorage), like the unit and language.
 */

export type Rest = { endsAt: number; seconds: number }

/** The lengths offered, in seconds: the usual rests between sets. */
export const REST_PRESETS = [60, 90, 120, 180] as const

export const REST_KEY = 'haki_rest'
// The length last started, which ticking a set starts again
export const REST_LAST_KEY = 'haki_rest_last'
export const DEFAULT_REST = 90
/** How much −/+ on the bar move a running rest. */
export const REST_STEP = 15

/** Whole seconds left, rounded up (0:01 until the very end), never below 0. */
export function remainingSeconds(rest: Rest, now: number): number {
  return Math.max(0, Math.ceil((rest.endsAt - now) / 1000))
}

/** Seconds as a clock: 90 is "1:30", 5 is "0:05". */
export function formatClock(seconds: number): string {
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

/** A rest read back from storage, or null when there is none or it makes no sense. */
export function parseRest(value: string | null): Rest | null {
  if (!value) return null
  try {
    const rest = JSON.parse(value) as Partial<Rest>
    if (Number.isFinite(rest.endsAt) && Number.isFinite(rest.seconds) && rest.seconds! > 0) {
      return { endsAt: rest.endsAt!, seconds: rest.seconds! }
    }
  } catch {
    // Anything else in the key is no rest
  }
  return null
}

type RestStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

function browserStorage(): RestStorage | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    return null
  }
}

/**
 * One timer for the whole app, which components subscribe to
 * (useSyncExternalStore): the editor starts it, the bar under the header
 * shows it on every screen.
 */
export function createRestStore(storage: RestStorage | null = browserStorage()) {
  const read = () => {
    try {
      return parseRest(storage?.getItem(REST_KEY) ?? null)
    } catch {
      return null
    }
  }
  let current = read()
  const listeners = new Set<() => void>()
  const emit = () => listeners.forEach((listener) => listener())
  const write = (rest: Rest | null) => {
    current = rest
    try {
      if (rest) storage?.setItem(REST_KEY, JSON.stringify(rest))
      else storage?.removeItem(REST_KEY)
    } catch {
      // Not kept across a reload, but it still runs
    }
    emit()
  }
  return {
    get: (): Rest | null => current,
    subscribe(listener: () => void): () => void {
      listeners.add(listener)
      return () => listeners.delete(listener)
    },
    start(seconds: number, now: number = Date.now()): void {
      try {
        storage?.setItem(REST_LAST_KEY, String(seconds))
      } catch {
        // Only the default next time
      }
      write({ endsAt: now + seconds * 1000, seconds })
    },
    /** Start the length started last (90 s at first), as a ticked set does. */
    startLast(now: number = Date.now()): void {
      let seconds = DEFAULT_REST
      try {
        const kept = Number(storage?.getItem(REST_LAST_KEY))
        if (Number.isFinite(kept) && kept > 0) seconds = kept
      } catch {
        // The default
      }
      write({ endsAt: now + seconds * 1000, seconds })
    },
    /** Move a running rest by some seconds; never ends before now. */
    adjust(seconds: number, now: number = Date.now()): void {
      if (!current) return
      write({
        endsAt: Math.max(now, current.endsAt + seconds * 1000),
        seconds: Math.max(1, current.seconds + seconds),
      })
    },
    stop(): void {
      write(null)
    },
    /** Pick up a change made in another tab of the app. */
    reload(): void {
      current = read()
      emit()
    },
  }
}

export const restStore = createRestStore()

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key === REST_KEY) restStore.reload()
  })
}
