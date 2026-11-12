import { describe, expect, it } from 'vitest'
import { REST_KEY, createRestStore, formatClock, parseRest, remainingSeconds } from './restTimer'

function memoryStorage() {
  const items = new Map<string, string>()
  return {
    items,
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
    removeItem: (key: string) => void items.delete(key),
  }
}

describe('time left', () => {
  const rest = { endsAt: 100_000, seconds: 90 }

  it('counts whole seconds, rounded up, from the moment the rest ends', () => {
    expect(remainingSeconds(rest, 10_000)).toBe(90)
    expect(remainingSeconds(rest, 99_001)).toBe(1)
    expect(remainingSeconds(rest, 100_000)).toBe(0)
  })

  it('never goes below 0, however late the screen looks again', () => {
    expect(remainingSeconds(rest, 1_000_000)).toBe(0)
  })

  it('shows as a clock', () => {
    expect(formatClock(90)).toBe('1:30')
    expect(formatClock(5)).toBe('0:05')
    expect(formatClock(180)).toBe('3:00')
  })
})

describe('the rest store', () => {
  it('keeps the end time, so a reload or another screen sees the same rest', () => {
    const storage = memoryStorage()
    const store = createRestStore(storage)

    store.start(90, 1_000)

    expect(store.get()).toEqual({ endsAt: 91_000, seconds: 90 })
    // A fresh store, as after a reload, reads the same rest back
    expect(createRestStore(storage).get()).toEqual({ endsAt: 91_000, seconds: 90 })
  })

  it('tells subscribers, and forgets the rest when stopped', () => {
    const storage = memoryStorage()
    const store = createRestStore(storage)
    let calls = 0
    const unsubscribe = store.subscribe(() => calls++)

    store.start(60, 0)
    store.stop()
    unsubscribe()
    store.start(60, 0)

    expect(calls).toBe(2)
    store.stop()
    expect(store.get()).toBeNull()
    expect(storage.items.has(REST_KEY)).toBe(false)
  })

  it('still runs without storage, or when storage refuses', () => {
    const refusing = {
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
      removeItem: () => {
        throw new Error('blocked')
      },
    }

    for (const storage of [null, refusing]) {
      const store = createRestStore(storage)
      store.start(60, 0)
      expect(store.get()).toEqual({ endsAt: 60_000, seconds: 60 })
    }
  })

  it('ignores anything in the key that is not a rest', () => {
    for (const value of [null, '', 'nope', '{}', '{"endsAt":5,"seconds":0}', '{"endsAt":"x","seconds":60}']) {
      expect(parseRest(value), String(value)).toBeNull()
    }
    expect(parseRest('{"endsAt":5000,"seconds":60}')).toEqual({ endsAt: 5000, seconds: 60 })
  })
})

describe('moving and repeating a rest', () => {
  it('moves a running rest by 15 s either way, never ending before now', () => {
    const store = createRestStore(memoryStorage())
    store.start(60, 0)

    store.adjust(15, 1_000)
    expect(store.get()).toEqual({ endsAt: 75_000, seconds: 75 })
    store.adjust(-15, 1_000)
    store.adjust(-15, 1_000)
    expect(store.get()).toEqual({ endsAt: 45_000, seconds: 45 })
    store.adjust(-120, 40_000)
    expect(store.get()!.endsAt).toBe(40_000)
  })

  it('does nothing when no rest runs', () => {
    const store = createRestStore(memoryStorage())
    store.adjust(15, 0)
    expect(store.get()).toBeNull()
  })

  it('starts the length started last, 90 s at first', () => {
    const storage = memoryStorage()
    const store = createRestStore(storage)

    store.startLast(0)
    expect(store.get()).toEqual({ endsAt: 90_000, seconds: 90 })
    store.start(120, 0)
    store.startLast(1_000)
    expect(store.get()).toEqual({ endsAt: 121_000, seconds: 120 })
  })
})
