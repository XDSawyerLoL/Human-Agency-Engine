import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const root = new URL('../', import.meta.url);
const publicDir = new URL('../public/', import.meta.url);
const read = (name) => readFileSync(new URL(name, publicDir), 'utf8');
const app = (name) => readFileSync(new URL(name, root), 'utf8');
const expected = ['veille-risques-entreprise','risque-inondation-entreprise','veille-energie-entreprise','risque-logistique-fournisseurs'];

test('quatre guides sourcés, page partenaire et ressources', () => {
  for(const slug of expected){
    const text=read(`${slug}.html`);
    assert.match(text, /rel="canonical"/);
    assert.match(text, /https:\/\//);
    assert.match(text, /Sources primaires/);
    assert.match(text, /source de référence|Sources primaires/i);
    assert.match(text, /Demander une démonstration/);
  }
  assert.match(read('partenaires.html'), /name="accepted_privacy"/);
  assert.match(read('partenaires.html'), /name="consent_marketing"/);
  assert.match(read('partenaires.html'), /data-source="partners"/);
});
test('référencement public et flux RSS sans exposition API',()=>{
  const sitemap=read('sitemap.xml');
  for (const slug of expected) assert.ok(sitemap.includes(`${slug}.html`));
  assert.ok(sitemap.includes('partenaires.html'));
  const robots=read('robots.txt');
  assert.match(robots, /Disallow: \/admin\.html/);
  assert.match(robots, /Disallow: \/api\//);
  assert.match(read('feed.xml'), /<rss/);
  assert.match(read('index.html'), /href="\/ressources\.html"/);
});
test('attribution partenaire conservée de bout en bout',()=>{
  assert.match(read('partners.js'), /utm_content/);
  assert.match(read('script.js'), /utm_content/);
  assert.match(app('api/leads.js'), /utm_content/);
  assert.match(app('api/admin/leads.js'), /utm_content/);
  assert.match(app('api/admin/stats.js'), /utm_content/);
});
test('purge programmée verrouillée par un secret serveur',()=>{
  const v=JSON.parse(app('vercel.json'));
  assert.equal(v.crons[0].path, '/api/internal/retention');
  assert.match(app('api/internal/retention.js'), /process\.env\.CRON_SECRET/);
  assert.match(app('api/internal/retention.js'), /interval '12 months'/);
  assert.ok(!read('index.html').includes('DATABASE_URL'));
});