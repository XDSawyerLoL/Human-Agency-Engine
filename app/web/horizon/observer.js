async function observerApi(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.apiKey) headers["X-API-Key"] = state.apiKey;
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const response = await fetch(path, { ...options, headers, cache: "no-store" });
  if (!response.ok) {
    if (response.status === 401) throw new Error("Clé API requise pour modifier le warehouse.");
    throw new Error(`HORIZON observer (${response.status})`);
  }
  return response.json();
}

function renderKnowledgeSources(payload) {
  const root = q("#behaviorSourceGrid");
  const sources = payload?.sources || [];
  if (!sources.length) {
    root.innerHTML = '<div class="empty-state">Aucune source comportementale déclarée.</div>';
    return;
  }
  root.innerHTML = sources.map((source) => `
    <article class="source-card">
      <h3>${escapeHtml(source.name)}</h3>
      <div class="knowledge-meta"><span>${escapeHtml(source.kind)}</span></div>
      <p>${escapeHtml(source.coverage)}</p>
      <span class="source-status">${source.runtime_adapter ? "connecteur actif" : "catalogue / ingestion contrôlée"}</span>
    </article>`).join("");
}

function cameraVisual(camera) {
  if (camera.embed_url) {
    return `<iframe src="${escapeHtml(camera.embed_url)}" title="${escapeHtml(camera.label)}" loading="lazy" referrerpolicy="no-referrer" sandbox="allow-scripts allow-same-origin allow-popups"></iframe>`;
  }
  if (camera.preview_url) {
    return `<a href="${escapeHtml(camera.public_page_url)}" target="_blank" rel="noopener noreferrer"><img src="${escapeHtml(camera.preview_url)}" alt="${escapeHtml(camera.label)}" loading="lazy"></a>`;
  }
  return '<div class="camera-placeholder">Flux public déclaré sans aperçu intégrable.</div>';
}

function renderCameras(payload) {
  const root = q("#cameraGrid");
  const cameras = payload?.cameras || [];
  q("#cameraCount").textContent = cameras.length;
  if (!cameras.length) {
    const windyConfigured = payload?.configuration?.windy_webcams_adapter_enabled;
    root.innerHTML = `
      <div class="empty-state">
        ${windyConfigured
          ? "Aucune webcam publique n'a été retournée pour ce filtre."
          : "Aucune webcam autorisée n'est configurée. Ajoutez une source autorisée ou une clé Windy Webcams pour alimenter le Public Reality Lab."}
        HORIZON n'explore pas des flux CCTV au hasard : il affiche uniquement les sources prévues pour une diffusion publique.
      </div>`;
    return;
  }
  root.innerHTML = cameras.map((camera) => `
    <article class="camera-card">
      <div class="camera-visual">${cameraVisual(camera)}</div>
      <div class="camera-body">
        <div class="camera-meta">
          <span class="camera-badge ${camera.analysis_authorized ? "" : "observe-only"}">${camera.analysis_authorized ? "analyse autorisée" : "affichage seulement"}</span>
          <span>${escapeHtml(camera.provider)}</span>
        </div>
        <h3>${escapeHtml(camera.label)}</h3>
        <div class="camera-meta"><span>${escapeHtml(camera.location_label)}</span></div>
        ${camera.attribution ? `<div class="camera-meta"><span>${escapeHtml(camera.attribution)}</span></div>` : ""}
        <a class="camera-link" href="${escapeHtml(camera.public_page_url)}" target="_blank" rel="noopener noreferrer">Source officielle ↗</a>
      </div>
    </article>`).join("");
}

function renderKnowledgeResults(payload) {
  const root = q("#behaviorKnowledgeResults");
  const results = payload?.results || [];
  if (!results.length) {
    root.innerHTML = '<div class="empty-state">Aucun résultat exploitable retourné.</div>';
    return;
  }
  root.innerHTML = results.slice(0, 24).map((item) => `
    <article class="knowledge-card">
      <div class="knowledge-meta">
        <span>${escapeHtml(item.source)}</span>
        <span>${escapeHtml(item.publication_year || "—")}</span>
        ${item.cited_by_count != null ? `<span>${escapeHtml(item.cited_by_count)} citations</span>` : ""}
      </div>
      <h3 class="knowledge-title">${escapeHtml(item.title || "Sans titre")}</h3>
      <p class="knowledge-abstract">${escapeHtml(item.abstract || "Résumé non disponible dans cette source.")}</p>
      <div class="knowledge-meta">
        <span>${escapeHtml(item.venue || item.work_type || "")}</span>
        ${item.open_access === true ? "<span>open access</span>" : ""}
      </div>
    </article>`).join("");
}

function renderWarehouseStatus(payload) {
  if (!payload) return;
  q("#warehouseDocuments").textContent = payload.documents ?? 0;
  q("#warehouseEffects").textContent = payload.effects?.total ?? 0;
  q("#warehouseAccepted").textContent = payload.effects?.accepted ?? 0;
  q("#warehouseCandidates").textContent = payload.effects?.candidate ?? 0;
  const sources = payload.sources?.length ? payload.sources.join(" · ") : "aucune source indexée";
  const mechanisms = payload.mechanisms?.length ? payload.mechanisms.join(" · ") : "aucun effet structuré";
  q("#warehouseStatus").textContent = `${sources} — ${mechanisms}. Les documents trouvés ne modifient jamais seuls les prédictions.`;
}

async function loadWarehouseStatus() {
  try {
    const payload = await observerApi("/v1/horizon/behavioral-warehouse/status");
    renderWarehouseStatus(payload);
  } catch (error) {
    q("#warehouseStatus").textContent = error.message;
  }
}

async function loadObserverSurfaces() {
  try {
    const [sources, cameras, warehouse] = await Promise.all([
      observerApi("/v1/horizon/behavioral-knowledge/sources"),
      observerApi("/v1/horizon/public-scenes/cameras"),
      observerApi("/v1/horizon/behavioral-warehouse/status"),
    ]);
    renderKnowledgeSources(sources);
    renderCameras(cameras);
    renderWarehouseStatus(warehouse);
  } catch (error) {
    q("#behaviorSourceGrid").innerHTML = `<div class="observer-error">${escapeHtml(error.message)}</div>`;
    q("#cameraGrid").innerHTML = `<div class="observer-error">${escapeHtml(error.message)}</div>`;
    q("#warehouseStatus").textContent = error.message;
  }
}

async function searchBehavioralKnowledge() {
  const input = q("#behaviorQueryInput");
  const button = q("#behaviorQueryButton");
  const query = input.value.trim();
  if (query.length < 3) return;
  button.disabled = true;
  q("#behaviorKnowledgeResults").innerHTML = '<div class="observer-loading">Recherche dans les archives scientifiques…</div>';
  try {
    const payload = await observerApi("/v1/horizon/behavioral-knowledge/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        sources: ["openalex", "pubmed"],
        limit_per_source: 12,
        open_access_only: false,
      }),
    });
    renderKnowledgeResults(payload);
  } catch (error) {
    q("#behaviorKnowledgeResults").innerHTML = `<div class="observer-error">${escapeHtml(error.message)}</div>`;
  } finally {
    button.disabled = false;
  }
}

async function harvestCurrentTopic() {
  const input = q("#behaviorQueryInput");
  const button = q("#warehouseHarvestButton");
  const query = input.value.trim();
  if (query.length < 3) {
    q("#warehouseStatus").textContent = "Entrez d'abord un sujet de recherche à indexer.";
    return;
  }
  button.disabled = true;
  q("#warehouseStatus").textContent = "Indexation et déduplication des références…";
  try {
    const result = await observerApi("/v1/horizon/behavioral-warehouse/harvest", {
      method: "POST",
      body: JSON.stringify({
        query,
        sources: ["openalex", "pubmed"],
        limit_per_source: 20,
        open_access_only: false,
      }),
    });
    q("#warehouseStatus").textContent = `${result.documents_created} nouveaux documents · ${result.documents_updated} références déjà connues actualisées.`;
    await loadWarehouseStatus();
  } catch (error) {
    q("#warehouseStatus").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

async function bootstrapWarehouse() {
  const button = q("#warehouseBootstrapButton");
  button.disabled = true;
  q("#warehouseStatus").textContent = "Construction du corpus comportemental transversal…";
  try {
    const result = await observerApi("/v1/horizon/behavioral-warehouse/bootstrap", {
      method: "POST",
      body: JSON.stringify({
        mechanisms: ["incentive", "habit", "social", "stress", "intention_action", "collective_dynamics"],
        scenario: "human behavior decision response adaptation",
        population: "general population",
        max_queries: 12,
        limit_per_source: 8,
        publication_year_from: 1980,
        open_access_only: false,
      }),
    });
    q("#warehouseStatus").textContent = `${result.queries_executed} requêtes · ${result.documents_created} nouveaux documents · ${result.documents_updated} actualisés.`;
    await loadWarehouseStatus();
  } catch (error) {
    q("#warehouseStatus").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}

q("#behaviorQueryButton")?.addEventListener("click", searchBehavioralKnowledge);
q("#warehouseHarvestButton")?.addEventListener("click", harvestCurrentTopic);
q("#warehouseBootstrapButton")?.addEventListener("click", bootstrapWarehouse);
q("#behaviorQueryInput")?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") searchBehavioralKnowledge();
});

loadObserverSurfaces();
