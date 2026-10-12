// Service Worker para Web Push - O Refugio
// Filosofia IndieWeb: 100% nativo, sem dependencias externas e sem emojis

self.addEventListener("install", (event) => {
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
    let data = {};
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data = {
                title: "O Refugio",
                body: event.data.text(),
                url: "/"
            };
        }
    } else {
        data = {
            title: "O Refugio",
            body: "Nova publicacao disponivel no blog.",
            url: "/"
        };
    }

    const title = data.title || "O Refugio";
    const options = {
        body: data.body || "Nova publicacao disponivel.",
        data: {
            url: data.url || "/"
        },
        vibrate: [100, 50, 100],
        tag: data.tag || "refugio-notification",
        renotify: true
    };

    if (data.icon) {
        options.icon = data.icon;
    }
    if (data.badge) {
        options.badge = data.badge;
    }

    console.log("[ServiceWorker] Disparando showNotification:", title, options);

    event.waitUntil(
        self.registration.showNotification(title, options)
            .then(() => {
                console.log("[ServiceWorker] Notificacao exibida com sucesso no sistema operacional.");
            })
            .catch((err) => {
                console.error("[ServiceWorker] Falha com icones, tentando fallback basico:", err);
                return self.registration.showNotification(title, {
                    body: options.body,
                    data: options.data
                });
            })
    );
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();

    const targetUrl = (event.notification.data && event.notification.data.url) 
        ? event.notification.data.url 
        : "/";

    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
            for (let i = 0; i < windowClients.length; i++) {
                const client = windowClients[i];
                if (client.url.includes(targetUrl) && "focus" in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
