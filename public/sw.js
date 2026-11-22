const CACHE_NAME = "knpc-schedule-v3";
const PRECACHE_URLS = [
  "/static/css/app.css",
  "/static/js/htmx.min.js",
  "/static/img/logo.png",
  "/static/img/favicon.png",
  "/static/img/apple-touch-icon.png",
  "/static/img/icon-192.png",
  "/static/img/icon-512.png",
  "/static/manifest.webmanifest"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/export/") || url.pathname === "/health" || url.pathname === "/sw.js") {
    return;
  }

  // Static assets: cache-first with background refresh
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const fetchPromise = fetch(request)
          .then((response) => {
            if (response && response.ok) {
              const copy = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
            }
            return response;
          })
          .catch(() => cached);
        return cached || fetchPromise;
      })
    );
    return;
  }

  // HTML / HTMX requests: network-first with offline cache fallback
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response && response.ok && !request.headers.get("HX-Request")) {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
        }
        return response;
      })
      .catch(async () => {
        const exact = await caches.match(request);
        if (exact) return exact;
        if (request.mode === "navigate") {
          const rootFallback = await caches.match("/");
          if (rootFallback) return rootFallback;
        }
        return new Response("Offline — connect once to load this schedule view.", {
          status: 503,
          headers: { "Content-Type": "text/plain; charset=utf-8" }
        });
      })
  );
});
