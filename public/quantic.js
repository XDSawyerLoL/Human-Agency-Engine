(() => {
  const endpoint = "/api/quantic-portal/status";
  const STATUS_TIMEOUT_MS = 6500;
  const labels = {
    online: "Disponible",
    offline: "Indisponible",
    pending: "Bientôt",
    checking: "Vérification…",
    unknown: "Non vérifié",
  };

  function setServiceState(id, state) {
    document.querySelectorAll(`[data-service-id="${id}"]`).forEach((card) => {
      const badge = card.querySelector("[data-service-state]");
      if (!badge) return;
      badge.dataset.state = state;
      badge.textContent = labels[state] || labels.unknown;
    });
  }

  function setSummary(state, text) {
    document.querySelectorAll("[data-quantic-status-summary]").forEach((summary) => {
      const dot = summary.querySelector(".q-status-dot");
      const label = summary.querySelector("[data-status-label]");
      if (dot) dot.className = `q-status-dot is-${state}`;
      if (label) label.textContent = text;
    });
  }

  function setContinuity(state, text) {
    document.querySelectorAll("[data-network-continuity]").forEach((card) => {
      const badge = card.querySelector("[data-network-continuity-state]");
      if (!badge) return;
      badge.dataset.state = state;
      badge.textContent = text;
    });
  }

  function summarizeContinuity(serviceStates) {
    const relays = ["relay-render", "relay-railway", "relay-hostinger"]
      .map((id) => serviceStates.get(id))
      .filter(Boolean);

    if (!relays.length || relays.every((state) => state === "unknown")) {
      setContinuity("unknown", "Non vérifié");
      return;
    }
    if (relays.some((state) => state === "online")) {
      setContinuity("online", "Chemin disponible");
      return;
    }
    if (relays.every((state) => state === "pending")) {
      setContinuity("pending", "En préparation");
      return;
    }
    setContinuity("offline", "Indisponible");
  }

  async function fetchStatus() {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), STATUS_TIMEOUT_MS);
    try {
      return await fetch(endpoint, {
        headers: { Accept: "application/json" },
        cache: "no-store",
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }
  }

  async function loadStatus() {
    if (!document.querySelector("[data-quantic-status-summary],[data-service-id],[data-network-continuity]")) return;

    setSummary("pending", "Vérification des services…");
    document.querySelectorAll("[data-service-state]").forEach((badge) => {
      badge.dataset.state = "checking";
      badge.textContent = labels.checking;
    });
    setContinuity("checking", labels.checking);

    try {
      const response = await fetchStatus();
      if (!response.ok) throw new Error("status unavailable");
      const payload = await response.json();
      if (!payload || !Array.isArray(payload.services)) throw new Error("invalid status payload");

      let active = 0;
      let online = 0;
      const serviceStates = new Map();

      payload.services.forEach((service) => {
        const state = service.state === "pending"
          ? "pending"
          : service.reachable === true
            ? "online"
            : service.reachable === false
              ? "offline"
              : "unknown";

        serviceStates.set(service.id, state);
        setServiceState(service.id, state);

        if (service.state !== "pending") {
          active += 1;
          if (state === "online") online += 1;
        }
      });

      summarizeContinuity(serviceStates);

      if (!active) setSummary("unknown", "Monitoring indisponible");
      else if (online === active) setSummary("online", "Services principaux disponibles");
      else if (online > 0) setSummary("partial", "Service partiellement disponible");
      else setSummary("offline", "Services temporairement indisponibles");
    } catch (_error) {
      document.querySelectorAll("[data-service-state]").forEach((badge) => {
        badge.dataset.state = "unknown";
        badge.textContent = labels.unknown;
      });
      setContinuity("unknown", labels.unknown);
      setSummary("unknown", "Monitoring indisponible");
    }
  }

  function initReveal() {
    const targets = [...document.querySelectorAll("[data-q-reveal]")];
    if (!targets.length) return;
    if (!("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      targets.forEach((el) => el.classList.add("is-visible"));
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    targets.forEach((el) => observer.observe(el));
  }

  function initPointerDepth() {
    if (window.matchMedia("(pointer: coarse)").matches || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    document.querySelectorAll("[data-q-tilt]").forEach((card) => {
      card.addEventListener("pointermove", (event) => {
        const rect = card.getBoundingClientRect();
        const px = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
        const py = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
        card.style.setProperty("--pointer-x", `${(px * 100).toFixed(2)}%`);
        card.style.setProperty("--pointer-y", `${(py * 100).toFixed(2)}%`);
        card.style.setProperty("--tilt-y", `${((px - .5) * 3.2).toFixed(2)}deg`);
        card.style.setProperty("--tilt-x", `${((.5 - py) * 3.2).toFixed(2)}deg`);
      });
      card.addEventListener("pointerleave", () => {
        card.style.removeProperty("--tilt-x");
        card.style.removeProperty("--tilt-y");
        card.style.removeProperty("--pointer-x");
        card.style.removeProperty("--pointer-y");
      });
    });
  }

  function boot() {
    initReveal();
    initPointerDepth();
    void loadStatus();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();