// Offline shell for the cloud app.
//
// ONLY the static shell is cached. Nothing from the API is ever stored: those
// responses are per-user and carry approval state, spending and personal data,
// and a cached copy could be shown to a different person on a shared device or
// long after it stopped being true.
const VERSION = 'linguafusion-online-2026.09.09.9';
const SHELL = [
  '/pilot/', '/pilot/pilot.css', '/pilot/pilot.mjs', '/pilot/cloud-auth.mjs',
  '/pilot/cloud-client.mjs', '/pilot/firebase-config.mjs', '/pilot/pronunciation.mjs',
  '/pilot/wav.mjs', '/pilot/icon.svg', '/pilot/manifest.webmanifest',
  '/pilot/updates.mjs', '/pilot/themes.mjs', '/pilot/linguafusion-themes.css',
];

self.addEventListener('install', event => {
  event.waitUntil(caches.open(VERSION).then(cache => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', event => {
  event.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // Anything outside the static shell -- every API route included -- goes to the
  // network untouched and is never written to the cache.
  if (!SHELL.includes(url.pathname)) return;

  event.respondWith((async () => {
    try {
      const fresh = await fetch(request);
      if (fresh && fresh.ok) {
        const cache = await caches.open(VERSION);
        cache.put(request, fresh.clone());
      }
      return fresh;
    } catch {
      const cached = await caches.match(request);
      if (cached) return cached;
      throw new Error('offline and not cached');
    }
  })());
});
