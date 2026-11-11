/**
 * Validation errors shown in a form, keyed by where they belong (e.g.
 * "exercise.2.set.0"), and the pure functions that drop them once the
 * user changes what they were about.
 */
export type FormErrors = Record<string, string>

/** The errors without the given keys; the same object when none of them is there. */
export function withoutKeys(errors: FormErrors, ...keys: string[]): FormErrors {
  if (!keys.some((key) => key in errors)) return errors
  const left = { ...errors }
  for (const key of keys) delete left[key]
  return left
}

/**
 * The errors without the rows under prefix from index on, and what is inside
 * them: "exercise", 2 drops "exercise.2", "exercise.2.sets", "exercise.3"...
 * but keeps "exercise.1". Removing a row shifts the rows after it up by one,
 * so their errors would show next to the wrong row.
 */
export function withoutRowsFrom(errors: FormErrors, prefix: string, index: number): FormErrors {
  const row = new RegExp(`^${prefix.replace(/\./g, '\\.')}\\.(\\d+)(\\.|$)`)
  const keys = Object.keys(errors).filter((key) => {
    const match = row.exec(key)
    return match !== null && Number(match[1]) >= index
  })
  return withoutKeys(errors, ...keys)
}

/**
 * The first place where two versions of a list differ, by identity: the
 * editors replace only the rows that change, so an unchanged row is the same
 * object. The length of before when only rows were added at the end.
 */
export function firstChangedRow<T>(before: T[], after: T[]): number {
  const index = before.findIndex((row, i) => after[i] !== row)
  return index === -1 ? before.length : index
}
