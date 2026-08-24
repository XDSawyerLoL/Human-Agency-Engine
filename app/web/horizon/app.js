const desktopMode = new URLSearchParams(window.location.search).get("desktop") === "1";
const state = {
  apiKey: sessionStorage.getItem("horizon_api_key") || "",
  externalId: sessionStorage.getItem("horizon_external_id") || (desktopMode ? "desktop-local" : ""),
  briefing: null,
  category: "all",
};

const icons = {
  weather_climate: "☼",
  natural_hazards: "⌁",
  social_collective_behavior: "◎",
  transport_mobility: "↔",
  supply_fuel: "◇",
  energy: "ϟ",
  media_attention: "◉",
  geopolitics_security: "⌖",
  economy_labor: "▦",
  public_health: "+",
  cyber_technology: "⌘",
  regulation_policy: "§",
  financial_stress: "∿",
  personal_context: "◌",
};

const maturityLabel = {
  historically_calibratable: "historique",
  live_multi_source: "multi-source",
  live_single_source: "source live",
  discovery_only: "détection",
  source_only: "source",
  missing: "à construire",
  personalized: "personnalisé",
};

const maturityWidth = {
  historically_calibratable: 100,
  live_multi_source: 78,
  live_single_source: 60,
  discovery_only: 42,
  source_only: 28,
  missing: 10,
  personalized: 86,
};

const q = (selector) => document.querySelector(selector);
const qa = (selector) => [...document.querySelectorAll(selector)];

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  })[char]);
}

function relativeTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  const seconds = Math.max(0, (Date.now() - date.getTime()) / 1000);
  if (seconds < 3600) return `${Math.max(1, Math.round(seconds / 60))} min`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h`;
  return `${Math.round(seconds / 86400)} j`;
}

function categoryName(category) {
  return {
    weather: "Météo", social: "Social", economy: "Économie",
    geopolitics: "Géopolitique", infrastructure: "Infrastructure",
    personal: "Personnel", other: "Autre",
  }[category] || category;
}

function setConnection(online, text) {
  const badge = q("#connectionBadge");
  badge.classList.toggle("online", online);
  badge.classList.toggle("offline", !online);
  badge.querySelector("span").textContent = text;
}

function openSettings() {
  q("#settingsPanel").classList.add("open");
  q("#settingsPanel").setAttribute("aria-hidden", "false");
  q("#apiKeyInput").value = state.apiKey;
  q("#externalIdInput").value = state.externalId;
}
function closeSettings() {
  q("#settingsPanel").classList.remove("open");
  q("#settingsPanel").setAttribute("aria-hidden", "true");
}

async function apiFetch(path) {
  const headers = {};
  if (state.apiKey) headers["X-API-Key"] = state.apiKey;
  const response = await fetch(path, { headers, cache: "no-store" });
  if (!response.ok) {
    const message = response.status === 401 ? "Clé API invalide." : `Erreur HORIZON (${response.status}).`;
    throw new Error(message);
  }
  return response.json();
}

function renderDomains() {
  const root = q("#domainGrid");
  const domains = (state.briefing?.domains || []).filter((domain) =>
    state.category === "all" || domain.macro_category === state.category
  );
  if (!domains.length) {
    root.innerHTML = '<div class="empty-state">Aucun domaine pour ce filtre.</div>';
    return;
  }
  root.classList.remove("empty-grid");
  root.innerHTML = "";
  for (const domain of domains) {
    const node = q("#domainTemplate").content.cloneNode(true);
    const card = node.querySelector(".domain-card");
    card.dataset.category = domain.macro_category;
    node.querySelector(".domain-icon").textContent = icons[domain.domain] || "·";
    const badge = node.querySelector(".maturity-badge");
    badge.textContent = maturityLabel[domain.current_maturity] || domain.current_maturity;
    node.querySelector("h3").textContent = domain.label;
    node.querySelector(".domain-events").textContent = domain.confirmed_events;
    node.querySelector(".domain-hypotheses").textContent = domain.emerging_hypotheses;
    node.querySelector(".maturity-track span").style.width =
      `${maturityWidth[domain.current_maturity] ?? 15}%`;
    node.querySelector(".domain-sources").textContent = `${domain.registered_sources} sources`;
    node.querySelector(".domain-mechanisms").textContent = `${domain.mechanisms} mécanismes`;
    root.appendChild(node);
  }
}

function combinedFeed() {
  const events = (state.briefing?.events || []).map((item) => ({ ...item, rank: 2 }));
  const hypotheses = (state.briefing?.hypotheses || []).map((item) => ({ ...item, rank: 1 }));
  return [...events, ...hypotheses]
    .filter((item) => state.category === "all" || item.macro_category === state.category)
    .sort((a, b) => new Date(b.observed_at) - new Date(a.observed_at))
    .slice(0, 40);
}

function renderFeed() {
  const root = q("#feedList");
  const items = combinedFeed();
  q("#feedCount").textContent = items.length;
  if (!items.length) {
    root.innerHTML = '<div class="empty-state">Aucun signal pour ce filtre.</div>';
    return;
  }
  root.innerHTML = items.map((item) => {
    const confirmed = item.kind === "confirmed_event";
    const statusClass = confirmed ? "status-confirmed" : "status-hypothesis";
    const statusText = confirmed ? "Confirmé" : "Hypothèse";
    const provisional = !confirmed && item.provisional_forecasts?.length
      ? item.provisional_forecasts[0]
      : null;
    const detail = confirmed
      ? (item.summary || `Source : ${item.source || "—"}`)
      : provisional
        ? `Hypothèse prédictive : ${provisional.predicted_response}`
        : "Épisode détecté par convergence de signaux, non encore confirmé.";
    return `
      <article class="feed-item">
        <div class="feed-top">
          <span class="status-chip ${statusClass}">${statusText}</span>
          <span class="feed-domain">${escapeHtml(item.domain_label)} · ${categoryName(item.macro_category)}</span>
        </div>
        <h4>${escapeHtml(item.title)}</h4>
        <p>${escapeHtml(detail)}</p>
        <div class="feed-meta">
          <span>${escapeHtml(item.event_type)}</span>
          <span>vu il y a ${relativeTime(item.observed_at)}</span>
          <span>${escapeHtml(item.maturity)}</span>
          ${provisional ? `<span>${escapeHtml(provisional.hypothesis_band)} · score diagnostic ${Math.round(provisional.provisional_score * 100)}/100</span>` : ""}
        </div>
      </article>`;
  }).join("");
}

function renderForecasts() {
  const root = q("#forecastList");
  const forecasts = (state.briefing?.personal_forecasts || [])
    .filter((item) => state.category === "all" || item.macro_category === state.category);
  if (!forecasts.length) {
    root.innerHTML = '<div class="empty-state">Aucune prévision personnelle active pour ce filtre.</div>';
    return;
  }
  root.innerHTML = forecasts.map((item) => {
    const chain = (item.behavior_chain || []).slice(0, 5)
      .map((part, index, array) => `<span>${escapeHtml(part)}</span>${index < array.length - 1 ? "<i>→</i>" : ""}`)
      .join("");
    const onset = item.expected_onset_low
      ? `${new Date(item.expected_onset_low).toLocaleString("fr-FR",{dateStyle:"short",timeStyle:"short"})} → ${item.expected_onset_high ? new Date(item.expected_onset_high).toLocaleString("fr-FR",{dateStyle:"short",timeStyle:"short"}) : "?"}`
      : "Fenêtre non établie";
    return `
      <article class="forecast-item">
        <div class="forecast-top">
          <span class="status-chip status-forecast">Prévision</span>
          <span class="likelihood">${escapeHtml(item.likelihood_band)}</span>
        </div>
        <h4>${escapeHtml(item.event_title)}</h4>
        <p>${escapeHtml(item.predicted_outcome)}</p>
        <div class="forecast-chain">${chain}</div>
        <div class="forecast-meta">
          <span>${escapeHtml(item.domain_label)}</span>
          <span>${escapeHtml(onset)}</span>
          <span>score diagnostic ${Math.round(item.predictive_score * 100)}/100</span>
        </div>
      </article>`;
  }).join("");
}

function render() {
  const body = state.briefing;
  if (!body) return;
  q("#metricEvents").textContent = body.summary.confirmed_events;
  q("#metricHypotheses").textContent = body.summary.emerging_hypotheses;
  q("#metricForecasts").textContent = body.summary.personal_forecasts;
  q("#metricDomains").textContent = body.summary.domains;
  q("#globalStatus").textContent = "Surveillance active";
  q("#globalStatusDetail").textContent =
    `${body.summary.confirmed_events} événements · ${body.summary.emerging_hypotheses} hypothèses · probabilités numériques désactivées`;
  renderDomains();
  renderFeed();
  renderForecasts();
}

async function loadBriefing() {
  q("#refreshButton").disabled = true;
  q("#globalStatus").textContent = "Synchronisation…";
  q("#globalStatusDetail").textContent = "Lecture du modèle du monde HORIZON.";
  try {
    const params = new URLSearchParams();
    if (state.externalId) params.set("external_id", state.externalId);
    state.briefing = await apiFetch(`/v1/horizon/world/briefing?${params}`);
    setConnection(true, desktopMode ? "Local" : "Connecté");
    render();
    q("#settingsError").textContent = "";
  } catch (error) {
    setConnection(false, "Erreur");
    q("#globalStatus").textContent = "Connexion requise";
    q("#globalStatusDetail").textContent = error.message;
    q("#settingsError").textContent = error.message;
    if (error.message.includes("Clé API")) openSettings();
  } finally {
    q("#refreshButton").disabled = false;
  }
}

q("#settingsButton").addEventListener("click", openSettings);
qa("[data-close-settings]").forEach((el) => el.addEventListener("click", closeSettings));
q("#refreshButton").addEventListener("click", loadBriefing);
q("#connectButton").addEventListener("click", async () => {
  state.apiKey = q("#apiKeyInput").value.trim();
  state.externalId = q("#externalIdInput").value.trim();
  sessionStorage.setItem("horizon_api_key", state.apiKey);
  sessionStorage.setItem("horizon_external_id", state.externalId);
  await loadBriefing();
  if (q("#connectionBadge").classList.contains("online")) closeSettings();
});
qa(".category-tab").forEach((button) => {
  button.addEventListener("click", () => {
    qa(".category-tab").forEach((el) => el.classList.remove("active"));
    button.classList.add("active");
    state.category = button.dataset.category;
    renderDomains();
    renderFeed();
    renderForecasts();
  });
});

async function desktopHeartbeat() {
  if (!desktopMode) return;
  try {
    await fetch("/desktop/heartbeat", { method: "POST", cache: "no-store" });
  } catch (_) {}
}

if (desktopMode) {
  desktopHeartbeat();
  setInterval(desktopHeartbeat, 10000);
  loadBriefing();
} else if (state.apiKey) {
  loadBriefing();
} else {
  openSettings();
}
