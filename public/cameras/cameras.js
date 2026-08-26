(() => {
  'use strict';

  const grid = document.querySelector('#cameraGrid');
  const filters = document.querySelector('#cameraFilters');
  const cameraCount = document.querySelector('#cameraCount');
  const regionCount = document.querySelector('#regionCount');
  const visibleCount = document.querySelector('#visibleCount');
  const collator = new Intl.Collator('fr', { sensitivity: 'base' });
  let cameras = [];
  let activeRegion = 'Toutes';

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
  })[character]);

  const localTime = timezone => {
    try {
      return new Intl.DateTimeFormat('fr-FR', {
        timeZone: timezone,
        hour: '2-digit',
        minute: '2-digit',
        hour12: false
      }).format(new Date());
    } catch {
      return '—';
    }
  };

  const cameraCard = camera => `
    <article class="camera-card" data-region="${escapeHtml(camera.region)}" data-camera-id="${escapeHtml(camera.id)}">
      <div class="camera-player">
        <iframe
          src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(camera.video_id)}?rel=0&modestbranding=1"
          title="Caméra en direct : ${escapeHtml(camera.name)}, ${escapeHtml(camera.city)}"
          loading="lazy"
          referrerpolicy="strict-origin-when-cross-origin"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowfullscreen></iframe>
        <span class="camera-live"><i></i> DIRECT EXTERNE</span>
        <span class="camera-kind">${escapeHtml(camera.kind)}</span>
      </div>
      <div class="camera-copy">
        <div>
          <p class="camera-place">${escapeHtml(camera.city)} · ${escapeHtml(camera.country)}</p>
          <h2>${escapeHtml(camera.name)}</h2>
        </div>
        <div class="camera-clock"><strong data-timezone="${escapeHtml(camera.timezone)}">${localTime(camera.timezone)}</strong><small>HEURE LOCALE</small></div>
      </div>
      <div class="camera-source">
        <span>Source : <strong>${escapeHtml(camera.provider)}</strong></span>
        <a href="${escapeHtml(camera.source_url)}" target="_blank" rel="noopener noreferrer">Ouvrir la source <b>↗</b></a>
      </div>
    </article>`;

  function renderFilters() {
    const regions = ['Toutes', ...new Set(cameras.map(camera => camera.region).sort(collator.compare))];
    filters.innerHTML = regions.map(region => `
      <button type="button" class="filter-button${region === activeRegion ? ' active' : ''}" data-region="${escapeHtml(region)}" aria-pressed="${region === activeRegion}">${escapeHtml(region)}</button>
    `).join('');
    filters.querySelectorAll('button').forEach(button => button.addEventListener('click', () => {
      activeRegion = button.dataset.region;
      renderFilters();
      renderCameras();
    }));
  }

  function renderCameras() {
    const visible = activeRegion === 'Toutes' ? cameras : cameras.filter(camera => camera.region === activeRegion);
    visibleCount.textContent = visible.length;
    grid.innerHTML = visible.length
      ? visible.map(cameraCard).join('')
      : '<div class="camera-empty"><strong>Aucun flux dans cette zone.</strong><span>Choisissez une autre région.</span></div>';
  }

  function updateClocks() {
    document.querySelectorAll('[data-timezone]').forEach(clock => {
      clock.textContent = localTime(clock.dataset.timezone);
    });
  }

  async function loadCatalog() {
    try {
      const response = await fetch(`./catalog.json?t=${Date.now()}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const catalog = await response.json();
      if (!Array.isArray(catalog.cameras) || !catalog.cameras.length) throw new Error('catalogue vide');
      cameras = catalog.cameras;
      cameraCount.textContent = cameras.length;
      regionCount.textContent = new Set(cameras.map(camera => camera.region)).size;
      renderFilters();
      renderCameras();
      updateClocks();
    } catch (error) {
      cameraCount.textContent = '0';
      regionCount.textContent = '0';
      visibleCount.textContent = '0';
      grid.innerHTML = `<div class="camera-empty error"><strong>Le catalogue des caméras est momentanément indisponible.</strong><span>${escapeHtml(error.message)}</span><button type="button" id="retryCatalog">Réessayer</button></div>`;
      document.querySelector('#retryCatalog')?.addEventListener('click', loadCatalog);
    }
  }

  loadCatalog();
  setInterval(updateClocks, 60 * 1000);
})();
