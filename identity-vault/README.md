# Quantic Identity Vault

Compagnon local de **Quantic ID**.

## Modes

- **PC** : la clé privée Ed25519 et le profil personnel sont chiffrés avec `Electron safeStorage` et stockés dans le profil local.
- **Portable USB** : le coffre reste à côté de l’exécutable sur la clé. La clé privée **et le profil personnel** sont chiffrés avec AES-256-GCM. La clé de chiffrement est dérivée localement avec scrypt à partir du code choisi par l’utilisateur.

## Chargement et déverrouillage

Le chargement du fichier du coffre et son déverrouillage sont deux opérations distinctes :

1. l’utilisateur peut sélectionner et charger `identity-vault.json` (ou un fichier `.qivault`) sans saisir son code ;
2. le fichier chargé expose uniquement les métadonnées publiques nécessaires pour identifier le coffre ;
3. le code local est demandé seulement pour déchiffrer la clé privée et le profil personnel.

Les coffres de format v1 restent lisibles. Lorsqu’un ancien coffre est déverrouillé puis qu’un profil est enregistré, il est migré vers le format v2.

## Profil personnel chiffré

Le format v2 peut conserver localement :

- photo (PNG, JPEG ou WebP) ;
- prénom, autres prénoms, nom et nom d’usage ;
- date et lieu de naissance, nationalité, genre/civilité ;
- email et téléphone ;
- adresse complète ;
- profession, organisation et site web ;
- contact d’urgence ;
- informations complémentaires.

Ces données ne sont pas renvoyées par le bridge local. Leur éventuel partage avec un service Quantic devra passer par un mécanisme de consentement explicite.

## Bridge local

Identity Vault écoute uniquement sur `127.0.0.1:47621`.

- `GET /v1/status` : présence et identité active, sans profil personnel.
- `POST /v1/assert` : signe un challenge avec Ed25519.

La clé privée et le profil personnel ne sont jamais renvoyés par cette API locale.

## État de sécurité

La v0.2.0 sépare le chargement du coffre du déverrouillage, chiffre le profil avec la clé privée et conserve la compatibilité avec les coffres v1. Le portail Quantic peut vérifier qu’une identité est active via le bridge sans recevoir les données privées du profil.
