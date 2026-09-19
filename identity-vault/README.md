# Quantic Identity Vault

Compagnon local de **Quantic ID**.

## Modes

- **PC** : la clé privée Ed25519 est chiffrée avec `Electron safeStorage` et stockée dans le profil local.
- **Portable USB** : le coffre reste à côté de l’exécutable sur la clé et la clé privée est chiffrée avec AES-256-GCM. La clé de chiffrement est dérivée localement avec scrypt à partir du code choisi par l’utilisateur.

## Bridge local

Identity Vault écoute uniquement sur `127.0.0.1:47621`.

- `GET /v1/status` : présence et identité active.
- `POST /v1/assert` : signe un challenge avec Ed25519.

La clé privée n’est jamais renvoyée par l’API locale.

## État de sécurité

La release 0.1.0 fournit la brique locale et la signature de challenge. Le portail Mail utilise actuellement la présence d’une identité active comme verrou d’ouverture. La validation cryptographique serveur du challenge reste la prochaine étape du SSO Quantic ID.
