import type { MessageKey } from './i18n/i18n'

// The backend's rules for a new password (app/schemas.py, NewPassword)
export const PASSWORD_MIN_LENGTH = 8
export const PASSWORD_MAX_LENGTH = 128

/**
 * What is wrong with a password change before it is sent, or null. The
 * current password is only checked by the server.
 */
export function passwordChangeError(
  current: string,
  next: string,
  confirm: string,
): MessageKey | null {
  if (next.length < PASSWORD_MIN_LENGTH) return 'password.tooShort'
  if (next.length > PASSWORD_MAX_LENGTH) return 'password.tooLong'
  if (next !== confirm) return 'password.mismatch'
  if (next === current) return 'password.same'
  return null
}
