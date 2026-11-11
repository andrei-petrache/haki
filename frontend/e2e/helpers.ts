/**
 * What every end-to-end file needs: a fresh account, calls to the API as
 * that account, and deleting everything it created at the end. Not a test
 * file itself (only *.e2e.ts are).
 */
import { randomBytes } from 'node:crypto'
import { expect } from '@playwright/test'
import type { Page } from '@playwright/test'

export const SHOTS = `${process.env.E2E_OUT ?? '/tmp/haki-e2e'}/screenshots`

/** Sign up a new account and land logged in. One per file: signup is rate limited. */
export async function signUp(page: Page): Promise<void> {
  const email = `e2e-${Date.now()}-${randomBytes(3).toString('hex')}@example.com`
  await page.goto('/')
  await page.getByRole('button', { name: 'New here? Create an account' }).click()
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(randomBytes(16).toString('hex'))
  await page.getByRole('button', { name: 'Sign up' }).click()
  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()
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
