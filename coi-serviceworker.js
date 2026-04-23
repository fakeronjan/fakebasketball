/* coi-serviceworker.js
 * Adapted from https://github.com/gzuidhof/coi-serviceworker (MIT)
 * Adds Cross-Origin-Opener-Policy + Cross-Origin-Embedder-Policy headers to
 * every response, enabling SharedArrayBuffer on GitHub Pages and other hosts
 * that don't control their own server headers.
 */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

// Allow pages to force skipWaiting if the SW ends up in a waiting state
// (e.g. when the user navigates back while a new SW version was installing).
self.addEventListener('message', (e) => {
  if (e.data === 'skipWaiting') self.skipWaiting();
});

self.addEventListener('fetch', (e) => {
  // Don't intercept cross-origin-only-if-cached — it throws in Firefox.
  if (e.request.cache === 'only-if-cached' && e.request.mode !== 'same-origin') return;

  e.respondWith(
    fetch(e.request)
      .then((resp) => {
        if (resp.status === 0) return resp;

        const headers = new Headers(resp.headers);
        headers.set('Cross-Origin-Opener-Policy',   'same-origin');
        headers.set('Cross-Origin-Embedder-Policy', 'require-corp');
        headers.set('Cross-Origin-Resource-Policy', 'cross-origin');

        return new Response(resp.body, {
          status:     resp.status,
          statusText: resp.statusText,
          headers,
        });
      })
      .catch(() => fetch(e.request))
  );
});
