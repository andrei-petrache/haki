import { useEffect, useState } from 'react'
import { useI18n } from './i18n/context'

export type ToastMessage = {
  // A new id restarts the timer, even for the same text
  id: number
  text: string
  // What Undo does; no Undo button without it
  undo?: () => Promise<void>
}

/** How long a message stays, long enough to reach Undo. */
export const TOAST_MS = 6000

/**
 * A short message above the bottom bar, e.g. "Added ... · Undo", that goes
 * away by itself. Announced politely to screen readers (role=status).
 */
export default function Toast({
  message,
  onDone,
}: {
  message: ToastMessage | null
  onDone: () => void
}) {
  const { t } = useI18n()
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!message) return
    const timer = window.setTimeout(onDone, TOAST_MS)
    return () => window.clearTimeout(timer)
  }, [message, onDone])

  if (!message) return null

  return (
    <div className="toast" role="status">
      <span>{message.text}</span>
      {message.undo && (
        <button
          type="button"
          className="link"
          disabled={busy}
          onClick={() => {
            setBusy(true)
            message
              .undo?.()
              .finally(() => {
                setBusy(false)
                onDone()
              })
          }}
        >
          {t('log.undo')}
        </button>
      )}
    </div>
  )
}
