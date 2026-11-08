#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
SERVICE="${1:-api}"
docker compose logs --tail=200 -f "$SERVICE"
