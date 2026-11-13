/**
 * The app as a PWA: an installable manifest with its icons, a service
 * worker that opens the app shell offline, and nothing of the account's
 * data in its caches (it never keeps /api/).
 */
import { expect, test } from '@playwright/test'
import type { BrowserContext, Page } from '@playwright/test'
import { signUp } from './helpers'

test.describe.configure({ mode: 'serial' })

// Service workers need a secure context: https, or localhost. The e2e stack
// serves http://frontend:8080, so this file's browser treats that origin as
// secure (staging's port-forward is 127.0.0.1, and go-live is https)
// (the full Chromium build in the pinned image: its headless shell ignores
// that switch)
test.use({
  channel: 'chromium',
  launchOptions: { args: ['--unsafely-treat-insecure-origin-as-secure=http://frontend:8080'] },
})

let context: BrowserContext
let page: Page

test.beforeAll(async ({ browser }) => {
  context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'en-US' })
  page = await context.newPage()
  await signUp(page)
})

test.afterAll(async () => {
  await context.close()
})

test('the manifest and its icons, served as what they are', async () => {
  const manifest = await page.request.get('/manifest.webmanifest')
  expect(manifest.status()).toBe(200)
  expect(manifest.headers()['content-type']).toContain('application/manifest+json')
  // Checked on every visit, so installed apps get a new version
  expect(manifest.headers()['cache-control']).toBe('no-cache')
  const data = (await manifest.json()) as {
    name: string
    display: string
    start_url: string
    icons: { src: string; sizes: string; purpose?: string }[]
  }
  expect(data).toMatchObject({ name: 'Haki', display: 'standalone', start_url: '/' })
  for (const size of ['192x192', '512x512']) expect(data.icons.some((icon) => icon.sizes === size)).toBe(true)
  expect(data.icons.some((icon) => icon.purpose === 'maskable')).toBe(true)
  for (const icon of data.icons) {
    const response = await page.request.get(icon.src)
    expect(response.status(), icon.src).toBe(200)
  }
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute('href', '/manifest.webmanifest')

  const worker = await page.request.get('/sw.js')
  expect(worker.headers()['content-type']).toContain('javascript')
  expect(worker.headers()['cache-control']).toBe('no-cache')
})

test('the service worker takes the page over, and opens the app offline', async () => {
  const active = await page.evaluate(async () => Boolean((await navigator.serviceWorker.ready).active))
  expect(active).toBe(true)
  // The first visit installed it; from the next load on it serves the page
  await page.reload()
  await expect(page.getByRole('navigation').getByRole('button').first()).toBeVisible()
  expect(await page.evaluate(() => Boolean(navigator.serviceWorker.controller))).toBe(true)

  await context.setOffline(true)
  await page.reload()
  // The shell opens; only the account's data cannot come, and it says so
  await expect(page.locator('#root')).not.toBeEmpty()
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible()
  await context.setOffline(false)
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('navigation').getByRole('button').first()).toBeVisible()
})

test('its caches hold the app, never the account', async () => {
  const urls = await page.evaluate(async () => {
    const all: string[] = []
    for (const name of await caches.keys()) {
      const cache = await caches.open(name)
      for (const request of await cache.keys()) all.push(new URL(request.url).pathname)
    }
    return all
  })
  expect(urls).toContain('/index.html')
  expect(urls.some((url) => url.startsWith('/assets/'))).toBe(true)
  expect(urls.filter((url) => url.startsWith('/api/'))).toEqual([])
})
