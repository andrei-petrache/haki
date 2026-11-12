import { useState } from 'react'
import { ApiError, changePassword, describeError } from './api'
import { useI18n } from './i18n/context'
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, passwordChangeError } from './passwordChange'

/**
 * Change the password from Profile: the current one, then the new one
 * twice. Folded away until asked for. Other devices stay signed in until
 * their session ends (tokens carry no password version yet), and the
 * message says so.
 */
export default function ChangePassword({ token }: { token: string }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)

  function close() {
    setOpen(false)
    setCurrent('')
    setNext('')
    setConfirm('')
    setError(null)
  }

  async function handleSubmit() {
    const problem = passwordChangeError(current, next, confirm)
    if (problem) {
      setError(t(problem))
      return
    }
    setError(null)
    setBusy(true)
    try {
      await changePassword(token, current, next)
      close()
      setDone(true)
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 403
          ? t('password.wrongCurrent')
          : describeError(err),
      )
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <>
        {done && <p role="status">{t('password.changed')}</p>}
        <button
          type="button"
          className="link"
          onClick={() => {
            setDone(false)
            setOpen(true)
          }}
        >
          {t('password.open')}
        </button>
      </>
    )
  }

  return (
    <form
      className="password-form"
      aria-label={t('password.title')}
      onSubmit={(event) => {
        event.preventDefault()
        void handleSubmit()
      }}
    >
      <h3>{t('password.title')}</h3>
      <label>
        {t('password.current')}
        <input
          type="password"
          autoComplete="current-password"
          required
          maxLength={PASSWORD_MAX_LENGTH}
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
        />
      </label>
      <label>
        {t('password.new')}
        <input
          type="password"
          autoComplete="new-password"
          required
          minLength={PASSWORD_MIN_LENGTH}
          maxLength={PASSWORD_MAX_LENGTH}
          value={next}
          onChange={(event) => setNext(event.target.value)}
        />
      </label>
      <label>
        {t('password.confirm')}
        <input
          type="password"
          autoComplete="new-password"
          required
          maxLength={PASSWORD_MAX_LENGTH}
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
        />
      </label>
      <p className="muted">{t('password.rules', { min: PASSWORD_MIN_LENGTH })}</p>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={busy}>
          {busy ? t('common.saving') : t('password.save')}
        </button>
        <button type="button" className="link" onClick={close}>
          {t('common.cancel')}
        </button>
      </div>
    </form>
  )
}
