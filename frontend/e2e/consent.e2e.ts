/**
 * The health data consent on a 390 px phone: body weight is behind it. A
 * new account sees the consent's exact text where the weight goes, can put
 * it off or agree; Profile says since when and withdraws it after a
 * warning (and a way to download everything first), which deletes the
 * weigh-ins at once and brings the text back.
 */
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { SHOTS, api, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page

function nav(name: string): Locator {
  return page.getByRole('navigation').getByRole('button', { name, exact: true })
}

function today(): string {
  const date = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await signUp(page)
})

test.afterAll(async () => {
  await page.close()
})

test('without consent: the text where the weight goes, the API refuses weights', async () => {
  const card = page.locator('section.consent-card')
  await expect(card.getByRole('heading', { name: 'Your body weight and the adaptive calorie target' })).toBeVisible()
  await expect(card).toContainText('I am 16 or older')
  await expect(card).toContainText('I can withdraw this consent at any time in Profile.')
  await expect(page.locator('section.weight-card')).toHaveCount(0)
  // Not a logout: the app goes on, the API answers 403 consent_required
  const refused = await api(page, 'PUT', `/weights/${today()}`, { weight_kg: 80 })
  expect(refused.status).toBe(403)
  expect((refused.body as { code: string }).code).toBe('consent_required')
  await card.scrollIntoViewIfNeeded()
  await page.screenshot({ path: `${SHOTS}/60-consent-card-phone.png`, fullPage: true })

  // "Not now": one line for this visit, the text one tap away
  await card.getByRole('button', { name: 'Not now' }).click()
  await expect(card).toHaveCount(0)
  await page.locator('section.weight-later').getByRole('button', { name: 'Read the consent ›' }).click()
  await expect(page.locator('section.consent-card')).toBeVisible()
})

test('"I agree": the weight card, and Profile says since when', async () => {
  await page.locator('section.consent-card').getByRole('button', { name: 'I agree' }).click()
  const weight = page.locator('section.weight-card')
  await expect(weight.getByLabel('Weight (kg)')).toBeVisible()
  await weight.getByLabel('Weight (kg)').fill('80.5')
  await weight.getByRole('button', { name: 'Save weight' }).click()
  await expect(weight.getByRole('status')).toContainText('Saved 80.5 kg')

  const status = (await api(page, 'GET', '/auth/me/consents/health_data')).body as { valid: boolean; given_version: string }
  expect(status.valid).toBe(true)
  await nav('Profile').click()
  const profile = page.locator('.consent-profile')
  await expect(profile.getByRole('heading', { name: 'Health data consent' })).toBeVisible()
  await expect(profile).toContainText(/Given on \d{1,2} \w+ \d{4}\./)
})

test('withdrawing: a warning and the export first, then the weigh-ins are gone', async () => {
  const profile = page.locator('.consent-profile')
  await profile.getByRole('button', { name: 'Withdraw consent' }).click()
  const step = profile.getByRole('group', { name: 'Withdraw the health data consent' })
  await expect(step).toContainText('This deletes all your weigh-ins and estimates at once')
  await expect(step.getByRole('button', { name: 'Download my data' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/61-consent-withdraw-phone.png`, fullPage: true })

  await step.getByRole('button', { name: 'Withdraw and delete my weigh-ins' }).click()
  await expect(profile.getByRole('status')).toHaveText('Consent withdrawn; your weigh-ins and estimates are deleted.')
  await expect(profile).toContainText('Not given.')

  // Gone on the server, the target back to manual, the text back on Today
  const me = (await api(page, 'GET', '/auth/me')).body as { target_mode: string }
  expect(me.target_mode).toBe('manual')
  expect((await api(page, 'GET', '/weights')).status).toBe(403)
  await nav('Today').click()
  await expect(page.locator('section.consent-card')).toBeVisible()
})
