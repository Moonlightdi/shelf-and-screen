// Shelf & Screen service worker: keeps the app working when the internet is gone.
const CACHE = "shelf-v1";
const SHELL = ["/offline", "/static/sky.js", "/static/music.js", "/static/listen.js", "/static/icons/icon-192.png"];

self.addEventListener("install", function(e) {
    e.waitUntil(caches.open(CACHE).then(function(c) { return c.addAll(SHELL); }).then(function() { return self.skipWaiting(); }));
});

self.addEventListener("activate", function(e) {
    e.waitUntil(caches.keys().then(function(keys) {
        return Promise.all(keys.filter(function(k) { return k !== CACHE; }).map(function(k) { return caches.delete(k); }));
    }).then(function() { return self.clients.claim(); }));
});

self.addEventListener("fetch", function(e) {
    const req = e.request;
    if (req.method !== "GET") return;
    const url = new URL(req.url);
    if (url.origin !== location.origin) return;

    // pages: try the internet first, keep a copy, and fall back to the copy or the offline page
    if (req.mode === "navigate") {
        e.respondWith(fetch(req).then(function(res) {
            const copy = res.clone();
            caches.open(CACHE).then(function(c) { c.put(req, copy); });
            return res;
        }).catch(function() {
            return caches.match(req).then(function(hit) { return hit || caches.match("/offline"); });
        }));
        return;
    }
    // scripts, icons and covers: use the saved copy, refresh it in the background
    if (url.pathname.startsWith("/static/") || url.pathname.startsWith("/api/cover/")) {
        e.respondWith(caches.match(req).then(function(hit) {
            const net = fetch(req).then(function(res) {
                if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(function(c) { c.put(req, copy); }); }
                return res;
            }).catch(function() { return hit; });
            return hit || net;
        }));
    }
});
