#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
source .env
docker compose ps
curl --max-time 5 -sS "http://127.0.0.1:${API_PORT:-18000}/healthz" || true
echo
