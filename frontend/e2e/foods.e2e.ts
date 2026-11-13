/**
 * Your foods in direction A, on a 390 px phone: the list first with a
 * filter, "New food" in a panel, a tap on a row to edit, and Delete with
 * Undo instead of the browser's confirm (a food in the diary says why it
 * cannot go).
 */
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { SHOTS, api, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page
let dialogs = 0

function list(): Locator {
  return page.locator('.food-list')
}

function row(name: string): Locator {
  return list().locator('li', { hasText: name })
}

// The row being edited: a form, whose name is a field's value, not text
function editing(): Locator {
  return list().locator('li.food-editing form')
}

async function food(name: string, calories: number): Promise<number> {
  const created = await api(page, 'POST', '/foods', {
    name,
    calories_per_100g: calories,
    protein_per_100g: 1,
    carbs_per_100g: 2,
    fat_per_100g: 3,
  })
  expect(created.status).toBe(201)
  return (created.body as { id: number }).id
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  page.on('dialog', (dialog) => {
    dialogs += 1
    void dialog.dismiss()
  })
  await signUp(page)
  await food('Iaurt grecesc', 97)
  await food('Brânză de vaci', 98)
  const oats = await food('Oats', 379)
  const today = new Date().toISOString().slice(0, 10)
  const entry = await api(page, 'POST', '/entries', { food_id: oats, eaten_on: today, meal_type: 'breakfast', grams: 60 })
  expect(entry.status).toBe(201)
  await page.getByRole('navigation').getByRole('button', { name: 'Foods', exact: true }).click()
  await expect(row('Oats')).toBeVisible()
})

test.afterAll(async () => {
  await page.close()
})

test('the list comes first, filtered while typing, diacritics or not', async () => {
  // The list starts on the first screen, under the filter and two buttons
  const first = await list().locator('li').first().boundingBox()
  expect(first!.y + first!.height).toBeLessThan(844 - 80)
  await expect(page.getByLabel('Name')).toHaveCount(0)

  const filter = page.getByPlaceholder('Filter your foods')
  await filter.fill('branza')
  await expect(list().locator('li')).toHaveCount(1)
  await expect(row('Brânză de vaci')).toBeVisible()
  await filter.fill('zzz')
  await expect(page.getByText('None of your foods matches "zzz".')).toBeVisible()
  await filter.fill('')
  await expect(list().locator('li')).toHaveCount(3)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/40-foods-phone.png`, fullPage: true })
})

test('New food opens a panel; adding closes it and says so', async () => {
  await page.getByRole('button', { name: '+ New food' }).click()
  await expect(page.getByRole('button', { name: '+ New food' })).toHaveAttribute('aria-expanded', 'true')
  const form = page.locator('.panel form')
  await form.getByLabel('Name').fill('Zacuscă')
  await form.getByLabel('Calories (kcal)').fill('120')
  await form.getByLabel('Protein (g)').fill('2')
  await form.getByLabel('Carbs (g)').fill('9')
  await form.getByLabel('Fat (g)').fill('8')
  await form.getByRole('button', { name: 'Add food' }).click()
  await expect(page.getByRole('status')).toHaveText('Added Zacuscă to your foods.')
  await expect(page.locator('.panel')).toHaveCount(0)
  await expect(row('Zacuscă')).toContainText('120 kcal')
})

test('a tap on a row edits it; Delete has Undo and no dialog', async () => {
  await row('Iaurt grecesc').getByRole('button', { name: /^Edit/ }).click()
  await expect(editing().getByLabel('Name')).toHaveValue('Iaurt grecesc')
  await editing().getByRole('button', { name: 'Delete' }).click()

  await expect(row('Iaurt grecesc')).toHaveCount(0)
  await expect(page.getByRole('status')).toHaveText(/Deleted Iaurt grecesc\./)
  await page.getByRole('status').getByRole('button', { name: 'Undo' }).click()
  await expect(row('Iaurt grecesc')).toBeVisible()

  // Without Undo the deletion goes once the message does
  await row('Iaurt grecesc').getByRole('button', { name: /^Edit/ }).click()
  await editing().getByRole('button', { name: 'Delete' }).click()
  await expect(page.getByRole('status')).toHaveCount(0, { timeout: 12_000 })
  await expect
    .poll(async () => ((await api(page, 'GET', '/foods')).body as { name: string }[]).map((f) => f.name))
    .not.toContain('Iaurt grecesc')
  expect(dialogs).toBe(0)
})

test('a deletion still waiting goes even when the page reloads', async () => {
  await row('Zacuscă').getByRole('button', { name: /^Edit/ }).click()
  await editing().getByRole('button', { name: 'Delete' }).click()
  await expect(page.getByRole('status')).toHaveText(/Deleted Zacuscă\./)
  await page.reload()
  await expect
    .poll(async () => ((await api(page, 'GET', '/foods')).body as { name: string }[]).map((f) => f.name))
    .not.toContain('Zacuscă')
  await page.getByRole('navigation').getByRole('button', { name: 'Foods', exact: true }).click()
  await expect(row('Oats')).toBeVisible()
  await expect(row('Zacuscă')).toHaveCount(0)
})

test('a food in the diary says it cannot be deleted', async () => {
  await row('Oats').getByRole('button', { name: /^Edit/ }).click()
  const form = editing()
  await expect(form.getByText('In your diary, so it cannot be deleted.')).toBeVisible()
  await expect(form.getByRole('button', { name: 'Delete' })).toHaveCount(0)
  await form.getByRole('button', { name: 'Cancel' }).click()
})
