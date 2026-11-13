import { useEffect, useState } from 'react'
import { ApiError, describeError, fetchConsent } from './api'
import type { ConsentStatus } from './api'

export type ConsentState =
  | { kind: 'loading' }
  | { kind: 'off' }
  | { kind: 'error'; message: string }
  | { kind: 'ok'; status: ConsentStatus }

/**
 * The account's health data consent. A 404 means body weight is switched
 * off on the server (the consent sits behind the same switch).
 */
export function useConsent(token: string, version: number): ConsentState {
  const [state, setState] = useState<ConsentState>({ kind: 'loading' })
  useEffect(() => {
    let cancelled = false
    fetchConsent(token)
      .then((status) => {
        if (!cancelled) setState({ kind: 'ok', status })
      })
      .catch((err) => {
        if (cancelled) return
        setState(err instanceof ApiError && err.status === 404 ? { kind: 'off' } : { kind: 'error', message: describeError(err) })
      })
    return () => {
      cancelled = true
    }
  }, [token, version])
  return state
}
