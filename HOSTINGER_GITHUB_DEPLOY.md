# PROVIDENCE — Déploiement Hostinger depuis GitHub

Dépôt : `XDSawyerLoL/Human-Agency-Engine`
Branche de production : `main`
Runtime : Node.js 22.x

## Paramètres Hostinger

- Répertoire du projet : racine du dépôt
- Commande d'installation : `npm install`
- Commande de build : `npm run build`
- Commande de démarrage : `npm start`
- Fichier d'entrée : `server.js`
- Port : fourni automatiquement par Hostinger via la variable `PORT`

PROVIDENCE écoute sur `0.0.0.0` et lit `process.env.PORT`, ce qui permet à Hostinger d'attribuer le port du runtime.

## Variables d'environnement

PROVIDENCE peut démarrer sans les fournisseurs optionnels. Les variables suivantes activent des capacités supplémentaires lorsqu'elles sont disponibles :

- `FRED_API_KEY`
- `FORECAST_API_KEY`
- `WINDY_POINT_FORECAST_API_KEY`
- `COPERNICUS_API_KEY`
- `POINT_API_KEY`
- `METACULUS_API_KEY`
- `FOOTBALL_DATA_API_KEY`
- `PROVIDENCE_QWEN_BASE_URL`
- `PROVIDENCE_QWEN_API_KEY`
- `PROVIDENCE_QWEN_MODEL`
- `PROVIDENCE_REDTEAM_MODEL`
- `SUPABASE_URL`
- `SUPABASE_API_KEY`
- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`
- `EVIDENCE_ADMIN_KEY`
- `MAIRAIY_NODE_NATIVE_ENABLED` (default: true)
- `MAIRAIY_PUBLIC_SPEECH_ENABLED` (default: true)
- `MAIRAIY_PUBLIC_REQUESTS_PER_MINUTE`
- `MAIRAIY_PUBLIC_REQUESTS_PER_DAY`
- `MAIRAIY_KOKORO_DTYPE` (default: q8)
- `MAIRAIY_KOKORO_CACHE_DIR`
- legacy optional: `MAIRAIY_VOICE_UPSTREAM_URL`, `MAIRAIY_VOICE_PROXY_TOKEN`, `MAIRAIY_VOICE_UPSTREAM_API_KEY`

## Vérification avant mise en production

Le build exécute automatiquement le préflight Hostinger et les principaux tests PROVIDENCE. Un déploiement ne doit être publié que si `npm run build` réussit.

Version préparée : PROVIDENCE 1.16.20.


## Voix Mairaiy

La production Hostinger gérée reste **100 % Node.js 22**. Mairaiy tourne désormais directement dans ce même processus :

- modèle : `onnx-community/Kokoro-82M-v1.0-ONNX`, révision épinglée ;
- variante : q8 par défaut ;
- moteur : Transformers.js / ONNX Runtime Node ;
- phonémisation française : eSpeak-NG WASM via `phonemizer` ;
- identité : `ff_siwis`, `fr-fr` ;
- aucun appel TTS facturé ;
- chargement paresseux : Providence démarre sans charger ~100 Mo de modèle ;
- cache local configurable ;
- limites publiques par IP + plafond journalier pour éviter qu'un endpoint gratuit soit transformé en service TTS ouvert illimité.

Routes publiques :

```text
GET  /voice/status
GET  /voice/health
GET  /voice/.well-known/voicestudio-speech
GET  /voice/v1/audio/voices
GET  /voice/v1/models
POST /voice/v1/audio/speech
```

Le premier `POST /voice/v1/audio/speech` télécharge le modèle q8 et `ff_siwis`, puis les appels suivants réutilisent le runtime chargé. Un ancien backend VPS peut rester configuré uniquement comme repli optionnel.
