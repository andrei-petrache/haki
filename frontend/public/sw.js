/*
 * Haki's service worker: the app shell offline, nothing else.
 *
 * - Pages (navigations): the network first, so a new version shows at once;
 *   offline, the last index.html seen.
 * - /assets/: Vite names them after their content, so a cached file never
 *   goes stale: the cache first.
 * - Icons and the manifest: the cache, refreshed in the background.
 * - Never /api/ nor anything but GET: the account's data stays between the
 *   app and the server (offline logging queues requests in the app, not
 *   here), and no response for one user is ever kept for another.
 *
 * A change to this file is a new version: the old caches go on activate.
 */
const VERSION = 'v1'
const SHELL = `haki-shell-${VERSION}`
const ASSETS = `haki-assets-${VERSION}`

self.addEventListener('install', (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL)
      // The page and what it loads first; fonts and the rest come as used
      const response = await fetch('/index.html', { cache: 'no-cache' })
      if (!response.ok) return
      const html = await response.clone().text()
      await cache.put('/index.html', response)
      const assets = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)].map((match) => match[1])
      const assetCache = await caches.open(ASSETS)
      await assetCache.addAll(assets)
      await cache.addAll(['/manifest.webmanifest', '/icon.svg', '/icon-192.png'])
    })(),
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keep = new Set([SHELL, ASSETS])
      for (const name of await caches.keys()) {
        if (name.startsWith('haki-') && !keep.has(name)) await caches.delete(name)
      }
      await self.clients.claim()
    })(),
  )
})

async function networkFirstPage(request) {
  const cache = await caches.open(SHELL)
  try {
    const response = await fetch(request)
    // Only the app's own page, whatever path asked for it (client routing)
    if (response.ok && response.headers.get('content-type')?.includes('text/html')) {
      await cache.put('/index.html', response.clone())
    }
    return response
  } catch {
    return (await cache.match('/index.html')) ?? Response.error()
  }
}

async function cacheFirst(request) {
  const cache = await caches.open(ASSETS)
  const cached = await cache.match(request)
  if (cached) return cached
  const response = await fetch(request)
  if (response.ok) await cache.put(request, response.clone())
  return response
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(SHELL)
  const cached = await cache.match(request)
  const fresh = fetch(request)
    .then(async (response) => {
      if (response.ok) await cache.put(request, response.clone())
      return response
    })
    .catch(() => cached ?? Response.error())
  return cached ?? fresh
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/') || url.pathname === '/health') return
  if (request.mode === 'navigate') {
    event.respondWith(networkFirstPage(request))
  } else if (url.pathname.startsWith('/assets/')) {
    event.respondWith(cacheFirst(request))
  } else if (/^\/(manifest\.webmanifest|icon[\w-]*\.(png|svg)|apple-touch-icon\.png|favicon\.svg)$/.test(url.pathname)) {
    event.respondWith(staleWhileRevalidate(request))
  }
})
