import {test} from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
const text=readFileSync(new URL('../api/admin/health.js',import.meta.url),'utf8');
test('la route de santé est protégée par ADMIN_SECRET',()=>{assert.match(text,/verifyAdmin\(req\)/);assert.match(text,/401/);assert.match(text,/SELECT now\(\)/);assert.match(text,/information_schema\.tables/)});
test('la route ne renvoie ni données personnelles ni mot de passe',()=>{assert.doesNotMatch(text,/SELECT \*/);assert.doesNotMatch(text,/process\.env\.(?:DATABASE_URL|ADMIN_SECRET)/);});