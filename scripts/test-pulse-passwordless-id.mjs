import fs from "node:fs";
import assert from "node:assert/strict";

const html=fs.readFileSync("public/pulse/index.html","utf8");
const app=fs.readFileSync("public/pulse/app.js","utf8");
const session=fs.readFileSync("public/pulse/session.js","utf8");
const backend=fs.readFileSync("src/quantic_pulse.js","utf8");

assert.ok(!html.includes('auth-password'),"Pulse must not render a password field");
assert.ok(!html.includes('Mot de passe'),"Pulse must not mention a password in auth UI");
assert.ok(html.includes('id="handle-field"'),"register handle field needs an explicit wrapper");

assert.ok(!app.includes("auth-password"),"Pulse auth JS must not read a password");
assert.ok(!app.includes("password:"),"Pulse auth requests must not send a password");
assert.ok(app.includes("identityProof('login','')"),"login must be driven only by Identity Vault");

assert.ok(session.includes("handleField.hidden=!register"),"handle field must be hidden for login");
assert.ok(session.includes("Entrer avec Quantic ID"),"login CTA must be passwordless");

for(const marker of ["hashPassword(","verifyPassword(","weak_password","passwordSalt","passwordHash"]){
  assert.ok(!backend.includes(marker),marker+" must be removed from Pulse auth");
}
assert.ok(backend.includes("Object.values(store.users).find(user=>user.identityKeyId===identity.keyId)"),"login must resolve the account from Quantic ID");
assert.ok(backend.includes("identity_not_registered"),"unknown Quantic IDs need an explicit error");
assert.ok(backend.includes("action==='login'"),"login challenge must support handle-free authentication");

console.log(JSON.stringify({ok:true,contract:"pulse-passwordless-quantic-id"}));
