import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { ApiError, describeError, fetchConsentText, giveConsent, withdrawConsent } from './api'
import type { ConsentStatus, ConsentText } from './api'
import { useI18n } from './i18n/context'
import { ExportData } from './Trust'
import { useConsent } from './useConsent'

/**
 * The consent's text exactly as the server holds it: a heading ("# "),
 * then paragraphs split by a blank line, "- " lines as a list. Rendered as
 * React text, never as HTML, so nothing in it can run.
 */
export function ConsentBody({ text }: { text: string }) {
  const blocks = text.trim().split(/\n\s*\n/)
  const out: ReactNode[] = []
  blocks.forEach((block, index) => {
    const lines = block.split('\n').map((line) => line.trim())
    if (lines[0].startsWith('# ')) {
      out.push(<h3 key={index}>{lines[0].slice(2)}</h3>)
      const rest = lines.slice(1).join(' ').trim()
      if (rest) out.push(<p key={`${index}-p`}>{rest}</p>)
    } else if (lines.every((line) => line.startsWith('- '))) {
      out.push(
        <ul key={index}>
          {lines.map((line, i) => (
            <li key={i}>{line.slice(2)}</li>
          ))}
        </ul>,
      )
    } else {
      out.push(<p key={index}>{lines.join(' ')}</p>)
    }
  })
  return <div className="consent-text">{out}</div>
}

/** Given once and not withdrawn since (the server keeps both dates). */
function stillGiven(status: ConsentStatus): boolean {
  if (!status.given_at) return false
  return !status.withdrawn_at || status.withdrawn_at < status.given_at
}

/**
 * Where body weight lives (Today's weight card), while the consent is not
 * valid: its exact text in the UI language, "I agree" and "Not now".
 * A text that changed meanwhile (409) is loaded again to be read anew.
 */
export function ConsentCard({
  token,
  status,
  onGiven,
  onLater,
}: {
  token: string
  status: ConsentStatus
  onGiven: () => void
  onLater: () => void
}) {
  const { t, locale } = useI18n()
  const [text, setText] = useState<ConsentText | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let cancelled = false
    fetchConsentText(token, locale)
      .then((loaded) => {
        if (!cancelled) setText(loaded)
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err))
      })
    return () => {
      cancelled = true
    }
  }, [token, locale, reload])

  async function agree(shown: ConsentText) {
    setError(null)
    setBusy(true)
    try {
      await giveConsent(token, shown.version, shown.locale)
      onGiven()
    } catch (err) {
      if (err instanceof ApiError && err.code === 'consent_version_outdated') {
        setText(null)
        setError(t('consent.changed'))
        setReload((n) => n + 1)
      } else {
        setError(describeError(err))
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card consent-card" aria-labelledby="consent-title">
      <h2 id="consent-title">{t('weight.title')}</h2>
      {/* Given before, for an older text: the data waits, it is not gone */}
      {stillGiven(status) && !status.valid && <p className="notice">{t('consent.renew')}</p>}
      {!text && !error && <p className="muted">{t('app.loading')}</p>}
      {text && <ConsentBody text={text.text} />}
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="button" disabled={!text || busy} onClick={() => text && void agree(text)}>
          {busy ? t('common.saving') : t('consent.agree')}
        </button>
        <button type="button" className="link" onClick={onLater}>
          {t('consent.later')}
        </button>
      </div>
    </section>
  )
}

/**
 * Profile: whether the consent is given, since when, and withdrawing it.
 * Withdrawing deletes every weigh-in and estimate at once (no password, by
 * backend's contract), so it takes a step of its own with the warning and
 * a way to download everything first.
 */
export function ConsentProfile({ token, onChanged }: { token: string; onChanged: () => void }) {
  const { t, locale } = useI18n()
  const [version, setVersion] = useState(0)
  const state = useConsent(token, version)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  if (state.kind === 'off' || state.kind === 'loading') return null
  if (state.kind === 'error') return <p className="error">{state.message}</p>
  const { status } = state
  const givenOn = status.given_at
    ? new Date(status.given_at).toLocaleDateString(locale === 'en' ? 'en-GB' : locale, {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      })
    : null

  async function withdraw() {
    setError(null)
    setBusy(true)
    try {
      await withdrawConsent(token)
      setConfirming(false)
      setDone(true)
      setVersion((v) => v + 1)
      onChanged()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="consent-profile">
      <h3>{t('consent.title')}</h3>
      {status.valid && givenOn ? (
        <p>{t('consent.givenOn', { date: givenOn })}</p>
      ) : (
        <p className="muted">{stillGiven(status) ? t('consent.renewShort') : t('consent.notGiven')}</p>
      )}
      {done && <p role="status">{t('consent.withdrawn')}</p>}
      {stillGiven(status) && !confirming && (
        <button type="button" className="link danger" onClick={() => setConfirming(true)}>
          {t('consent.withdraw')}
        </button>
      )}
      {confirming && (
        <div className="delete-account withdraw-step" role="group" aria-label={t('consent.withdrawTitle')}>
          <p>
            <strong>{t('consent.withdrawTitle')}</strong>
          </p>
          <p>{t('consent.withdrawWarning')}</p>
          <ExportData token={token} />
          {error && <p className="error">{error}</p>}
          <div className="actions">
            <button type="button" disabled={busy} onClick={() => void withdraw()}>
              {busy ? t('common.saving') : t('consent.withdrawConfirm')}
            </button>
            <button type="button" className="link" onClick={() => setConfirming(false)}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
