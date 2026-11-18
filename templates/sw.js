const V = 'centerly-v1';
self.addEventListener('install', e => {
  e.waitUntil(caches.open(V).then(c => c.add('/app/')).catch(() => {}).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== V).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== 'GET' || u.origin !== location.origin || u.pathname !== '/app/') return;
  e.respondWith(fetch(r).then(res => {
    if (res.ok && !res.redirected) { const cp = res.clone(); caches.open(V).then(c => c.put('/app/', cp)); }
    return res;
  }).catch(() => caches.match('/app/')));
});
