/**
 * Programs end to end, in a real browser against a throwaway stack: plan,
 * list, detail, start a workout from a day, delete. One account for the
 * whole file (login and signup are rate limited); everything it created is
 * deleted through the API at the end, and the stack is thrown away after.
 */
import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'

const SHOTS = `${process.env.E2E_OUT ?? '/tmp/haki-e2e'}/screenshots`
const EMAIL = `e2e-${Date.now()}-${randomBytes(3).toString('hex')}@example.com`
const PASSWORD = randomBytes(16).toString('hex')

test.describe.configure({ mode: 'serial' })

let page: Page

async function token(): Promise<string> {
  const value = await page.evaluate(() => localStorage.getItem('haki_token'))
  if (!value) throw new Error('not logged in')
  return value
}

async function api(method: string, path: string): Promise<{ status: number; body: unknown }> {
  const response = await page.request.fetch(`/api${path}`, {
    method,
    headers: { Authorization: `Bearer ${await token()}` },
  })
  const text = await response.text()
  return { status: response.status(), body: text ? JSON.parse(text) : null }
}

async function ids(path: string): Promise<number[]> {
  const { body } = await api('GET', path)
  return (body as { id: number }[]).map((item) => item.id)
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
  // Leave nothing behind but the account itself, which goes with the stack.
  // Workouts and programs first: an exercise they use cannot be deleted.
  for (const id of await ids('/workouts')) await api('DELETE', `/workouts/${id}`)
  for (const id of await ids('/programs')) await api('DELETE', `/programs/${id}`)
  for (const id of await ids('/exercises')) await api('DELETE', `/exercises/${id}`)

  expect(await ids('/workouts')).toEqual([])
  expect(await ids('/programs')).toEqual([])
  expect(await ids('/exercises')).toEqual([])
  await page.close()
})

test('sign up a fresh test account', async () => {
  await page.goto('/')
  await page.getByRole('button', { name: 'New here? Create an account' }).click()
  await page.getByLabel('Email').fill(EMAIL)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign up' }).click()

  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()
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

test('deletes a program and keeps the workout started from it', async () => {
  await tab('Programs').click()
  await page.locator('.workout-card', { hasText: 'E2E Push/Pull' }).click()

  await page.getByRole('button', { name: 'Delete' }).click()

  await expect(page.locator('.workout-card')).toHaveCount(1)
  await expect(page.locator('.workout-card')).toContainText('E2E Full body')
  expect(await ids('/workouts')).toHaveLength(1)
})
