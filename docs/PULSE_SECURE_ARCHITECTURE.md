# Pulse Secure — sécurité et décentralisation

Date: 2026-09-21
Status: architecture active, E2EE V1 implemented

## Product rule

Quantic Sillage treats security and decentralization as product constraints, not marketing labels.

For Pulse:

- public posts are ephemeral and expire after 24 hours;
- private messages are persistent by default;
- private-message plaintext must never be stored by the Pulse server or a relay;
- Quantic ID is the root used to authorize Pulse devices;
- a transport outage must never reset a mailbox or replace durable state with an empty local file;
- encrypted envelopes must remain portable between transports so no single relay becomes mandatory.

## Pulse Secure V1 — implemented

Private-message clients now generate device-local cryptographic material:

- X25519 encryption key;
- Ed25519 signing key;
- private keys stored as non-extractable browser CryptoKey objects in IndexedDB;
- public device keys registered only after a fresh Quantic Identity Vault proof.

A private message is encrypted independently for each recipient device and for the sender's own registered devices.

Each envelope uses:

- a fresh ephemeral X25519 key;
- X25519 shared-secret derivation;
- HKDF-SHA-256;
- AES-256-GCM with authenticated associated data;
- an Ed25519 device signature.

The Pulse backend stores only the opaque encrypted envelopes plus minimal routing metadata. New plaintext private-message submissions are rejected with `e2ee_required`.

The client pins the peer's Quantic identity on first contact and blocks silent identity-key replacement. A conversation exposes a human-readable safety number derived from both Quantic identities.

## What V1 does not claim

Pulse Secure V1 is **not the Signal Protocol** and must not be described as Signal-compatible or Signal-grade.

V1 does not yet provide a complete X3DH/PQXDH + Double Ratchet state machine. Compromise of a recipient's long-lived encryption private key can therefore weaken confidentiality of historical V1 ciphertexts.

This limitation is explicit until the ratchet layer is implemented and audited.

## V2 cryptographic target

The next cryptographic layer must add:

1. signed one-time prekeys per device;
2. asynchronous initial key agreement following the PQXDH/X3DH model;
3. a Double Ratchet session with per-message key deletion;
4. skipped-message-key handling for out-of-order delivery;
5. multi-device session management;
6. device revocation and key-change warnings;
7. encrypted local history and secure device transfer;
8. protocol-version negotiation with fail-closed downgrade protection.

No home-grown shortcut may be marketed as Double Ratchet.

## Decentralized transport target

Pulse must reuse Quantic Network instead of creating a second incompatible relay system.

Quantic Network already has:

- durable encrypted queues;
- signed device identities;
- one-time prekey pools;
- multiple relay endpoints;
- relay failover;
- signed Route Manifests;
- relay-to-relay Federation V1;
- anti-replay/idempotence;
- delivery receipts;
- local/NAS/VPS self-hosting.

Pulse Secure envelopes are transport payloads. The relay must remain unable to decrypt them.

Target path:

```
Pulse device
  -> Pulse Secure encryption / ratchet
  -> opaque portable envelope
  -> Quantic Network relay A
  -> federation / route manifest
  -> relay B or local self-hosted relay
  -> recipient device
  -> local decryption
```

The Pulse application server remains useful for public social content and discovery, but must not become a mandatory plaintext private-message authority.

## Release gates

Pulse private messaging cannot be presented as fully decentralized until all of the following are true:

- a message can be sent and received through at least two independent Quantic relays;
- the conversation still works when the main Pulse application API is unavailable after first contact;
- relay failover does not change user identity;
- relays store ciphertext only;
- duplicate delivery is idempotent;
- device revocation converges across relay routes;
- the cryptographic protocol has deterministic interoperability tests and external review.

Pulse cannot be presented as Signal-equivalent until PQXDH/X3DH + Double Ratchet behavior is implemented, tested against published vectors where available, and independently reviewed.
