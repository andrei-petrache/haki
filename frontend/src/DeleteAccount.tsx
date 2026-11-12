import { useState } from 'react'
import { ApiError, deleteAccount, describeError } from './api'
import { useI18n } from './i18n/context'
import { PASSWORD_MAX_LENGTH } from './passwordChange'

/**
 * Delete the account, from Profile. Deletion is immediate and permanent
 * (Andrei's decision, no grace period), so it takes a separate step that
 * names the account, says it cannot be undone, asks for the password and
 * for an explicit "I understand"; no browser dialog. Folded away until
 * asked for. A wrong password (403) deletes nothing.
 */
export default function DeleteAccount({
  token,
  email,
  onDeleted,
}: {
  token: string
  email: string
  onDeleted: () => void
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [understood, setUnderstood] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function close() {
    setOpen(false)
    setPassword('')
    setUnderstood(false)
    setError(null)
  }

  async function handleSubmit() {
    setError(null)
    setBusy(true)
    try {
      await deleteAccount(token, password)
      onDeleted()
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403 ? t('account.wrongPassword') : describeError(err),
      )
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button type="button" className="link danger" onClick={() => setOpen(true)}>
        {t('account.deleteOpen')}
      </button>
    )
  }

  return (
    <form
      className="delete-account"
      aria-label={t('account.deleteTitle')}
      onSubmit={(event) => {
        event.preventDefault()
        void handleSubmit()
      }}
    >
      <h3>{t('account.deleteTitle')}</h3>
      <p>{t('account.deleteWarning', { email })}</p>
      <label>
        {t('account.password')}
        <input
          type="password"
          autoComplete="current-password"
          required
          maxLength={PASSWORD_MAX_LENGTH}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={understood}
          onChange={(event) => setUnderstood(event.target.checked)}
        />
        {t('account.understand')}
      </label>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" className="danger" disabled={busy || !understood || password === ''}>
          {busy ? t('account.deleting') : t('account.deleteConfirm')}
        </button>
        <button type="button" className="link" onClick={close}>
          {t('common.cancel')}
        </button>
      </div>
    </form>
  )
}
