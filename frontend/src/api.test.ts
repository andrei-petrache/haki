import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  PROGRAMS_PAGE_SIZE,
  RECENT_FOODS_LIMIT,
  deleteMealEntry,
  fetchBestSet,
  fetchLastSession,
  entryKey,
  fetchFoods,
  fetchPrograms,
  fetchRecentFoods,
  login,
  setUnauthorizedHandler,
  startWorkout,
} from './api'

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
    // With the token refused: another tab may hold a newer one
    expect(onUnauthorized).toHaveBeenCalledExactlyOnceWith('expired-token')
  })
})

/** Make every fetch succeed with this JSON body and record what was called. */
function respondJson(body: unknown) {
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** The URL and the parsed JSON body of the one call a mocked fetch received. */
function calledWith(fetchMock: ReturnType<typeof vi.fn>): { url: string; body: unknown } {
  expect(fetchMock).toHaveBeenCalledOnce()
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit | undefined]
  const raw = init?.body
  return { url, body: typeof raw === 'string' ? JSON.parse(raw) : null }
}

describe('programs', () => {
  it('asks for one page of programs with limit and offset', async () => {
    const fetchMock = respondJson([])

    await fetchPrograms('a-token', PROGRAMS_PAGE_SIZE, 40)

    expect(calledWith(fetchMock).url).toBe('/api/programs?limit=20&offset=40')
  })

  it('starts a workout from a day of a program with only its date', async () => {
    const fetchMock = respondJson({ id: 9, performed_on: '2026-11-11', note: null, exercises: [] })

    const started = await startWorkout('a-token', 3, 7, '2026-11-11')

    expect(started.id).toBe(9)
    expect(calledWith(fetchMock)).toEqual({
      url: '/api/programs/3/days/7/workouts',
      body: { performed_on: '2026-11-11' },
    })
  })
})

describe('recent foods', () => {
  it('asks for the few Today shows, newest first as the server sends them', async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify([{ id: 2, name: 'Oats' }]), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const foods = await fetchRecentFoods('a-token')

    expect(foods).toEqual([{ id: 2, name: 'Oats' }])
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url.endsWith(`/foods/recent?limit=${RECENT_FOODS_LIMIT}`)).toBe(true)
  })
})

describe('quick entries', () => {
  it('keys food and quick entries apart, even with the same id', () => {
    expect(entryKey({ id: 3 })).toBe('food-3')
    expect(entryKey({ id: 3, quick: false })).toBe('food-3')
    expect(entryKey({ id: 3, quick: true })).toBe('quick-3')
  })

  it('deletes each kind through its own path', async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await deleteMealEntry('a-token', { id: 3, quick: true })
    await deleteMealEntry('a-token', { id: 3 })

    const urls = (fetchMock.mock.calls as unknown as [string][]).map(([url]) => url)
    expect(urls[0].endsWith('/entries/quick/3')).toBe(true)
    expect(urls[1].endsWith('/entries/3')).toBe(true)
  })
})

describe('exercise history', () => {
  it('asks before the given workout, or about all of them, and reads null as never done', async () => {
    const fetchMock = vi.fn(
      async () => new Response('null', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    )
    vi.stubGlobal('fetch', fetchMock)

    expect(await fetchLastSession('a-token', 4, 12)).toBeNull()
    expect(await fetchBestSet('a-token', 4)).toBeNull()

    const urls = (fetchMock.mock.calls as unknown as [string][]).map(([url]) => url)
    expect(urls[0].endsWith('/exercises/4/last?before_workout=12')).toBe(true)
    expect(urls[1].endsWith('/exercises/4/best')).toBe(true)
  })
})
