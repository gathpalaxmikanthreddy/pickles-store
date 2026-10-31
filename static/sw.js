const CACHE_NAME = "pickels-static-v1";
const STATIC_FILE_PATTERN = /\.(?:css|js|png|jpe?g|gif|webp|svg|ico)$/i;
const NEVER_CACHE_PATHS = [
    "/admin",
    "/login",
    "/checkout",
    "/cart",
    "/place-order",
    "/create-razorpay-order",
    "/verify-razorpay-payment"
];

self.addEventListener("install", function(event) {
    event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", function(event) {
    event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", function(event) {
    const request = event.request;
    if (request.method !== "GET") {
        return;
    }

    const url = new URL(request.url);
    if (url.origin !== self.location.origin) {
        return;
    }

    const isSensitivePath = NEVER_CACHE_PATHS.some(function(path) {
        return url.pathname === path || url.pathname.startsWith(path + "/");
    });
    const isStaticAsset =
        url.pathname.startsWith("/static/") &&
        STATIC_FILE_PATTERN.test(url.pathname);

    if (isSensitivePath || !isStaticAsset) {
        event.respondWith(fetch(request));
        return;
    }

    event.respondWith((async function() {
        try {
            const response = await fetch(request);
            if (response.ok && response.type !== "opaque") {
                const cache = await caches.open(CACHE_NAME);
                await cache.put(request, response.clone());
            }
            return response;
        } catch (error) {
            const cachedResponse = await caches.match(request);
            if (cachedResponse) {
                return cachedResponse;
            }
            throw error;
        }
    })());
});
