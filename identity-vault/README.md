# Quantic Identity Vault

Compagnon local de **Quantic ID**.

## Modes

### USB standard

- aucun code local à mémoriser ;
- `identity-vault.json` contient le coffre chiffré ;
- `identity-vault.key` contient le secret logiciel qui ouvre le coffre ;
- brancher la clé permet un déverrouillage en un clic ;
- retirer la clé verrouille l’identité.

Ce mode est simple, mais une copie complète de la clé USB peut être clonée.

### Quantic Hardware Key

Depuis la v0.4.0, Identity Vault comprend le protocole **QHK/1**.

Dans ce mode :

- la clé privée d’identité est créée dans un composant sécurisé ;
- elle n’est jamais écrite dans `identity-vault.json` ;
- elle n’est jamais transmise à Identity Vault, au navigateur ou au serveur ;
- la preuve Quantic ID est signée directement par la clé matérielle ;
- le profil personnel reste chiffré sur la clé USB ;
- la copie des fichiers USB ne suffit pas à reproduire l’identité.

Le protocole est USB HID et ne dépend d’aucun fournisseur cryptographique Microsoft, Google ou Apple. Le transport utilise seulement la pile HID de l’OS.

Le mode Hardware utilise **ECDSA P-256 / SHA-256** avec une signature IEEE-P1363. Les identités Ed25519 existantes restent compatibles.

## Matériel requis

Une clé USB de stockage ordinaire ne peut pas rendre une clé privée non exportable.

La garantie Hardware exige un périphérique dédié avec :

- microcontrôleur USB ;
- élément sécurisé ou enclave matérielle ;
- génération de clé P-256 interne ;
- export de la clé privée interdit par configuration matérielle.

Le protocole complet est documenté dans `hardware-key/PROTOCOL.md`.

Le firmware de référence est séparé du backend de l’élément sécurisé afin de ne pas verrouiller Quantic sur un fabricant unique.

## Profil personnel

Le coffre peut conserver localement :

- photo ;
- état civil ;
- coordonnées ;
- adresse ;
- activité professionnelle ;
- contact d’urgence ;
- informations complémentaires.

Ces données ne sont pas renvoyées par le bridge local.

## Bridge local

Identity Vault écoute uniquement sur `127.0.0.1:47621`.

- `GET /v1/status` : présence et identité active, sans profil personnel ;
- `POST /v1/assert` : demande une preuve cryptographique.

En mode Hardware, `/v1/assert` transmet le payload au périphérique QHK/1 et reçoit uniquement la signature.

## Migration

Créer une identité Hardware produit nécessairement une **nouvelle paire cryptographique** et donc un nouveau `qid_...`.

Avant remplacement du coffre actif, Identity Vault sauvegarde automatiquement le coffre existant.


## Compatibilité SWAPP.TV — v0.4.1

La version 0.4.1 (20 novembre 2026) autorise spécifiquement les origines HTTPS `https://swapp.tv` et `https://www.swapp.tv` pour la **présence Quantic ID optionnelle**.

- Installer l'édition Windows v0.4.1 sur le même PC que le navigateur.
- Lancer Identity Vault, puis déverrouiller l'identité.
- Ouvrir `https://swapp.tv/compte`, puis cliquer « Activer ma présence Quantic ID ».
- Si Chrome ou Edge le demande, autoriser l'accès de SWAPP aux **applications sur cet appareil** (réseau local / loopback). Ne jamais désactiver la sécurité générale du navigateur.
- Dans Identity Vault, confirmer le domaine `swapp.tv` dans la boîte de dialogue Quantic ID ; sans cet accord, aucune preuve n'est émise.
- L'autorisation d'un site n'est conservée qu'en mémoire pour la session déverrouillée. Le verrouillage du coffre annule l'autorisation et les preuves de présence ne peuvent plus être renouvelées.
- Le test direct `http://127.0.0.1:47621/v1/status` permet uniquement de savoir si le bridge local est lancé. Son état public est restreint pour les origines non autorisées.

Une erreur « Failed to fetch » sur SWAPP peut signifier que l'application est absente, que la version est trop ancienne ou qu'Edge/Chrome a refusé la connexion locale. Le site doit afficher un diagnostic précis au lieu de ce message générique.

La présence Quantic ID sur SWAPP n'accorde **aucun accès à un compte SWAPP existant**. Les comptes SWAPP, leurs messages et leurs droits ne sont pas migrés par cette mise à jour.
