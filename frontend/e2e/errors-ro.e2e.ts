/**
 * The server's errors in the UI language: the app translates them by their
 * stable code, so a Romanian screen never shows the server's English.
 */
import { expect, test } from '@playwright/test'

test('a wrong password on a Romanian login screen is said in Romanian', async ({ browser }) => {
  const context = await browser.newContext({ locale: 'ro-RO', viewport: { width: 390, height: 844 } })
  const page = await context.newPage()
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Bine ai revenit' })).toBeVisible()
  await page.getByLabel('Email').fill('nobody-here@example.com')
  await page.getByLabel('Parolă').fill('not-the-password')
  await page.getByRole('button', { name: 'Intră' }).click()
  // invalid_credentials, never "Invalid email or password"
  await expect(page.locator('.error')).toHaveText(/^(Email sau parolă greșită\.|Prea multe încercări)/)
  await expect(page.locator('.error')).not.toContainText('Invalid')
  await context.close()
})
