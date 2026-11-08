#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
command -v docker >/dev/null || { echo "Docker가 없습니다. 10-prepare-host.sh를 먼저 실행하세요."; exit 1; }
docker build --pull -t aiops-api:0.3.1 ./apps/api
docker run --rm -v "$ROOT/apps/web:/app" -w /app node:22-alpine sh -lc 'npm install --no-audit --no-fund && npm run build'
test -s apps/web/dist/index.html
# Pull all runtime images now, while Internet is available. Never pull in offline phase.
docker compose pull postgres clickhouse redis ollama open-webui nginx
echo "앱 빌드 및 런타임 이미지 다운로드 완료."
