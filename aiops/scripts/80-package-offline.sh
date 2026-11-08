#!/usr/bin/env bash
# (v0.3.3) 이전 방식. 새 PC 재구축·폐쇄망 반입에는 build-offline-caches.sh + restore-offline-caches.sh 를 사용하세요.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .env
OUT="$ROOT/offline-bundle"
rm -rf "$OUT"
mkdir -p "$OUT/images" "$OUT/manifests" "$OUT/models" "$OUT/python"
# Export every runtime/local image referenced by Compose.
docker compose config --images | sort -u > "$OUT/manifests/image-list.txt"
while IFS= read -r image; do
  [[ -n "$image" ]] || continue
  docker image inspect "$image" >/dev/null 2>&1 || { echo "누락 이미지: $image"; exit 4; }
  tag="$(echo "$image" | tr '/:' '__')"
  docker image save "$image" -o "$OUT/images/${tag}.tar"
done < "$OUT/manifests/image-list.txt"
cp docker-compose.yml .env.example README.md "$OUT/"
cp apps/api/requirements.txt "$OUT/python/requirements.txt"
cp scripts/75-verify-offline-prep.sh "$OUT/"
# Keep model files portable as a separate archive; never include .env or credentials.
if [[ -d "$DATA_ROOT/models/ollama" ]]; then
  tar --numeric-owner -czf "$OUT/models/ollama-models.tar.gz" -C "$DATA_ROOT/models" ollama
  du -sh "$OUT/models/ollama-models.tar.gz" > "$OUT/manifests/model-archive-size.txt"
else
  echo "모델 디렉터리 없음: $DATA_ROOT/models/ollama" > "$OUT/manifests/model-archive-warning.txt"
fi
cp -r config apps scripts docs dify "$OUT/"
rm -rf "$OUT/apps/web/node_modules"
docker version > "$OUT/manifests/docker-version.txt"
docker compose version >> "$OUT/manifests/docker-version.txt"
docker image ls --digests > "$OUT/manifests/docker-images.txt"
nvidia-smi -q > "$OUT/manifests/nvidia-smi.txt"
find "$OUT" -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > "$OUT/SHA256SUMS"
mkdir -p "$BACKUP_ROOT/aiops-install"
archive="$BACKUP_ROOT/aiops-install/aiops-offline-bundle-$(date +%Y%m%d-%H%M%S).tar.gz"
tar --numeric-owner -czf "$archive" -C "$ROOT" offline-bundle
sha256sum "$archive" > "$archive.sha256"
chmod 600 "$archive" "$archive.sha256"
echo "오프라인 번들: $OUT"
echo "압축본: $archive"
echo "Ollama 모델은 번들 models/ollama-models.tar.gz에도 별도 보관했습니다(디스크 여유 공간 확인)."
echo "실제 .env/토큰은 기본 번들에 넣지 않았습니다. 동일 PC 이동 시 기존 root 전용 .env를 보존하세요."
