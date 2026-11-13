/**
 * Onboarding on a 390 px phone: signing up leads to four short steps
 * (units, a daily target, a first food, a first set) and then Today, well
 * under a minute; an existing account never sees them.
 */
import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { SHOTS, api, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page

test.afterAll(async () => {
  await page?.close()
})

test('a new account: units, target, a food and a first set, then Today, in under a minute', async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 }, locale: 'en-US' })
  await page.goto('/')
  const started = Date.now()
  await page.getByRole('button', { name: 'New here? Create an account' }).click()
  await page.getByLabel('Email').fill(`e2e-${Date.now()}-${randomBytes(3).toString('hex')}@example.com`)
  await page.getByLabel('Password').fill(randomBytes(12).toString('hex'))
  await page.getByRole('button', { name: 'Sign up', exact: true }).click()

  const setup = page.locator('section.onboarding')
  await expect(setup).toContainText('Step 1 of 4')
  // No tabs during the setup: they would lead nowhere yet
  await expect(page.getByRole('navigation')).toHaveCount(0)
  await setup.getByRole('button', { name: 'Pounds (lb)' }).click()
  await setup.getByRole('button', { name: 'Next' }).click()

  await expect(setup).toContainText('Step 2 of 4')
  await setup.getByRole('button', { name: '2200 kcal' }).click()

  await expect(setup).toContainText('Step 3 of 4')
  await setup.getByLabel('Search the catalog').fill('oats')
  await setup.getByRole('button', { name: /^Add Oats/ }).first().click()
  await expect(setup.getByRole('status')).toContainText('to your foods')
  await setup.getByRole('button', { name: 'Next' }).click()

  await expect(setup).toContainText('Step 4 of 4')
  await setup.getByRole('button', { name: 'From the catalog' }).click()
  await setup.getByLabel('Search the catalog').fill('bench press')
  await setup.locator('.catalog-panel li, .catalog-inline li').first().getByRole('button').first().click()
  await setup.getByLabel('Reps').fill('5')
  await setup.getByLabel('Weight (lb)').fill('135')
  await page.screenshot({ path: `${SHOTS}/80-onboarding-set-phone.png`, fullPage: true })
  await setup.getByRole('button', { name: 'Log it and finish' }).click()

  // Today, with the chosen target; everything saved
  await expect(setup).toHaveCount(0)
  await expect(page.getByPlaceholder('Search a food')).toBeVisible()
  await expect(page.getByRole('navigation').getByRole('button')).toHaveCount(5)
  expect(Date.now() - started).toBeLessThan(60_000)
  const me = (await api(page, 'GET', '/auth/me')).body as { daily_calorie_target: number }
  expect(me.daily_calorie_target).toBe(2200)
  expect(((await api(page, 'GET', '/foods')).body as unknown[]).length).toBe(1)
  const workouts = (await api(page, 'GET', '/workouts')).body as { id: number }[]
  expect(workouts).toHaveLength(1)
  const workout = (await api(page, 'GET', `/workouts/${workouts[0].id}`)).body as {
    exercises: { sets: { reps: number; weight_kg: number }[] }[]
  }
  expect(workout.exercises[0].sets[0].reps).toBe(5)
  expect(workout.exercises[0].sets[0].weight_kg).toBeCloseTo(61.235, 2)
  expect(await page.evaluate(() => localStorage.getItem('haki_weight_unit'))).toBe('lb')

  // A reload does not bring the setup back
  await page.reload()
  await expect(page.getByPlaceholder('Search a food')).toBeVisible()
  await expect(page.locator('section.onboarding')).toHaveCount(0)
})

test('an existing account goes straight to Today', async ({ browser }) => {
  const other = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await signUp(other)
  await expect(other.getByPlaceholder('Search a food')).toBeVisible()
  await expect(other.locator('section.onboarding')).toHaveCount(0)
  await other.close()
})
