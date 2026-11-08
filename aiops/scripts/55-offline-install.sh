#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ -f .env && -f docker-compose.yml ]] || { echo "프로젝트 루트의 .env와 docker-compose.yml이 필요합니다."; exit 2; }
source .env
install -d -m 0750 "$BACKUP_ROOT/aiops-install/clickhouse"
if [[ -z "$(find "$BACKUP_ROOT/aiops-install/clickhouse" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then chown 101:101 "$BACKUP_ROOT/aiops-install/clickhouse"; fi
mountpoint -q "$DATA_ROOT" || { echo "$DATA_ROOT 마운트가 없습니다."; exit 3; }
mountpoint -q "$BACKUP_ROOT" || { echo "$BACKUP_ROOT 마운트가 없습니다."; exit 3; }
# Verify the offline bundle before loading any image archive.
IMAGE_DIR=""
if [[ -d "$ROOT/offline-bundle/images" ]]; then IMAGE_DIR="$ROOT/offline-bundle/images"; elif [[ -d "$ROOT/images" ]]; then IMAGE_DIR="$ROOT/images"; fi
if [[ -n "$IMAGE_DIR" ]]; then
  CHECK_DIR="$(dirname "$IMAGE_DIR")"
  if [[ -f "$CHECK_DIR/SHA256SUMS" ]]; then (cd "$CHECK_DIR" && sha256sum -c SHA256SUMS); fi
  if [[ -f "$CHECK_DIR/manifests/image-list.txt" ]]; then
    while IFS= read -r image; do
      [[ -n "$image" ]] || continue
      if docker image inspect "$image" >/dev/null 2>&1; then continue; fi
      tarfile="$IMAGE_DIR/$(echo "$image" | tr '/:' '__').tar"
      [[ -f "$tarfile" ]] || { echo "오프라인 이미지 누락: $image"; exit 6; }
      docker load -i "$tarfile"
    done < "$CHECK_DIR/manifests/image-list.txt"
  else
    for f in "$IMAGE_DIR"/*.tar; do [[ -f "$f" ]] || continue; docker load -i "$f"; done
  fi
fi
[[ -s apps/web/dist/index.html ]] || { echo "React dist가 없습니다. 온라인 준비 단계의 40-build-apps.sh를 다시 실행하세요."; exit 4; }
[[ "$(ip -4 -o addr show | awk '{print $4}' | cut -d/ -f1 | grep -Fx "$WEB_BIND_IP" || true)" == "$WEB_BIND_IP" ]] || { echo "현재 IP에 WEB_BIND_IP=$WEB_BIND_IP가 없습니다. Netplan/IP 설정을 먼저 확인하세요."; exit 5; }
# No pulls/builds in closed network.
docker compose up -d --no-build --pull never
docker compose ps
if [[ -f "$ROOT/scripts/95-install-backup-timer.sh" ]]; then bash "$ROOT/scripts/95-install-backup-timer.sh"; fi
echo "오프라인 기동 완료. 다음: sudo bash scripts/70-healthcheck.sh"
