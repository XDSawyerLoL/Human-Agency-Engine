import { readFile } from 'node:fs/promises';

const path = new URL('../public/cameras/catalog.json', import.meta.url);
const catalog = JSON.parse(await readFile(path, 'utf8'));
const cameras = catalog.cameras;

if (!Array.isArray(cameras) || cameras.length < 8) {
  throw new Error('The public camera catalog must contain at least eight cameras.');
}

const ids = new Set();
const regions = new Set();
for (const camera of cameras) {
  for (const field of ['id', 'name', 'city', 'country', 'region', 'kind', 'timezone', 'video_id', 'provider', 'source_url']) {
    if (typeof camera[field] !== 'string' || !camera[field].trim()) {
      throw new Error(`Camera ${camera.id || '<unknown>'} is missing ${field}.`);
    }
  }
  if (ids.has(camera.id)) throw new Error(`Duplicate camera id: ${camera.id}`);
  if (!/^https:\/\/www\.youtube\.com\/watch\?v=[A-Za-z0-9_-]{11}$/.test(camera.source_url)) {
    throw new Error(`Invalid public camera source URL: ${camera.source_url}`);
  }
  if (!/^[A-Za-z0-9_-]{11}$/.test(camera.video_id)) throw new Error(`Invalid YouTube video id: ${camera.video_id}`);
  new Intl.DateTimeFormat('fr-FR', { timeZone: camera.timezone }).format(new Date());
  ids.add(camera.id);
  regions.add(camera.region);
}

if (regions.size < 6) throw new Error('The camera catalog must cover at least six world regions.');

console.log(`Live camera catalog OK: ${cameras.length} feeds across ${regions.size} regions.`);
