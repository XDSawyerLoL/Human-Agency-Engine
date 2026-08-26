import { moduleCatalog } from '../src/lab_modules.js';

const modules = moduleCatalog();
const byKey = new Map(modules.map(m => [m.key, m]));
for (const key of ['gdelt','pubmed','arxiv','polymarket','trends','fred','metaculus','windy']) {
  if (!byKey.has(key)) throw new Error(`missing lab module: ${key}`);
}
for (const key of ['gdelt','pubmed','arxiv','fred']) {
  if (!byKey.get(key).core_input) throw new Error(`${key} must be marked as engine input`);
}
for (const key of ['polymarket','trends','metaculus','windy']) {
  if (byKey.get(key).core_input) throw new Error(`${key} must stay external/reference-only`);
}
if (!Array.isArray(byKey.get('gdelt').themes) || byKey.get('gdelt').themes.length < 8) throw new Error('GDELT thematic module is too narrow');
console.log(`lab modules ok: ${modules.map(m => m.key).join(', ')}`);
