import { moduleCatalog, runLabModule } from '../src/lab_modules.js';
import { scenarioMemoryStats } from '../src/scenario_memory.js';

const modules = moduleCatalog().filter(m => m.key !== 'future-engine');
const byKey = new Map(modules.map(m => [m.key, m]));
for (const key of ['gdelt','pubmed','arxiv','polymarket','trends','fred','metaculus','windy']) {
  if (!byKey.has(key)) throw new Error(`missing public lab module: ${key}`);
  if (!byKey.get(key).actionable) throw new Error(`${key} is published but not actionable`);
}
for (const key of ['gdelt','pubmed','arxiv','fred']) {
  if (!byKey.get(key).core_input) throw new Error(`${key} must be marked as engine input`);
}
for (const key of ['polymarket','trends','metaculus','windy']) {
  if (byKey.get(key).core_input) throw new Error(`${key} must stay external/reference-only`);
}
if (!Array.isArray(byKey.get('gdelt').themes) || byKey.get('gdelt').themes.length < 8) throw new Error('GDELT thematic module is too narrow');
const stats=scenarioMemoryStats(Date.parse('2026-08-26T12:00:00Z'));
if (stats.total !== 60 || stats.active < 50) throw new Error(`scenario memory incomplete: ${JSON.stringify(stats)}`);

// These modules are deterministic/local and must work even when external APIs are unavailable.
for (const key of ['metaculus','windy']) {
  const result=await runLabModule(key);
  if (result?.key !== key) throw new Error(`${key} did not execute`);
  if (key==='metaculus' && !(result.items||[]).length) throw new Error('Metaculus module did not expose remembered forecasting questions');
  if (key==='windy' && !result.map_embed_url) throw new Error('Windy module did not expose a map');
}
console.log(`lab modules ok: ${modules.map(m => m.key).join(', ')}; scenario memory=${stats.total}`);
