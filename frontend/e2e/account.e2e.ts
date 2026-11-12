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
  // Still logged in: the tabs show (Log out sits in Profile on a phone)
  await expect(page.getByRole('navigation').getByRole('button').first()).toBeVisible()
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

/**
 * Submit, waiting out Nginx's login budget (5 a minute, shared with
 * signup, login and password changes) like the API helper does: on 429
 * the form says so; wait, then submit again. Returns once anything else
 * happened.
 */
async function submitPatiently(button: Locator, form: Locator) {
  for (let attempt = 0; attempt < 6; attempt++) {
    await button.click()
    const limited = form.locator('.error', { hasText: 'Too many attempts' })
    await page.waitForTimeout(500)
    if (!(await limited.isVisible().catch(() => false))) return
    await page.waitForTimeout(13_000)
  }
}

test('delete the account: a step that names it, the password, and nothing without both', async () => {
  let dialogs = 0
  page.on('dialog', (dialog) => {
    dialogs += 1
    void dialog.dismiss()
  })
  const password = 'a-new-secret-1'
  // The password test reloaded the page, which opens on Today
  await tab('Profile').click()
  await page.getByRole('button', { name: 'Delete account' }).click()
  const step = page.getByRole('form', { name: 'Delete your account' })
  await expect(step).toContainText(account.email)
  await expect(step).toContainText('It cannot be undone.')
  const confirm = step.getByRole('button', { name: 'Delete my account' })
  await expect(confirm).toBeDisabled()

  // A wrong password: refused, nothing deleted, still logged in
  await step.getByLabel('Your password').fill('not-the-password')
  await step.getByRole('checkbox').check()
  await submitPatiently(confirm, step)
  await expect(step).toContainText('The password is wrong. Nothing was deleted.')
  await expect(page.getByRole('navigation')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: `${SHOTS}/40-delete-account-phone.png`, fullPage: true })

  await step.getByLabel('Your password').fill(password)
  await submitPatiently(confirm, step)
  await expect(page.getByRole('status')).toHaveText('Your account and its data were deleted.')
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  expect(dialogs).toBe(0)

  // Gone for good: the login is refused, and the email is free again
  let status = 429
  for (let attempt = 0; attempt < 6 && status === 429; attempt++) {
    if (attempt > 0) await page.waitForTimeout(13_000)
    status = (await page.request.post('/api/auth/login', { data: { email: account.email, password } })).status()
  }
  expect(status).toBe(401)
})
