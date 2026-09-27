// ==========================================================================
// O REFÚGIO - JAVASCRIPT DINÂMICO RETRÔ & NEO-BRUTALIST
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
  // 1. Relógio ao Vivo no Top Terminal Ticker
  const clockEl = document.getElementById("ticker-clock");
  if (clockEl) {
    const updateClock = () => {
      const now = new Date();
      const timeStr = now.toTimeString().split(" ")[0];
      clockEl.textContent = `[TIME: ${timeStr} UTC]`;
    };
    updateClock();
    setInterval(updateClock, 1000);
  }

  // 2. Sistema de Modais Retrô (Lab Submission)
  const openModalBtns = document.querySelectorAll("[data-open-modal]");
  const closeModalBtns = document.querySelectorAll("[data-close-modal]");

  openModalBtns.forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const modalId = btn.getAttribute("data-open-modal");
      const modal = document.getElementById(modalId);
      if (modal) {
        modal.classList.add("active");
        document.body.style.overflow = "hidden";
      }
    });
  });

  const closeModal = (modal) => {
    if (modal) {
      modal.classList.remove("active");
      document.body.style.overflow = "";
    }
  };

  closeModalBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const modal = btn.closest(".modal-overlay");
      closeModal(modal);
    });
  });

  // Fechar modal clicando no backdrop escuro ou via ESC
  window.addEventListener("click", (e) => {
    if (e.target.classList.contains("modal-overlay")) {
      closeModal(e.target);
    }
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const activeModal = document.querySelector(".modal-overlay.active");
      if (activeModal) closeModal(activeModal);
    }
  });

  // 3. Admin Tab Switcher
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-pane");

  tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");

      tabBtns.forEach((b) => b.classList.remove("active"));
      tabContents.forEach((c) => (c.style.display = "none"));

      btn.classList.add("active");
      const activePane = document.getElementById(`tab-${targetTab}`);
      if (activePane) {
        activePane.style.display = "block";
      }
    });
  });

  // 4. Copiar link de compartilhamento
  const copyBtns = document.querySelectorAll("[data-copy-link]");
  copyBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      navigator.clipboard.writeText(window.location.href).then(() => {
        const originalText = btn.innerHTML;
        btn.innerHTML = "[COPIADO!]";
        setTimeout(() => {
          btn.innerHTML = originalText;
        }, 2000);
      });
    });
  });
});
