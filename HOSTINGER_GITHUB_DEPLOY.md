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

## Vérification avant mise en production

Le build exécute automatiquement le préflight Hostinger et les principaux tests PROVIDENCE. Un déploiement ne doit être publié que si `npm run build` réussit.

Version préparée : PROVIDENCE 1.16.20.
