#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
[[ -f .env ]] || { echo ".env가 없습니다."; exit 2; }
source .env
command -v docker >/dev/null || { echo "Docker가 필요합니다."; exit 3; }
command -v nvidia-smi >/dev/null || { echo "NVIDIA 드라이버/nvidia-smi 확인 필요"; exit 4; }
echo "== 런타임 이미지 확인 =="
docker compose config --images | sort -u | while read -r image; do
  docker image inspect "$image" >/dev/null 2>&1 || { echo "이미지 누락: $image"; exit 10; }
  echo "OK $image"
done
echo "== 앱 이미지 확인 =="
docker image inspect aiops-api:0.3.1 >/dev/null
echo "== Ollama 모델 확인 =="
for model in "$PRIMARY_MODEL" "$EMBEDDING_MODEL"; do
  docker compose exec -T ollama ollama show "$model" >/dev/null || { echo "모델 누락: $model"; exit 11; }
done
if [[ "${DOWNLOAD_CODER_MODEL:-true}" == "true" ]]; then
  docker compose exec -T ollama ollama show "$CODER_MODEL" >/dev/null || { echo "개발 모델 누락: $CODER_MODEL"; exit 12; }
fi
echo "== 모델 용량 =="
du -sh "$DATA_ROOT/models/ollama" || true
echo "== 호스트 패키지 캐시 참고 =="
find /var/cache/apt/archives -maxdepth 1 -type f -name '*.deb' -printf '%f\n' 2>/dev/null | sort || true
echo "검증 완료: Dify 서버 이미지와 기관별 MCP 서버는 별도 반입 대상입니다."
