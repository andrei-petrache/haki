import { describe, expect, it, vi } from 'vitest'
import { ApiError } from './api'
import type { MealEntry } from './api'
import { dropOwner, enqueue, flushOutbox, loadOutbox, logOrQueue, newKey } from './outbox'
import type { OutboxItem } from './outbox'

function store() {
  const data = new Map<string, string>()
  return { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v) }
}

function item(key: string, owner = 1): OutboxItem {
  return {
    key,
    owner,
    name: `Food ${key}`,
    created_at: '2026-11-13T12:00:00Z',
    kind: 'entry',
    body: { food_id: 3, eaten_on: '2026-11-13', meal_type: 'lunch', grams: 100 },
  }
}

const entry = { id: 9 } as MealEntry
const offline = () => Promise.reject(new TypeError('Failed to fetch'))

describe('newKey', () => {
  it('makes a v4 UUID, even without crypto.randomUUID', () => {
    const key = newKey((bytes) => bytes.fill(0xff))
    expect(key).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
    expect(newKey()).not.toBe(newKey())
  })
})

describe('logOrQueue', () => {
  it('logs at once when the server answers', async () => {
    const s = store()
    expect(await logOrQueue(s, item('a'), () => Promise.resolve(entry))).toEqual({ entry })
    expect(loadOutbox(s)).toEqual([])
  })

  it('keeps the item, under the same key, when nothing answers', async () => {
    const s = store()
    const result = await logOrQueue(s, item('a'), offline)
    expect(result).toEqual({ queued: item('a') })
    expect(loadOutbox(s).map((i) => i.key)).toEqual(['a'])
  })

  it('passes a refusal on instead of queuing it', async () => {
    const s = store()
    await expect(logOrQueue(s, item('a'), () => Promise.reject(new ApiError(409, 'Meal is full')))).rejects.toThrow(
      'Meal is full',
    )
    expect(loadOutbox(s)).toEqual([])
  })
})

describe('flushOutbox', () => {
  it('sends the owner\'s items oldest first, with their own keys, and only theirs', async () => {
    const s = store()
    for (const [key, owner] of [['a', 1], ['b', 2], ['c', 1]] as const) enqueue(s, item(key, owner))
    const send = vi.fn<(item: OutboxItem) => Promise<MealEntry>>(() => Promise.resolve(entry))
    expect(await flushOutbox(s, 1, send)).toEqual({ sent: 2, refused: [], left: 0 })
    expect(send.mock.calls.map(([i]) => i.key)).toEqual(['a', 'c'])
    expect(loadOutbox(s).map((i) => i.key)).toEqual(['b'])
  })

  it('stops at no answer, a 5xx or a 429, and keeps the rest in order', async () => {
    for (const failure of [offline, () => Promise.reject(new ApiError(503, 'busy')), () => Promise.reject(new ApiError(429, 'slow'))]) {
      const s = store()
      for (const key of ['a', 'b', 'c']) enqueue(s, item(key))
      let calls = 0
      const send = () => (++calls === 2 ? failure() : Promise.resolve(entry))
      expect(await flushOutbox(s, 1, send)).toEqual({ sent: 1, refused: [], left: 2 })
      expect(loadOutbox(s).map((i) => i.key)).toEqual(['b', 'c'])
    }
  })

  it('drops a refused item (4xx) and goes on, saying which', async () => {
    const s = store()
    for (const key of ['a', 'b']) enqueue(s, item(key))
    let calls = 0
    const send = () => (++calls === 1 ? Promise.reject(new ApiError(404, 'Food not found')) : Promise.resolve(entry))
    const result = await flushOutbox(s, 1, send)
    expect(result.sent).toBe(1)
    expect(result.refused.map((r) => [r.item.key, r.message])).toEqual([['a', 'Food not found']])
    expect(loadOutbox(s)).toEqual([])
  })

  it('stops at a 401 and keeps the items for their owner', async () => {
    const s = store()
    enqueue(s, item('a'))
    expect(await flushOutbox(s, 1, () => Promise.reject(new ApiError(401, 'expired')))).toEqual({
      sent: 0,
      refused: [],
      left: 1,
    })
    expect(loadOutbox(s)).toHaveLength(1)
  })
})

describe('dropOwner', () => {
  it('removes one account\'s items only', () => {
    const s = store()
    enqueue(s, item('a', 1))
    enqueue(s, item('b', 2))
    dropOwner(s, 1)
    expect(loadOutbox(s).map((i) => i.key)).toEqual(['b'])
  })
})
