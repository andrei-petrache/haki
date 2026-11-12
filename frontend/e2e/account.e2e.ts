/**
 * The account in Profile: changing the password. A wrong current password
 * is refused without logging out; afterwards this tab keeps going with the
 * new token, the old token is refused, and the new password logs in.
 */
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { SHOTS, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page
let account: { email: string; password: string }

function tab(name: string): Locator {
  return page.getByRole('navigation').getByRole('button', { name, exact: true })
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  account = await signUp(page)
})

test.afterAll(async () => {
  await page.close()
})

test('change the password: checked here first, then by the server', async () => {
  await tab('Profile').click()
  await page.getByRole('button', { name: 'Change password' }).click()
  const form = page.getByRole('form', { name: 'Change password' })

  // Checked in the browser, before any request
  await form.getByLabel('Current password').fill(account.password)
  await form.getByLabel('New password', { exact: true }).fill('a-new-secret-1')
  await form.getByLabel('New password again').fill('a-new-secret-2')
  await form.getByRole('button', { name: 'Change password' }).click()
  await expect(form).toContainText('The two new passwords are not the same.')

  // Wrong current password: refused, and the session stays
  await form.getByLabel('Current password').fill('not-the-password')
  await form.getByLabel('New password again').fill('a-new-secret-1')
  await form.getByRole('button', { name: 'Change password' }).click()
  await expect(form).toContainText('The current password is wrong.')
  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/25-change-password-phone.png`, fullPage: true })

  const oldToken = await page.evaluate(() => localStorage.getItem('haki_token'))
  await form.getByLabel('Current password').fill(account.password)
  await form.getByRole('button', { name: 'Change password' }).click()
  await expect(page.getByRole('status')).toContainText('Password changed.')
  await expect(form).toHaveCount(0)

  // This tab carries on with the new token, across a reload; the old one,
  // like every other device's, is refused
  const newToken = await page.evaluate(() => localStorage.getItem('haki_token'))
  expect(newToken).not.toBe(oldToken)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()
  const me = (value: string | null) =>
    page.request.get('/api/auth/me', { headers: { Authorization: `Bearer ${value}` } })
  expect((await me(oldToken)).status()).toBe(401)
  expect((await me(newToken)).status()).toBe(200)

  // The new password logs in, the old one no longer does
  const login = (password: string) =>
    page.request.post('/api/auth/login', { data: { email: account.email, password } })
  expect((await login('a-new-secret-1')).status()).toBe(200)
  expect((await login(account.password)).status()).toBe(401)
})
