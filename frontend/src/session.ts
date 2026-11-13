/** Where the token lives, shared by every tab of this browser. */
export const TOKEN_KEY = 'haki_token'

/**
 * After the server rejected `rejected` (401): the token this tab should carry
 * on with, or null to log out. Another tab may have stored a newer token
 * meanwhile (a password change signs the old one out): then this tab takes
 * it up instead of logging out, and the stored one is left alone. Only the
 * rejected token itself is ever removed from storage.
 */
export function afterRejected(storage: Pick<Storage, 'getItem' | 'removeItem'>, rejected: string): string | null {
  const stored = storage.getItem(TOKEN_KEY)
  if (stored && stored !== rejected) return stored
  if (stored === rejected) storage.removeItem(TOKEN_KEY)
  return null
}

/**
 * The account a token belongs to: its "sub" claim (the user id), read from
 * the payload without verifying anything. Only to compare, e.g. that the
 * offline queue sends an account's entries with that account's token; the
 * server is what checks tokens. Null for anything that is not a JWT.
 */
export function tokenSubject(token: string): string | null {
  try {
    const part = token.split('.')[1]
    if (!part) return null
    const json = atob(part.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(part.length / 4) * 4, '='))
    const sub = (JSON.parse(json) as { sub?: unknown }).sub
    return typeof sub === 'string' || typeof sub === 'number' ? String(sub) : null
  } catch {
    return null
  }
}
