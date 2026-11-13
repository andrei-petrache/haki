/**
 * The strict Content-Security-Policy that Nginx sends (nginx.conf.template):
 * on every answer, and nothing in the app breaks it. Every screen is opened
 * with a listener for the browser's securitypolicyviolation events; a
 * single violation (an inline style or script, a font or request elsewhere)
 * fails the test.
 */
import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { signUp } from './helpers'

const CSP =
  "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; " +
  "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"

let page: Page

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  // Before any of the app's code: every violation from the first byte on
  await page.addInitScript(() => {
    const seen: string[] = []
    ;(window as unknown as { cspViolations: string[] }).cspViolations = seen
    document.addEventListener('securitypolicyviolation', (event) => {
      seen.push(`${event.violatedDirective} ${event.blockedURI || 'inline'} ${event.sourceFile}:${event.lineNumber}`)
    })
  })
  await signUp(page)
})

test.afterAll(async () => {
  await page.close()
})

async function violations(): Promise<string[]> {
  return page.evaluate(() => (window as unknown as { cspViolations?: string[] }).cspViolations ?? [])
}

test('every answer carries the strict policy', async () => {
  for (const path of ['/', '/index.html', '/health']) {
    const response = await page.request.get(path)
    expect(response.headers()['content-security-policy'], path).toBe(CSP)
  }
})

test('no screen breaks it', async () => {
  const nav = (name: string) => page.getByRole('navigation').getByRole('button', { name, exact: true })
  await expect(nav('Today')).toBeVisible()
  // The bundled fonts are in use, so they were loaded under the policy
  await page.evaluate(() => document.fonts.ready)
  expect(await page.evaluate(() => document.fonts.check('16px Inter'))).toBe(true)

  for (const name of ['Foods', 'Workouts', 'Programs', 'Profile', 'Today']) {
    await nav(name).click()
    await page.waitForLoadState('networkidle')
  }
  // A few screens with their own styles set from code
  await nav('Workouts').click()
  await page.getByRole('button', { name: /new workout/i }).first().click()
  await nav('Programs').click()
  await page.getByRole('button', { name: /new program/i }).first().click()
  await nav('Today').click()
  await page.waitForLoadState('networkidle')

  expect(await violations()).toEqual([])
})
