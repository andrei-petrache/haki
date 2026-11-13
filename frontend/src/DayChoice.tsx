import { useRef } from 'react'
import { formatDayLabel, localDateString } from './format'
import { useI18n } from './i18n/context'

/**
 * A day as words ("Today, 13 Nov" / "Azi, 13 nov."), which opens the
 * browser's own date picker, kept invisible under it. Today's header, the
 * workout editor and a program's start date all use it.
 */
export default function DayChoice({
  day,
  onChange,
  fieldLabel,
}: {
  day: string
  onChange: (day: string) => void
  // The hidden date input's own label, e.g. "Day" or "Workout date"
  fieldLabel: string
}) {
  const { t } = useI18n()
  const input = useRef<HTMLInputElement>(null)
  const label = formatDayLabel(day, localDateString(), {
    today: t('today.today'),
    yesterday: t('today.yesterday'),
    tomorrow: t('today.tomorrow'),
  })

  return (
    <span className="day-choice">
      <button
        type="button"
        className="day-label"
        aria-label={t('today.chooseDay', { day: label })}
        onClick={() => {
          const field = input.current
          if (!field) return
          try {
            field.showPicker()
          } catch {
            field.focus()
          }
        }}
      >
        {label}
      </button>
      <input
        ref={input}
        type="date"
        className="day-input"
        tabIndex={-1}
        aria-label={fieldLabel}
        value={day}
        // Clearing the field gives an empty string: keep the current day
        onChange={(event) => event.target.value && onChange(event.target.value)}
      />
    </span>
  )
}
