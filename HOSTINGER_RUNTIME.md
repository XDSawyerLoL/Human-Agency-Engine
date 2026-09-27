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
- `mairaiy-voice` (optional profile `voice`): VoiceStudio/OmniVoice GGUF, private on the Docker network and reverse-proxied by the VPS Nginx under `/voice/`.

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

The public Providence deployment at `mediumorchid-badger-314305.hostingersite.com` is currently a managed **Node.js** Web App. The Python/FastAPI services in this repository belong to the separate VPS/Docker topology. Hostinger's managed Web/Cloud runtime does not provide the root/Python environment required by PyTorch/VoiceStudio; the voice engine therefore runs on the VPS and the Node Web App remains the public same-site facade.

### VPS side

Set in `.env.hostinger`:

```env
MAIRAIY_VOICE_ENABLED=true
OMNIVOICE_API_KEY=<long random secret>
MAIRAIY_VOICE_DEVICE=cpu
MAIRAIY_VOICE_ENGINE=omnivoice-gguf
```

Then deploy with:

```bash
bash scripts/hostinger_deploy.sh
```

The deploy script enables Compose profile `voice`, refuses an obviously undersized host below the VoiceStudio RAM floor unless explicitly overridden, and checks `/voice/health` through Nginx before declaring success.

VoiceStudio itself documents roughly 8 GB RAM as a minimum and 16 GB+ as recommended. Because HORIZON/PostgreSQL/workers share the same VPS, 16 GB total RAM is the safer target; `omnivoice-gguf` is selected to reduce memory pressure on CPU-only hosts.

### Managed Node side

Expose the voice to AURA through the existing public site without giving the browser the upstream secret:

```env
MAIRAIY_VOICE_UPSTREAM_URL=https://<voice-vps-tls-host>
MAIRAIY_VOICE_PROXY_TOKEN=<second long random secret>
MAIRAIY_VOICE_UPSTREAM_API_KEY=<same OMNIVOICE_API_KEY as VPS>
MAIRAIY_VOICE_PROXY_TIMEOUT_MS=120000
```

The Node runtime exposes only:

- `GET /voice/health`
- `GET /voice/.well-known/voicestudio-speech`
- `GET /voice/v1/audio/voices`
- `GET /voice/v1/models`
- `POST /voice/v1/audio/speech`

All proxy routes except the public static status require `Authorization: Bearer <MAIRAIY_VOICE_PROXY_TOKEN>`. The proxy replaces that token with the private VoiceStudio API key server-side.

AURA Cloud can then use:

```env
AURA_VOICE_FABRIC_BASE_URL=https://mediumorchid-badger-314305.hostingersite.com/voice
AURA_VOICE_FABRIC_API_KEY=<MAIRAIY_VOICE_PROXY_TOKEN>
AURA_VOICE_FABRIC_MODEL=omnivoice-gguf
AURA_MAIRAIY_VOICE_PROFILE_NAME=Mairaiy
AURA_MAIRAIY_REQUIRE_PROFILE=true
AURA_VOICE_FABRIC_ZERO_COST_CONFIRMED=true
AURA_VOICE_FABRIC_STRICT_IDENTITY=true
```

A voice profile named `Mairaiy` must still be created from a clean reference clip that you have the right to use. Until that profile exists, strict identity mode intentionally refuses to substitute a different voice.
