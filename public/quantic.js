(() => {
  const endpoint = "/api/quantic-portal/status";
  const labels = {
    online: "Disponible",
    offline: "Indisponible",
    pending: "Bientôt",
    unknown: "État inconnu",
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

  async function loadStatus() {
    setSummary("pending", "Vérification du réseau…");
    try {
      const response = await fetch(endpoint, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) throw new Error("status unavailable");
      const payload = await response.json();
      if (!payload || !Array.isArray(payload.services)) throw new Error("invalid status payload");

      let active = 0;
      let online = 0;
      payload.services.forEach((service) => {
        const state = service.state === "pending"
          ? "pending"
          : service.reachable === true
            ? "online"
            : service.reachable === false
              ? "offline"
              : "unknown";
        setServiceState(service.id, state);
        if (service.state !== "pending") {
          active += 1;
          if (state === "online") online += 1;
        }
      });

      if (!active) {
        setSummary("unknown", "État du réseau inconnu");
      } else if (online === active) {
        setSummary("online", `${online}/${active} services vérifiés`);
      } else if (online > 0) {
        setSummary("partial", `${online}/${active} services disponibles`);
      } else {
        setSummary("offline", "Services temporairement indisponibles");
      }
    } catch (_error) {
      document.querySelectorAll("[data-service-id]").forEach((card) => {
        const badge = card.querySelector("[data-service-state]");
        if (badge && badge.dataset.state !== "pending") {
          badge.dataset.state = "unknown";
          badge.textContent = labels.unknown;
        }
      });
      setSummary("unknown", "État du réseau inconnu");
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadStatus, { once: true });
  } else {
    loadStatus();
  }
})();