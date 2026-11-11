/**
 * The catalog, loaded into the throwaway stack by the backend's import
 * command (scripts/e2e.sh): credits here; searching and picking follow.
 */
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { SHOTS, deleteEverything, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page

function tab(name: string): Locator {
  return page.getByRole('navigation').getByRole('button', { name, exact: true })
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await signUp(page)
})

test.afterAll(async () => {
  await deleteEverything(page)
  await page.close()
})

test('Credits lists the catalog sources with licence and version', async () => {
  await tab('Profile').click()
  await page.getByRole('button', { name: 'Credits: where the catalog comes from' }).click()

  await expect(page.getByRole('heading', { name: 'Credits' })).toBeVisible()
  const usda = page.locator('.credit', { hasText: 'USDA FoodData Central' })
  await expect(usda).toContainText('CC0-1.0')
  await expect(usda).toContainText('2018-04')
  const exercises = page.locator('.credit', { hasText: 'Free Exercise DB' })
  await expect(exercises).toContainText('Unlicense')
  await expect(page.getByRole('link', { name: 'Free Exercise DB' })).toHaveAttribute(
    'href',
    'https://github.com/yuhonas/free-exercise-db',
  )
  // Neither licence requires an on-screen attribution today
  await expect(page.locator('.attribution')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/16-credits-phone.png`, fullPage: true })

  await page.getByRole('button', { name: '‹ Back to profile' }).click()
  await expect(page.getByLabel('Weights in')).toBeVisible()
})
