// Service Worker Mínimo para PWA
self.addEventListener('install', function(event) {
    console.log('Service Worker instalado');
});

self.addEventListener('fetch', function(event) {
    // Apenas repassa as requisições (não faz cache complexo para evitar bugs de versão)
    event.respondWith(fetch(event.request));
});