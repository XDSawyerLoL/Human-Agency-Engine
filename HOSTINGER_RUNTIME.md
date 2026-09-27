# HORIZON / ÉVIDENCE — runtime Hostinger

GitHub is source control only. It must not store or execute the rolling HORIZON world state.

## Production topology

- `db`: PostgreSQL 17 with persistent Docker volume.
- `api`: HORIZON FastAPI, private on `127.0.0.1:8000` by default.
- `init`: one-shot synchronization of source registry and predictive pattern libraries.
- `collector`: permanent world collector.
- `corpus-worker`: historical calibration worker, rate-separated from live collection.
- `snapshot`: regenerates the sanitized ÉVIDENCE public snapshot locally every 5 minutes.
- `web`: Nginx serves the ÉVIDENCE cockpit and the local snapshot on port `8080` by default.
- `backup`: daily PostgreSQL application dump with seven-day retention by default.
- `mairaiy-voice` (optional profile `voice`): lightweight Kokoro ONNX / `ff_siwis`, private on the Docker network and reverse-proxied by the VPS Nginx under `/voice/`.

The former `.github/workflows/horizon-live.yml` runtime is intentionally removed. No rolling SQLite database or HORIZON state artifact should be uploaded to GitHub again.

## Deploy on a Hostinger VPS

Hostinger VPS Docker Manager can deploy a Docker Compose project from a repository/Compose URL. The same stack can also be launched over SSH.

1. Install/use a Hostinger VPS with Docker support.
2. Put this repository on the VPS (Docker Manager repository deployment or `git clone`).
3. Copy `.env.hostinger.example` to `.env.hostinger` and fill the required secrets.
4. Run:

```bash
bash scripts/hostinger_deploy.sh
```

Equivalent manual command:

```bash
docker compose --env-file .env.hostinger -f docker-compose.hostinger.yml up -d --build --remove-orphans
```

Then verify:

```bash
docker compose --env-file .env.hostinger -f docker-compose.hostinger.yml ps
curl http://127.0.0.1:8000/ready
curl http://127.0.0.1:8080/data/evidence-live.json
```

The public cockpit is available on `http://SERVER_IP:8080/` until a domain/reverse proxy is attached.

## Data migration policy

Do **not** import the old multi-gigabyte GitHub SQLite state wholesale. That state contains repeated/raw collection material that caused the GitHub artifact growth. Start the PostgreSQL runtime clean and let the current-world collectors rebuild active evidence. Preserve only explicitly useful compact calibration exports or public probability trajectories if needed.

## Backups

Application-level PostgreSQL dumps are stored in the Docker volume `horizon_postgres_backups`. Default interval is 24 hours and retention is seven days. Hostinger VPS backups can be used as an additional infrastructure recovery layer.

## Updating the application

After code changes:

```bash
git pull --ff-only
bash scripts/hostinger_deploy.sh
```

Runtime data remains in PostgreSQL volumes and is not replaced by rebuilding containers.


## Mairaiy / AURA Voice Fabric

### Managed Node production — preferred path

`mediumorchid-badger-314305.hostingersite.com` is deployed from this repository's `main` branch as a Hostinger managed **Node.js 22** Web App. Mairaiy now runs directly inside that Node process; no VPS voice service is required for the normal production path.

The native engine lives in `src/mairaiy_kokoro_node.js` and uses:

- pinned Kokoro ONNX model revision `1939ad2a8e416c0acfeecc08a694d14ef25f2231`;
- q8 inference by default;
- CPU execution through Transformers.js / ONNX Runtime Node;
- French phonemization with the pure-JavaScript `@piper-plus/g2p` French rules;
- locked voice `ff_siwis`;
- 24 kHz PCM/WAV output;
- lazy loading and a local model cache;
- no billable speech API;
- per-client rate limiting and a process-level daily ceiling.

The same-site speech contract is exposed directly under `/voice/`. `GET /voice/status` reports `mode: node-native`. A real production smoke performs a live `POST /voice/v1/audio/speech` and validates a RIFF/WAVE response, so a green smoke proves actual synthesis rather than merely proving that the route exists.

### Optional VPS fallback

The Python `mairaiy_voice_service/`, `Dockerfile.mairaiy-voice`, and the Compose `voice` profile remain available as an optional fallback for a VPS deployment. They are no longer required by the managed Hostinger Web App. If an upstream fallback is configured, the Node route can use it only after a native synthesis failure.

The Python fallback keeps the same identity: Kokoro ONNX, `ff_siwis`, `fr-fr`.
