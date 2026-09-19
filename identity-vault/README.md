# Quantic Identity Vault

Compagnon local de **Quantic ID**.

## Modes

- **PC** : la clé privée Ed25519 et le profil personnel sont chiffrés avec `Electron safeStorage`.
- **Portable USB** : aucun code local n’est demandé. La présence physique de la clé USB est le facteur d’accès.

## Déverrouillage USB sans code

Depuis la v0.3.0, un coffre USB est composé de deux éléments placés ensemble sur la clé :

- `identity-vault.json` : coffre chiffré contenant la clé privée et le profil ;
- `identity-vault.key` : secret cryptographique aléatoire généré automatiquement.

L’utilisateur ne saisit aucun mot de passe. Si les deux fichiers sont présents sur la clé, un clic sur **Déverrouiller** active Quantic ID. **Verrouiller** retire la clé privée de la mémoire. Si la clé USB disparaît, l’identité active est automatiquement invalidée.

Ce modèle protège surtout contre l’utilisation de l’identité sans possession de la clé USB. Une personne qui obtient physiquement la clé complète obtient également le facteur de déverrouillage.

## Anciens coffres

Les coffres v1/v2 protégés par un code local sont détectés comme anciens formats. Ils ne peuvent pas être déchiffrés sans leur ancien code. Lorsqu’une nouvelle identité USB sans code est créée, l’ancien `identity-vault.json` est sauvegardé automatiquement sous un nom `identity-vault.backup-*.json` avant remplacement.

## Profil personnel chiffré

Le coffre peut conserver localement la photo, l’état civil, les coordonnées, l’adresse, l’activité professionnelle, un contact d’urgence et des informations complémentaires. Ces données ne sont jamais exposées par le bridge local sans mécanisme de partage explicite.

## Bridge local

Identity Vault écoute uniquement sur `127.0.0.1:47621`.

- `GET /v1/status` : présence et identité active, sans profil personnel.
- `POST /v1/assert` : signe un challenge avec Ed25519.

La clé privée et le profil personnel ne sont jamais renvoyés par cette API locale.
