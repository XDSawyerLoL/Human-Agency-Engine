import fs from "node:fs";
import assert from "node:assert/strict";

for(const path of [
  "identity-vault/package.json",
  "identity-vault/src/main.mjs",
  "identity-vault/src/preload.cjs",
  "identity-vault/src/renderer.js",
  "identity-vault/src/index.html",
  ".github/workflows/quantic-identity-vault.yml",
  "public/quantic-id-runtime.js"
]) assert.ok(fs.existsSync(path),path);

const pkg=JSON.parse(fs.readFileSync("identity-vault/package.json","utf8"));
assert.equal(pkg.productName,"Quantic Identity Vault");
assert.ok(pkg.scripts["dist:setup"]);
assert.ok(pkg.scripts["dist:portable"]);

const main=fs.readFileSync("identity-vault/src/main.mjs","utf8");
for(const marker of [
  "127.0.0.1",
  "47621",
  "/v1/status",
  "/v1/assert",
  "safeStorage",
  "PORTABLE_EXECUTABLE_DIR",
  "ed25519",
  "aes-256-gcm"
]) assert.ok(main.includes(marker),marker);

const runtime=fs.readFileSync("public/quantic-id-runtime.js","utf8");
assert.ok(runtime.includes("new Set([1,2,3])"));
assert.ok(main.includes('version:1'));

const downloads=fs.readFileSync("public/downloads/index.html","utf8");
assert.ok(downloads.includes("Quantic Identity Vault"));
assert.ok(downloads.includes("Quantic-Identity-Vault-Setup.exe"));
assert.ok(downloads.includes("Quantic-Identity-Vault-Portable.exe"));
assert.ok(downloads.toLowerCase().includes("clé usb"));

const identity=fs.readFileSync("public/quantic/index.html","utf8");
assert.ok(identity.includes("Quantic Identity Vault"));
assert.ok(identity.includes("Télécharger Identity Vault"));

console.log(JSON.stringify({ok:true,contract:"quantic-identity-vault-distribution"}));
