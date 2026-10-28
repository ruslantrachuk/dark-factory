// The page opens offline from this cache; the feed itself is never cached (it carries the state).
const SHELL = "factory-shell-v1";
const FILES = ["./", "app.js", "app.css", "manifest.webmanifest", "icon-180.png", "icon-192.png", "icon-512.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// The shell: network first (a new release shows at once), the cache when offline. The feed: network only.
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.endsWith("/status.json") || url.pathname.endsWith("/events")) return;
  event.respondWith(fetch(event.request)
    .then((r) => { const copy = r.clone(); caches.open(SHELL).then((c) => c.put(event.request, copy)); return r; })
    .catch(() => caches.match(event.request)));
});
