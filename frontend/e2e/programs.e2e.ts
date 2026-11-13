/**
 * Programs end to end, in a real browser against a throwaway stack: plan,
 * list, detail, start a workout from a day, delete. One account for the
 * whole file (login and signup are rate limited); everything it created is
 * deleted through the API at the end, and the stack is thrown away after.
 */
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import * as session from './helpers'
import { SHOTS } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page

/** The shared helpers, on this file's page. */
function api(method: string, path: string) {
  return session.api(page, method, path)
}

function ids(path: string) {
  return session.ids(page, path)
}

function dayBlock(index: number): Locator {
  return page.locator('fieldset.exercise-block').nth(index)
}

/** A day's place in the plan: its first select (a select's accessible name includes its chosen option). */
function daySelect(day: Locator): Locator {
  return day.locator('select').first()
}

/** Fill one planned exercise of a day: a catalog name or a new one, then the numbers. */
async function plan(
  day: Locator,
  index: number,
  exercise: { pick?: string; create?: string },
  sets: string,
  reps: string,
  weight: string,
) {
  const row = day.locator('.planned').nth(index)
  // Not getByLabel: a select's accessible name includes its chosen option
  if (exercise.create) {
    await row.locator('select').selectOption({ label: 'New exercise…' })
    await row.getByLabel('New exercise name').fill(exercise.create)
  } else if (exercise.pick) {
    await row.locator('select').selectOption({ label: exercise.pick })
  }
  await row.getByLabel('Sets').fill(sets)
  await row.getByLabel('Reps').fill(reps)
  await row.getByLabel('Weight (kg)').fill(weight)
}

function tab(name: string): Locator {
  return page.getByRole('navigation').getByRole('button', { name, exact: true })
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage()
  // Delete asks for confirmation: accept it
  page.on('dialog', (dialog) => void dialog.accept())
})

test.afterAll(async () => {
  await session.deleteEverything(page)
  await page.close()
})

test('sign up a fresh test account', async () => {
  await session.signUp(page)
})

test('starts with no programs', async () => {
  await tab('Programs').click()

  await expect(page.getByText('No programs yet')).toBeVisible()
})

test('shows what is missing before sending anything', async () => {
  await page.getByRole('button', { name: 'New program' }).click()
  await page.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByText('Enter a name for the program')).toBeVisible()
  await expect(page.getByText('Enter a name for the day')).toBeVisible()
  await expect(page.getByText('Enter the new exercise name')).toBeVisible()
  await expect(page.getByText('Enter the sets')).toBeVisible()
  expect(await ids('/programs')).toEqual([])
})

test('creates a two-day program with new exercises', async () => {
  await page.getByLabel('Name', { exact: true }).first().fill('E2E Push/Pull')
  // Each error goes away as soon as its field is changed, before any Save
  await expect(page.getByText('Enter a name for the program')).toBeHidden()
  await expect(page.getByText('Enter a name for the day')).toBeVisible()
  const push = dayBlock(0)
  await push.getByLabel('Name', { exact: true }).fill('Push')
  await expect(page.getByText('Enter a name for the day')).toBeHidden()
  await plan(push, 0, { create: 'E2E Bench' }, '3', '8', '60')
  await expect(page.getByText('Enter the new exercise name')).toBeHidden()
  await expect(page.getByText('Enter the sets')).toBeHidden()
  await push.getByRole('button', { name: '+ Add exercise' }).click()
  await plan(push, 1, { create: 'E2E Dips' }, '3', '10', '0')

  await page.getByRole('button', { name: 'Add day' }).click()
  const pull = dayBlock(1)
  // The first free place in the plan
  await expect(daySelect(pull)).toHaveValue('2')
  await pull.getByLabel('Name', { exact: true }).fill('Pull')
  await plan(pull, 0, { create: 'E2E Row' }, '4', '10', '52.5')
  await page.screenshot({ path: `${SHOTS}/3-editor.png`, fullPage: true })

  await page.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByRole('heading', { name: 'E2E Push/Pull' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Day 1 · Push' })).toBeVisible()
  await expect(page.getByText('E2E Bench: 3 × 8 × 60 kg')).toBeVisible()
  await expect(page.getByText('E2E Dips: 3 × 10 × bodyweight')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Day 2 · Pull' })).toBeVisible()
  await expect(page.getByText(/^E2E Row: 4 × 10 × 52[.,]5 kg$/)).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/2-detail.png`, fullPage: true })
})

test('reuses a catalog exercise in a second program', async () => {
  await page.getByRole('button', { name: '‹ Back to programs' }).click()
  await page.getByRole('button', { name: 'New program' }).click()
  await page.getByLabel('Name', { exact: true }).first().fill('E2E Full body')
  await daySelect(dayBlock(0)).selectOption('3')
  await dayBlock(0).getByLabel('Name', { exact: true }).fill('Full')
  await plan(dayBlock(0), 0, { pick: 'E2E Bench' }, '5', '5', '70')

  await page.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByRole('heading', { name: 'Day 3 · Full' })).toBeVisible()
  // No second "E2E Bench" in the catalog
  const { body } = await api('GET', '/exercises')
  expect((body as { name: string }[]).map((item) => item.name)).toEqual([
    'E2E Bench',
    'E2E Dips',
    'E2E Row',
  ])
})

test('lists the programs by name with their day counts', async () => {
  await page.getByRole('button', { name: '‹ Back to programs' }).click()

  const cards = page.locator('.workout-card')
  await expect(cards).toHaveCount(2)
  await expect(cards.nth(0)).toContainText('E2E Full body')
  await expect(cards.nth(0)).toContainText('1 day')
  await expect(cards.nth(1)).toContainText('E2E Push/Pull')
  await expect(cards.nth(1)).toContainText('2 days')
  await page.screenshot({ path: `${SHOTS}/1-list.png`, fullPage: true })
})

test('refuses a duplicate name, ignoring case, next to the name', async () => {
  await page.getByRole('button', { name: 'New program' }).click()
  await page.getByLabel('Name', { exact: true }).first().fill(' e2e push/pull ')
  await dayBlock(0).getByLabel('Name', { exact: true }).fill('Again')
  await plan(dayBlock(0), 0, { pick: 'E2E Bench' }, '1', '1', '0')

  await page.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByText('You already have a program with this name')).toBeVisible()
  expect(await ids('/programs')).toHaveLength(2)
  await page.getByLabel('Name', { exact: true }).first().fill('E2E Push/Pull 2')
  await expect(page.getByText('You already have a program with this name')).toBeHidden()
  await page.getByRole('button', { name: 'Cancel' }).click()
})

test('starts a workout from a day, with the planned sets copied', async () => {
  await page.locator('.workout-card', { hasText: 'E2E Push/Pull' }).click()

  await page.getByRole('button', { name: 'Start a workout from day 1, Push' }).click()

  // Straight to the new workout, in the Workouts tab
  await expect(tab('Workouts')).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('button', { name: '‹ Back to workouts' })).toBeVisible()
  const bench = page.locator('.workout-exercise', { hasText: 'E2E Bench' })
  await expect(bench.locator('.sets li')).toHaveText(Array(3).fill('8 × 60 kg'))
  const dips = page.locator('.workout-exercise', { hasText: 'E2E Dips' })
  await expect(dips.locator('.sets li')).toHaveText(Array(3).fill('10 × bodyweight'))
  await expect(page.locator('.workout-exercise')).toHaveCount(2)
  await page.screenshot({ path: `${SHOTS}/4-started-workout.png`, fullPage: true })
  expect(await ids('/workouts')).toHaveLength(1)
})

test('keeps an exercise a program uses from being deleted (409)', async () => {
  const { body } = await api('GET', '/exercises')
  const row = (body as { id: number; name: string }[]).find((item) => item.name === 'E2E Row')

  const response = await api('DELETE', `/exercises/${row?.id}`)

  // Only the Pull day uses it: no workout does
  expect(response.status).toBe(409)
  expect(response.body).toEqual({ detail: 'Exercise is used by workouts or programs' })
})

test('edits a program in place: renamed, the rest kept exactly', async () => {
  await tab('Programs').click()
  await page.locator('.workout-card', { hasText: 'E2E Full body' }).click()
  const programId = (await api('GET', '/programs')).body as { id: number; name: string }[]
  const id = programId.find((item) => item.name === 'E2E Full body')!.id
  const before = (await api('GET', `/programs/${id}`)).body as {
    days: { id: number; exercises: unknown[] }[]
  }

  await page.getByRole('button', { name: 'Edit' }).click()
  await expect(page.getByRole('heading', { name: 'Edit E2E Full body' })).toBeVisible()
  await page.getByLabel('Name', { exact: true }).first().fill('E2E Full body B')
  await dayBlock(0).getByLabel('Name', { exact: true }).fill('Everything')
  await page.getByRole('button', { name: 'Save' }).click()

  // Back on the program, under its new name, with the same id
  await expect(page.getByRole('heading', { name: 'E2E Full body B' })).toBeVisible()
  await expect(page.getByText('Everything')).toBeVisible()
  const after = (await api('GET', `/programs/${id}`)).body as {
    name: string
    days: { id: number; name: string; exercises: unknown[] }[]
  }
  expect(after.name).toBe('E2E Full body B')
  expect(after.days.map((day) => day.name)).toEqual(['Everything'])
  // The same day, renamed in place: its id (and workouts' link to it) kept
  expect(after.days.map((day) => day.id)).toEqual(before.days.map((day) => day.id))
  // The planned exercises, weights included, come back unchanged
  expect(after.days.map((day) => day.exercises)).toEqual(before.days.map((day) => day.exercises))
  expect(await ids('/programs')).toHaveLength(2)
  await page.screenshot({ path: `${SHOTS}/5-edited-program.png`, fullPage: true })
  // The next test opens the list from the tab, which keeps the current view
  await page.getByRole('button', { name: '‹ Back to programs' }).click()
})

test('deletes a program and keeps the workout started from it', async () => {
  await tab('Programs').click()
  await page.locator('.workout-card', { hasText: 'E2E Push/Pull' }).click()

  await page.getByRole('button', { name: 'Delete' }).click()

  await expect(page.locator('.workout-card')).toHaveCount(1)
  await expect(page.locator('.workout-card')).toContainText('E2E Full body')
  expect(await ids('/workouts')).toHaveLength(1)
})
