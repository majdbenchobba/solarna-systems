const CACHE = "solarna-shell-v44";
const SHELL = [
  "/",
  "/login.html",
  "/reset-password.html",
  "/privacy.html",
  "/app.css?v=44",
  "/config.js?v=44",
  "/i18n.js?v=44",
  "/supabase-client.js?v=44",
  "/system-config.js?v=44",
  "/result-summary.js?v=44",
  "/install-support.js?v=44",
  "/cloud-storage.js?v=44",
  "/login.js?v=44",
  "/reset-password.js?v=44",
  "/app.js?v=44",
  "/manifest.webmanifest?v=44",
  "/solarna-mark.svg?v=44",
  "/favicon.svg?v=44",
  "/icon-180.png?v=44",
  "/icon-192.png?v=44",
  "/icon-512.png?v=44"
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin ||
      url.pathname.startsWith("/api/") ||
      url.pathname.startsWith("/downloads/")) {
    return;
  }
  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(event.request, copy));
        }
        return response;
      })
      .catch(async () => {
        const hit = await caches.match(event.request);
        if (hit) return hit;
        if (event.request.mode === "navigate") return caches.match("/");
        return Response.error();
      })
  );
});
