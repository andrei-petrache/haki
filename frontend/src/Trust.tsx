import { useState } from 'react'
import { ApiError, confirmPasswordReset, describeError, exportAccount, requestPasswordReset } from './api'
import { localDateString } from './format'
import { useI18n } from './i18n/context'
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH } from './passwordChange'

/**
 * "Forgot password?" under the login form: the e-mail, then the same
 * answer whether it has an account or not (the server never tells). A 404
 * means the server has the reset switched off: said once, then the link
 * goes (onUnavailable).
 */
export function ForgotPassword({ initialEmail, onUnavailable }: { initialEmail: string; onUnavailable: () => void }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState(initialEmail)
  const [sent, setSent] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!open) {
    return (
      <button type="button" className="link" onClick={() => setOpen(true)}>
        {t('reset.forgot')}
      </button>
    )
  }

  if (sent) return <p role="status">{t('reset.sent')}</p>

  return (
    <form
      className="card forgot-form"
      aria-label={t('reset.forgotTitle')}
      onSubmit={(event) => {
        event.preventDefault()
        setError(null)
        setBusy(true)
        requestPasswordReset(email.trim())
          .then(() => setSent(true))
          .catch((err) => {
            if (err instanceof ApiError && err.status === 404) {
              setError(t('reset.unavailable'))
              onUnavailable()
            } else {
              setError(describeError(err))
            }
          })
          .finally(() => setBusy(false))
      }}
    >
      <h3>{t('reset.forgotTitle')}</h3>
      <label>
        {t('auth.email')}
        <input type="email" required autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={busy}>
          {busy ? t('auth.wait') : t('reset.send')}
        </button>
        <button type="button" className="link" onClick={() => setOpen(false)}>
          {t('common.cancel')}
        </button>
      </div>
    </form>
  )
}

/**
 * /reset, from the e-mailed link: a new password twice. The token came
 * from the fragment and is already gone from the address (reset.ts). On
 * success the server signs out every other session and this one is logged
 * in with the token it returns.
 */
export function ResetPassword({
  token,
  onDone,
  onBackToLogin,
}: {
  token: string | null
  onDone: (accessToken: string) => void
  onBackToLogin: () => void
}) {
  const { t } = useI18n()
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [invalid, setInvalid] = useState(token === null)
  const [busy, setBusy] = useState(false)

  if (invalid) {
    return (
      <section className="card">
        <h2>{t('reset.title')}</h2>
        <p className="error">{error ?? t('reset.invalid')}</p>
        <button type="button" onClick={onBackToLogin}>
          {t('reset.backToLogin')}
        </button>
      </section>
    )
  }

  return (
    <form
      className="card"
      aria-label={t('reset.title')}
      onSubmit={(event) => {
        event.preventDefault()
        if (next.length < PASSWORD_MIN_LENGTH) return setError(t('password.tooShort'))
        if (next.length > PASSWORD_MAX_LENGTH) return setError(t('password.tooLong'))
        if (next !== confirm) return setError(t('password.mismatch'))
        setError(null)
        setBusy(true)
        confirmPasswordReset(token as string, next)
          .then(({ access_token }) => onDone(access_token))
          .catch((err) => {
            if (err instanceof ApiError && (err.status === 400 || err.status === 404)) {
              setError(err.status === 404 ? t('reset.unavailable') : t('reset.invalid'))
              setInvalid(true)
            } else {
              setError(describeError(err))
            }
          })
          .finally(() => setBusy(false))
      }}
    >
      <h2>{t('reset.title')}</h2>
      <label>
        {t('password.new')}
        <input
          type="password"
          required
          autoComplete="new-password"
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
          required
          autoComplete="new-password"
          maxLength={PASSWORD_MAX_LENGTH}
          value={confirm}
          onChange={(event) => setConfirm(event.target.value)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={busy}>
          {busy ? t('common.saving') : t('reset.save')}
        </button>
        <button type="button" className="link" onClick={onBackToLogin}>
          {t('reset.backToLogin')}
        </button>
      </div>
    </form>
  )
}

/**
 * Profile: download everything the account holds, after the password. The
 * file is fetched with the token in a header, checked whole, and handed
 * over as a download from memory: never a link that carries the token.
 */
export function ExportData({ token }: { token: string }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!open) {
    return (
      <div className="export-data">
        <button type="button" className="link" onClick={() => setOpen(true)}>
          {t('export.open')}
        </button>
        {done && <p role="status">{t('export.done', { name: done })}</p>}
      </div>
    )
  }

  return (
    <form
      className="export-form"
      aria-label={t('export.title')}
      onSubmit={(event) => {
        event.preventDefault()
        setError(null)
        setBusy(true)
        exportAccount(token, password, localDateString())
          .then(({ blob, name }) => {
            const url = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = url
            link.download = name
            document.body.append(link)
            link.click()
            link.remove()
            // After the click has started the download
            window.setTimeout(() => URL.revokeObjectURL(url), 1000)
            setPassword('')
            setOpen(false)
            setDone(name)
          })
          .catch((err) => {
            setError(err instanceof ApiError && err.status === 403 ? t('export.wrongPassword') : describeError(err))
          })
          .finally(() => setBusy(false))
      }}
    >
      <h3>{t('export.title')}</h3>
      <p className="muted small">{t('export.note')}</p>
      <label>
        {t('auth.password')}
        <input
          type="password"
          required
          autoComplete="current-password"
          maxLength={PASSWORD_MAX_LENGTH}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={busy || password === ''}>
          {busy ? t('export.preparing') : t('export.download')}
        </button>
        <button type="button" className="link" onClick={() => setOpen(false)}>
          {t('common.cancel')}
        </button>
      </div>
    </form>
  )
}
