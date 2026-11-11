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
