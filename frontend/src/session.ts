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
