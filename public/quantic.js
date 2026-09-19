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

  function setServiceState(id, state, metaText = "") {
    document.querySelectorAll(`[data-service-id="${id}"]`).forEach((card) => {
      const badge = card.querySelector("[data-service-state]");
      const meta = card.querySelector("[data-service-meta]");
      if (badge) {
        badge.dataset.state = state;
        badge.textContent = labels[state] || labels.unknown;
      }
      if (meta && metaText) meta.textContent = metaText;
    });
  }

  function setSummary(state, text, metaText = "") {
    document.querySelectorAll("[data-quantic-status-summary]").forEach((summary) => {
      const dot = summary.querySelector(".q-status-dot");
      const label = summary.querySelector("[data-status-label]");
      const meta = summary.querySelector("[data-status-meta]");
      if (dot) dot.className = `q-status-dot is-${state}`;
      if (label) label.textContent = text;
      if (meta && metaText) meta.textContent = metaText;
    });
  }

  function timeLabel(value = new Date()) {
    const d = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(d.getTime())) return "heure indisponible";
    return new Intl.DateTimeFormat("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(d);
  }

  function serviceMeta(service, fallbackTime) {
    const latency = Number(service?.latency_ms ?? service?.latencyMs ?? service?.latency);
    const checkedAt = service?.checked_at ?? service?.checkedAt ?? fallbackTime;
    const parts = [`Vérifié à ${timeLabel(checkedAt)}`];
    if (Number.isFinite(latency) && latency >= 0) parts.push(`${Math.round(latency)} ms`);
    return parts.join(" · ");
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

  let statusLoading = false;
  let lastSuccessfulCheck = null;

  async function loadStatus() {
    if (!document.querySelector("[data-quantic-status-summary],[data-service-id],[data-network-continuity]")) return;
    if (statusLoading) return;
    statusLoading = true;

    const startedAt = performance.now();
    const attemptedAt = new Date();
    setSummary("pending", "Vérification des services…", `Tentative à ${timeLabel(attemptedAt)}`);
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
        setServiceState(service.id, state, serviceMeta(service, payload.checked_at ?? payload.checkedAt ?? new Date()));

        if (service.state !== "pending") {
          active += 1;
          if (state === "online") online += 1;
        }
      });

      summarizeContinuity(serviceStates);

      lastSuccessfulCheck = new Date();
      const requestLatency = Math.max(0, Math.round(performance.now() - startedAt));
      const summaryMeta = `Dernière vérification ${timeLabel(lastSuccessfulCheck)} · monitoring ${requestLatency} ms`;
      document.querySelectorAll("[data-continuity-meta]").forEach((meta) => {
        meta.textContent = `Calculé à ${timeLabel(lastSuccessfulCheck)} sur ${serviceStates.size} services surveillés`;
      });

      if (!active) setSummary("unknown", "Monitoring indisponible", summaryMeta);
      else if (online === active) setSummary("online", "Services principaux disponibles", summaryMeta);
      else if (online > 0) setSummary("partial", "Service partiellement disponible", summaryMeta);
      else setSummary("offline", "Services temporairement indisponibles", summaryMeta);
    } catch (_error) {
      document.querySelectorAll("[data-service-state]").forEach((badge) => {
        badge.dataset.state = "unknown";
        badge.textContent = labels.unknown;
      });
      document.querySelectorAll("[data-service-meta]").forEach((meta) => {
        meta.textContent = `Tentative à ${timeLabel(attemptedAt)} · aucune mesure reçue`;
      });
      setContinuity("unknown", labels.unknown);
      const prior = lastSuccessfulCheck ? `Dernier succès ${timeLabel(lastSuccessfulCheck)}` : "Aucun contrôle réussi dans cette session";
      setSummary("unknown", "Monitoring indisponible", `Dernière tentative ${timeLabel(attemptedAt)} · ${prior}`);
    } finally {
      statusLoading = false;
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
    document.querySelectorAll("[data-network-refresh]").forEach((button) => {
      button.addEventListener("click", () => void loadStatus());
    });
    if (document.querySelector("[data-quantic-status-summary]")) {
      setInterval(() => void loadStatus(), 60000);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();