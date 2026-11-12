/**
 * What every end-to-end file needs: a fresh account, calls to the API as
 * that account, and deleting everything it created at the end. Not a test
 * file itself (only *.e2e.ts are).
 */
import { randomBytes } from 'node:crypto'
import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'

export const SHOTS = `${process.env.E2E_OUT ?? '/tmp/haki-e2e'}/screenshots`

/**
 * A POST to sign-up or login, waiting out Nginx's rate limit (5 a minute
 * per address, then one every 12 s) instead of failing: with several files,
 * each signing up its own account, a run can hit it.
 */
async function postAuth(page: Page, path: string, data: unknown) {
  for (let attempt = 0; ; attempt++) {
    const response = await page.request.post(`/api${path}`, { data })
    if (response.status() !== 429 || attempt === 5) return response
    await new Promise((resolve) => setTimeout(resolve, 13_000))
  }
}

/**
 * A new account, logged in. Through the API, not the form (language.e2e.ts
 * signs up through the form); one per file, the files run one after another.
 * Returns the credentials, for a file that needs them again.
 */
export async function signUp(page: Page): Promise<{ email: string; password: string }> {
  const email = `e2e-${Date.now()}-${randomBytes(3).toString('hex')}@example.com`
  const password = randomBytes(16).toString('hex')
  await page.goto('/')
  expect((await postAuth(page, '/auth/signup', { email, password })).status()).toBe(201)
  const login = await postAuth(page, '/auth/login', { email, password })
  expect(login.status()).toBe(200)
  const { access_token } = (await login.json()) as { access_token: string }
  await page.evaluate((value) => localStorage.setItem('haki_token', value), access_token)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()
  return { email, password }
}

async function token(page: Page): Promise<string> {
  const value = await page.evaluate(() => localStorage.getItem('haki_token'))
  if (!value) throw new Error('not logged in')
  return value
}

/** One call to the API as the logged-in user, with the parsed JSON answer. */
export async function api(
  page: Page,
  method: string,
  path: string,
  data?: unknown,
): Promise<{ status: number; body: unknown }> {
  const response = await page.request.fetch(`/api${path}`, {
    method,
    headers: { Authorization: `Bearer ${await token(page)}` },
    data,
  })
  const text = await response.text()
  return { status: response.status(), body: text ? JSON.parse(text) : null }
}

/** The ids in a list the API returns, e.g. /workouts. */
export async function ids(page: Page, path: string): Promise<number[]> {
  const { body } = await api(page, 'GET', path)
  return (body as { id: number }[]).map((item) => item.id)
}

/**
 * Delete everything the account created, and check nothing is left. The
 * account itself goes with the throwaway stack. Workouts and programs
 * first: an exercise they use cannot be deleted.
 */
export async function deleteEverything(page: Page): Promise<void> {
  for (const id of await ids(page, '/workouts')) await api(page, 'DELETE', `/workouts/${id}`)
  for (const id of await ids(page, '/programs')) await api(page, 'DELETE', `/programs/${id}`)
  for (const id of await ids(page, '/exercises')) await api(page, 'DELETE', `/exercises/${id}`)

  expect(await ids(page, '/workouts')).toEqual([])
  expect(await ids(page, '/programs')).toEqual([])
  expect(await ids(page, '/exercises')).toEqual([])
}
