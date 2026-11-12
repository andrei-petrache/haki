import { useState } from 'react'
import { describeError, setCalorieTarget } from './api'
import type { User } from './api'
import { useI18n } from './i18n/context'

/**
 * The daily calorie target, set, changed or cleared. Lives in Profile:
 * Today's card keeps to the number, the bar and the macros.
 */
export default function TargetEditor({
  token,
  target,
  onSaved,
}: {
  token: string
  target: number | null
  onSaved: (user: User) => void
}) {
  const { t } = useI18n()
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function save(newTarget: number | null) {
    setError(null)
    setBusy(true)
    try {
      const user = await setCalorieTarget(token, newTarget)
      setEditing(false)
      onSaved(user)
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  if (!editing) {
    return (
      <button
        type="button"
        className="link"
        onClick={() => {
          setValue(target === null ? '' : String(target))
          setError(null)
          setEditing(true)
        }}
      >
        {target === null ? t('today.setTarget') : t('today.changeTarget')}
      </button>
    )
  }

  return (
    <form
      className="target-form"
      onSubmit={(event) => {
        event.preventDefault()
        void save(Number(value))
      }}
    >
      <label>
        {t('today.dailyTarget')}
        <input
          type="number"
          inputMode="numeric"
          min={500}
          max={10000}
          step={1}
          required
          autoFocus
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      </label>
      <div className="actions">
        <button type="submit" disabled={busy}>
          {t('common.save')}
        </button>
        {target !== null && (
          <button
            type="button"
            className="secondary"
            disabled={busy}
            onClick={() => void save(null)}
          >
            {t('today.clearTarget')}
          </button>
        )}
        <button type="button" className="link" onClick={() => setEditing(false)}>
          {t('common.cancel')}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </form>
  )
}
