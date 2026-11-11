import { afterEach, describe, expect, it, vi } from 'vitest'
import { copyCatalogFood, searchCatalogFoods } from './api'
import { catalogLanguage, catalogName, searchText } from './catalog'

afterEach(() => vi.unstubAllGlobals())

function respond(status: number, body: unknown) {
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('names and languages', () => {
  const feta = { name: 'Feta cheese', name_ro: 'Brânză feta' }

  it('shows the Romanian name in Romanian, else the English one', () => {
    expect(catalogName(feta, 'ro')).toBe('Brânză feta')
    expect(catalogName(feta, 'en')).toBe('Feta cheese')
    expect(catalogName({ name: 'Lard', name_ro: null }, 'ro')).toBe('Lard')
  })

  it('asks the catalog in the app language', () => {
    expect(catalogLanguage('ro')).toBe('ro')
    expect(catalogLanguage('en')).toBe('en')
  })

  it('tidies the search text', () => {
    expect(searchText('  branza   feta ')).toBe('branza feta')
  })
})

describe('the catalog client', () => {
  it('searches with q, language, limit and offset', async () => {
    const fetchMock = respond(200, [])

    await searchCatalogFoods('a-token', 'brânză feta', 'ro', 20, 40)

    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/api/catalog/foods?q=br%C3%A2nz%C4%83+feta&language=ro&limit=20&offset=40')
  })

  it('tells a new copy (201) from one the user already had (200)', async () => {
    const food = { id: 7, name: 'Brânză feta', calories_per_100g: 264, catalog_food_id: 3 }

    respond(201, food)
    expect(await copyCatalogFood('a-token', 3, 'ro')).toEqual({ item: food, created: true })
    respond(200, food)
    expect(await copyCatalogFood('a-token', 3, 'ro')).toEqual({ item: food, created: false })
  })

  it('rejects a name collision (409) with its status', async () => {
    respond(409, { detail: 'A food with this name already exists' })

    await expect(copyCatalogFood('a-token', 3, 'en')).rejects.toMatchObject({ status: 409 })
  })
})
