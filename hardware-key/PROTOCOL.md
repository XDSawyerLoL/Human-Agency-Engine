# Quantic Hardware Key — QHK/1

QHK/1 est le protocole ouvert entre **Quantic Identity Vault** et une clé matérielle Quantic.

## Objectif de sécurité

La clé privée d'identité est générée dans un composant sécurisé et ne doit jamais être exportée vers le PC, la clé USB de stockage ou le réseau.

Le stockage USB contient uniquement :

- le coffre chiffré `identity-vault.json` ;
- la clé publique ;
- l'identifiant du périphérique matériel ;
- les métadonnées nécessaires à Identity Vault.

Le secret qui ouvre le profil chiffré est fourni temporairement par le périphérique matériel lorsqu'il est physiquement connecté. La clé privée de signature, elle, ne sort jamais du composant sécurisé.

## Transport

- USB HID, sans pilote propriétaire.
- Rapport HID : 64 octets.
- Report ID : `1`.
- Version protocole : `1`.
- VID/PID de développement : `0xCAFE / 0x5148`.
- La production devra utiliser un VID/PID officiellement attribué ; ces identifiants de développement ne constituent pas une allocation USB officielle.

Le protocole ne dépend d'aucun fournisseur cryptographique Microsoft, Google ou Apple. Sous chaque OS, Identity Vault utilise seulement la pile HID du système pour transporter les paquets.

## Format d'un rapport

| Offset | Taille | Champ |
|---|---:|---|
| 0 | 4 | ASCII `QHK1` |
| 4 | 1 | version protocole |
| 5 | 1 | commande |
| 6 | 2 | request id, little endian |
| 8 | 1 | index du fragment |
| 9 | 1 | nombre total de fragments |
| 10 | 1 | longueur utile |
| 11 | 53 | données UTF-8 JSON |

Une réponse utilise la commande de requête avec le bit `0x80` activé.

## Commandes

### 0x01 INFO

Réponse minimale :

```json
{
  "protocol": 1,
  "deviceId": "qhk_...",
  "firmware": "0.1.0",
  "secureElement": true,
  "provisioned": true
}
```

### 0x02 PROVISION

Crée, si nécessaire, l'identité dans le composant sécurisé.

Requête :

```json
{"algorithm":"ecdsa-p256-sha256"}
```

Réponse :

```json
{
  "deviceId": "qhk_...",
  "publicKeyRaw": "<base64url du point SEC1 non compressé 65 octets>",
  "vaultKey": "<secret aléatoire >= 256 bits>"
}
```

La clé privée P-256 reste non exportable. `vaultKey` est un secret distinct utilisé uniquement pour chiffrer le profil local.

### 0x03 UNLOCK

Réponse :

```json
{
  "deviceId": "qhk_...",
  "vaultKey": "<secret du coffre>"
}
```

### 0x04 SIGN

Requête :

```json
{"payload":"<payload Quantic ID exact>"}
```

Réponse :

```json
{"signature":"<ECDSA P-256 SHA-256, IEEE-P1363 r||s, base64url>"}
```

## Algorithme d'identité

Le mode Hardware utilise `ecdsa-p256-sha256`.

Le `keyId` est calculé par Identity Vault comme pour les identités existantes :

```
qid_ + first_32_hex(SHA256(SPKI_DER(public_key)))
```

## Règles matérielles

Un périphérique ne peut être présenté comme **Quantic Hardware Key sécurisé** que si :

1. la clé privée est créée dans un élément sécurisé ou une enclave matérielle ;
2. l'interface du composant interdit l'export de cette clé privée ;
3. le firmware ne contient aucune commande permettant de lire la clé privée ;
4. un clonage bit-à-bit du stockage USB ne suffit pas à signer ;
5. la génération aléatoire matérielle est utilisée pour les secrets persistants ;
6. le firmware et le schéma matériel peuvent être audités.

Une implémentation purement logicielle peut servir de simulateur de développement, mais ne doit jamais être annoncée comme non exportable.
