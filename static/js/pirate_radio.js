// ==========================================================================
// O REFÚGIO - RÁDIO PIRATA LO-FI (SERVIÇO DE ÁUDIO EM SEGUNDO PLANO)
// Clássicos Históricos de Protesto + Cena Contemporânea / 2026
// ==========================================================================

(function () {
  const STORAGE_KEY = "refugio_lofi_radio_state_v1";

  let playlist = [];
  let filteredPlaylist = [];
  let currentIndex = -1;
  let shuffleHistory = [];
  let ytPlayer = null;
  let ytApiReady = false;
  let isPlaying = false;
  let desiredAutoPlay = false;
  let pendingSeekSeconds = 0;
  let eraFilter = "all"; // 'all' | 'classics' | '2026'
  let volume = 80;
  let isMinimized = false;
  let isVideoVisible = false;
  let isDrawerOpen = false;
  let stateSaveInterval = null;

  function loadSavedState() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function saveState() {
    try {
      const currentTrack = filteredPlaylist[currentIndex] || null;
      let currentTime = pendingSeekSeconds || 0;
      if (ytPlayer && typeof ytPlayer.getCurrentTime === "function") {
        const t = ytPlayer.getCurrentTime();
        if (typeof t === "number" && !isNaN(t) && t > 0) {
          currentTime = Math.floor(t);
        }
      }
      const payload = {
        trackId: currentTrack ? currentTrack.id : null,
        youtubeId: currentTrack ? currentTrack.youtube_id : null,
        currentTime: currentTime,
        isPlaying: isPlaying,
        eraFilter: eraFilter,
        volume: volume,
        isMinimized: isMinimized,
        updatedAt: Date.now(),
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch (e) {
      // Ignore storage quota errors
    }
  }

  function isTrack2026(track) {
    const genre = (track.genre || "").toLowerCase();
    return genre.includes("2026") || genre.includes("contempor");
  }

  function isTrackClassic(track) {
    const genre = (track.genre || "").toLowerCase();
    if (genre.includes("clássico") || genre.includes("classico")) return true;
    return !isTrack2026(track);
  }

  function applyEraFilter(newFilter, preserveCurrentTrack = true) {
    eraFilter = newFilter || "all";
    const previousTrack = filteredPlaylist[currentIndex] || null;

    if (eraFilter === "2026") {
      filteredPlaylist = playlist.filter(isTrack2026);
    } else if (eraFilter === "classics") {
      filteredPlaylist = playlist.filter(isTrackClassic);
    } else {
      filteredPlaylist = [...playlist];
    }

    if (filteredPlaylist.length === 0) {
      filteredPlaylist = [...playlist];
    }

    // Update filter buttons UI
    document.querySelectorAll("[data-lofi-era]").forEach((btn) => {
      const btnEra = btn.getAttribute("data-lofi-era");
      if (btnEra === eraFilter) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });

    if (preserveCurrentTrack && previousTrack) {
      const foundIdx = filteredPlaylist.findIndex((t) => t.id === previousTrack.id);
      if (foundIdx !== -1) {
        currentIndex = foundIdx;
        renderDrawerList();
        saveState();
        return;
      }
    }

    // Pick a random track from the newly filtered list
    const nextIdx = pickRandomIndex();
    if (nextIdx !== -1) {
      loadTrackByIndex(nextIdx, isPlaying, 0);
    }
    renderDrawerList();
    saveState();
  }

  function pickRandomIndex() {
    if (!filteredPlaylist.length) return -1;
    if (filteredPlaylist.length === 1) return 0;

    const candidates = [];
    for (let i = 0; i < filteredPlaylist.length; i++) {
      if (i !== currentIndex) candidates.push(i);
    }
    const randomPick = candidates[Math.floor(Math.random() * candidates.length)];
    return randomPick;
  }

  function updateUIForTrack(track) {
    const titleEl = document.getElementById("lofi-track-title");
    const metaEl = document.getElementById("lofi-track-meta");
    const eraBadgeEl = document.getElementById("lofi-era-badge");
    const ytLinkEl = document.getElementById("lofi-yt-external");

    if (!track) {
      if (titleEl) titleEl.textContent = "Sem faixas cadastradas";
      if (metaEl) metaEl.textContent = "--";
      return;
    }

    const isModern = isTrack2026(track);
    if (titleEl) {
      titleEl.textContent = `${track.title} — ${track.artist}`;
    }
    if (metaEl) {
      metaEl.textContent = `[${track.country || "América Latina"}] // ${track.genre || "Protesto"}`;
    }
    if (eraBadgeEl) {
      eraBadgeEl.textContent = isModern ? "[SAFRA 2026]" : "[CLÁSSICO]";
      eraBadgeEl.className = isModern ? "lofi-era-tag era-2026" : "lofi-era-tag era-classic";
    }
    if (ytLinkEl) {
      ytLinkEl.href = `https://www.youtube.com/watch?v=${encodeURIComponent(track.youtube_id)}`;
    }

    // Sincroniza também elementos da página /radio caso ela esteja aberta
    const pageTitleEl = document.getElementById("radio-track-title");
    const pageArtistEl = document.getElementById("radio-track-artist");
    const pageCountryEl = document.getElementById("radio-track-country");
    const pageGenreEl = document.getElementById("radio-track-genre");
    const pageDescEl = document.getElementById("radio-track-desc");
    const pageVideoIdLabel = document.getElementById("radio-video-id-label");
    const pageYtExt = document.getElementById("radio-yt-external");

    if (pageTitleEl) pageTitleEl.textContent = track.title;
    if (pageArtistEl) pageArtistEl.textContent = track.artist;
    if (pageCountryEl) pageCountryEl.textContent = track.country || "América Latina";
    if (pageGenreEl) pageGenreEl.textContent = track.genre || "Protesto";
    if (pageDescEl) pageDescEl.textContent = track.description || "Transmissão da Rádio Pirata O Refúgio.";
    if (pageVideoIdLabel) pageVideoIdLabel.textContent = "ID: " + track.youtube_id;
    if (pageYtExt) pageYtExt.href = `https://www.youtube.com/watch?v=${encodeURIComponent(track.youtube_id)}`;

    renderDrawerList();
  }

  function updatePlaybackUI(playing) {
    isPlaying = playing;
    const playBtn = document.getElementById("lofi-play-btn");
    const statusBadge = document.getElementById("lofi-status-badge");
    const eqBox = document.getElementById("lofi-eq");
    const tickerBtn = document.getElementById("ticker-radio-toggle");
    const barEl = document.getElementById("lofi-pirate-radio-bar");

    if (playBtn) {
      playBtn.textContent = playing ? "[⏸ PAUSAR]" : "[▶ TOCAR LO-FI]";
      if (playing) {
        playBtn.classList.add("playing");
      } else {
        playBtn.classList.remove("playing");
      }
    }

    if (statusBadge) {
      statusBadge.textContent = playing ? "[NO AR // 99.9 FM]" : "[STANDBY // 99.9 FM]";
      statusBadge.className = playing ? "lofi-status-badge on-air" : "lofi-status-badge";
    }

    if (eqBox) {
      if (playing) {
        eqBox.classList.add("active");
      } else {
        eqBox.classList.remove("active");
      }
    }

    if (tickerBtn) {
      tickerBtn.textContent = playing
        ? "[99.9 FM: NO AR ⏸ PAUSAR]"
        : "[99.9 FM: RÁDIO PIRATA ▶ TOCAR]";
    }

    if (barEl) {
      if (playing) {
        barEl.classList.add("is-playing");
      } else {
        barEl.classList.remove("is-playing");
      }
    }

    const pageStatusEl = document.getElementById("radio-status-indicator");
    const pagePlayBtn = document.getElementById("radio-play-btn");
    if (pageStatusEl) {
      pageStatusEl.textContent = playing ? "[STATUS: TRANSMITINDO NO AR]" : "[STATUS: TRANSMISSÃO EM PAUSA]";
    }
    if (pagePlayBtn) {
      pagePlayBtn.textContent = playing ? "[⏸ PAUSAR TRANSMISSÃO]" : "[▶ TOCAR / RETOMAR]";
    }

    saveState();
  }

  function renderDrawerList() {
    const listContainer = document.getElementById("lofi-drawer-list");
    const countSpan = document.getElementById("lofi-drawer-count");
    if (countSpan) {
      countSpan.textContent = `${filteredPlaylist.length} FAIXAS`;
    }
    if (!listContainer) return;

    listContainer.innerHTML = "";
    filteredPlaylist.forEach((track, idx) => {
      const item = document.createElement("div");
      const active = idx === currentIndex;
      const isModern = isTrack2026(track);
      item.className = `lofi-drawer-item ${active ? "active" : ""}`;
      item.innerHTML = `
        <div class="lofi-drawer-item-info">
          <span class="lofi-drawer-item-title">${active ? "▶ " : ""}${escapeHtml(track.title)} — <strong>${escapeHtml(track.artist)}</strong></span>
          <span class="lofi-drawer-item-sub">[${escapeHtml(track.country || "LatAm")}] ${escapeHtml(track.genre || "Protesto")}</span>
        </div>
        <span class="lofi-era-tag ${isModern ? "era-2026" : "era-classic"}">${isModern ? "2026" : "CLÁSSICO"}</span>
      `;
      item.addEventListener("click", () => {
        loadTrackByIndex(idx, true, 0);
      });
      listContainer.appendChild(item);
    });
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function loadTrackByIndex(idx, autoPlay = true, startSeconds = 0) {
    if (idx < 0 || idx >= filteredPlaylist.length) return;
    currentIndex = idx;
    const track = filteredPlaylist[currentIndex];
    if (
      shuffleHistory.length === 0 ||
      shuffleHistory[shuffleHistory.length - 1] !== idx
    ) {
      shuffleHistory.push(idx);
    }

    pendingSeekSeconds = startSeconds || 0;
    desiredAutoPlay = autoPlay;
    updateUIForTrack(track);

    if (ytPlayer && typeof ytPlayer.loadVideoById === "function") {
      if (autoPlay) {
        ytPlayer.loadVideoById({
          videoId: track.youtube_id,
          startSeconds: pendingSeekSeconds,
        });
        updatePlaybackUI(true);
      } else {
        ytPlayer.cueVideoById({
          videoId: track.youtube_id,
          startSeconds: pendingSeekSeconds,
        });
        updatePlaybackUI(false);
      }
    } else if (autoPlay) {
      ensureYouTubePlayer();
    }

    saveState();
  }

  function togglePlayPause() {
    if (!filteredPlaylist.length) return;
    if (currentIndex === -1) {
      currentIndex = pickRandomIndex();
    }

    if (!ytPlayer || typeof ytPlayer.getPlayerState !== "function") {
      desiredAutoPlay = true;
      updatePlaybackUI(true);
      ensureYouTubePlayer();
      return;
    }

    const state = ytPlayer.getPlayerState();
    // YT.PlayerState.PLAYING === 1, BUFFERING === 3
    if (state === 1 || state === 3 || isPlaying) {
      ytPlayer.pauseVideo();
      updatePlaybackUI(false);
    } else {
      ytPlayer.playVideo();
      updatePlaybackUI(true);
    }
  }

  function playNextRandom() {
    const nextIdx = pickRandomIndex();
    if (nextIdx !== -1) {
      loadTrackByIndex(nextIdx, true, 0);
    }
  }

  function playPrevTrack() {
    if (shuffleHistory.length > 1) {
      shuffleHistory.pop();
      const prevIdx = shuffleHistory.pop();
      if (typeof prevIdx === "number" && prevIdx >= 0 && prevIdx < filteredPlaylist.length) {
        loadTrackByIndex(prevIdx, true, 0);
        return;
      }
    }
    playNextRandom();
  }

  function ensureYouTubePlayer() {
    if (ytPlayer) return;

    if (window.YT && window.YT.Player) {
      createPlayerInstance();
      return;
    }

    if (!document.getElementById("refugio-yt-iframe-api")) {
      const tag = document.createElement("script");
      tag.id = "refugio-yt-iframe-api";
      tag.src = "https://www.youtube.com/iframe_api";
      const firstScriptTag = document.getElementsByTagName("script")[0];
      firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
    }

    const prevCallback = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = function () {
      if (typeof prevCallback === "function") prevCallback();
      ytApiReady = true;
      createPlayerInstance();
    };
  }

  function createPlayerInstance() {
    if (ytPlayer) return;
    const mountEl = document.getElementById("lofi-yt-mount");
    if (!mountEl) return;

    const initialTrack = filteredPlaylist[currentIndex] || filteredPlaylist[0];
    if (!initialTrack) return;

    ytPlayer = new window.YT.Player("lofi-yt-mount", {
      height: "180",
      width: "320",
      videoId: initialTrack.youtube_id,
      playerVars: {
        autoplay: desiredAutoPlay ? 1 : 0,
        controls: 1,
        rel: 0,
        modestbranding: 1,
        playsinline: 1,
        start: pendingSeekSeconds || 0,
      },
      events: {
        onReady: (event) => {
          event.target.setVolume(volume);
          if (pendingSeekSeconds > 0) {
            event.target.seekTo(pendingSeekSeconds, true);
          }
          if (desiredAutoPlay) {
            event.target.playVideo();
            updatePlaybackUI(true);
          }
        },
        onStateChange: (event) => {
          if (event.data === window.YT.PlayerState.PLAYING) {
            updatePlaybackUI(true);
          } else if (event.data === window.YT.PlayerState.PAUSED) {
            updatePlaybackUI(false);
          } else if (event.data === window.YT.PlayerState.ENDED) {
            playNextRandom();
          }
        },
        onError: () => {
          // Auto-skip if a video is restricted or unavailable
          setTimeout(() => {
            playNextRandom();
          }, 800);
        },
      },
    });
  }

  // ==========================================================================
  // SOFT NAVIGATION (PJAX) PARA MANTER O ÁUDIO CONTÍNUO ENTRE ABAS/POSTS
  // ==========================================================================
  function shouldInterceptLink(anchor) {
    if (!anchor || !anchor.href) return false;
    if (anchor.target && anchor.target !== "_self") return false;
    if (anchor.hasAttribute("download") || anchor.hasAttribute("data-no-pjax")) return false;

    let url;
    try {
      url = new URL(anchor.href, window.location.origin);
    } catch (e) {
      return false;
    }

    if (url.origin !== window.location.origin) return false;
    // Ignore same-page hash changes
    if (url.pathname === window.location.pathname && url.search === window.location.search && url.hash) {
      return false;
    }

    // Paths that should do full navigation (auth/admin/static/api)
    const excludedPrefixes = ["/admin", "/login", "/logout", "/register", "/api/", "/static/", "/feed.xml"];
    for (const prefix of excludedPrefixes) {
      if (url.pathname.startsWith(prefix)) return false;
    }

    return true;
  }

  async function navigateSoftly(urlString, pushState = true) {
    try {
      const response = await fetch(urlString, {
        headers: { "X-Requested-With": "RefugioLoFiPJAX" },
        credentials: "same-origin",
      });
      if (!response.ok) {
        window.location.href = urlString;
        return;
      }

      const htmlText = await response.text();
      const parser = new DOMParser();
      const doc = parser.parseFromString(htmlText, "text/html");

      const newMain = doc.querySelector("main");
      const currentMain = document.querySelector("main");
      if (!newMain || !currentMain) {
        window.location.href = urlString;
        return;
      }

      currentMain.innerHTML = newMain.innerHTML;
      document.title = doc.title || document.title;

      // Update active state in main-nav
      const newNav = doc.querySelector(".main-nav");
      const currentNav = document.querySelector(".main-nav");
      if (newNav && currentNav) {
        currentNav.innerHTML = newNav.innerHTML;
      }

      // Replace page-specific modals if any
      const newLabModal = doc.getElementById("lab-submit-modal");
      const currentLabModal = document.getElementById("lab-submit-modal");
      if (newLabModal && !currentLabModal) {
        document.body.appendChild(newLabModal);
      } else if (newLabModal && currentLabModal) {
        currentLabModal.outerHTML = newLabModal.outerHTML;
      }

      if (pushState) {
        window.history.pushState({ pjax: true, url: urlString }, doc.title, urlString);
      }

      window.scrollTo({ top: 0, behavior: "smooth" });
      rebindDynamicPageElements();
    } catch (err) {
      window.location.href = urlString;
    }
  }

  function rebindDynamicPageElements() {
    // Rebind copy buttons
    document.querySelectorAll("[data-copy-link]").forEach((btn) => {
      btn.onclick = () => {
        navigator.clipboard.writeText(window.location.href).then(() => {
          const originalText = btn.innerHTML;
          btn.innerHTML = "[COPIADO!]";
          setTimeout(() => {
            btn.innerHTML = originalText;
          }, 2000);
        });
      };
    });

    // Rebind modal openers
    document.querySelectorAll("[data-open-modal]").forEach((btn) => {
      btn.onclick = (e) => {
        e.preventDefault();
        const modalId = btn.getAttribute("data-open-modal");
        const modal = document.getElementById(modalId);
        if (modal) {
          modal.classList.add("active");
          document.body.style.overflow = "hidden";
        }
      };
    });

    document.querySelectorAll("[data-close-modal]").forEach((btn) => {
      btn.onclick = () => {
        const modal = btn.closest(".modal-overlay");
        if (modal) {
          modal.classList.remove("active");
          document.body.style.overflow = "";
        }
      };
    });
  }

  function bindGlobalEvents() {
    const playBtn = document.getElementById("lofi-play-btn");
    const nextBtn = document.getElementById("lofi-next-btn");
    const prevBtn = document.getElementById("lofi-prev-btn");
    const volSlider = document.getElementById("lofi-volume");
    const minBtn = document.getElementById("lofi-minimize-btn");
    const videoBtn = document.getElementById("lofi-video-btn");
    const drawerBtn = document.getElementById("lofi-playlist-btn");
    const drawerCloseBtn = document.getElementById("lofi-drawer-close");
    const tickerToggle = document.getElementById("ticker-radio-toggle");
    const footerToggle = document.getElementById("footer-radio-toggle");
    const barEl = document.getElementById("lofi-pirate-radio-bar");
    const videoBox = document.getElementById("lofi-video-popover");
    const drawerBox = document.getElementById("lofi-playlist-drawer");

    if (playBtn) playBtn.addEventListener("click", togglePlayPause);
    if (nextBtn) nextBtn.addEventListener("click", playNextRandom);
    if (prevBtn) prevBtn.addEventListener("click", playPrevTrack);

    if (tickerToggle) {
      tickerToggle.addEventListener("click", (e) => {
        e.preventDefault();
        if (isMinimized && barEl) {
          isMinimized = false;
          barEl.classList.remove("minimized");
        }
        togglePlayPause();
      });
    }

    if (footerToggle) {
      footerToggle.addEventListener("click", (e) => {
        e.preventDefault();
        if (isMinimized && barEl) {
          isMinimized = false;
          barEl.classList.remove("minimized");
        }
        togglePlayPause();
      });
    }

    if (volSlider) {
      volSlider.addEventListener("input", (e) => {
        volume = parseInt(e.target.value, 10) || 0;
        if (ytPlayer && typeof ytPlayer.setVolume === "function") {
          ytPlayer.setVolume(volume);
        }
        saveState();
      });
    }

    document.querySelectorAll("[data-lofi-era]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const selectedEra = btn.getAttribute("data-lofi-era") || "all";
        applyEraFilter(selectedEra, false);
      });
    });

    if (minBtn && barEl) {
      minBtn.addEventListener("click", () => {
        isMinimized = !isMinimized;
        if (isMinimized) {
          barEl.classList.add("minimized");
          minBtn.textContent = "[▲ EXPANDIR RÁDIO]";
        } else {
          barEl.classList.remove("minimized");
          minBtn.textContent = "[▼ MINIMIZAR]";
        }
        saveState();
      });
    }

    if (videoBtn && videoBox) {
      videoBtn.addEventListener("click", () => {
        isVideoVisible = !isVideoVisible;
        if (isVideoVisible) {
          videoBox.classList.add("visible");
          videoBtn.classList.add("active");
          ensureYouTubePlayer();
        } else {
          videoBox.classList.remove("visible");
          videoBtn.classList.remove("active");
        }
      });
    }

    if (drawerBtn && drawerBox) {
      drawerBtn.addEventListener("click", () => {
        isDrawerOpen = !isDrawerOpen;
        drawerBox.style.display = isDrawerOpen ? "block" : "none";
        if (isDrawerOpen) {
          drawerBtn.classList.add("active");
          renderDrawerList();
        } else {
          drawerBtn.classList.remove("active");
        }
      });
    }

    if (drawerCloseBtn && drawerBox) {
      drawerCloseBtn.addEventListener("click", () => {
        isDrawerOpen = false;
        drawerBox.style.display = "none";
        if (drawerBtn) drawerBtn.classList.remove("active");
      });
    }

    // Intercept internal links with PJAX so background music never interrupts
    document.addEventListener("click", (e) => {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
        return;
      }
      const anchor = e.target.closest("a");
      if (!anchor) return;
      if (!shouldInterceptLink(anchor)) return;

      e.preventDefault();
      navigateSoftly(anchor.href, true);
    });

    window.addEventListener("popstate", () => {
      navigateSoftly(window.location.href, false);
    });

    window.addEventListener("beforeunload", () => {
      saveState();
    });
  }

  async function initPirateRadioService() {
    const barEl = document.getElementById("lofi-pirate-radio-bar");
    if (!barEl) return;

    bindGlobalEvents();

    const saved = loadSavedState();
    if (saved) {
      if (typeof saved.volume === "number") {
        volume = saved.volume;
        const volSlider = document.getElementById("lofi-volume");
        if (volSlider) volSlider.value = String(volume);
      }
      if (saved.eraFilter) {
        eraFilter = saved.eraFilter;
      }
      if (saved.isMinimized) {
        isMinimized = true;
        barEl.classList.add("minimized");
        const minBtn = document.getElementById("lofi-minimize-btn");
        if (minBtn) minBtn.textContent = "[▲ EXPANDIR RÁDIO]";
      }
    }

    try {
      const res = await fetch("/api/radio/playlist");
      if (!res.ok) return;
      const data = await res.json();
      playlist = Array.isArray(data.tracks) ? data.tracks : [];
    } catch (err) {
      playlist = [];
    }

    if (!playlist.length) {
      updateUIForTrack(null);
      return;
    }

    // Filter according to saved era
    if (eraFilter === "2026") {
      filteredPlaylist = playlist.filter(isTrack2026);
    } else if (eraFilter === "classics") {
      filteredPlaylist = playlist.filter(isTrackClassic);
    } else {
      filteredPlaylist = [...playlist];
    }
    if (!filteredPlaylist.length) filteredPlaylist = [...playlist];

    document.querySelectorAll("[data-lofi-era]").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-lofi-era") === eraFilter);
    });

    // Restore saved track or pick a random starting track
    let initialIdx = -1;
    let resumeTime = 0;
    let shouldResumePlay = false;

    if (saved && saved.trackId) {
      initialIdx = filteredPlaylist.findIndex((t) => t.id === saved.trackId);
      if (initialIdx !== -1) {
        resumeTime = saved.currentTime || 0;
        // Resume automatically if it was playing recently (within last 30 mins)
        if (saved.isPlaying && saved.updatedAt && Date.now() - saved.updatedAt < 30 * 60 * 1000) {
          shouldResumePlay = true;
        }
      }
    }

    if (initialIdx === -1) {
      initialIdx = pickRandomIndex();
    }

    currentIndex = initialIdx;
    shuffleHistory.push(currentIndex);
    updateUIForTrack(filteredPlaylist[currentIndex]);

    if (shouldResumePlay) {
      pendingSeekSeconds = resumeTime;
      desiredAutoPlay = true;
      ensureYouTubePlayer();
    }

    if (stateSaveInterval) clearInterval(stateSaveInterval);
    stateSaveInterval = setInterval(() => {
      if (isPlaying) saveState();
    }, 2000);
  }

  function playTrackById(trackId) {
    const idNum = Number(trackId);
    let idx = filteredPlaylist.findIndex((t) => Number(t.id) === idNum);
    if (idx === -1) {
      applyEraFilter("all", true);
      idx = filteredPlaylist.findIndex((t) => Number(t.id) === idNum);
    }
    if (idx !== -1) {
      loadTrackByIndex(idx, true, 0);
    }
  }

  // Expose API globally for external buttons or diagnostics
  window.RefugioPirateRadio = {
    togglePlayPause,
    playNextRandom,
    playPrevTrack,
    playTrackById,
    applyEraFilter,
    getPlaylist: () => playlist,
    getCurrentTrack: () => filteredPlaylist[currentIndex] || null,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initPirateRadioService);
  } else {
    initPirateRadioService();
  }
})();
