#!/usr/bin/env bash
# 폐쇄망(또는 새 PC 재구축, D-09)에서 build-offline-caches.sh 결과를 복원합니다.
#   sudo bash scripts/restore-offline-caches.sh /backup/aiops-offline/20261108
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
SRC="${1:?번들 폴더를 지정하세요 (예: /backup/aiops-offline/20261108)}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
source .env
( cd "$SRC" && sha256sum -c SHA256SUMS )
echo "[1/4] Docker 이미지 적재"; docker load -i "$SRC/images.tar"
echo "[2/4] wheelhouse"; tar -xzf "$SRC/wheelhouse.tgz" -C "$ROOT"
echo "[3/4] npm 캐시"; tar -xzf "$SRC/npm-cache.tgz" -C "$ROOT"
echo "[4/4] Ollama 모델"
if [[ -n "$(ls -A "${DATA_ROOT}/models/ollama" 2>/dev/null)" ]]; then
  echo "  ${DATA_ROOT}/models/ollama 에 기존 모델이 있어 건너뜁니다 (덮어쓰려면 비운 뒤 재실행)"
else
  install -d "${DATA_ROOT}/models/ollama"; tar -xzf "$SRC/ollama-models.tgz" -C "${DATA_ROOT}/models/ollama"
fi
echo "완료. 다음: DEPLOY_MODE=offline 확인 후 sudo bash scripts/50-deploy-services.sh"
echo "대시보드 재빌드가 필요하면:"
echo "  docker run --rm -v \$PWD/apps/web:/app -v \$PWD/.npm-cache:/npm-cache -w /app node:22-alpine sh -lc 'npm ci --offline --cache /npm-cache && npm run build'"
