/**
 * Offline logging: meal entries that could not reach the server wait here,
 * on this device, and go when the connection is back.
 *
 * Each item carries an Idempotency-Key made when the entry was first tried
 * (not when it is resent): if that first request did reach the server and
 * only its answer was lost, the server recognizes the key and returns the
 * entry it made instead of a second one. Items belong to the account that
 * made them (owner) and are only ever sent with that account's token.
 */
import { ApiError } from './api'
import type { MealEntry, MealEntryInput, QuickEntryInput } from './api'

export const OUTBOX_KEY = 'haki_outbox'

export type OutboxItem = {
  key: string
  owner: number
  name: string
  created_at: string
} & ({ kind: 'entry'; body: MealEntryInput } | { kind: 'quick'; body: QuickEntryInput })

type Store = Pick<Storage, 'getItem' | 'setItem'>

/** A random UUID (v4), also where crypto.randomUUID is missing (plain http). */
export function newKey(
  random: (bytes: Uint8Array<ArrayBuffer>) => void = (bytes) => {
    crypto.getRandomValues(bytes)
  },
): string {
  const bytes = new Uint8Array(16)
  random(bytes)
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

export function loadOutbox(store: Store): OutboxItem[] {
  try {
    const data: unknown = JSON.parse(store.getItem(OUTBOX_KEY) ?? '[]')
    return Array.isArray(data) ? (data as OutboxItem[]) : []
  } catch {
    return []
  }
}

function saveOutbox(store: Store, items: OutboxItem[]): void {
  store.setItem(OUTBOX_KEY, JSON.stringify(items))
}

export function enqueue(store: Store, item: OutboxItem): void {
  saveOutbox(store, [...loadOutbox(store), item])
}

export function removeItem(store: Store, key: string): void {
  saveOutbox(store, loadOutbox(store).filter((item) => item.key !== key))
}

/** The account's items gone from this device (its deletion). */
export function dropOwner(store: Store, owner: number): void {
  saveOutbox(store, loadOutbox(store).filter((item) => item.owner !== owner))
}

/** No answer at all (offline, DNS, a dropped connection): worth trying again. */
export function isNetworkError(err: unknown): boolean {
  return !(err instanceof ApiError)
}

/** An answer that means "later": the server busy or down, or rate limited. */
function isTransient(err: unknown): boolean {
  return isNetworkError(err) || (err instanceof ApiError && (err.status >= 500 || err.status === 429 || err.status === 408))
}

export type SendFn = (item: OutboxItem) => Promise<MealEntry>

/**
 * Try to log now; with no answer, keep it here under the same key. Any
 * answer, a refusal included, is passed on: only silence is queued.
 */
export async function logOrQueue(
  store: Store,
  item: OutboxItem,
  send: SendFn,
): Promise<{ entry: MealEntry } | { queued: OutboxItem }> {
  try {
    return { entry: await send(item) }
  } catch (err) {
    if (!isNetworkError(err)) throw err
    enqueue(store, item)
    return { queued: item }
  }
}

export type FlushResult = { sent: number; refused: { item: OutboxItem; message: string }[]; left: number }

/**
 * Send the owner's items, oldest first. An answer (2xx or a 4xx refusal)
 * takes an item out: resending would only get the same answer. No answer,
 * a 5xx or a 429 stops the round: the rest waits, in order, for the next.
 * A 401 stops it too; the app logs out and the items wait for the owner.
 */
export async function flushOutbox(store: Store, owner: number, send: SendFn): Promise<FlushResult> {
  const result: FlushResult = { sent: 0, refused: [], left: 0 }
  const mine = loadOutbox(store).filter((item) => item.owner === owner)
  for (const [index, item] of mine.entries()) {
    try {
      await send(item)
      removeItem(store, item.key)
      result.sent += 1
    } catch (err) {
      if (isTransient(err) || (err instanceof ApiError && err.status === 401)) {
        result.left = mine.length - index
        return result
      }
      removeItem(store, item.key)
      result.refused.push({ item, message: err instanceof ApiError ? err.message : String(err) })
    }
  }
  return result
}
