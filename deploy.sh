#!/usr/bin/env bash
# Deploy script for the proxy-pool management system on 158.180.87.150
set -euo pipefail

cd "$(dirname "$0")"

echo "==> Pulling images..."
docker compose pull

echo "==> Building images..."
docker compose build

echo "==> Starting stack..."
docker compose up -d --remove-orphans

echo "==> Waiting for API to be healthy..."
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8082/health >/dev/null 2>&1; then
    echo "API is healthy"
    break
  fi
  sleep 2
done

echo "==> Done"