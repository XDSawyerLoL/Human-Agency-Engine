import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
const read=name=>readFileSync(new URL(`../public/${name}`,import.meta.url),'utf8');

test('le schéma relie les trois étapes métier et annonce ses limites',()=>{
 const html=read('index.html');
 for (const t of ['Observer','Qualifier','Agir','source → qualification → impact → action']) assert.ok(html.includes(t),`Missing: ${t}`);
 assert.match(html,/SCÉNARIO FICTIF/);
 assert.match(html,/EXEMPLE NON RÉEL/);
 assert.match(html,/Aucune promesse de prédiction/);
});
test('le simulateur inclut trois métiers sans API ni métriques artificielles',()=>{
 const html=read('index.html'); const js=read('homepage-v4.js');
 for(const sector of ['transport','industrie','commerce']){
  assert.ok(html.includes(`data-sector="${sector}"`));
  assert.match(js,new RegExp(`\\b${sector}: \\{`));
 }
 assert.ok(!js.includes('fetch('));
 assert.ok(!js.includes('innerHTML'));
 assert.match(js,/setAttribute\('aria-pressed'/);
});
test('le formulaire existant et les conversions restent raccordés',()=>{
 const html=read('index.html'); const js=read('script.js');
 for (const id of ['contactForm','sendBtn','formStatus','demo']) assert.ok(html.includes(`id="${id}"`));
 for (const key of ['accepted_privacy','consent_marketing','utm_source','utm_medium','utm_campaign']) assert.ok(html.includes(key)||js.includes(key));
 assert.match(js,/fetch\('\/api\/leads'/);
 assert.match(html,/href="\/diagnostic\.html"/);
 assert.match(html,/href="\/ressources\.html"/);
});