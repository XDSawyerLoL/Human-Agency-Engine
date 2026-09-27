#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.hostinger.yml}"
ENV_FILE="${ENV_FILE:-.env.hostinger}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE. Copy .env.hostinger.example and fill the required secrets." >&2
  exit 1
fi

env_value() {
  local key="$1"
  awk -v key="$key" '
    index($0, key "=") == 1 {
      sub(/^[^=]*=/, "")
      sub(/\r$/, "")
      gsub(/^["'\''"]|["'\''"]$/, "")
      print
      exit
    }
  ' "$ENV_FILE"
}

is_true() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON|oui|OUI) return 0 ;;
    *) return 1 ;;
  esac
}

voice_enabled="$(env_value MAIRAIY_VOICE_ENABLED)"
voice_key="$(env_value OMNIVOICE_API_KEY)"
allow_low_memory="$(env_value MAIRAIY_VOICE_ALLOW_LOW_MEMORY)"

compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

if is_true "$voice_enabled"; then
  if [ "${#voice_key}" -lt 24 ]; then
    echo "MAIRAIY voice is enabled but OMNIVOICE_API_KEY is missing or too short." >&2
    exit 1
  fi

  mem_kb="$(awk '/MemTotal:/ {print $2; exit}' /proc/meminfo 2>/dev/null || echo 0)"
  if [ "${mem_kb:-0}" -gt 0 ] && [ "$mem_kb" -lt 7340032 ]; then
    if ! is_true "$allow_low_memory"; then
      echo "Mairaiy Voice requires about 8 GB RAM minimum. This VPS reports less than 7 GiB usable." >&2
      echo "Set MAIRAIY_VOICE_ALLOW_LOW_MEMORY=true only to override intentionally." >&2
      exit 1
    fi
    echo "WARNING: Mairaiy Voice is starting below the recommended RAM floor." >&2
  elif [ "${mem_kb:-0}" -gt 0 ] && [ "$mem_kb" -lt 12582912 ]; then
    echo "WARNING: Mairaiy Voice will run in low-memory GGUF/CPU mode; 16 GB total RAM is recommended with the HORIZON stack." >&2
  fi

  disk_kb="$(df -Pk . 2>/dev/null | awk 'NR==2 {print $4}' || echo 0)"
  if [ "${disk_kb:-0}" -gt 0 ] && [ "$disk_kb" -lt 12582912 ]; then
    echo "WARNING: less than 12 GiB free disk remains; VoiceStudio models may exhaust storage." >&2
  fi

  compose+=(--profile voice)
fi

"${compose[@]}" config >/dev/null
"${compose[@]}" up -d --build --remove-orphans

for attempt in $(seq 1 60); do
  if curl --fail --silent "http://127.0.0.1:${HORIZON_PORT:-8000}/ready" >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "HORIZON API did not become ready." >&2
    "${compose[@]}" ps
    "${compose[@]}" logs --tail=200 api init collector
    exit 1
  fi
  sleep 2
done

for attempt in $(seq 1 60); do
  if curl --fail --silent "http://127.0.0.1:${EVIDENCE_HTTP_PORT:-8080}/data/evidence-live.json" >/dev/null 2>&1; then
    break
  fi
  if [ "$attempt" -eq 60 ]; then
    echo "ÉVIDENCE snapshot is not published yet." >&2
    "${compose[@]}" ps
    "${compose[@]}" logs --tail=200 snapshot web
    exit 1
  fi
  sleep 5
done

if is_true "$voice_enabled"; then
  voice_ready=false
  for attempt in $(seq 1 60); do
    if curl --fail --silent \
      -H "Authorization: Bearer $voice_key" \
      "http://127.0.0.1:${EVIDENCE_HTTP_PORT:-8080}/voice/health" >/dev/null 2>&1; then
      voice_ready=true
      break
    fi
    sleep 3
  done
  if [ "$voice_ready" != true ]; then
    echo "Mairaiy VoiceStudio did not become healthy behind /voice/." >&2
    "${compose[@]}" ps
    "${compose[@]}" logs --tail=200 mairaiy-voice web
    exit 1
  fi
fi

"${compose[@]}" ps
printf '\nHORIZON ready:  http://127.0.0.1:%s/ready\n' "${HORIZON_PORT:-8000}"
printf 'ÉVIDENCE ready: http://SERVER_IP:%s/\n' "${EVIDENCE_HTTP_PORT:-8080}"
if is_true "$voice_enabled"; then
  printf 'Mairaiy Voice:   http://127.0.0.1:%s/voice/health\n' "${EVIDENCE_HTTP_PORT:-8080}"
fi
