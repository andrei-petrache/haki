/**
 * The password reset link: <origin>/reset#token=… The token rides in the
 * URL's fragment, which browsers never send to a server (no access logs,
 * no Referer), and the page removes it from the address bar and history
 * before anything else runs.
 */

export const RESET_PATH = '/reset'

/** The token in a fragment such as "#token=abc", or null. */
export function parseResetFragment(hash: string): string | null {
  const params = new URLSearchParams(hash.startsWith('#') ? hash.slice(1) : hash)
  const token = params.get('token')
  return token && token.trim() !== '' ? token : null
}

/**
 * On /reset: take the token out of the address and the history entry (so
 * Back, a bookmark or a shared screen does not carry it), and return it.
 * Elsewhere: null, and the address is left alone.
 */
export function takeResetToken(location: Pick<Location, 'pathname' | 'hash'>, history: Pick<History, 'replaceState'>): string | null | undefined {
  if (location.pathname !== RESET_PATH) return undefined
  const token = parseResetFragment(location.hash)
  history.replaceState(null, '', RESET_PATH)
  return token
}
