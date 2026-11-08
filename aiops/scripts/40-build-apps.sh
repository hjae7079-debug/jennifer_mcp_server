#!/usr/bin/env bash
# 인터넷망에서 실행: 앱 이미지 빌드, 대시보드 빌드(package-lock.json 생성), 런타임·빌드 기반 이미지 pull
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
command -v docker >/dev/null || { echo "Docker가 없습니다. 10-prepare-host.sh를 먼저 실행하세요."; exit 1; }
source .env
V="${APP_VERSION:-0.3.3}"
NODE_IMAGE="${NODE_IMAGE:-node:22-alpine}"

# 빌드 기반 이미지: 폐쇄망 재빌드에 필요하므로 오프라인 번들에도 넣습니다
for img in python:3.12-slim-bookworm "$NODE_IMAGE" ubuntu:22.04; do docker pull "$img"; done

docker build -t "aiops-api:${V}" ./apps/api
docker build -t "aiops-jennifer-mcp:${V}" ./mcp-servers/jennifer

# package-lock.json 이 없으면 npm install 로 만들고, 있으면 npm ci 로 같은 버전을 설치
docker run --rm -v "$ROOT/apps/web:/app" -w /app "$NODE_IMAGE" sh -lc \
  'if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; else npm install --no-audit --no-fund; fi && npm run build'
test -s apps/web/dist/index.html
test -s apps/web/package-lock.json

docker compose pull postgres clickhouse redis ollama open-webui nginx
echo "앱 빌드 및 런타임 이미지 다운로드 완료. package-lock.json 은 git 에 커밋해 두세요."
