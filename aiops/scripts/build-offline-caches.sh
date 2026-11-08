#!/usr/bin/env bash
# 인터넷망에서 실행: pip wheelhouse, npm 캐시, Docker 이미지, Ollama 모델, 체크섬을 한 폴더로 묶습니다.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
source .env
OUT="${BACKUP_ROOT}/aiops-offline/$(date +%Y%m%d)"; install -d -m 0750 "$OUT"

echo "[1/4] pip wheelhouse"
python3 -m pip download -r apps/api/requirements.txt -r apps/api/requirements-extra.txt \
  -d apps/api/wheelhouse --only-binary=:all: \
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 \
  --python-version 3.12 --implementation cp
ls apps/api/wheelhouse > "$OUT/wheelhouse.list"
tar -czf "$OUT/wheelhouse.tgz" -C apps/api wheelhouse

echo "[2/4] npm 캐시"
( cd apps/web && npm ci )
tar -czf "$OUT/npm-cache.tgz" -C "$HOME" .npm

echo "[3/4] Docker 이미지"
images="$(docker compose -f docker-compose.yml config --images | sort -u) python:3.12-slim-bookworm"
for img in $images; do docker pull "$img" >/dev/null 2>&1 || true; done
docker save -o "$OUT/images.tar" $images

echo "[4/4] Ollama 모델"
docker compose stop ollama
tar -czf "$OUT/ollama-models.tgz" -C "${DATA_ROOT}/models/ollama" .
docker compose start ollama

( cd "$OUT" && sha256sum * > SHA256SUMS )
echo "번들 완료: $OUT"
