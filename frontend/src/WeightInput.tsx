import { maxWeightIn, stepWeight, weightStep } from './units'
import type { WeightUnit } from './units'

/**
 * A weight field in the chosen unit, with − / + buttons for the smallest
 * plate pair (2.5 lb or 1.25 kg).
 *
 * The input keeps step="any", not the plate step: with step="2.5" the
 * browser marks 61 lb, or 132.28 lb for a saved 60 kg, as :invalid. The
 * buttons give the plate steps instead and never go below 0. They sit
 * outside the label, so the label still names the input.
 */
export default function WeightInput({
  value,
  unit,
  of,
  onChange,
}: {
  value: string
  unit: WeightUnit
  /** What the weight belongs to, for the buttons' labels: "set 2 of exercise 1" */
  of: string
  onChange: (text: string) => void
}) {
  const step = weightStep(unit)
  const max = maxWeightIn(unit)
  const current = Number(value)

  return (
    <div className="weight-input">
      <label>
        Weight ({unit})
        <input
          type="number"
          inputMode="decimal"
          min={0}
          max={max}
          step="any"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
      <button
        type="button"
        className="icon"
        aria-label={`Decrease the weight of ${of} by ${step} ${unit}`}
        // Blank, 0 or not a number: there is nothing to take away
        disabled={!(current > 0)}
        onClick={() => onChange(stepWeight(value, unit, -1))}
      >
        −
      </button>
      <button
        type="button"
        className="icon"
        aria-label={`Increase the weight of ${of} by ${step} ${unit}`}
        disabled={current >= max}
        onClick={() => onChange(stepWeight(value, unit, 1))}
      >
        +
      </button>
    </div>
  )
}
