import { useState } from 'react'
import { createWorkout, describeError, setCalorieTarget } from './api'
import type { Exercise, User } from './api'
import CatalogExercisePicker from './CatalogExercisePicker'
import CatalogFoodPicker from './CatalogFoodPicker'
import { localDateString } from './format'
import { useI18n } from './i18n/context'
import { unitToKg, weightError } from './units'
import type { WeightUnit } from './units'

const STEPS = ['units', 'target', 'food', 'workout'] as const
type Step = (typeof STEPS)[number]

// Common daily targets, one tap each; any other is typed
const TARGET_PICKS = [1800, 2000, 2200, 2500]

/**
 * Right after signing up, before the app: the units, a daily target, a
 * first food and a first workout, each one tap or a skip away, in about a
 * minute. Never shown again (App keeps it to the signup's session).
 */
export default function Onboarding({
  token,
  unit,
  onUnitChange,
  onUserChange,
  onDone,
}: {
  token: string
  unit: WeightUnit
  onUnitChange: (unit: WeightUnit) => void
  onUserChange: (user: User) => void
  onDone: () => void
}) {
  const { t } = useI18n()
  const [step, setStep] = useState<Step>('units')
  const index = STEPS.indexOf(step)
  const next = () => (index === STEPS.length - 1 ? onDone() : setStep(STEPS[index + 1]))

  return (
    <section className="card onboarding" aria-labelledby="onboarding-title">
      <p className="muted small">{t('onboarding.step', { n: String(index + 1), of: String(STEPS.length) })}</p>
      <div className="onboarding-progress" aria-hidden="true">
        {STEPS.map((s, i) => (
          <span key={s} className={i <= index ? 'done' : ''} />
        ))}
      </div>
      {step === 'units' && (
        <>
          <h2 id="onboarding-title">{t('onboarding.unitsTitle')}</h2>
          <div className="segmented onboarding-units" role="group" aria-label={t('profile.weightsIn')}>
            {(['kg', 'lb'] as const).map((value) => (
              <button key={value} type="button" aria-pressed={unit === value} onClick={() => onUnitChange(value)}>
                {value === 'kg' ? t('profile.kilograms') : t('profile.pounds')}
              </button>
            ))}
          </div>
          <div className="actions">
            <button type="button" onClick={next}>
              {t('onboarding.next')}
            </button>
          </div>
        </>
      )}
      {step === 'target' && <TargetStep token={token} onSaved={onUserChange} onNext={next} />}
      {step === 'food' && (
        <>
          <h2 id="onboarding-title">{t('onboarding.foodTitle')}</h2>
          <p className="muted small">{t('onboarding.foodNote')}</p>
          <CatalogFoodPicker token={token} onAdded={() => {}} embedded />
          <div className="actions">
            <button type="button" onClick={next}>
              {t('onboarding.next')}
            </button>
          </div>
        </>
      )}
      {step === 'workout' && <WorkoutStep token={token} unit={unit} onNext={next} />}
      <button type="button" className="link onboarding-skip" onClick={step === 'units' ? onDone : next}>
        {step === 'units' ? t('onboarding.skipAll') : t('onboarding.skip')}
      </button>
    </section>
  )
}

function TargetStep({ token, onSaved, onNext }: { token: string; onSaved: (user: User) => void; onNext: () => void }) {
  const { t } = useI18n()
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function save(target: number) {
    setError(null)
    setBusy(true)
    try {
      onSaved(await setCalorieTarget(token, target))
      onNext()
    } catch (err) {
      setError(describeError(err))
      setBusy(false)
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault()
        void save(Number(value))
      }}
    >
      <h2 id="onboarding-title">{t('onboarding.targetTitle')}</h2>
      <p className="muted small">{t('onboarding.targetNote')}</p>
      <div className="chip-row onboarding-picks">
        {TARGET_PICKS.map((pick) => (
          <button key={pick} type="button" className="chip" disabled={busy} onClick={() => void save(pick)}>
            {pick} kcal
          </button>
        ))}
      </div>
      <label>
        {t('onboarding.targetOther')}
        <input
          type="number"
          inputMode="numeric"
          min={500}
          max={10000}
          required
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
      </label>
      {error && <p className="error">{error}</p>}
      <div className="actions">
        <button type="submit" disabled={busy || value === ''}>
          {t('onboarding.saveNext')}
        </button>
      </div>
    </form>
  )
}

function WorkoutStep({ token, unit, onNext }: { token: string; unit: WeightUnit; onNext: () => void }) {
  const { t } = useI18n()
  const [exercise, setExercise] = useState<Exercise | null>(null)
  const [reps, setReps] = useState('')
  const [weight, setWeight] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function log() {
    if (!exercise) return
    const problem = weightError(weight, unit)
    const repsNumber = Number(reps)
    if (problem) return setError(problem)
    if (!Number.isInteger(repsNumber) || repsNumber < 1 || repsNumber > 1000) return setError(t('form.repsRange', { max: '1000' }))
    setError(null)
    setBusy(true)
    try {
      await createWorkout(token, {
        performed_on: localDateString(),
        note: null,
        exercises: [{ exercise_id: exercise.id, sets: [{ reps: repsNumber, weight_kg: unit === 'kg' ? Number(weight) : unitToKg(Number(weight), unit) }] }],
      })
      onNext()
    } catch (err) {
      setError(describeError(err))
      setBusy(false)
    }
  }

  return (
    <>
      <h2 id="onboarding-title">{t('onboarding.workoutTitle')}</h2>
      <p className="muted small">{t('onboarding.workoutNote')}</p>
      {!exercise ? (
        <CatalogExercisePicker token={token} own={[]} onPick={setExercise} />
      ) : (
        <form
          className="onboarding-set"
          onSubmit={(event) => {
            event.preventDefault()
            void log()
          }}
        >
          <p>
            <strong>{exercise.name}</strong>{' '}
            <button type="button" className="link" onClick={() => setExercise(null)}>
              {t('onboarding.change')}
            </button>
          </p>
          <div className="onboarding-set-fields">
            <label>
              {t('workouts.reps')}
              <input type="number" inputMode="numeric" min={1} required value={reps} onChange={(e) => setReps(e.target.value)} />
            </label>
            <label>
              {t('weight.field', { unit })}
              <input type="number" inputMode="decimal" min={0} step="any" required value={weight} onChange={(e) => setWeight(e.target.value)} />
            </label>
          </div>
          {error && <p className="error">{error}</p>}
          <div className="actions">
            <button type="submit" disabled={busy}>
              {t('onboarding.logSet')}
            </button>
          </div>
        </form>
      )}
    </>
  )
}
