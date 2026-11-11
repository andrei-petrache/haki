/**
 * The language, end to end: a Romanian browser gets Romanian, a choice in
 * Profile wins over the browser and lasts across a reload. Short on
 * purpose; the other files run in English (see playwright.config.ts).
 */
import { randomBytes } from 'node:crypto'
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { SHOTS, deleteEverything } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page

function tab(name: string): Locator {
  return page.getByRole('navigation').getByRole('button', { name, exact: true })
}

/**
 * A weight input wide enough to type "102,5" into (72 px or more), whose
 * label's text fits on one line.
 */
async function expectRoomyWeight(input: Locator) {
  const box = await input.boundingBox()
  expect(box, 'weight input').not.toBeNull()
  expect(box!.width, 'weight input width').toBeGreaterThanOrEqual(72)
  const lines = await input.evaluate((element) => {
    const text = element.closest('label')?.firstChild
    if (!text) return 0
    const range = document.createRange()
    range.selectNodeContents(text)
    return new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size
  })
  expect(lines, 'weight label lines').toBe(1)
}

/** The labels' texts in a row of fields do not touch or overlap. */
async function expectLabelsApart(row: Locator) {
  const edges = await row.evaluate((element) =>
    [...element.querySelectorAll('label')].map((label) => {
      const range = document.createRange()
      range.selectNodeContents(label.firstChild ?? label)
      const rect = range.getBoundingClientRect()
      return { left: rect.left, right: rect.right }
    }),
  )
  for (let i = 1; i < edges.length; i++) {
    expect(edges[i].left, `label ${i + 1} starts after label ${i} ends`).toBeGreaterThan(edges[i - 1].right)
  }
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ locale: 'ro-RO' })
})

test.afterAll(async () => {
  await deleteEverything(page)
  await page.close()
})

test('a Romanian browser gets the app in Romanian, signing up included', async () => {
  await page.goto('/')
  await expect(page.locator('html')).toHaveAttribute('lang', 'ro')
  await expect(page.getByRole('heading', { name: 'Bine ai revenit' })).toBeVisible()

  await page.getByRole('button', { name: 'Ești nou? Fă-ți un cont' }).click()
  await page.getByLabel('Email').fill(`e2e-${Date.now()}-${randomBytes(3).toString('hex')}@example.com`)
  await page.getByLabel('Parolă').fill(randomBytes(16).toString('hex'))
  await page.getByRole('button', { name: 'Creează contul' }).click()

  await expect(page.getByRole('button', { name: 'Ieși' })).toBeVisible()
  for (const name of ['Azi', 'Alimente', 'Antrenamente', 'Programe', 'Profil']) {
    await expect(tab(name)).toBeVisible()
  }
})

test('the header fits a phone in Romanian', async () => {
  await page.setViewportSize({ width: 390, height: 844 })
  await tab('Profil').click()

  // Every tab on screen, none cut off or pushed out, all on one row
  const tops = new Set<number>()
  for (const name of ['Azi', 'Alimente', 'Antrenamente', 'Programe', 'Profil']) {
    const box = await tab(name).boundingBox()
    expect(box, name).not.toBeNull()
    expect(box!.x, name).toBeGreaterThanOrEqual(0)
    expect(box!.x + box!.width, name).toBeLessThanOrEqual(390)
    tops.add(Math.round(box!.y))
  }
  expect(tops.size, 'tabs on one row').toBe(1)
  const pageWidth = await page.evaluate(() => document.documentElement.scrollWidth)
  expect(pageWidth).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/8-ro-profile-phone.png`, fullPage: true })
  await page.setViewportSize({ width: 1280, height: 720 })
})

test('Foods and Today in Romanian fit a phone', async () => {
  await page.setViewportSize({ width: 390, height: 844 })

  await tab('Alimente').click()
  await expect(page.getByRole('heading', { name: 'Adaugă un aliment' })).toBeVisible()
  await expect(page.getByLabel('Carbohidrați (g)')).toBeVisible()
  await expect(page.getByText('Niciun aliment încă. Adaugă-l pe primul mai sus.')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/9-ro-foods-phone.png`, fullPage: true })

  await tab('Azi').click()
  await expect(page.getByText('kcal mâncate')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Mergi la Alimente' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Ziua de dinainte' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/10-ro-today-phone.png`, fullPage: true })

  await page.setViewportSize({ width: 1280, height: 720 })
  await tab('Profil').click()
})

test('the workout editor in Romanian fits a phone', async () => {
  await page.setViewportSize({ width: 390, height: 844 })
  await tab('Antrenamente').click()
  await expect(page.getByText('Niciun antrenament încă')).toBeVisible()

  await page.getByRole('button', { name: 'Antrenament nou' }).click()

  await expect(page.getByRole('heading', { name: 'Antrenament nou' })).toBeVisible()
  await expect(page.getByText('Exercițiul 1')).toBeVisible()
  await expect(page.getByLabel('Repetări')).toBeVisible()
  await expect(page.getByLabel('Greutate (kg)')).toBeVisible()
  // The step in Romanian, with a decimal comma
  await expect(
    page.getByRole('button', { name: 'Crește greutatea la setul 1 din exercițiul 1 cu 1,25 kg' }),
  ).toBeVisible()
  // Room to type a weight, and its label on one line
  await expectRoomyWeight(page.getByLabel('Greutate (kg)'))
  await expectLabelsApart(page.locator('.set-row').first())
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/11-ro-workout-editor-phone.png`, fullPage: true })

  // Validation, made outside the components, follows the language too
  await page.getByRole('button', { name: 'Salvează' }).click()
  await expect(page.getByText('Scrie numele exercițiului nou')).toBeVisible()
  await expect(page.getByText('Scrie repetările')).toBeVisible()

  await page.getByRole('button', { name: 'Renunță' }).click()
  await page.setViewportSize({ width: 1280, height: 720 })
  await tab('Profil').click()
})

test('the program editor in Romanian fits a phone', async () => {
  await page.setViewportSize({ width: 390, height: 844 })
  await tab('Programe').click()
  await expect(page.getByText('Niciun program încă')).toBeVisible()

  await page.getByRole('button', { name: 'Program nou' }).click()

  await expect(page.getByRole('heading', { name: 'Program nou' })).toBeVisible()
  await expect(page.locator('legend', { hasText: 'Ziua 1' })).toBeVisible()
  await expect(page.getByLabel('Seturi')).toBeVisible()
  await expectRoomyWeight(page.getByLabel('Greutate (kg)'))
  await expectLabelsApart(page.locator('.planned-row').first())
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/12-ro-program-editor-phone.png`, fullPage: true })

  await page.getByRole('button', { name: 'Renunță' }).click()
  await page.setViewportSize({ width: 1280, height: 720 })
  await tab('Profil').click()
})

test('choosing English in Profile wins over the browser, across a reload', async () => {
  await expect(page.getByLabel('Limba')).toHaveValue('auto')

  await page.getByLabel('Limba').selectOption('en')

  await expect(tab('Today')).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  await page.reload()
  await expect(tab('Today')).toBeVisible()
  await tab('Profile').click()
  await expect(page.getByLabel('Language')).toHaveValue('en')
})

test('going back to the browser language gives Romanian again', async () => {
  await page.getByLabel('Language').selectOption('auto')

  await expect(tab('Azi')).toBeVisible()
  await expect(page.getByLabel('Limba').locator('option[value="auto"]')).toHaveText(
    'Ca în browser (Română)',
  )
})
