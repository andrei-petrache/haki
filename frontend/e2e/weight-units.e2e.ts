/**
 * Weights in pounds, end to end: the API always stores kilograms, and what
 * the UI shows and sends in pounds must never change a saved weight by
 * itself. Checked through the API after each save.
 */
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { SHOTS, api, deleteEverything, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page
let workoutId: number

type Sets = { reps: number; weight_kg: number }[]

/** The sets of the first exercise of a workout, as the API stores them. */
async function storedSets(id: number): Promise<Sets> {
  const { body } = await api(page, 'GET', `/workouts/${id}`)
  return (body as { exercises: { sets: Sets }[] }).exercises[0].sets
}

function tab(name: string): Locator {
  return page.getByRole('navigation').getByRole('button', { name, exact: true })
}

function weightField(index: number): Locator {
  return page.getByLabel('Weight (lb)').nth(index)
}

async function openTheWorkout() {
  await tab('Workouts').click()
  await page.locator('.workout-card').first().click()
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage()
  page.on('dialog', (dialog) => void dialog.accept())
})

test.afterAll(async () => {
  await deleteEverything(page)
  await page.close()
})

test('a workout saved in kg, through the API', async () => {
  await signUp(page)
  const { body: bench } = await api(page, 'POST', '/exercises', { name: 'E2E Bench' })
  const { status, body } = await api(page, 'POST', '/workouts', {
    performed_on: '2026-11-10',
    exercises: [
      {
        exercise_id: (bench as { id: number }).id,
        sets: [
          { reps: 8, weight_kg: 60 },
          { reps: 10, weight_kg: 0 },
        ],
      },
    ],
  })

  expect(status).toBe(201)
  workoutId = (body as { id: number }).id
})

test('choosing pounds in Profile lasts across a reload', async () => {
  await tab('Profile').click()
  await page.getByLabel('Weights in').selectOption('lb')
  await page.reload()
  await tab('Profile').click()

  await expect(page.getByLabel('Weights in')).toHaveValue('lb')
})

test('shows a weight saved in kg in lb', async () => {
  await openTheWorkout()

  const sets = page.locator('.workout-exercise .sets li')
  await expect(sets.nth(0)).toHaveText(/^8 × 132[.,]28 lb$/)
  await expect(sets.nth(1)).toHaveText('10 × bodyweight')
  await page.screenshot({ path: `${SHOTS}/5-lb-workout.png`, fullPage: true })
})

test('saving without changes keeps the saved kilograms exactly', async () => {
  await page.getByRole('button', { name: 'Edit' }).click()
  await expect(weightField(0)).toHaveValue('132.28')
  await expect(weightField(1)).toHaveValue('0')

  await page.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByRole('button', { name: '‹ Back to workouts' })).toBeVisible()
  // 132.28 lb on its own would be 60.001 kg
  expect(await storedSets(workoutId)).toEqual([
    { reps: 8, weight_kg: 60 },
    { reps: 10, weight_kg: 0 },
  ])
})

test('the plate buttons move by 2.5 lb and never below 0', async () => {
  await page.getByRole('button', { name: 'Edit' }).click()
  const decrease = (set: number) =>
    page.getByRole('button', { name: `Decrease the weight of set ${set} of exercise 1 by 2.5 lb` })
  const increase = (set: number) =>
    page.getByRole('button', { name: `Increase the weight of set ${set} of exercise 1 by 2.5 lb` })

  await increase(1).click()
  await expect(weightField(0)).toHaveValue('134.78')
  // The bodyweight set: nothing to take away
  await expect(decrease(2)).toBeDisabled()
  await increase(2).click()
  await expect(weightField(1)).toHaveValue('2.5')
  await decrease(2).click()
  await expect(weightField(1)).toHaveValue('0')
  await page.screenshot({ path: `${SHOTS}/6-lb-editor.png`, fullPage: true })

  await page.getByRole('button', { name: 'Save' }).click()

  await expect(page.locator('.workout-exercise .sets li').nth(0)).toHaveText(/^8 × 134[.,]78 lb$/)
  // 134.78 lb = 61.1352 kg, kept to the gram; 0 stays 0
  expect(await storedSets(workoutId)).toEqual([
    { reps: 8, weight_kg: 61.135 },
    { reps: 10, weight_kg: 0 },
  ])
})

test('a typed 61 lb is valid for the browser too, and saved to the gram', async () => {
  await page.getByRole('button', { name: 'Edit' }).click()
  await weightField(0).fill('61')

  // step="any": with step="2.5" the browser would mark 61 as :invalid
  expect(await weightField(0).evaluate((input: HTMLInputElement) => input.validity.valid)).toBe(true)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.screenshot({ path: `${SHOTS}/7-lb-editor-phone.png`, fullPage: true })
  await page.setViewportSize({ width: 1280, height: 720 })
  await page.getByRole('button', { name: 'Save' }).click()

  await expect(page.locator('.workout-exercise .sets li').nth(0)).toHaveText('8 × 61 lb')
  expect((await storedSets(workoutId))[0]).toEqual({ reps: 8, weight_kg: 27.669 })
})

test('a program planned in lb is stored in kg and starts a workout in lb', async () => {
  await tab('Programs').click()
  await page.getByRole('button', { name: 'New program' }).click()
  await page.getByLabel('Name', { exact: true }).first().fill('E2E Pounds')
  const day = page.locator('fieldset.exercise-block').first()
  await day.getByLabel('Name', { exact: true }).fill('Heavy')
  const row = day.locator('.planned').first()
  await row.locator('select').selectOption({ label: 'E2E Bench' })
  await row.getByLabel('Sets').fill('3')
  await row.getByLabel('Reps').fill('5')
  await row.getByLabel('Weight (lb)').fill('135')

  await page.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByText('E2E Bench: 3 × 5 × 135 lb')).toBeVisible()
  const { body: programs } = await api(page, 'GET', '/programs')
  const programId = (programs as { id: number }[])[0].id
  const { body: program } = await api(page, 'GET', `/programs/${programId}`)
  // 135 lb = 61.2350 kg
  expect((program as { days: { exercises: { weight_kg: number }[] }[] }).days[0].exercises[0].weight_kg).toBe(61.235)

  await page.getByRole('button', { name: 'Start a workout from day 1, Heavy' }).click()

  await expect(page.locator('.workout-exercise .sets li')).toHaveText(Array(3).fill('5 × 135 lb'))
})

test('back to kg, the same weights show in kg', async () => {
  await tab('Profile').click()
  await page.getByLabel('Weights in').selectOption('kg')
  await tab('Programs').click()
  await page.locator('.workout-card', { hasText: 'E2E Pounds' }).click()

  await expect(page.getByText(/^E2E Bench: 3 × 5 × 61[.,]2[34] kg$/)).toBeVisible()
})
