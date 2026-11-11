import { describe, expect, it } from 'vitest'
import type { Exercise, Workout } from './api'
import {
  DATE_KEY,
  EXERCISES_KEY,
  NEW_EXERCISE,
  NOTE_KEY,
  clearExerciseErrors,
  clearRemovedExercise,
  emptyExercise,
  exerciseKey,
  exercisesToCreate,
  newWorkoutFields,
  setKey,
  setsKey,
  toWorkoutInput,
  validateWorkout,
  workoutToFields,
} from './workoutForm'
import type { ExerciseFields, WorkoutFields } from './workoutForm'

const CATALOG: Exercise[] = [
  { id: 1, name: 'Bench press' },
  { id: 2, name: 'Squat' },
]

function block(exercise: string, sets: [string, string][], newName = ''): ExerciseFields {
  return { exercise, newName, sets: sets.map(([reps, weight]) => ({ reps, weight })) }
}

function workout(...exercises: ExerciseFields[]): WorkoutFields {
  return { performedOn: '2026-11-02', note: '', exercises }
}

/** A new exercise block with one valid set. */
function newBlock(name: string): ExerciseFields {
  return block(NEW_EXERCISE, [['5', '100']], name)
}

describe('new and prefilled fields', () => {
  it('starts on the given day with one empty exercise to choose', () => {
    const fields = newWorkoutFields('2026-11-02', CATALOG)

    expect(fields.performedOn).toBe('2026-11-02')
    expect(fields.exercises).toEqual([
      { exercise: '', newName: '', sets: [{ reps: '', weight: '' }] },
    ])
  })

  it('goes straight to a new name when the catalog is empty', () => {
    expect(emptyExercise([]).exercise).toBe(NEW_EXERCISE)
  })

  it('prefills weights with String(), which a number input accepts', () => {
    const saved: Workout = {
      id: 7,
      performed_on: '2026-11-01',
      note: null,
      exercises: [
        { exercise_id: 2, exercise_name: 'Squat', sets: [{ reps: 8, weight_kg: 22.5 }] },
      ],
    }

    const fields = workoutToFields(saved)

    expect(fields).toEqual({
      performedOn: '2026-11-01',
      note: '',
      exercises: [{ ...block('2', [['8', '22.5']]), sets: [{ reps: '8', weight: '22.5', savedKg: 22.5 }] }],
    })
  })
})

describe('validateWorkout', () => {
  it('accepts a valid workout, including a bodyweight set written as 0', () => {
    const fields = workout(block('1', [['8', '60'], ['12', '0']]), newBlock('Dips'))

    expect(validateWorkout(fields)).toEqual({})
  })

  it('rejects a blank weight instead of treating it as bodyweight', () => {
    // Number('') and Number('  ') are both 0
    for (const weight of ['', '  ']) {
      const errors = validateWorkout(workout(block('1', [['8', weight]])))

      expect(errors, `weight ${JSON.stringify(weight)}`).toEqual({
        [setKey(0, 0)]: 'Enter the weight (0 for bodyweight)',
      })
    }
  })

  it('rejects empty set rows, next to the right row', () => {
    const errors = validateWorkout(workout(block('1', [['8', '60']]), block('2', [['', '']])))

    expect(errors).toEqual({ [setKey(1, 0)]: 'Enter the reps' })
  })

  it('accepts reps from 1 to 1000', () => {
    for (const reps of ['1', '1000']) {
      const errors = validateWorkout(workout(block('1', [[reps, '60']])))

      expect(errors, `reps ${reps}`).toEqual({})
    }
  })

  it('rejects reps that are not a whole number from 1 to 1000', () => {
    // 'abc' is NaN, which no < or > comparison catches
    for (const reps of ['0', '1001', '8.5', '-3', 'abc']) {
      const errors = validateWorkout(workout(block('1', [[reps, '60']])))

      expect(errors[setKey(0, 0)], `reps ${reps}`).toBe(
        'Reps must be a whole number from 1 to 1000',
      )
    }
  })

  it('accepts weights from 0 to 1000 kg, with decimals', () => {
    for (const weight of ['0', '22.5', '1000']) {
      const errors = validateWorkout(workout(block('1', [['5', weight]])))

      expect(errors, `weight ${weight}`).toEqual({})
    }
  })

  it('rejects weights outside 0 to 1000 kg, or not a number', () => {
    for (const weight of ['-0.5', '1000.5', 'abc']) {
      const errors = validateWorkout(workout(block('1', [['5', weight]])))

      expect(errors[setKey(0, 0)], `weight ${weight}`).toBe(
        'Weight must be from 0 to 1000 kg',
      )
    }
  })

  it('needs at least one exercise, each with at least one set', () => {
    expect(validateWorkout(workout())).toEqual({
      [EXERCISES_KEY]: 'Add at least one exercise',
    })
    expect(validateWorkout(workout(block('1', [])))).toEqual({
      [setsKey(0)]: 'Add at least one set',
    })
  })

  it('caps exercises and sets at 50', () => {
    const tooManySets = block('1', Array.from({ length: 51 }, () => ['5', '60']))
    const tooManyExercises = Array.from({ length: 51 }, () => block('1', [['5', '60']]))

    expect(validateWorkout(workout(tooManySets))[setsKey(0)]).toBe(
      'An exercise can have at most 50 sets',
    )
    expect(validateWorkout(workout(...tooManyExercises))[EXERCISES_KEY]).toBe(
      'A workout can have at most 50 exercises',
    )
  })

  it('needs an exercise chosen, or a new name of at most 100 characters', () => {
    const fields = workout(
      block('', [['5', '60']]),
      newBlock('   '),
      newBlock('x'.repeat(101)),
      newBlock(` ${'x'.repeat(100)} `),
    )

    expect(validateWorkout(fields)).toEqual({
      [exerciseKey(0)]: 'Choose an exercise',
      [exerciseKey(1)]: 'Enter the new exercise name',
      [exerciseKey(2)]: 'The name can have at most 100 characters',
    })
  })

  it('caps the note at 500 characters, not counting spaces around it', () => {
    const fields = workout(block('1', [['5', '60']]))

    expect(validateWorkout({ ...fields, note: ` ${'n'.repeat(500)} ` })).toEqual({})
    expect(validateWorkout({ ...fields, note: 'n'.repeat(501) })).toEqual({
      [NOTE_KEY]: 'The note can have at most 500 characters',
    })
  })

  it('needs a date', () => {
    const fields = { ...workout(block('1', [['5', '60']])), performedOn: '' }

    expect(validateWorkout(fields)).toEqual({ [DATE_KEY]: 'Choose a date' })
  })

  it('accepts dates from 2000-01-01 to tomorrow, local', () => {
    for (const performedOn of ['2000-01-01', '2026-11-02', '2026-11-03']) {
      const fields = { ...workout(block('1', [['5', '60']])), performedOn }

      expect(validateWorkout(fields, '2026-11-02'), performedOn).toEqual({})
    }
  })

  it('rejects dates before 2000-01-01 or after tomorrow', () => {
    for (const performedOn of ['1999-12-31', '2026-11-04', '2099-01-01']) {
      const fields = { ...workout(block('1', [['5', '60']])), performedOn }

      expect(validateWorkout(fields, '2026-11-02'), performedOn).toEqual({
        [DATE_KEY]: 'The date must be from 2000-01-01 to 2026-11-03',
      })
    }
  })

  it('finds tomorrow across the end of a year', () => {
    const fields = { ...workout(block('1', [['5', '60']])), performedOn: '2027-01-01' }

    expect(validateWorkout(fields, '2026-12-31')).toEqual({})
    expect(validateWorkout({ ...fields, performedOn: '2027-01-02' }, '2026-12-31')).toEqual({
      [DATE_KEY]: 'The date must be from 2000-01-01 to 2027-01-01',
    })
  })
})

describe('exercisesToCreate', () => {
  it('reuses a catalog exercise, ignoring case and spaces around the name', () => {
    const fields = workout(newBlock('  squat '), newBlock('Deadlift'))

    expect(exercisesToCreate(fields, CATALOG)).toEqual(['Deadlift'])
  })

  it('creates a name used by two blocks only once', () => {
    const fields = workout(newBlock('Deadlift'), newBlock('deadlift '))

    expect(exercisesToCreate(fields, CATALOG)).toEqual(['Deadlift'])
  })

  it('creates nothing again on a retry after a failed save', () => {
    const fields = workout(newBlock('Deadlift'))
    // The first attempt created it, then saving the workout failed
    const catalogAfterFirstTry = [...CATALOG, { id: 3, name: 'Deadlift' }]

    expect(exercisesToCreate(fields, catalogAfterFirstTry)).toEqual([])
  })
})

describe('toWorkoutInput', () => {
  it('builds the request body, with new names resolved to their ids', () => {
    const fields = workout(
      block('1', [['8', '60'], ['6', '61.25']]),
      newBlock('deadlift'),
      newBlock(' SQUAT'),
    )
    const catalog = [...CATALOG, { id: 3, name: 'Deadlift' }]

    const input = toWorkoutInput(fields, catalog)

    expect(input).toEqual({
      performed_on: '2026-11-02',
      note: null,
      exercises: [
        {
          exercise_id: 1,
          sets: [
            { reps: 8, weight_kg: 60 },
            { reps: 6, weight_kg: 61.25 },
          ],
        },
        { exercise_id: 3, sets: [{ reps: 5, weight_kg: 100 }] },
        { exercise_id: 2, sets: [{ reps: 5, weight_kg: 100 }] },
      ],
    })
  })

  it('sends a blank or spaces-only note as null, and trims a real one', () => {
    const fields = workout(block('1', [['5', '60']]))

    expect(toWorkoutInput({ ...fields, note: '' }, CATALOG).note).toBeNull()
    expect(toWorkoutInput({ ...fields, note: '  \n ' }, CATALOG).note).toBeNull()
    expect(toWorkoutInput({ ...fields, note: ' Leg day ' }, CATALOG).note).toBe('Leg day')
  })

  it('refuses a new name that was not created first', () => {
    expect(() => toWorkoutInput(workout(newBlock('Deadlift')), CATALOG)).toThrow(
      'Exercise not created: Deadlift',
    )
  })
})

describe('clearing errors as the user edits', () => {
  const before = block('', [['', '60'], ['8', ''], ['8', '60']])
  const errors = {
    [EXERCISES_KEY]: 'A workout can have at most 50 exercises',
    [exerciseKey(0)]: 'Choose an exercise',
    [setKey(0, 0)]: 'Enter the reps',
    [setKey(0, 1)]: 'Enter the weight (0 for bodyweight)',
    [exerciseKey(1)]: 'Choose an exercise',
  }

  it('drops the error of the field that changed, and only that one', () => {
    const after = { ...before, sets: before.sets.map((set, i) => (i === 0 ? { ...set, reps: '5' } : set)) }

    expect(clearExerciseErrors(errors, 0, before, after)).toEqual({
      [EXERCISES_KEY]: 'A workout can have at most 50 exercises',
      [exerciseKey(0)]: 'Choose an exercise',
      [setKey(0, 1)]: 'Enter the weight (0 for bodyweight)',
      [exerciseKey(1)]: 'Choose an exercise',
    })
  })

  it('drops the exercise error when another exercise or a new name is chosen', () => {
    expect(clearExerciseErrors(errors, 0, before, { ...before, exercise: '2' })).not.toHaveProperty(
      exerciseKey(0),
    )
    expect(clearExerciseErrors(errors, 0, before, { ...before, newName: 'D' })).not.toHaveProperty(
      exerciseKey(0),
    )
  })

  it('drops the errors of a removed set and of the sets after it', () => {
    const after = { ...before, sets: [before.sets[1], before.sets[2]] }

    const left = clearExerciseErrors({ ...errors, [setsKey(0)]: 'x' }, 0, before, after)

    expect(left).not.toHaveProperty(setKey(0, 0))
    expect(left).not.toHaveProperty(setKey(0, 1))
    expect(left).not.toHaveProperty(setsKey(0))
    expect(left).toHaveProperty(exerciseKey(0))
  })

  it('keeps the set errors when a set is added at the end', () => {
    const after = { ...before, sets: [...before.sets, { reps: '', weight: '' }] }

    const left = clearExerciseErrors({ ...errors, [setsKey(0)]: 'Add at least one set' }, 0, before, after)

    expect(left).not.toHaveProperty(setsKey(0))
    expect(left).toHaveProperty(setKey(0, 0))
    expect(left).toHaveProperty(setKey(0, 1))
  })

  it('drops the errors of a removed exercise and of those after it', () => {
    expect(clearRemovedExercise(errors, 1)).toEqual({
      [exerciseKey(0)]: 'Choose an exercise',
      [setKey(0, 0)]: 'Enter the reps',
      [setKey(0, 1)]: 'Enter the weight (0 for bodyweight)',
    })
  })
})

describe('weights in pounds', () => {
  const saved: Workout = {
    id: 7,
    performed_on: '2026-11-01',
    note: null,
    exercises: [
      {
        exercise_id: 1,
        exercise_name: 'Bench press',
        sets: [
          { reps: 8, weight_kg: 60 },
          { reps: 12, weight_kg: 0 },
        ],
      },
    ],
  }

  it('prefills a saved workout in lb, keeping the kilograms it came with', () => {
    const fields = workoutToFields(saved, 'lb')

    expect(fields.exercises[0].sets).toEqual([
      { reps: '8', weight: '132.28', savedKg: 60 },
      { reps: '12', weight: '0', savedKg: 0 },
    ])
  })

  it('sends the saved kilograms back unchanged when nothing was edited', () => {
    const input = toWorkoutInput(workoutToFields(saved, 'lb'), CATALOG, 'lb')

    // 132.28 lb alone would be 60.001 kg
    expect(input.exercises[0].sets).toEqual([
      { reps: 8, weight_kg: 60 },
      { reps: 12, weight_kg: 0 },
    ])
  })

  it('converts an edited weight, and a new set, from lb', () => {
    const fields = workoutToFields(saved, 'lb')
    const sets = [{ ...fields.exercises[0].sets[0], weight: '135' }, { reps: '5', weight: '61' }]
    const edited = { ...fields, exercises: [{ ...fields.exercises[0], sets }] }

    expect(toWorkoutInput(edited, CATALOG, 'lb').exercises[0].sets).toEqual([
      { reps: 8, weight_kg: 61.235 },
      { reps: 5, weight_kg: 27.669 },
    ])
  })

  it('checks the limit in lb, and accepts 61 lb', () => {
    expect(validateWorkout(workout(block('1', [['5', '61'], ['5', '2204.62']])), '2026-11-02', 'lb')).toEqual({})
    expect(validateWorkout(workout(block('1', [['5', '2205']])), '2026-11-02', 'lb')).toEqual({
      [setKey(0, 0)]: 'Weight must be from 0 to 2204.62 lb',
    })
  })
})
