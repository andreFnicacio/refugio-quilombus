// Cliente de Notificacoes Web Push & Alertas - O Refugio
// Fluxo via modal neo-brutalista + controle de status no rodape, sem rastreadores externos.

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

    function updateFooterPushBtn(stateText, isGranted) {
        const btn = document.getElementById("footer-push-toggle");
        if (!btn) return;
        btn.textContent = stateText;
        if (isGranted) {
            btn.style.borderColor = "var(--border-green)";
            btn.style.color = "var(--border-green)";
            btn.style.boxShadow = "3px 3px 0 var(--border-green)";
        }
    }

    async function createOrSyncPushSubscription(reg) {
        const resKey = await fetch("/api/push/vapid-public-key");
        if (!resKey.ok) return null;
        const keyData = await resKey.json();
        const convertedKey = urlBase64ToUint8Array(keyData.public_key);

        let sub = await reg.pushManager.getSubscription();
        if (!sub) {
            try {
                sub = await reg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: convertedKey
                });
            } catch (subErr) {
                // Caso haja chave VAPID antiga travada, limpa e tenta novamente
                const stale = await reg.pushManager.getSubscription();
                if (stale) {
                    await stale.unsubscribe();
                }
                sub = await reg.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: convertedKey
                });
            }
        }

        if (!sub) return null;

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

        updateFooterPushBtn("[SINAL PUSH: ATIVO NO NAVEGADOR]", true);
        return sub;
    }

    async function syncSubscriptionIfGranted() {
        if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
            updateFooterPushBtn("[SINAL PUSH: INDISPONIVEL]", false);
            return;
        }
        if (Notification.permission === "denied") {
            updateFooterPushBtn("[SINAL PUSH: BLOQUEADO NO NAVEGADOR]", false);
            return;
        }
        if (Notification.permission !== "granted") {
            updateFooterPushBtn("[SINAL PUSH: ATIVAR NOTIFICACOES]", false);
            return;
        }

        try {
            const reg = await getRegistration();
            if (!reg) return;
            await createOrSyncPushSubscription(reg);
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

        // Se o usuario ja bloqueou ou ja permitiu no navegador, nao exibe o modal automatico
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
                updateFooterPushBtn("[SINAL PUSH: NAO AUTORIZADO]", false);
                closeConsentModal();
                return;
            }

            await createOrSyncPushSubscription(reg);
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

        // Configura botoes do modal de consentimento e do rodape
        const modal = document.getElementById("push-consent-modal");
        const acceptBtn = document.getElementById("push-consent-accept");
        const declineBtn = document.getElementById("push-consent-decline");
        const closeBtn = document.getElementById("push-consent-close");
        const footerBtn = document.getElementById("footer-push-toggle");

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

        if (footerBtn) {
            footerBtn.addEventListener("click", (e) => {
                e.preventDefault();
                if ("Notification" in window && Notification.permission === "granted") {
                    syncSubscriptionIfGranted();
                } else {
                    showConsentModal();
                }
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
            sync: syncSubscriptionIfGranted,
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
