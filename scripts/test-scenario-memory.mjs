import { buildScenarioMemoryForecasts, scenarioMemoryStats, scenarioMemorySeeds } from '../src/scenario_memory.js';
import { selectPublicForecasts } from '../src/public_selection.js';

const now = Date.parse('2026-08-26T12:00:00Z');
const stats = scenarioMemoryStats(now);
if (stats.total !== 57) throw new Error(`scenario memory incomplete: ${stats.total}/57`);
if (stats.active < 50) throw new Error(`too few active scenario-memory seeds: ${stats.active}`);
if (scenarioMemorySeeds({activeOnly:false}).length !== 57) throw new Error('scenarioMemorySeeds lost catalog entries');

const rows = buildScenarioMemoryForecasts([], { now });
if (rows.length !== stats.active) throw new Error(`memory builder mismatch: ${rows.length}/${stats.active}`);
if (new Set(rows.map(x => x.scenario_id)).size !== rows.length) throw new Error('scenario memory produced duplicate scenario ids');
for (const needle of ['cadre contraignant','suppressions de postes','mer de Chine','banque centrale','nuclear fusion']) {
  if (!rows.some(x => `${x.title}`.toLowerCase().includes(needle.toLowerCase()))) throw new Error(`missing remembered scenario: ${needle}`);
}
if (!rows.every(x => x.memory?.recomputed && x.probability?.method === 'evidence-scenario-memory-v2')) throw new Error('scenario memory forecasts are not explicitly recomputed');

const selected = selectPublicForecasts(rows, 72);
if (selected.length < 25) throw new Error(`public selector suppresses too much scenario memory: ${selected.length}`);
if (selected.filter(x => x.event_type === 'memory_climate_scenario').length > 7) throw new Error('climate memory escaped environmental cap');
console.log(`scenario memory ok: ${stats.total} total, ${stats.active} active, ${selected.length} publishable under diversity caps`);
