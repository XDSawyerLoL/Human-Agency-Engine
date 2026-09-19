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
assert.ok(session.includes("startIdentityPresenceGuard"),"Pulse must actively monitor Identity Vault presence");
assert.ok(session.includes("/api/pulse/auth/presence/challenge"),"Pulse must renew its server-side identity presence lease");
assert.ok(session.includes("await revokePulseSession()"),"Pulse must revoke its local/server session when Identity Vault disappears");

for(const marker of ["hashPassword(","verifyPassword(","weak_password","passwordSalt","passwordHash"]){
  assert.ok(!backend.includes(marker),marker+" must be removed from Pulse auth");
}
assert.ok(backend.includes("Object.values(store.users).find(user=>user.identityKeyId===identity.keyId)"),"login must resolve the account from Quantic ID");
assert.ok(backend.includes("identity_not_registered"),"unknown Quantic IDs need an explicit error");
assert.ok(backend.includes("handle=action==='register'?")&&backend.includes("verifyIdentityProof(b.identityProof,{action:'login',handle:''})"),"login challenge must support handle-free authentication");
assert.ok(backend.includes("PRESENCE_LEASE_MS=12000"),"Pulse sessions need a short cryptographic presence lease");
assert.ok(backend.includes("/api/pulse/auth/presence/challenge"),"Pulse backend must expose a presence challenge");
assert.ok(backend.includes("/api/pulse/auth/presence"),"Pulse backend must verify signed presence renewals");
assert.ok(backend.includes("presenceUntil"),"Pulse sessions must expire when identity presence is not renewed");
assert.equal(backend.includes("const s=store.sessions[sha(bearer(req))],user=s&&store.users[s.userId]"),false,"authenticated actions must not bypass the presence lease");

console.log(JSON.stringify({ok:true,contract:"pulse-passwordless-quantic-id"}));
