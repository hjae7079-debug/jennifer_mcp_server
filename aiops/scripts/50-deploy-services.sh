#!/usr/bin/env bash
# DEPLOY_MODE=online: 빌드·이미지 pull 허용 / offline: 로컬 자원만 사용
# IMAGE_MODE=dev: 코드 마운트 포함 / release: 이미지 고정
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
[[ -f .env ]] || { echo ".env가 없습니다. 06-init-secrets.sh를 먼저 실행하세요."; exit 1; }
source .env
mountpoint -q "$DATA_ROOT" || { echo "$DATA_ROOT 마운트를 확인하세요."; exit 2; }
mountpoint -q "$BACKUP_ROOT" || { echo "$BACKUP_ROOT 마운트를 확인하세요."; exit 2; }
[[ -f "$DATA_ROOT/certs/cert.pem" && -f "$DATA_ROOT/certs/htpasswd" ]] || { echo "07-gen-cert.sh 와 06-init-secrets.sh 를 먼저 실행하세요."; exit 4; }
if [[ "$WEB_BIND_IP" != "127.0.0.1" ]]; then
  ip -4 -o addr show | awk '{print $4}' | cut -d/ -f1 | grep -Fxq "$WEB_BIND_IP" \
    || { echo "현재 호스트에 WEB_BIND_IP=$WEB_BIND_IP 주소가 없습니다. 폐쇄망 IP를 먼저 적용하세요."; exit 3; }
fi
for d in postgresql clickhouse redis models/ollama open-webui logs/clickhouse; do install -d "$DATA_ROOT/$d"; done

FILES=(-f docker-compose.yml)
[[ "${IMAGE_MODE:-dev}" == "dev" ]] && FILES+=(-f docker-compose.dev.yml)

if [[ "${DEPLOY_MODE:-online}" == "online" ]]; then
  docker compose "${FILES[@]}" build --build-arg PIP_NO_INDEX=0 api
  docker compose "${FILES[@]}" up -d
else
  docker compose "${FILES[@]}" build --pull=false --build-arg PIP_NO_INDEX=1 api
  docker compose "${FILES[@]}" up -d --no-build --pull never
fi
docker compose "${FILES[@]}" ps
echo "대시보드: https://${WEB_BIND_IP}:${WEB_PORT}"
echo "Open WebUI: https://${WEB_BIND_IP}:${WEBUI_PORT}"
echo "FastAPI: 127.0.0.1:${API_PORT} (관리자 SSH 터널 전용)"
