import { moduleCatalog } from '../src/lab_modules.js';
import { getFutureEngineCatalogStats, getFutureEngineReferenceForecasts } from '../src/future_engine_reference.js';

const modules = moduleCatalog();
const byKey = new Map(modules.map(m => [m.key, m]));
for (const key of ['future-engine','gdelt','pubmed','arxiv','polymarket','trends','fred','metaculus','windy']) {
  if (!byKey.has(key)) throw new Error(`missing lab module: ${key}`);
  if (!byKey.get(key).actionable) throw new Error(`${key} is published but not actionable`);
}
for (const key of ['gdelt','pubmed','arxiv','fred']) {
  if (!byKey.get(key).core_input) throw new Error(`${key} must be marked as engine input`);
}
for (const key of ['future-engine','polymarket','trends','metaculus','windy']) {
  if (byKey.get(key).core_input) throw new Error(`${key} must stay external/reference-only`);
}
if (!Array.isArray(byKey.get('gdelt').themes) || byKey.get('gdelt').themes.length < 8) throw new Error('GDELT thematic module is too narrow');
const stats=getFutureEngineCatalogStats();
if (stats.total !== 57) throw new Error(`Future Engine catalog incomplete: ${stats.total}/57`);
if (getFutureEngineReferenceForecasts({activeOnly:false}).length !== 57) throw new Error('Future Engine transformer lost forecast cards');
console.log(`lab modules ok: ${modules.map(m => m.key).join(', ')}; Future Engine catalog=${stats.total}`);
