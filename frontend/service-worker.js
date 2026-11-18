const CACHE_NAME = 'yuktix-shell-v1'
const SHELL = ['/', '/index.html', '/app.js', '/api.js', '/app.css', '/app-extra.css', '/app-auth.css', '/app-interactions.css', '/config.example.js', '/manifest.webmanifest', '/yuktix-icon.svg']

self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith('yuktix-shell-') && key !== CACHE_NAME).map(key => caches.delete(key)))).then(() => self.clients.claim()))
})

self.addEventListener('fetch', event => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== self.location.origin) return
  event.respondWith(fetch(request).then(response => {
    if (response.ok) caches.open(CACHE_NAME).then(cache => cache.put(request, response.clone()))
    return response
  }).catch(async () => {
    const cached = await caches.match(request)
    return cached || (request.mode === 'navigate' ? caches.match('/index.html') : Response.error())
  }))
})


