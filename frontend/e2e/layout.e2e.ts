/**
 * The app's frame in direction A: bottom navigation on a phone, tabs at
 * the top on a desktop, one Log out on screen, and the dark theme down to
 * the browser's own controls, with a visible keyboard focus.
 */
import { expect, test } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { SHOTS, signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

let page: Page

function tabs(): Locator {
  return page.getByRole('navigation').getByRole('button')
}

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await signUp(page)
})

test.afterAll(async () => {
  await page.close()
})

test('on a phone: five tabs in a bar at the bottom, Log out in Profile', async () => {
  await expect(tabs()).toHaveCount(5)
  for (let i = 0; i < 5; i++) {
    const box = await tabs().nth(i).boundingBox()
    expect(box, `tab ${i}`).not.toBeNull()
    expect(box!.height, `tab ${i} height`).toBeGreaterThanOrEqual(44)
    expect(box!.width, `tab ${i} width`).toBeGreaterThanOrEqual(44)
    // At the bottom of the screen, within it
    expect(box!.y + box!.height, `tab ${i} bottom`).toBeLessThanOrEqual(844)
    expect(box!.y, `tab ${i} top`).toBeGreaterThan(844 - 100)
  }
  await expect(tabs().first()).toHaveAttribute('aria-current', 'page')
  // Wordmark and the day, as words between the arrows, on one row at the top
  const brand = await page.locator('.brand').boundingBox()
  const previous = await page.getByRole('button', { name: 'Previous day' }).boundingBox()
  const label = page.locator('button.day-label')
  await expect(label).toHaveText(/^Today, \d{1,2} [A-Z][a-z]{2}$/)
  expect(Math.abs(brand!.y + brand!.height / 2 - (previous!.y + previous!.height / 2))).toBeLessThan(12)
  expect(previous!.y).toBeLessThan(80)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)

  // The header has no Log out on a phone; Profile has it
  await expect(page.getByRole('button', { name: 'Log out' })).toHaveCount(0)
  await tabs().nth(4).click()
  await expect(page.getByRole('button', { name: 'Log out' })).toHaveCount(1)
  await page.screenshot({ path: `${SHOTS}/28-bottom-nav-phone.png`, fullPage: true })

  // The last content is not hidden under the bar
  await page.getByRole('button', { name: 'Log out' }).scrollIntoViewIfNeeded()
  const logout = await page.getByRole('button', { name: 'Log out' }).boundingBox()
  const bar = await page.getByRole('navigation').boundingBox()
  expect(logout!.y + logout!.height).toBeLessThanOrEqual(bar!.y)
})

test('on a desktop: tabs at the top, Log out in the header', async () => {
  await page.setViewportSize({ width: 1280, height: 900 })
  const box = await tabs().first().boundingBox()
  expect(box!.y).toBeLessThan(120)
  await expect(page.getByRole('button', { name: 'Log out' })).toHaveCount(1)
  await expect(page.locator('header').getByRole('button', { name: 'Log out' })).toBeVisible()
  await page.setViewportSize({ width: 390, height: 844 })
})

test('dark down to native controls, with a visible keyboard focus', async () => {
  await tabs().nth(0).click()
  const day = page.getByLabel('Day', { exact: true })
  const look = await day.evaluate((input) => {
    const style = getComputedStyle(input)
    return { scheme: style.colorScheme, color: style.color, background: style.backgroundColor }
  })
  expect(look.scheme).toContain('dark')
  expect(look.background).toBe('rgb(35, 35, 38)')
  expect(look.color).toBe('rgb(243, 240, 234)')
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe('rgb(14, 14, 15)')

  // Keyboard focus shows an outline in the focus colour
  await day.focus()
  await page.keyboard.press('Shift+Tab')
  const focused = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement
    const style = getComputedStyle(el)
    return { tag: el.tagName, outline: style.outlineStyle, color: style.outlineColor }
  })
  expect(focused.outline).toBe('solid')
  expect(focused.color).toBe('rgb(255, 115, 102)')
  await page.screenshot({ path: `${SHOTS}/29-dark-today-phone.png`, fullPage: true })
})
