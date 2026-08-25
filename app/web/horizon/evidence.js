(() => {
  const desktopMode = new URLSearchParams(window.location.search).get("desktop") === "1";
  const root = document.querySelector("#opportunityGrid");
  const count = document.querySelector("#opportunityCount");
  const status = document.querySelector("#opportunityStatus");
  if (!root) return;

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  })[char]);

  const strengthLabel = {
    strong_signal: "Signal fort",
    emerging_signal: "Signal émergent",
    weak_signal: "Signal faible",
  };

  function evidenceLinks(items) {
    const rows = (items || []).slice(0, 3);
    if (!rows.length) return '<span class="opportunity-evidence-empty">Aucune référence disponible</span>';
    return rows.map((item) => {
      const label = escapeHtml(item.title || item.source || item.kind || "Signal");
      if (item.source_url) {
        return `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer">${label}</a>`;
      }
      return `<span>${label}</span>`;
    }).join("");
  }

  function render(body) {
    const opportunities = body?.opportunities || [];
    count.textContent = opportunities.length;
    status.textContent = opportunities.length
      ? `${body.summary?.strong_signals || 0} forts · ${body.summary?.emerging_signals || 0} émergents`
      : "Aucun problème suffisamment étayé";

    if (!opportunities.length) {
      root.innerHTML = '<div class="empty-state">Évidence n’a pas encore assez de matière pour proposer un problème à investiguer.</div>';
      return;
    }

    root.innerHTML = opportunities.map((item, index) => {
      const signal = item.signal_strength || {};
      const action = item.candidate_action || {};
      const unresolved = item.unresolvedness || {};
      const novelty = item.novelty || {};
      return `
        <article class="opportunity-card" data-strength="${escapeHtml(signal.label)}">
          <div class="opportunity-head">
            <span class="opportunity-rank">${String(index + 1).padStart(2, "0")}</span>
            <div class="opportunity-chips">
              <span class="opportunity-chip strength-${escapeHtml(signal.label)}">${escapeHtml(strengthLabel[signal.label] || signal.label || "Signal")}</span>
              <span class="opportunity-chip needs-scan">Solution à vérifier</span>
            </div>
          </div>
          <p class="opportunity-domain">${escapeHtml(item.domain_label || item.domain)} · ${escapeHtml(item.event_type)}</p>
          <h3>${escapeHtml(item.problem_statement)}</h3>

          <div class="opportunity-proof">
            <div><strong>${Number(signal.diagnostic_score || 0)}</strong><span>score signal<br>≠ probabilité</span></div>
            <div><strong>${Number(signal.confirmed_evidence_count || 0)}</strong><span>faits<br>confirmés</span></div>
            <div><strong>${Number(signal.source_diversity_count || 0)}</strong><span>familles<br>de sources</span></div>
            <div><strong>${Math.round(Number(signal.persistence_hours || 0))}h</strong><span>persistance<br>observée</span></div>
          </div>

          <div class="opportunity-action">
            <span>INTERVENTION À TESTER</span>
            <strong>${escapeHtml(action.tool_archetype || "Expérience ciblée")}</strong>
            <p>${escapeHtml(action.mechanism || action.first_build || "")}</p>
          </div>

          <div class="opportunity-checks">
            <div><span>PROBLÈME NON RÉSOLU</span><strong>${unresolved.solution_absence_verified ? "Vérifié" : "Non vérifié"}</strong></div>
            <div><span>NOUVEAUTÉ MONDIALE</span><strong>${novelty.globally_unique_claim ? "Étayée" : "Non évaluée"}</strong></div>
          </div>

          <div class="opportunity-evidence">
            <span>PREUVES SOUS-JACENTES</span>
            <div>${evidenceLinks(item.evidence)}</div>
          </div>
        </article>`;
    }).join("");
  }

  async function loadOpportunities() {
    const apiKey = sessionStorage.getItem("horizon_api_key") || "";
    const externalId = sessionStorage.getItem("horizon_external_id") || (desktopMode ? "desktop-local" : "");
    const params = new URLSearchParams({ limit: "12", event_limit: "160", candidate_limit: "160" });
    if (externalId) params.set("external_id", externalId);
    const headers = {};
    if (apiKey) headers["X-API-Key"] = apiKey;

    status.textContent = "Analyse des frictions humaines…";
    try {
      const response = await fetch(`/v1/horizon/world/human-signals/opportunities?${params}`, {
        headers,
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`Évidence indisponible (${response.status})`);
      render(await response.json());
    } catch (error) {
      count.textContent = "—";
      status.textContent = error.message;
      root.innerHTML = '<div class="empty-state">Le radar de problèmes sera disponible dès que le moteur HORIZON sera connecté.</div>';
    }
  }

  document.querySelector("#refreshButton")?.addEventListener("click", loadOpportunities);
  document.querySelector("#connectButton")?.addEventListener("click", loadOpportunities);

  if (desktopMode || sessionStorage.getItem("horizon_api_key")) {
    loadOpportunities();
  }
})();
