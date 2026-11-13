/**
 * Trust on a 390 px phone: the data export (password, a whole file, never
 * a link with the token), and the password reset end to end: "Forgot
 * password?", the e-mail as Mailpit keeps it (the e2e stack routes the
 * backend's mail there), the link's token read from the fragment and
 * cleared from the address, a new password, and a link used twice.
 */
import { readFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'
import type { Browser, Locator, Page } from '@playwright/test'
import { SHOTS, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

const MAILPIT = 'http://mailpit:8025'
const PHONE = { width: 390, height: 844 }
let page: Page
let account: { email: string; password: string }

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: PHONE })
  account = await signUp(page)
})

test.afterAll(async () => {
  await page.close()
})

/**
 * Submit, waiting out Nginx's budget (5 a minute, shared by login, signup,
 * the export and the reset): on 429 the form says so; wait, then again.
 */
async function submitPatiently(on: Page, button: Locator, form: Locator) {
  for (let attempt = 0; attempt < 6; attempt++) {
    await button.click()
    await on.waitForTimeout(500)
    const limited = form.locator('.error', { hasText: 'Too many attempts' })
    if (!(await limited.isVisible().catch(() => false))) return
    await on.waitForTimeout(13_000)
  }
}

test('the export: the password first, then the whole account as one file', async () => {
  await page.getByRole('navigation').getByRole('button', { name: 'Profile', exact: true }).click()
  await page.getByRole('button', { name: 'Download my data' }).click()
  const form = page.getByRole('form', { name: 'Download my data' })
  const download = form.getByRole('button', { name: 'Download' })
  await expect(download).toBeDisabled()

  await form.getByLabel('Password').fill('not-the-password')
  await submitPatiently(page, download, form)
  await expect(form).toContainText('The password is wrong.')

  await form.getByLabel('Password').fill(account.password)
  const [file] = await Promise.all([page.waitForEvent('download'), submitPatiently(page, download, form)])
  expect(file.suggestedFilename()).toMatch(/^haki-export-\d{4}-\d{2}-\d{2}\.json$/)
  // From memory, not from a URL that could carry the token
  expect(file.url()).toMatch(/^blob:/)
  const data = JSON.parse(readFileSync((await file.path())!, 'utf8')) as { complete?: boolean }
  expect(data.complete).toBe(true)
  expect(JSON.stringify(data)).toContain(account.email)
  await expect(page.getByRole('status')).toHaveText(`Downloaded ${file.suggestedFilename()}.`)
})

async function resetLink(email: string): Promise<string> {
  // Mailpit keeps the newest message first
  for (let attempt = 0; attempt < 20; attempt++) {
    const list = (await (await page.request.get(`${MAILPIT}/api/v1/messages`)).json()) as {
      messages: { ID: string; To: { Address: string }[] }[]
    }
    const message = list.messages.find((m) => m.To.some((to) => to.Address === email))
    if (message) {
      const full = (await (await page.request.get(`${MAILPIT}/api/v1/message/${message.ID}`)).json()) as { Text: string }
      const link = full.Text.match(/https?:\/\/\S+\/reset#token=\S+/)
      if (link) return link[0]
    }
    await page.waitForTimeout(500)
  }
  throw new Error(`no reset e-mail for ${email}`)
}

async function guestPage(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ viewport: PHONE, locale: 'en-US' })
  return context.newPage()
}

test('the reset: request, the e-mailed link, a new password, logged in', async ({ browser }) => {
  const guest = await guestPage(browser)
  await guest.goto('/')
  await guest.getByRole('button', { name: 'Forgot password?' }).click()
  const forgot = guest.getByRole('form', { name: 'Reset your password' })
  await forgot.getByLabel('Email').fill(account.email)
  await submitPatiently(guest, forgot.getByRole('button', { name: 'Send me a link' }), forgot)
  await expect(guest.getByRole('status')).toContainText('If that e-mail has an account, a reset link is on its way.')

  const link = await resetLink(account.email)
  expect(link).toMatch(/^http:\/\/frontend:8080\/reset#token=/)
  await guest.goto(link)
  // Out of the address bar (and the history entry) before anything else
  await expect(guest.getByRole('heading', { name: 'Choose a new password' })).toBeVisible()
  expect(new URL(guest.url()).hash).toBe('')
  expect(new URL(guest.url()).pathname).toBe('/reset')

  const reset = guest.getByRole('form', { name: 'Choose a new password' })
  await reset.getByLabel('New password', { exact: true }).fill('a-reset-secret-1')
  await reset.getByLabel('New password again').fill('a-reset-secret-2')
  await reset.getByRole('button', { name: 'Save the new password' }).click()
  await expect(reset).toContainText('The two new passwords are not the same.')
  await reset.getByLabel('New password again').fill('a-reset-secret-1')
  await submitPatiently(guest, reset.getByRole('button', { name: 'Save the new password' }), reset)

  // Logged in with the token the reset returned, back on the app's own address
  await expect(guest.getByRole('navigation').getByRole('button').first()).toBeVisible()
  expect(new URL(guest.url()).pathname).toBe('/')
  await guest.screenshot({ path: `${SHOTS}/50-after-reset-phone.png` })
  account.password = 'a-reset-secret-1'

  // The same link again: refused, said plainly
  await guest.goto(link)
  const again = guest.getByRole('form', { name: 'Choose a new password' })
  await again.getByLabel('New password', { exact: true }).fill('a-reset-secret-3')
  await again.getByLabel('New password again').fill('a-reset-secret-3')
  await submitPatiently(guest, again.getByRole('button', { name: 'Save the new password' }), again)
  await expect(guest.getByText('This link has expired or was already used.')).toBeVisible()
  await guest.context().close()
})

test('a /reset address without a token says so, and leads back to login', async ({ browser }) => {
  const guest = await guestPage(browser)
  await guest.goto('/reset')
  await expect(guest.getByText('This link has expired or was already used.')).toBeVisible()
  await guest.getByRole('button', { name: '‹ Back to login' }).click()
  await expect(guest.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  expect(new URL(guest.url()).pathname).toBe('/')
  await guest.context().close()
})

test('with the reset switched off on the server, no "Forgot password?"', async ({ browser }) => {
  const guest = await guestPage(browser)
  await guest.route('**/api/features', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ password_reset: false, body_weight: true, export: true }),
    }),
  )
  await guest.goto('/')
  await expect(guest.getByRole('heading', { name: 'Welcome back' })).toBeVisible()
  await guest.waitForTimeout(300)
  await expect(guest.getByRole('button', { name: 'Forgot password?' })).toHaveCount(0)
  await guest.context().close()
})
