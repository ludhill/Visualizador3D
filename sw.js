const CACHE_NAME = 'webar-engine-v1';

// Ajuste as rotas para refletir exatamente os arquivos da sua estrutura
const PRECACHE_ASSETS = [
  './',
  './index.html',
  '../../public/targets/targets.mind'
];

// Instalação tolerante a falhas individuais de 404
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[Service Worker] Pré-carregando ativos...');
      return Promise.allSettled(
        PRECACHE_ASSETS.map((url) =>
          cache.add(url).catch((err) => {
            console.warn(`[Service Worker] Não foi possível colocar em cache: ${url}`, err);
          })
        )
      );
    })
  );
  self.skipWaiting();
});

// Ativação e limpeza de caches antigos
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// Interceção e entrega via Cache First (ignorando APIs)
self.addEventListener('fetch', (event) => {
  const requestUrl = new URL(event.request.url);

  // Nunca armazena requisições de API em cache
  if (requestUrl.pathname.startsWith('/api/')) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      if (cachedResponse) {
        return cachedResponse;
      }
      return fetch(event.request).then((networkResponse) => {
        if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
          return networkResponse;
        }
        const responseToCache = networkResponse.clone();
        caches.open(CACHE_NAME).then((cache) => {
          cache.put(event.request, responseToCache);
        });
        return networkResponse;
      });
    })
  );
});