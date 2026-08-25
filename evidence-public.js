(() => {
  "use strict";

  const REPO = "XDSawyerLoL/Human-Agency-Engine";
  const SNAPSHOT_URL = `https://raw.githubusercontent.com/${REPO}/evidence-live-data/evidence-live.json`;
  const HEARTBEAT_URL = `https://api.github.com/repos/${REPO}/actions/workflows/horizon-live.yml/runs?per_page=1`;

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
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;",
  })[c]);

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, Number(value) || 0));
  }

  function probabilityPercent(forecast) {
    const explicit = Number(forecast?.probability?.percent);
    if (Number.isFinite(explicit)) return Math.round(clamp(explicit, 0, 100));
    return Math.round(clamp(Number(forecast?.probability?.estimate) * 100, 0, 100));
  }

  function probabilityInterval(forecast) {
    const direct = forecast?.probability?.interval_percent;
    if (Array.isArray(direct) && direct.length >= 2) {
      return [Math.round(Number(direct[0]) || 0), Math.round(Number(direct[1]) || 0)];
    }
    return [
      Math.round(clamp(Number(forecast?.probability?.interval_low) * 100, 0, 100)),
      Math.round(clamp(Number(forecast?.probability?.interval_high) * 100, 0, 100)),
    ];
  }

  function probabilityClass(percent) {
    if (percent >= 70) return "gap";
    if (percent >= 50) return "sparse";
    if (percent >= 30) return "known";
    return "unknown";
  }

  function trajectoryLabel(value) {
    return ({ building: "EN RENFORCEMENT", forming: "EN FORMATION", fragile: "FRAGILE" })[value] || "EN OBSERVATION";
  }

  function calibrationLabel(forecast) {
    return forecast?.probability?.empirically_calibrated
      ? "CALIBRÉ HISTORIQUEMENT"
      : "ESTIMATION MODÈLE · NON CALIBRÉE";
  }

  function forecastOriginLabel(forecast) {
    return forecast?.fact_status === "forecast_from_confirmed_event"
      ? "PRÉCURSEUR CONFIRMÉ"
      : "SIGNAL ÉMERGENT";
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

  function sourceFamilyCount(forecasts) {
    const sources = new Set();
    for (const forecast of forecasts) {
      for (const driver of forecast?.drivers || []) {
        for (const source of driver?.source_classes || []) sources.add(String(source));
      }
    }
    return sources.size;
  }

  function renderList(items, emptyText) {
    const clean = (items || []).filter(Boolean);
    if (!clean.length) return `<span class="detail-block">${esc(emptyText)}</span>`;
    return `<div class="match-list">${clean.map((item) => `<span>› ${esc(item)}</span>`).join("")}</div>`;
  }

  function renderChain(forecast) {
    const chain = (forecast?.causal_chain || []).filter(Boolean);
    if (!chain.length) return `<span class="detail-block">Chaîne non disponible.</span>`;
    return `<div class="match-list">${chain.map((step, index) => `<span>${index + 1}. ${esc(step)}</span>`).join("")}</div>`;
  }

  function driverSummary(forecast) {
    const drivers = forecast?.drivers || [];
    if (!drivers.length) return "Aucun précurseur supplémentaire n’est publié dans ce snapshot.";
    const precursorCount = drivers.filter((d) => d.type === "precursor_dependency").length;
    const primary = drivers.find((d) => d.type === "emerging_signal" || d.type === "confirmed_precursor");
    const support = Math.round((Number(primary?.support_score) || 0) * 100);
    const families = primary?.source_classes?.length || 0;
    const label = primary?.type === "confirmed_precursor" ? "fiabilité source" : "corroboration";
    return `${forecastOriginLabel(forecast)} · ${families} famille${families === 1 ? "" : "s"} de sources · ${label} ${support}/100 · ${precursorCount} dépendance${precursorCount === 1 ? "" : "s"} amont plausible${precursorCount === 1 ? "" : "s"}.`;
  }

  function terminalLine(kind, message, time = new Date()) {
    const terminal = $("#terminalLog");
    if (!terminal) return;
    const line = document.createElement("div");
    const hhmmss = time.toLocaleTimeString("fr-FR", { hour12: false });
    const label = { sys: "SYSTEM", scan: "GRAPH", signal: "FORECAST", warn: "CALIB", error: "ERROR" }[kind] || "SYSTEM";
    line.innerHTML = `<time>${esc(hhmmss)}</time><span class="${esc(kind)}">${esc(label)}</span><p>${esc(message)}</p>`;
    terminal.appendChild(line);
    while (terminal.children.length > 28) terminal.removeChild(terminal.firstChild);
    terminal.scrollTop = terminal.scrollHeight;
  }

  function renderTerminal(snapshot, forecasts) {
    const terminal = $("#terminalLog");
    if (terminal) terminal.innerHTML = "";
    const generated = snapshot?.generated_at ? new Date(snapshot.generated_at) : new Date();
    terminalLine("sys", `Snapshot prédictif chargé · ${snapshot?.engine || "Évidence"}.`, generated);
    terminalLine("sys", `${snapshot?.summary?.evidence_items_considered || 0} éléments examinés · ${forecasts.length} scénarios publiés.`, generated);
    terminalLine("scan", `${snapshot?.summary?.dependency_edges_considered || 0} dépendances précurseur → situation examinées.`, generated);
    forecasts.slice(0, 6).forEach((forecast) => {
      const p = probabilityPercent(forecast);
      const [low, high] = probabilityInterval(forecast);
      terminalLine(
        "signal",
        `${forecastOriginLabel(forecast)} · ${forecast.headline || forecast.event_type || "scénario"} → ${p}% [${low}–${high}] · ${forecast?.time_window?.human || "fenêtre inconnue"}.`,
        generated,
      );
    });
    terminalLine("warn", "Les pourcentages actuels sont des estimations de modèle, pas encore des fréquences historiques calibrées.", generated);
    terminalLine("warn", "Une dépendance du graphe augmente un scénario mais ne constitue pas une preuve de causalité.", generated);
    terminalLine("warn", "Une fenêtre expirée sans matérialisation doit compter comme un échec de prévision.", generated);
  }

  function topForecastHtml(forecast) {
    const p = probabilityPercent(forecast);
    const [low, high] = probabilityInterval(forecast);
    const cls = probabilityClass(p);
    return `
      <article class="top-card" data-scenario="${esc(forecast.scenario_key || "")}">
        <div>
          <span class="top-card-rank">FORECAST F-01 · ${esc(forecastOriginLabel(forecast))} · ${esc(domainLabels[forecast.domain] || forecast.domain_label || forecast.domain || "domaine")}</span>
          <h3>${esc(forecast.headline || forecast.outcome || "Scénario en formation")}</h3>
          <p class="reason">${esc(forecast.why_now || "Aucune explication publiée.")}</p>
          <div class="top-card-action">
            <span>FENÊTRE ATTENDUE</span>
            <strong>${esc(forecast?.time_window?.human || "indéterminée")}</strong>
            <p>${esc(driverSummary(forecast))}</p>
          </div>
        </div>
        <div class="top-card-side">
          <div class="anomaly-score">${p}<small>%</small></div>
          <span class="score-label">ESTIMATION ACTUELLE</span>
          <span class="score-note">Intervalle ${low}–${high} %</span>
          <span class="gap-badge ${cls}" style="margin-top:14px;max-width:max-content">${esc(trajectoryLabel(forecast.trajectory))}</span>
          <span class="score-note" style="margin-top:10px">${esc(calibrationLabel(forecast))}</span>
        </div>
      </article>
      <div class="anomaly-grid" style="margin-top:16px">
        <article class="anomaly-card"><p class="anomaly-domain">CHAÎNE PROJETÉE</p>${renderChain(forecast)}</article>
        <article class="anomaly-card"><p class="anomaly-domain">LE SCÉNARIO MONTE SI…</p>${renderList(forecast.probability_up_if, "Aucun déclencheur haussier publié.")}</article>
        <article class="anomaly-card"><p class="anomaly-domain">LE SCÉNARIO BAISSE SI…</p>${renderList(forecast.probability_down_if, "Aucun déclencheur baissier publié.")}</article>
      </div>`;
  }

  function renderCards(forecasts) {
    const grid = $("#anomalyGrid");
    if (!grid) return;
    grid.innerHTML = forecasts.slice(1).map((forecast, index) => {
      const p = probabilityPercent(forecast);
      const [low, high] = probabilityInterval(forecast);
      const components = forecast.model_components || {};
      const cls = probabilityClass(p);
      return `
        <article class="anomaly-card" data-scenario="${esc(forecast.scenario_key || "")}">
          <div class="anomaly-card-head"><span class="anomaly-rank">F-${String(index + 2).padStart(2, "0")}</span><span class="gap-badge ${cls}">${esc(trajectoryLabel(forecast.trajectory))}</span></div>
          <p class="anomaly-domain">${esc(forecastOriginLabel(forecast))} · ${esc(domainLabels[forecast.domain] || forecast.domain_label || forecast.domain || "Domaine")}</p>
          <h3>${esc(forecast.headline || forecast.outcome || "Scénario")}</h3>
          <div class="mini-score"><strong>${p}%</strong><div><span style="width:${p}%"></span></div></div>
          <div class="proof-row">
            <div><strong>${low}–${high}%</strong><span>intervalle</span></div>
            <div><strong>${Number(components.source_diversity || 0)}</strong><span>sources</span></div>
            <div><strong>${Math.round(Number(components.persistence_hours || 0))} h</strong><span>persistance</span></div>
          </div>
          <div class="card-action"><small>FENÊTRE</small><strong>${esc(forecast?.time_window?.human || "indéterminée")}</strong><p>${esc(calibrationLabel(forecast))}</p></div>
          <details>
            <summary>Pourquoi maintenant + comment l’invalider ↘</summary>
            <div class="detail-grid">
              <div class="detail-block"><b>LECTURE DU MOTEUR</b>${esc(forecast.why_now || "Non publiée.")}</div>
              <div class="detail-block"><b>CHAÎNE PROJETÉE</b>${renderChain(forecast)}</div>
              <div class="detail-block"><b>À SURVEILLER ENSUITE</b>${renderList(forecast.watch_next, "Aucun signal suivant publié.")}</div>
              <div class="detail-block"><b>INVALIDATION</b>${esc(forecast.falsification || "Règle non publiée.")}</div>
            </div>
          </details>
        </article>`;
    }).join("");
  }

  function renderSnapshot(snapshot) {
    const forecasts = [...(snapshot?.forecasts || [])].sort((a, b) => probabilityPercent(b) - probabilityPercent(a));

    $("#heroAnomalyCount").textContent = forecasts.length;
    $("#metricEvidence").textContent = snapshot?.summary?.evidence_items_considered ?? "—";
    $("#metricProblems").textContent = forecasts.length;
    $("#metricScans").textContent = snapshot?.summary?.dependency_edges_considered ?? "—";
    $("#metricSources").textContent = snapshot?.summary?.source_families || sourceFamilyCount(forecasts) || "—";
    $("#metricTopAnomaly").textContent = forecasts.length ? `${probabilityPercent(forecasts[0])}%` : "—";
    $("#runtimeMode").textContent = snapshot?.runtime_mode || "GitHub / HORIZON";

    if (snapshot?.generated_at) {
      $("#snapshotState").textContent = forecasts.length ? "Flux prédictif synchronisé" : "Snapshot sans scénario publiable";
      $("#snapshotTimestamp").textContent = `mis à jour ${formatRelative(snapshot.generated_at)}`;
    } else {
      $("#snapshotState").textContent = "Moteur prédictif en initialisation";
      $("#snapshotTimestamp").textContent = "aucun snapshot v2 généré";
    }

    const fieldEmpty = $("#fieldEmpty");
    if (fieldEmpty) {
      fieldEmpty.hidden = forecasts.length > 0;
      fieldEmpty.classList.toggle("hidden", forecasts.length > 0);
    }
    $("#queueStatusText").textContent = forecasts.length ? `${forecasts.length} ACTIVE${forecasts.length > 1 ? "S" : ""}` : "NO FORECAST";
    $("#queueStatusDot")?.classList.toggle("live", forecasts.length > 0);

    const top = $("#topAnomaly");
    if (top) {
      top.innerHTML = forecasts.length
        ? topForecastHtml(forecasts[0])
        : `<div class="top-anomaly-empty"><span>?</span><div><strong>Aucun scénario suffisamment soutenu</strong><small>Le moteur ne remplit pas l’écran avec des prédictions fictives.</small></div></div>`;
    }
    renderCards(forecasts);
    renderTerminal(snapshot, forecasts);
    renderSignalField(forecasts);
  }

  async function loadSnapshot() {
    try {
      const response = await fetch(`${SNAPSHOT_URL}?v=${Date.now()}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`snapshot HTTP ${response.status}`);
      const snapshot = await response.json();
      if (!String(snapshot?.schema || "").startsWith("evidence-public-snapshot-v2")) {
        renderSnapshot({ status: "migrating", generated_at: null, runtime_mode: "predictive-migration", summary: {}, forecasts: [] });
        terminalLine("warn", "Le flux public disponible est encore au format diagnostic v1 ; attente d’un snapshot prédictif v2.");
        return;
      }
      renderSnapshot(snapshot);
    } catch (error) {
      renderSnapshot({ status: "unavailable", generated_at: null, summary: {}, forecasts: [] });
      terminalLine("error", `Flux prédictif indisponible : ${error?.message || error}`);
      $("#snapshotState").textContent = "Flux prédictif indisponible";
    }
  }

  async function loadHeartbeat() {
    const badge = $("#heartbeatBadge");
    const text = $("#heartbeatText");
    try {
      const response = await fetch(HEARTBEAT_URL, { headers: { Accept: "application/vnd.github+json" }, cache: "no-store" });
      if (!response.ok) throw new Error(`heartbeat ${response.status}`);
      const data = await response.json();
      const run = data?.workflow_runs?.[0];
      if (!run) throw new Error("aucune exécution");
      const good = run.status === "in_progress" || run.conclusion === "success";
      badge.dataset.state = good ? "success" : "failure";
      text.textContent = run.status === "in_progress" ? "cycle en cours" : `${run.conclusion || run.status} · ${formatRelative(run.updated_at)}`;
    } catch (_) {
      badge.dataset.state = "failure";
      text.textContent = "heartbeat non vérifié";
    }
  }

  function initAmbient() {
    const canvas = $("#ambientCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let particles = [];
    function resize() {
      const dpr = Math.min(devicePixelRatio || 1, 2);
      canvas.width = innerWidth * dpr;
      canvas.height = innerHeight * dpr;
      canvas.style.width = `${innerWidth}px`;
      canvas.style.height = `${innerHeight}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      particles = Array.from({ length: Math.min(80, Math.max(35, Math.floor(innerWidth / 20))) }, (_, i) => ({
        x: (i * 137.3) % innerWidth,
        y: (i * 89.7) % innerHeight,
        r: 0.4 + (i % 5) * 0.18,
        phase: i * 0.73,
      }));
    }
    let t = 0;
    function draw() {
      ctx.clearRect(0, 0, innerWidth, innerHeight);
      t += 0.003;
      for (const p of particles) {
        const alpha = 0.08 + (Math.sin(t * 9 + p.phase) + 1) * 0.035;
        ctx.fillStyle = `rgba(105, 203, 230, ${alpha})`;
        ctx.beginPath();
        ctx.arc(p.x + Math.sin(t + p.phase) * 4, p.y + Math.cos(t * 0.8 + p.phase) * 3, p.r, 0, Math.PI * 2);
        ctx.fill();
      }
      requestAnimationFrame(draw);
    }
    addEventListener("resize", resize, { passive: true });
    resize(); draw();
  }

  let fieldAnimation = null;
  function renderSignalField(forecasts) {
    const canvas = $("#signalCanvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let nodes = [];
    let selected = null;
    let t = 0;

    function sharedDriver(a, b) {
      const left = new Set((a.drivers || []).filter((d) => d.type === "precursor_dependency").map((d) => d.label));
      return (b.drivers || []).some((d) => d.type === "precursor_dependency" && left.has(d.label));
    }

    function colorFor(p) {
      if (p >= 70) return [235, 103, 110];
      if (p >= 50) return [226, 176, 82];
      if (p >= 30) return [86, 190, 191];
      return [104, 129, 153];
    }

    function buildNodes(width, height) {
      nodes = forecasts.map((forecast, index) => {
        const p = probabilityPercent(forecast);
        const angle = (index / Math.max(1, forecasts.length)) * Math.PI * 2 + (index % 3) * 0.27;
        const ring = Math.min(width, height) * (0.22 + (index % 3) * 0.09);
        return {
          forecast,
          p,
          baseX: width / 2 + Math.cos(angle) * ring,
          baseY: height / 2 + Math.sin(angle) * ring * 0.66,
          x: 0,
          y: 0,
          r: 7 + p * 0.15,
          phase: index * 1.27,
          color: colorFor(p),
        };
      });
    }

    function resize() {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, rect.width * dpr);
      canvas.height = Math.max(1, rect.height * dpr);
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
          if (a.forecast.domain !== b.forecast.domain && !sharedDriver(a.forecast, b.forecast)) continue;
          ctx.strokeStyle = sharedDriver(a.forecast, b.forecast) ? "rgba(236, 145, 111, .24)" : "rgba(73, 152, 184, .14)";
          ctx.lineWidth = sharedDriver(a.forecast, b.forecast) ? 1.1 : 0.6;
          ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        }
      }
      for (const n of nodes) {
        const [r, g, b] = n.color;
        const pulse = 1 + Math.sin(t * 5 + n.phase) * 0.10;
        const rr = n.r * pulse;
        const grd = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, rr * 2.7);
        grd.addColorStop(0, `rgba(${r},${g},${b},.82)`);
        grd.addColorStop(.2, `rgba(${r},${g},${b},.28)`);
        grd.addColorStop(1, `rgba(${r},${g},${b},0)`);
        ctx.fillStyle = grd;
        ctx.beginPath(); ctx.arc(n.x, n.y, rr * 2.7, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = `rgba(${r},${g},${b},.62)`;
        ctx.lineWidth = selected === n ? 1.6 : .8;
        ctx.beginPath(); ctx.arc(n.x, n.y, rr, 0, Math.PI * 2); ctx.stroke();
      }
      fieldAnimation = requestAnimationFrame(draw);
    }

    canvas.onpointermove = (event) => {
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      selected = nodes.find((n) => Math.hypot(n.x - x, n.y - y) <= n.r * 1.7) || null;
      canvas.style.cursor = selected ? "pointer" : "default";
      $("#selectedNodeLabel").textContent = selected ? `${selected.forecast.event_type || "scénario"} · ${selected.p}%` : "—";
    };
    canvas.onpointerleave = () => {
      selected = null;
      $("#selectedNodeLabel").textContent = "—";
    };
    canvas.onclick = () => {
      if (!selected) return;
      const scenario = selected.forecast.scenario_key || "";
      const target = [...document.querySelectorAll("[data-scenario]")].find((el) => el.dataset.scenario === scenario);
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
    };

    addEventListener("resize", resize, { passive: true });
    if (fieldAnimation) cancelAnimationFrame(fieldAnimation);
    resize(); draw();
  }

  function startUtcClock() {
    const el = $("#utcClock");
    const tick = () => { if (el) el.textContent = new Date().toLocaleTimeString("fr-FR", { timeZone: "UTC", hour12: false }); };
    tick(); setInterval(tick, 1000);
  }

  function initDialog() {
    const dialog = $("#explainDialog");
    $("#explainButton")?.addEventListener("click", () => dialog?.showModal());
    $("#dialogClose")?.addEventListener("click", () => dialog?.close());
    dialog?.addEventListener("click", (event) => { if (event.target === dialog) dialog.close(); });
  }

  initAmbient();
  initDialog();
  startUtcClock();
  loadHeartbeat();
  loadSnapshot();
  setInterval(loadHeartbeat, 180000);
  setInterval(loadSnapshot, 300000);
})();