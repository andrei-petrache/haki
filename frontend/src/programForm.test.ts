import { describe, expect, it } from 'vitest'
import type { Exercise } from './api'
import {
  DAYS_KEY,
  NAME_KEY,
  dayExercisesKey,
  dayNameKey,
  dayPositionKey,
  newDay,
  newProgramFields,
  nextFreePosition,
  plannedExerciseKey,
  plannedValuesKey,
  programExercisesToCreate,
  toProgramInput,
  validateProgram,
} from './programForm'
import type { DayFields, PlannedFields, ProgramFields } from './programForm'
import { NEW_EXERCISE } from './workoutForm'

const CATALOG: Exercise[] = [
  { id: 1, name: 'Bench press' },
  { id: 2, name: 'Squat' },
]

function planned(exercise: string, sets = '3', reps = '8', weight = '60', newName = ''): PlannedFields {
  return { exercise, newName, sets, reps, weight }
}

function newPlanned(name: string): PlannedFields {
  return planned(NEW_EXERCISE, '3', '8', '60', name)
}

function day(position: number, ...exercises: PlannedFields[]): DayFields {
  return { position, name: `Day ${position}`, exercises }
}

function program(...days: DayFields[]): ProgramFields {
  return { name: 'Push/Pull/Legs', days }
}

describe('new fields', () => {
  it('starts with one day at position 1 and one exercise to choose', () => {
    expect(newProgramFields(CATALOG)).toEqual({
      name: '',
      days: [
        {
          position: 1,
          name: '',
          exercises: [{ exercise: '', newName: '', sets: '', reps: '', weight: '' }],
        },
      ],
    })
  })

  it('goes straight to a new name when the catalog is empty', () => {
    expect(newProgramFields([]).days[0].exercises[0].exercise).toBe(NEW_EXERCISE)
  })

  it('puts a new day at the first free place in the plan', () => {
    const days = [day(1, planned('1')), day(2, planned('1')), day(4, planned('1'))]

    expect(nextFreePosition(days)).toBe(3)
    expect(newDay(days, CATALOG)?.position).toBe(3)
  })

  it('adds no day once all 7 places are taken', () => {
    const week = [1, 2, 3, 4, 5, 6, 7].map((position) => day(position, planned('1')))

    expect(nextFreePosition(week)).toBeNull()
    expect(newDay(week, CATALOG)).toBeNull()
  })
})

describe('validateProgram', () => {
  it('accepts a valid program, including a bodyweight exercise at 0 kg', () => {
    const fields = program(
      day(1, planned('1'), planned('2', '3', '10', '0')),
      day(3, newPlanned('Dips')),
    )

    expect(validateProgram(fields)).toEqual({})
  })

  it('accepts values at the limits', () => {
    const exercises = Array.from({ length: 20 }, () => planned('1', '50', '1000', '1000'))
    const week = [1, 2, 3, 4, 5, 6, 7].map((position) => day(position, planned('1', '1', '1', '0')))
    week[0] = { ...day(1, ...exercises), name: 'x'.repeat(100) }

    expect(validateProgram({ name: 'x'.repeat(100), days: week })).toEqual({})
  })

  it('needs a program name of at most 100 characters', () => {
    const valid = program(day(1, planned('1')))

    expect(validateProgram({ ...valid, name: '   ' })).toEqual({
      [NAME_KEY]: 'Enter a name for the program',
    })
    expect(validateProgram({ ...valid, name: 'x'.repeat(101) })).toEqual({
      [NAME_KEY]: 'The name can have at most 100 characters',
    })
    expect(validateProgram({ ...valid, name: ` ${'x'.repeat(100)} ` })).toEqual({})
  })

  it('needs at least one day and at most 7', () => {
    const eight = [1, 2, 3, 4, 5, 6, 7, 7].map((position) => day(position, planned('1')))

    expect(validateProgram(program())).toEqual({ [DAYS_KEY]: 'Add at least one day' })
    expect(validateProgram(program(...eight))[DAYS_KEY]).toBe(
      'A program can have at most 7 days',
    )
  })

  it('rejects two days on the same place in the plan, next to the later one', () => {
    const errors = validateProgram(program(day(2, planned('1')), day(2, planned('2'))))

    expect(errors).toEqual({ [dayPositionKey(1)]: 'Another day is already day 2' })
  })

  it('rejects a place outside 1 to 7', () => {
    for (const position of [0, 8, 1.5]) {
      const errors = validateProgram(program(day(position, planned('1'))))

      expect(errors, `position ${position}`).toEqual({
        [dayPositionKey(0)]: 'Choose a day from 1 to 7',
      })
    }
  })

  it('needs a day name', () => {
    const fields = program({ ...day(1, planned('1')), name: '  ' })

    expect(validateProgram(fields)).toEqual({ [dayNameKey(0)]: 'Enter a name for the day' })
  })

  it('needs 1 to 20 exercises a day', () => {
    const many = day(1, ...Array.from({ length: 21 }, () => planned('1')))

    expect(validateProgram(program(day(1)))).toEqual({
      [dayExercisesKey(0)]: 'Add at least one exercise',
    })
    expect(validateProgram(program(many))[dayExercisesKey(0)]).toBe(
      'A day can have at most 20 exercises',
    )
  })

  it('needs an exercise chosen, or a new name', () => {
    const fields = program(day(1, planned(''), newPlanned('  ')))

    expect(validateProgram(fields)).toEqual({
      [plannedExerciseKey(0, 0)]: 'Choose an exercise',
      [plannedExerciseKey(0, 1)]: 'Enter the new exercise name',
    })
  })

  it('rejects sets that are blank or not a whole number from 1 to 50', () => {
    expect(validateProgram(program(day(1, planned('1', ' ')))))
      .toEqual({ [plannedValuesKey(0, 0)]: 'Enter the sets' })
    for (const sets of ['0', '51', '2.5', 'abc']) {
      const errors = validateProgram(program(day(1, planned('1', sets))))

      expect(errors[plannedValuesKey(0, 0)], `sets ${sets}`).toBe(
        'Sets must be a whole number from 1 to 50',
      )
    }
  })

  it('checks reps and weight as for a logged set, a blank weight included', () => {
    const fields = program(
      day(1, planned('1', '3', '0'), planned('1', '3', '8', ''), planned('1', '3', '8', '1000.5')),
    )

    expect(validateProgram(fields)).toEqual({
      [plannedValuesKey(0, 0)]: 'Reps must be a whole number from 1 to 1000',
      [plannedValuesKey(0, 1)]: 'Enter the weight (0 for bodyweight)',
      [plannedValuesKey(0, 2)]: 'Weight must be from 0 to 1000 kg',
    })
  })
})

describe('programExercisesToCreate', () => {
  it('creates each new name once across days, reusing the catalog', () => {
    const fields = program(
      day(1, newPlanned('Deadlift'), newPlanned(' squat ')),
      day(2, newPlanned('deadlift')),
    )

    expect(programExercisesToCreate(fields, CATALOG)).toEqual(['Deadlift'])
  })
})

describe('toProgramInput', () => {
  it('builds the request body, trimmed, with new names resolved to their ids', () => {
    const fields: ProgramFields = {
      name: '  PPL ',
      days: [
        { position: 4, name: ' Legs ', exercises: [planned('2', '5', '5', '102.5')] },
        { position: 1, name: 'Push', exercises: [planned('1'), newPlanned('dips')] },
      ],
    }
    const catalog = [...CATALOG, { id: 3, name: 'Dips' }]

    expect(toProgramInput(fields, catalog)).toEqual({
      name: 'PPL',
      days: [
        {
          position: 4,
          name: 'Legs',
          exercises: [{ exercise_id: 2, sets: 5, reps: 5, weight_kg: 102.5 }],
        },
        {
          position: 1,
          name: 'Push',
          exercises: [
            { exercise_id: 1, sets: 3, reps: 8, weight_kg: 60 },
            { exercise_id: 3, sets: 3, reps: 8, weight_kg: 60 },
          ],
        },
      ],
    })
  })

  it('refuses a new name that was not created first', () => {
    expect(() => toProgramInput(program(day(1, newPlanned('Dips'))), CATALOG)).toThrow(
      'Exercise not created: Dips',
    )
  })
})
