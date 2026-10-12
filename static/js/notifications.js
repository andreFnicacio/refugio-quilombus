// Cliente de Notificacoes Web Push - O Refugio
// Fluxo 100% via modal de consentimento neo-brutalista, sem botoes no cabecalho, sem emojis e sem rastreadores.

(function () {
    const STORAGE_KEY = "refugio_push_decision";
    const DISMISS_TTL_MS = 14 * 24 * 60 * 60 * 1000; // 14 dias se recusar

    function urlBase64ToUint8Array(base64String) {
        const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
        const base64 = (base64String + padding)
            .replace(/\-/g, "+")
            .replace(/_/g, "/");

        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);

        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    async function getRegistration() {
        if (!("serviceWorker" in navigator)) return null;
        return await navigator.serviceWorker.register("/sw.js", { scope: "/" });
    }

    async function syncSubscriptionIfGranted() {
        if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
        if (Notification.permission !== "granted") return;

        try {
            const reg = await getRegistration();
            if (!reg) return;
            const sub = await reg.pushManager.getSubscription();
            if (!sub) return;

            // Garante que o endpoint esta registrado no backend
            const rawSub = sub.toJSON();
            const payload = {
                endpoint: rawSub.endpoint,
                p256dh: rawSub.keys.p256dh,
                auth: rawSub.keys.auth,
                user_agent: navigator.userAgent
            };

            await fetch("/api/push/subscribe", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
        } catch (e) {
            console.debug("[Push] Falha ao sincronizar assinatura existente:", e);
        }
    }

    function shouldShowConsentModal() {
        if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
            return false;
        }

        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has("reset") || urlParams.has("test_modal")) {
            localStorage.removeItem(STORAGE_KEY);
            return true;
        }

        // Se o usuario ja bloqueou ou ja permitiu no Chrome, nao exibe o modal
        if (Notification.permission === "denied" || Notification.permission === "granted") {
            return false;
        }

        const saved = localStorage.getItem(STORAGE_KEY);
        if (!saved) return true;

        try {
            const parsed = JSON.parse(saved);
            if (parsed.choice === "dismissed" && Date.now() - parsed.timestamp < DISMISS_TTL_MS) {
                return false;
            }
        } catch (e) {
            return true;
        }
        return true;
    }

    function showConsentModal() {
        const modal = document.getElementById("push-consent-modal");
        if (modal) {
            modal.style.display = "flex";
        }
    }

    function closeConsentModal() {
        const modal = document.getElementById("push-consent-modal");
        if (modal) {
            modal.style.display = "none";
        }
    }

    function dismissConsent() {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ choice: "dismissed", timestamp: Date.now() }));
        closeConsentModal();
    }

    async function subscribeUser() {
        try {
            const reg = await getRegistration();
            if (!reg) {
                closeConsentModal();
                return;
            }

            const permission = await Notification.requestPermission();
            if (permission !== "granted") {
                localStorage.setItem(STORAGE_KEY, JSON.stringify({ choice: permission, timestamp: Date.now() }));
                closeConsentModal();
                return;
            }

            // Busca chave publica VAPID do backend
            const resKey = await fetch("/api/push/vapid-public-key");
            if (!resKey.ok) {
                console.error("[Push] Falha ao obter chave publica VAPID.");
                closeConsentModal();
                return;
            }
            const keyData = await resKey.json();
            const convertedKey = urlBase64ToUint8Array(keyData.public_key);

            // Cria assinatura no PushManager
            const subscription = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: convertedKey
            });

            // Persiste no backend
            const rawSub = subscription.toJSON();
            const payload = {
                endpoint: rawSub.endpoint,
                p256dh: rawSub.keys.p256dh,
                auth: rawSub.keys.auth,
                user_agent: navigator.userAgent
            };

            await fetch("/api/push/subscribe", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            localStorage.setItem(STORAGE_KEY, JSON.stringify({ choice: "granted", timestamp: Date.now() }));
            closeConsentModal();
        } catch (err) {
            console.error("[Push] Erro durante inscricao no modal:", err);
            closeConsentModal();
        }
    }

    // Inicializacao quando o DOM carregar
    window.addEventListener("DOMContentLoaded", async () => {
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.has("reset") || urlParams.has("test_modal")) {
            localStorage.removeItem(STORAGE_KEY);
        }

        // Sincroniza em background caso ja esteja ativo
        syncSubscriptionIfGranted();

        // Configura botoes do modal de consentimento
        const modal = document.getElementById("push-consent-modal");
        const acceptBtn = document.getElementById("push-consent-accept");
        const declineBtn = document.getElementById("push-consent-decline");
        const closeBtn = document.getElementById("push-consent-close");

        if (acceptBtn) {
            acceptBtn.addEventListener("click", (e) => {
                e.preventDefault();
                subscribeUser();
            });
        }

        if (declineBtn) {
            declineBtn.addEventListener("click", (e) => {
                e.preventDefault();
                dismissConsent();
            });
        }

        if (closeBtn) {
            closeBtn.addEventListener("click", (e) => {
                e.preventDefault();
                dismissConsent();
            });
        }

        if (modal) {
            modal.addEventListener("click", (e) => {
                if (e.target === modal) {
                    dismissConsent();
                }
            });
        }

        // Helper para depuracao no console
        window.refugioPush = {
            show: showConsentModal,
            reset: () => {
                localStorage.removeItem(STORAGE_KEY);
                showConsentModal();
            }
        };

        // Exibe o modal neo-brutalista de consentimento
        if (shouldShowConsentModal()) {
            setTimeout(() => {
                showConsentModal();
            }, 500);
        }
    });
})();
