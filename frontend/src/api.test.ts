import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, fetchFoods, login, setUnauthorizedHandler } from './api'

/** Make the next fetch answer with this status and body, like the server would. */
function respondWith(status: number, body: string, contentType = 'text/html') {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(body, { status, headers: { 'Content-Type': contentType } })),
  )
}

/** The ApiError a call rejects with (fails the test if it resolves). */
async function errorFrom(call: Promise<unknown>): Promise<ApiError> {
  const err = await call.then(
    () => expect.fail('expected the call to fail'),
    (e: unknown) => e,
  )
  expect(err).toBeInstanceOf(ApiError)
  return err as ApiError
}

afterEach(() => {
  vi.unstubAllGlobals()
  setUnauthorizedHandler(null)
})

describe('request errors', () => {
  it('turns a 429 from Nginx (an HTML page) into a clear message', async () => {
    respondWith(429, '<html><body>429 Too Many Requests</body></html>')

    const err = await errorFrom(login('andrei@example.com', 'wrong-password'))

    expect(err.status).toBe(429)
    expect(err.message).toBe('Too many attempts. Wait a minute, then try again.')
  })

  it('does not log the user out on 429', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    respondWith(429, '<html>429</html>')

    await errorFrom(fetchFoods('a-token'))

    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('turns a 503 into a clear message', async () => {
    respondWith(503, '{"detail":"Server busy, try again shortly"}', 'application/json')

    const err = await errorFrom(login('andrei@example.com', 'correct-password'))

    expect(err.status).toBe(503)
    expect(err.message).toBe('Service temporarily unavailable, try again in a moment.')
  })

  it('logs out on a 401 for an authenticated call, but not for login', async () => {
    const onUnauthorized = vi.fn()
    setUnauthorizedHandler(onUnauthorized)
    respondWith(401, '{"detail":"Invalid or expired token"}', 'application/json')

    await errorFrom(login('andrei@example.com', 'wrong-password'))
    expect(onUnauthorized).not.toHaveBeenCalled()

    await errorFrom(fetchFoods('expired-token'))
    expect(onUnauthorized).toHaveBeenCalledOnce()
  })
})
