// Bump CACHE_NAME whenever the shell changes in a way old installs must drop.
const CACHE_NAME = "aes-logistics-shell-v2";
const SHELL_FILES = [
  "/",
  "/index.html",
  "/styles.css",
  "/app.js",
  "/manifest.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Never cache API calls - uploads must always hit the network live.
  if (url.pathname.startsWith("/api/")) {
    return;
  }
  if (event.request.method !== "GET") {
    return;
  }

  // App shell: network-first so every deploy reaches phones immediately;
  // fall back to the cached copy when offline (end-of-shift sync still works).
  event.respondWith(
    fetch(event.request)
      .then((resp) => {
        if (resp && resp.ok && url.origin === self.location.origin) {
          const copy = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        }
        return resp;
      })
      .catch(() => caches.match(event.request))
  );
});
