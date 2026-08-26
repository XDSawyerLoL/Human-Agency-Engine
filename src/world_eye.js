const EPIC_API = 'https://epic.gsfc.nasa.gov/api/natural';
const CACHE_MS = 20 * 60_000;
let cache = null;
let cacheAt = 0;

function imageUrl(item) {
  const raw = String(item?.date || '').slice(0, 10);
  const [year, month, day] = raw.split('-');
  if (!year || !month || !day || !item?.image) return null;
  return `https://epic.gsfc.nasa.gov/archive/natural/${year}/${month}/${day}/png/${item.image}.png`;
}

export async function getWorldEye() {
  if (cache && Date.now() - cacheAt < CACHE_MS) return cache;
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 12_000);
    const response = await fetch(EPIC_API, {
      signal: controller.signal,
      headers: { accept: 'application/json', 'user-agent': 'Evidence-World-Eye/1.0' }
    });
    clearTimeout(timer);
    if (!response.ok) throw new Error(`NASA EPIC HTTP ${response.status}`);
    const rows = await response.json();
    if (!Array.isArray(rows) || !rows.length) throw new Error('NASA EPIC: aucune acquisition');
    const latest = [...rows].sort((a, b) => String(b?.date || '').localeCompare(String(a?.date || '')))[0];
    const url = imageUrl(latest);
    if (!url) throw new Error('NASA EPIC: image invalide');
    cache = {
      status: 'live',
      provider: 'NASA DSCOVR / EPIC',
      instrument: 'Earth Polychromatic Imaging Camera',
      captured_at: latest.date || null,
      image_url: url,
      caption: latest.caption || 'Face éclairée de la Terre vue depuis le point L1.',
      centroid_coordinates: latest.centroid_coordinates || null,
      source_url: 'https://epic.gsfc.nasa.gov/',
      freshness_note: 'Dernière acquisition disponible publiée par NASA EPIC.'
    };
    cacheAt = Date.now();
    return cache;
  } catch (error) {
    if (cache) return { ...cache, status: 'stale', error: String(error?.message || error) };
    throw error;
  }
}
