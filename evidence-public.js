(() => {
  "use strict";

  const REPO = "XDSawyerLoL/Human-Agency-Engine";
  const SNAPSHOT_URL = `https://raw.githubusercontent.com/${REPO}/evidence-live-data/evidence-live.json`;
  const HEARTBEAT_URL = `https://api.github.com/repos/${REPO}/actions/workflows/horizon-live.yml/runs?per_page=1`;

  const gapLabels = {
    insufficient_source_coverage: "Couverture insuffisante",
    candidate_gap_in_scanned_sources: "Lacune candidate",
    underexplored_in_scanned_sources: "Zone sous-explorée",
    related_work_found: "Travail connexe trouvé",
    substantial_existing_work_found: "Écosystème déjà actif",
    not_scanned_in_this_cycle: "À scanner",
    pending: "À scanner",
  };

  const domainLabels = {
    weather_climate: "Météo & climat",
    natural_hazards: "Risques naturels",
    transport_mobility: "Transport & mobilité",
    social_collective_behavior: "Comportements collectifs",
    supply_fuel: "Approvisionnement",
    energy: "Énergie",
    media_attention: "Attention médiatique",
    geopolitics_security: "Géopolitique",
    economy_labor: "Économie & travail",
    public_health: "Santé publique",
    cyber_technology: "Cyber & technologie",
    regulation_policy: "Régulation",
    financial_stress: "Stress financier",
    personal_context: "Contexte personnel",
  };

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];

  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[c]);

  const safeUrl = (value) => {
    try {
      const url = new URL(String(value || ""));
      return ["http:", "https:"].includes(url.protocol) ? url.href : "";
    } catch (_) {
      return "";
    }
  };

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, Number(value) || 0));
  }

  function hashString(value) {
    let h = 2166136261;
    for (let i = 0; i < String(value).length; i += 1) {
      h ^= String(value).charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function formatRelative(dateValue) {
    if (!dateValue) return "date inconnue";
    const date = new Date(dateValue);
    if (Number.isNaN(date.getTime())) return "date inconnue";
    const seconds = Math.round((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return "à l’instant";
    if (seconds < 3600) return `il y a ${Math.floor(seconds / 60)} min`;
    if (seconds < 86400) return `il y a ${Math.floor(seconds / 3600)} h`;
    return `il y a ${Math.floor(seconds / 86400)} j`;
  }

  function formatObservedHours(hours) {
    const value = Number(hours) || 0;
    if (value >= 24 * 30) return `${Math.round(value / (24 * 30))} mois`;
    if (value >= 48) return `${Math.round(value / 24)} j`;
    return `${Math.round(value)} h`;
  }

  function scanStatus(opportunity) {
    return opportunity?.solution_scan?.assessment?.gap_status
      || opportunity?.solution_scan?.status
      || "not_scanned_in_this_cycle";
  }

  function anomalyIndex(opportunity) {
    const signal = opportunity?.signal_strength || {};
    const score = clamp(signal.diagnostic_score, 0, 100);
    const persistence = clamp(Math.log10(1 + (Number(signal.persistence_hours) || 0)) * 5.2, 0, 12);
    const diversity = clamp((Number(signal.source_diversity_count) || 0) * 1.4, 0, 8);
    const confirmed = clamp((Number(signal.confirmed_evidence_count) || 0) * 2, 0, 8);
    const gap = {
      candidate_gap_in_scanned_sources: 18,
      underexplored_in_scanned_sources: 10,
      related_work_found: -4,
      substantial_existing_work_found: -12,
      insufficient_source_coverage: -8,
      not_scanned_in_this_cycle: 0,
      pending: 0,
    }[scanStatus(opportunity)] || 0;
    return Math.round(clamp(score * 0.66 + persistence + diversity + confirmed + gap, 0, 100));
  }

  function gapClass(status) {
    if (status === "candidate_gap_in_scanned_sources") return "gap";
    if (status === "underexplored_in_scanned_sources") return "sparse";
    if (["related_work_found", "substantial_existing_work_found"].includes(status)) return "known";
    return "unknown";
  }

  function explainWhy(opportunity) {
    const signal = opportunity?.signal_strength || {};
    const parts = [];
    const confirmed = Number(signal.confirmed_evidence_count) || 0;
    const diversity = Number(signal.source_diversity_count) || 0;
    const persistence = Number(signal.persistence_hours) || 0;
    const status = scanStatus(opportunity);
    const scan = opportunity?.solution_scan?.assessment || {};

    if (confirmed) parts.push(`${confirmed} fait${confirmed > 1 ? "s" : ""} confirmé${confirmed > 1 ? "s" : ""}`);
    if (diversity) parts.push(`${diversity} famille${diversity > 1 ? "s" : ""} de sources`);
    if (persistence >= 6) parts.push(`persistance observée ${formatObservedHours(persistence)}`);

    let ending = "";
    if (status === "candidate_gap_in_scanned_sources") {
      ending = `Le scan a couvert ${scan.successful_source_count || "plusieurs"} écosystèmes sans trouver de travail suffisamment proche.`;
    } else if (status === "underexplored_in_scanned_sources") {
      ending = `Le travail connexe retrouvé reste sparse malgré une couverture de sources suffisante.`;
    } else if (status === "related_work_found") {
      ending = `Des réponses existent déjà ; la question devient de savoir si elles résolvent la friction de bout en bout.`;
    } else if (status === "substantial_existing_work_found") {
      ending = `Le terrain est déjà actif : l’opportunité éventuelle est probablement dans l’intégration ou un segment oublié.`;
    } else if (status === "insufficient_source_coverage") {
      ending = `Le scan de solutions est trop incomplet pour conclure à une lacune.`;
    } else {
      ending = "Le problème est suffisamment visible pour mériter un scan de solutions, mais ce scan n’a pas été publié dans ce cycle.";
    }

    const evidence = parts.length ? `Le signal combine ${parts.join(", ")}. ` : "";
    return evidence + ending;
  }

  function sourceCount(opportunities) {
    const sources = new Set();
    for (const op of opportunities) {
      for (const source of op?.signal_strength?.independent_source_keys || []) sources.add(source);
    }
    return sources.size;
  }

  function relevantMatches(opportunity) {
    return (opportunity?.solution_scan?.matches || []).filter((m) => m.is_relevant).slice(0, 4);
  }

  function terminalLine(kind, message, time = new Date()) {
    const terminal = $("#terminalLog");
    if (!terminal) return;
    const line = document.createElement("div");
    const hhmmss = time.toLocaleTimeString("fr-FR", { hour12: false });
    const label = { sys: "SYSTEM", scan: "SCAN", signal: "SIGNAL", warn: "GUARD", error: "ERROR" }[kind] || "SYSTEM";
    line.innerHTML = `<time>${esc(hhmmss)}</time><span class="${esc(kind)}">${esc(label)}</span><p>${esc(message)}</p>`;
    terminal.appendChild(line);
    while (terminal.children.length > 26) terminal.removeChild(terminal.firstChild);
    terminal.scrollTop = terminal.scrollHeight;
  }

  function resetTerminal() {
    const terminal = $("#terminalLog");
    if (terminal) terminal.innerHTML = "";
  }

  function renderTerminal(snapshot, opportunities) {
    resetTerminal();
    const generated = snapshot?.generated_at ? new Date(snapshot.generated_at) : new Date();
    terminalLine("sys", `Snapshot public chargé · ${snapshot?.engine || "Évidence"}.`, generated);
    terminalLine("sys", `Mode ${snapshot?.runtime_mode || "public-world-evidence"} · données personnelles interdites.`, generated);
    terminalLine("signal", `${snapshot?.summary?.evidence_items_considered || 0} éléments de preuve considérés · ${opportunities.length} problèmes surfacés.`, generated);

    const scanned = opportunities.filter((op) => op.solution_scan?.assessment).length;
    terminalLine("scan", `${scanned} Solution Scan${scanned > 1 ? "s" : ""} inclus dans ce snapshot public.`, generated);

    opportunities.slice(0, 5).forEach((op) => {
      const idx = anomalyIndex(op);
      terminalLine("signal", `${op.problem_key || op.event_type || "signal"} → anomalie ${idx}/100 · ${gapLabels[scanStatus(op)] || scanStatus(op)}.`, generated);
    });

    if (opportunities.some((op) => scanStatus(op) === "insufficient_source_coverage")) {
      terminalLine("warn", "Couverture insuffisante détectée : aucune inférence négative de lacune autorisée sur ces signaux.", generated);
    }
    terminalLine("warn", "Les indices sont des scores de priorisation. Aucun n’est une probabilité.", generated);
    terminalLine("warn", "Une lacune candidate reste limitée aux sources effectivement scannées.", generated);
  }

  function matchHtml(opportunity) {
    const matches = relevantMatches(opportunity);
    if (!matches.length) return `<span class="detail-block">Aucun résultat connexe publié dans ce snapshot.</span>`;
    return `<div class="match-list">${matches.map((match) => {
      const url = safeUrl(match.url);
      const label = `${match.title || match.ecosystem || "Résultat"} · ${match.ecosystem || "source"}`;
      return url ? `<a href="${esc(url)}" target="_blank" rel="noreferrer">↗ ${esc(label)}</a>` : `<span>${esc(label)}</span>`;
    }).join("")}</div>`;
  }

  function renderTopAnomaly(opportunity) {
    const root = $("#topAnomaly");
    if (!root || !opportunity) return;
    const idx = anomalyIndex(opportunity);
    const action = opportunity.candidate_action || {};
    const status = scanStatus(opportunity);
    root.innerHTML = `
      <article class="top-card">
        <div>
          <span class="top-card-rank">CANDIDAT A-01 · ${esc(domainLabels[opportunity.domain] || opportunity.domain_label || opportunity.domain || "domaine")}</span>
          <h3>${esc(opportunity.problem_statement || opportunity.event_type || "Problème à investiguer")}</h3>
          <p class="reason">${esc(explainWhy(opportunity))}</p>
          <div class="top-card-action">
            <span>INTERVENTION À TESTER</span>
            <strong>${esc(action.tool_archetype || "Expérience ciblée")}</strong>
            <p>${esc(action.mechanism || action.first_build || "Aucune intervention publiée.")}</p>
          </div>
        </div>
        <div class="top-card-side">
          <div class="anomaly-score">${idx}<small>/100</small></div>
          <span class="score-label">INDICE D’ANOMALIE</span>
          <span class="score-note">Diagnostic explicable · ≠ probabilité</span>
          <span class="gap-badge ${gapClass(status)}" style="margin-top:14px;max-width:max-content">${esc(gapLabels[status] || status)}</span>
        </div>
      </article>`;
  }

  function renderCards(opportunities) {
    const grid = $("#anomalyGrid");
    if (!grid) return;
    grid.innerHTML = opportunities.slice(1).map((op, index) => {
      const signal = op.signal_strength || {};
      const action = op.candidate_action || {};
      const validation = op.validation || {};
      const idx = anomalyIndex(op);
      const status = scanStatus(op);
      return `
        <article class="anomaly-card">
          <div class="anomaly-card-head">
            <span class="anomaly-rank">A-${String(index + 2).padStart(2, "0")}</span>
            <span class="gap-badge ${gapClass(status)}">${esc(gapLabels[status] || status)}</span>
          </div>
          <p class="anomaly-domain">${esc(domainLabels[op.domain] || op.domain_label || op.domain || "Domaine")}</p>
          <h3>${esc(op.problem_statement || op.event_type || "Signal à investiguer")}</h3>
          <div class="mini-score"><strong>${idx}</strong><div><span style="width:${idx}%"></span></div></div>
          <div class="proof-row">
            <div><strong>${Number(signal.confirmed_evidence_count || 0)}</strong><span>faits</span></div>
            <div><strong>${Number(signal.source_diversity_count || 0)}</strong><span>sources</span></div>
            <div><strong>${formatObservedHours(signal.persistence_hours || 0)}</strong><span>persistance</span></div>
          </div>
          <div class="card-action">
            <small>ACTION À TESTER</small>
            <strong>${esc(action.tool_archetype || "Expérience ciblée")}</strong>
            <p>${esc(action.mechanism || "Intervention non publiée.")}</p>
          </div>
          <details>
            <summary>Pourquoi ceci est étrange + preuves ↘</summary>
            <div class="detail-grid">
              <div class="detail-block"><b>LECTURE DU MOTEUR</b>${esc(explainWhy(op))}</div>
              <div class="detail-block"><b>CE QUI TUERAIT L’IDÉE</b>${esc(validation.reject_if || "Condition de rejet non publiée.")}</div>
              <div class="detail-block"><b>TRAVAIL CONNEXE</b>${matchHtml(op)}</div>
            </div>
          </details>
        </article>`;
    }).join("");
  }

  function renderSnapshot(snapshot) {
    const opportunities = [...(snapshot?.opportunities || [])]
      .sort((a, b) => anomalyIndex(b) - anomalyIndex(a));

    $("#heroAnomalyCount").textContent = opportunities.length;
    $("#metricEvidence").textContent = snapshot?.summary?.evidence_items_considered ?? "—";
    $("#metricProblems").textContent = opportunities.length;
    $("#metricScans").textContent = opportunities.filter((op) => op.solution_scan?.assessment).length;
    $("#metricSources").textContent = sourceCount(opportunities) || "—";
    $("#metricTopAnomaly").textContent = opportunities.length ? `${anomalyIndex(opportunities[0])}` : "—";
    $("#runtimeMode").textContent = snapshot?.runtime_mode || "GitHub / HORIZON";

    if (snapshot?.generated_at) {
      $("#snapshotState").textContent = opportunities.length ? "Flux public synchronisé" : "Snapshot public sans anomalie";
      $("#snapshotTimestamp").textContent = `${formatRelative(snapshot.generated_at)} · ${new Date(snapshot.generated_at).toLocaleString("fr-FR")}`;
    }

    const queueDot = $("#queueStatusDot");
    const queueText = $("#queueStatusText");
    if (opportunities.length) {
      queueDot?.classList.add("live");
      if (queueText) queueText.textContent = `${opportunities.length} ACTIVE`;
      $("#fieldEmpty")?.classList.add("hidden");
      renderTopAnomaly(opportunities[0]);
      renderCards(opportunities);
      initSignalCanvas(opportunities);
    } else {
      if (queueText) queueText.textContent = "EMPTY";
    }

    renderTerminal(snapshot, opportunities);
  }

  async function loadSnapshot() {
    terminalLine("sys", "Connexion au canal public Evidence…");
    try {
      const response = await fetch(`${SNAPSHOT_URL}?t=${Math.floor(Date.now() / 60000)}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`snapshot ${response.status}`);
      const snapshot = await response.json();
      if (!snapshot || snapshot.status === "awaiting_first_runtime_snapshot") {
        throw new Error("snapshot non initialisé");
      }
      renderSnapshot(snapshot);
    } catch (error) {
      $("#snapshotState").textContent = "Canal public non initialisé";
      $("#snapshotTimestamp").textContent = "Aucune donnée fictive affichée";
      terminalLine("warn", `Snapshot live indisponible (${error.message}). L’interface reste vide plutôt que d’inventer des signaux.`);
    }
  }

  async function loadHeartbeat() {
    const badge = $("#heartbeatBadge");
    const text = $("#heartbeatText");
    try {
      const response = await fetch(HEARTBEAT_URL, {
        headers: { Accept: "application/vnd.github+json" },
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`GitHub ${response.status}`);
      const body = await response.json();
      const run = body.workflow_runs?.[0];
      if (!run) throw new Error("aucun run");
      const success = run.status === "completed" && run.conclusion === "success";
      badge.dataset.state = success ? "success" : (run.status === "in_progress" ? "loading" : "failure");
      text.textContent = run.status === "in_progress"
        ? "cycle actif"
        : `${run.conclusion || run.status} · ${formatRelative(run.updated_at)}`;
    } catch (_) {
      badge.dataset.state = "loading";
      text.textContent = "status public indisponible";
    }
  }

  function initAmbient() {
    const canvas = $("#ambientCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let particles = [];

    function resize() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(innerWidth * dpr);
      canvas.height = Math.floor(innerHeight * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      particles = Array.from({ length: Math.min(90, Math.floor(innerWidth / 17)) }, (_, i) => ({
        x: (hashString(`x${i}`) % innerWidth),
        y: (hashString(`y${i}`) % innerHeight),
        r: 0.35 + ((hashString(`r${i}`) % 100) / 160),
        s: 0.03 + ((hashString(`s${i}`) % 100) / 3500),
      }));
    }

    function draw() {
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      ctx.fillStyle = "rgba(95, 202, 235, .35)";
      for (const p of particles) {
        p.y += p.s;
        if (p.y > innerHeight + 4) p.y = -4;
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
      }
      requestAnimationFrame(draw);
    }
    addEventListener("resize", resize, { passive: true });
    resize(); draw();
  }

  let fieldAnimation = null;
  function initSignalCanvas(opportunities) {
    const canvas = $("#signalCanvas");
    if (!canvas || !opportunities.length) return;
    const ctx = canvas.getContext("2d");
    let nodes = [];
    let t = 0;
    let selected = null;

    const palette = {
      gap: [100, 224, 177],
      sparse: [255, 207, 120],
      known: [114, 168, 255],
      unknown: [110, 138, 154],
    };

    function buildNodes(width, height) {
      nodes = opportunities.map((op, index) => {
        const seed = hashString(op.problem_key || `${op.domain}-${index}`);
        const angle = ((seed % 360) / 180) * Math.PI;
        const radius = 0.16 + (((seed >>> 7) % 100) / 100) * 0.32;
        const idx = anomalyIndex(op);
        return {
          op,
          idx,
          x: width / 2 + Math.cos(angle) * width * radius,
          y: height / 2 + Math.sin(angle) * height * radius * 0.72,
          baseX: width / 2 + Math.cos(angle) * width * radius,
          baseY: height / 2 + Math.sin(angle) * height * radius * 0.72,
          r: 4 + idx / 9,
          phase: ((seed >>> 13) % 628) / 100,
          color: palette[gapClass(scanStatus(op))] || palette.unknown,
        };
      });
    }

    function resize() {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(devicePixelRatio || 1, 2);
      canvas.width = Math.floor(rect.width * dpr);
      canvas.height = Math.floor(rect.height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      buildNodes(rect.width, rect.height);
    }

    function draw() {
      const { width, height } = canvas.getBoundingClientRect();
      ctx.clearRect(0, 0, width, height);
      t += 0.008;

      for (let i = 0; i < nodes.length; i += 1) {
        const a = nodes[i];
        a.x = a.baseX + Math.cos(t * 0.7 + a.phase) * 6;
        a.y = a.baseY + Math.sin(t * 0.9 + a.phase) * 5;
        for (let j = i + 1; j < nodes.length; j += 1) {
          const b = nodes[j];
          if (a.op.domain !== b.op.domain) continue;
          const dist = Math.hypot(a.x - b.x, a.y - b.y);
          if (dist > width * 0.42) continue;
          ctx.strokeStyle = `rgba(73, 152, 184, ${Math.max(.04, .18 - dist / 1800)})`;
          ctx.lineWidth = 0.6;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }

      for (const n of nodes) {
        const [r, g, b] = n.color;
        const pulse = 1 + Math.sin(t * 5 + n.phase) * 0.12;
        const rr = n.r * pulse;
        const grd = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, rr * 2.7);
        grd.addColorStop(0, `rgba(${r},${g},${b},.85)`);
        grd.addColorStop(.18, `rgba(${r},${g},${b},.35)`);
        grd.addColorStop(1, `rgba(${r},${g},${b},0)`);
        ctx.fillStyle = grd;
        ctx.beginPath(); ctx.arc(n.x, n.y, rr * 2.7, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = `rgba(${r},${g},${b},.55)`;
        ctx.lineWidth = selected === n ? 1.5 : .8;
        ctx.beginPath(); ctx.arc(n.x, n.y, rr, 0, Math.PI * 2); ctx.stroke();
        ctx.fillStyle = `rgba(${r},${g},${b},.75)`;
        ctx.beginPath(); ctx.arc(n.x, n.y, Math.max(1.7, rr * .18), 0, Math.PI * 2); ctx.fill();
      }
      fieldAnimation = requestAnimationFrame(draw);
    }

    canvas.onpointermove = (event) => {
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      selected = nodes.find((n) => Math.hypot(n.x - x, n.y - y) <= n.r * 1.7) || null;
      canvas.style.cursor = selected ? "pointer" : "default";
      $("#selectedNodeLabel").textContent = selected
        ? `${selected.op.event_type || selected.op.problem_key} · ${selected.idx}/100`
        : "—";
    };
    canvas.onpointerleave = () => {
      selected = null;
      $("#selectedNodeLabel").textContent = "—";
    };
    canvas.onclick = () => {
      if (!selected) return;
      const key = selected.op.problem_key;
      const cards = $$(".anomaly-card, .top-card");
      const targetIndex = opportunities.findIndex((op) => op.problem_key === key);
      const target = targetIndex === 0 ? $("#topAnomaly") : cards[targetIndex];
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
    };

    addEventListener("resize", resize, { passive: true });
    if (fieldAnimation) cancelAnimationFrame(fieldAnimation);
    resize(); draw();
  }

  function startUtcClock() {
    const el = $("#utcClock");
    const tick = () => {
      if (el) el.textContent = new Date().toLocaleTimeString("fr-FR", { timeZone: "UTC", hour12: false });
    };
    tick(); setInterval(tick, 1000);
  }

  function initDialog() {
    const dialog = $("#explainDialog");
    $("#explainButton")?.addEventListener("click", () => dialog?.showModal());
    $("#dialogClose")?.addEventListener("click", () => dialog?.close());
    dialog?.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  }

  initAmbient();
  initDialog();
  startUtcClock();
  loadHeartbeat();
  loadSnapshot();
  setInterval(loadHeartbeat, 180000);
  setInterval(loadSnapshot, 300000);
})();
