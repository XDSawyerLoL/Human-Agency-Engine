(() => {
  const desktopMode = new URLSearchParams(window.location.search).get("desktop") === "1";
  const root = document.querySelector("#opportunityGrid");
  const count = document.querySelector("#opportunityCount");
  const status = document.querySelector("#opportunityStatus");
  if (!root) return;

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
  })[char]);

  const safeUrl = (value) => {
    try {
      const url = new URL(String(value || ""));
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch (_) {
      return "";
    }
  };

  const strengthLabel = {
    strong_signal: "Signal fort",
    emerging_signal: "Signal émergent",
    weak_signal: "Signal faible",
  };

  const scanLabel = {
    insufficient_source_coverage: "Couverture insuffisante",
    candidate_gap_in_scanned_sources: "Lacune candidate",
    underexplored_in_scanned_sources: "Zone sous-explorée",
    related_work_found: "Travail connexe trouvé",
    substantial_existing_work_found: "Écosystème déjà actif",
  };

  function connection() {
    const apiKey = sessionStorage.getItem("horizon_api_key") || "";
    const externalId = sessionStorage.getItem("horizon_external_id") || (desktopMode ? "desktop-local" : "");
    const headers = {};
    if (apiKey) headers["X-API-Key"] = apiKey;
    return { headers, externalId };
  }

  function evidenceLinks(items) {
    const rows = (items || []).slice(0, 3);
    if (!rows.length) return '<span class="opportunity-evidence-empty">Aucune référence disponible</span>';
    return rows.map((item) => {
      const label = escapeHtml(item.title || item.source || item.kind || "Signal");
      const url = safeUrl(item.source_url);
      if (url) {
        return `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${label}</a>`;
      }
      return `<span>${label}</span>`;
    }).join("");
  }

  function solutionLinks(items) {
    const relevant = (items || []).filter((item) => item.is_relevant).slice(0, 5);
    if (!relevant.length) {
      return '<span class="solution-scan-empty">Aucun résultat suffisamment proche dans les sources interrogées.</span>';
    }
    return relevant.map((item) => {
      const title = escapeHtml(item.title || item.ecosystem || "Résultat");
      const source = escapeHtml(item.ecosystem || "source");
      const score = Number(item.relevance_score || 0);
      const url = safeUrl(item.url);
      const label = `${title}<small>${source} · pertinence ${score}/100</small>`;
      return url
        ? `<a class="solution-match" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${label}</a>`
        : `<span class="solution-match">${label}</span>`;
    }).join("");
  }

  function renderSolutionScan(region, body) {
    const assessment = body?.assessment || {};
    const sourceRows = body?.sources || [];
    const sourceOk = Number(assessment.successful_source_count || 0);
    const matchCount = Number(assessment.relevant_match_count || 0);
    const statusKey = assessment.gap_status || "insufficient_source_coverage";
    const errors = sourceRows.filter((source) => source.status !== "ok").length;
    const ecosystems = (assessment.ecosystems_with_relevant_matches || []).join(" · ");

    region.innerHTML = `
      <div class="solution-scan-head">
        <div>
          <span>SOLUTION SCAN</span>
          <strong>${escapeHtml(scanLabel[statusKey] || statusKey)}</strong>
        </div>
        <div class="solution-scan-metrics">
          <span><b>${sourceOk}/4</b> sources</span>
          <span><b>${matchCount}</b> proches</span>
        </div>
      </div>
      <p class="solution-scan-explanation">${escapeHtml(assessment.explanation || "Scan terminé.")}</p>
      ${ecosystems ? `<p class="solution-scan-ecosystems">Présence détectée : ${escapeHtml(ecosystems)}</p>` : ""}
      <div class="solution-scan-matches">${solutionLinks(body?.matches)}</div>
      <div class="solution-scan-foot">
        <span>${errors ? `${errors} source${errors > 1 ? "s" : ""} indisponible${errors > 1 ? "s" : ""}` : "4 sources interrogées"}</span>
        <strong>≠ preuve de nouveauté mondiale</strong>
      </div>`;
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
      const problemKey = escapeHtml(item.problem_key || "");
      return `
        <article class="opportunity-card" data-strength="${escapeHtml(signal.label)}">
          <div class="opportunity-head">
            <span class="opportunity-rank">${String(index + 1).padStart(2, "0")}</span>
            <div class="opportunity-chips">
              <span class="opportunity-chip strength-${escapeHtml(signal.label)}">${escapeHtml(strengthLabel[signal.label] || signal.label || "Signal")}</span>
              <span class="opportunity-chip needs-scan" data-scan-chip>Solution à vérifier</span>
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

          <div class="solution-scan-control">
            <button class="solution-scan-button" type="button" data-solution-scan="${problemKey}">
              <span>⌁</span> Scanner les solutions existantes
            </button>
            <small>GitHub · OpenAlex · Hacker News · GDELT</small>
          </div>
          <div class="solution-scan-region" data-solution-scan-region></div>
        </article>`;
    }).join("");
  }

  async function runSolutionScan(button) {
    const problemKey = button.dataset.solutionScan || "";
    const card = button.closest(".opportunity-card");
    const region = card?.querySelector("[data-solution-scan-region]");
    const chip = card?.querySelector("[data-scan-chip]");
    if (!problemKey || !region) return;

    const { headers, externalId } = connection();
    const params = new URLSearchParams({
      problem_key: problemKey,
      max_results_per_source: "8",
    });
    if (externalId) params.set("external_id", externalId);

    button.disabled = true;
    button.classList.add("scanning");
    button.innerHTML = "<span>⌁</span> Scan en cours…";
    region.innerHTML = '<div class="solution-scan-loading"><i></i><span>Recherche dans 4 écosystèmes indépendants…</span></div>';
    if (chip) chip.textContent = "Scan en cours";

    try {
      const response = await fetch(`/v1/horizon/world/human-signals/solution-scan?${params}`, {
        headers,
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`Solution Scan indisponible (${response.status})`);
      const body = await response.json();
      renderSolutionScan(region, body);
      const key = body?.assessment?.gap_status || "";
      if (chip) {
        chip.textContent = scanLabel[key] || "Scan terminé";
        chip.dataset.scanStatus = key;
      }
      button.innerHTML = "<span>↻</span> Refaire le scan";
    } catch (error) {
      region.innerHTML = `<div class="solution-scan-error">${escapeHtml(error.message || "Scan impossible")}</div>`;
      if (chip) chip.textContent = "Scan indisponible";
      button.innerHTML = "<span>↻</span> Réessayer le scan";
    } finally {
      button.disabled = false;
      button.classList.remove("scanning");
    }
  }

  async function loadOpportunities() {
    const { headers, externalId } = connection();
    const params = new URLSearchParams({ limit: "12", event_limit: "160", candidate_limit: "160" });
    if (externalId) params.set("external_id", externalId);

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

  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-solution-scan]");
    if (button) runSolutionScan(button);
  });

  document.querySelector("#refreshButton")?.addEventListener("click", loadOpportunities);
  document.querySelector("#connectButton")?.addEventListener("click", loadOpportunities);

  if (desktopMode || sessionStorage.getItem("horizon_api_key")) {
    loadOpportunities();
  }
})();
