#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.hostinger.yml}"
ENV_FILE="${ENV_FILE:-.env.hostinger}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE. Copy .env.hostinger.example and fill the required secrets." >&2
  exit 1
fi

compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

"${compose[@]}" config >/dev/null
"${compose[@]}" up -d --build --remove-orphans

for attempt in $(seq 1 60); do
  if curl --fail --silent http://127.0.0.1:${HORIZON_PORT:-8000}/ready >/dev/null 2>&1; then
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
  if curl --fail --silent http://127.0.0.1:${EVIDENCE_HTTP_PORT:-8080}/data/evidence-live.json >/dev/null 2>&1; then
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

"${compose[@]}" ps
printf '\nHORIZON ready:  http://127.0.0.1:%s/ready\n' "${HORIZON_PORT:-8000}"
printf 'ÉVIDENCE ready: http://SERVER_IP:%s/\n' "${EVIDENCE_HTTP_PORT:-8080}"
