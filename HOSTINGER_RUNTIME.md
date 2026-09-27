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

The public Providence deployment at `mediumorchid-badger-314305.hostingersite.com` is currently a managed **Node.js** Web App. The Python/FastAPI services in this repository belong to the separate VPS/Docker topology. Hostinger's managed Web/Cloud runtime does not provide the Python/root environment needed for local TTS, so the voice compute runs on the VPS and the Node Web App remains the single public same-site facade.

### Voice identity

AURA already had a stable local Mairaiy identity before the Gemini experiments:

- engine: **Kokoro ONNX**
- voice: **`ff_siwis`**
- language: **`fr-fr`**
- browser/system voice fallback: not required

The online service in `mairaiy_voice_service/` reuses that same identity and exposes the small subset of the VoiceStudio/OpenAI speech contract needed by AURA Voice Fabric. This avoids cloning a replacement voice and avoids the much larger PyTorch/OmniVoice runtime for ordinary public speech.

### VPS side

Set in `.env.hostinger`:

```env
MAIRAIY_VOICE_ENABLED=true
OMNIVOICE_API_KEY=<long random secret>
MAIRAIY_KOKORO_VOICE=ff_siwis
MAIRAIY_KOKORO_LANGUAGE=fr-fr
MAIRAIY_KOKORO_SPEED=1.0
```

Then deploy with:

```bash
bash scripts/hostinger_deploy.sh
```

The Compose profile `voice` builds `Dockerfile.mairaiy-voice`, keeps port 3900 private on the Docker network, persists the ONNX assets, and checks `/voice/health` through Nginx.

The first real synthesis downloads the same Kokoro model/voice pack that AURA's former local runtime used. Kokoro is an 82M ONNX model and is substantially lighter than the full VoiceStudio/OmniVoice stack, making CPU hosting on the Providence VPS much more realistic.

### Managed Node side

Keep `mediumorchid` as the only public URL. Configure the existing Node Hostinger Web App:

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

All proxied routes require `Authorization: Bearer <MAIRAIY_VOICE_PROXY_TOKEN>`. The Node server replaces that token with the private VPS API key. The browser never receives either secret.

### AURA Cloud side

AURA Voice Fabric then points only to the public Providence URL:

```env
AURA_VOICE_FABRIC_BASE_URL=https://mediumorchid-badger-314305.hostingersite.com/voice
AURA_VOICE_FABRIC_API_KEY=<MAIRAIY_VOICE_PROXY_TOKEN>
AURA_VOICE_FABRIC_MODEL=kokoro
AURA_MAIRAIY_VOICE_PROFILE_NAME=Mairaiy
AURA_MAIRAIY_REQUIRE_PROFILE=true
AURA_VOICE_FABRIC_ZERO_COST_CONFIRMED=true
AURA_VOICE_FABRIC_STRICT_IDENTITY=true
```

The service advertises `Mairaiy` as a profile and maps it internally to `ff_siwis`. Strict identity therefore keeps the historical AURA timbre and never substitutes the Android/browser voice.
