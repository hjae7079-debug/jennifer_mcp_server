#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .env
docker compose up -d ollama
for i in $(seq 1 60); do docker compose exec -T ollama ollama list >/dev/null 2>&1 && break; sleep 5; done
echo "주력 LLM 다운로드: ${PRIMARY_MODEL}"
docker compose exec -T ollama ollama pull "${PRIMARY_MODEL}"
echo "임베딩 모델 다운로드: ${EMBEDDING_MODEL}"
docker compose exec -T ollama ollama pull "${EMBEDDING_MODEL}"
if [[ "${DOWNLOAD_CODER_MODEL:-true}" == "true" ]]; then
  echo "선택 개발 모델 다운로드: ${CODER_MODEL} (자동 실행하지 않음)"
  docker compose exec -T ollama ollama pull "${CODER_MODEL}"
fi
docker compose exec -T ollama ollama list
for model in "${PRIMARY_MODEL}" "${EMBEDDING_MODEL}"; do
  docker compose exec -T ollama ollama show "$model" >/dev/null || { echo "모델 확인 실패: $model"; exit 8; }
done
if [[ "${DOWNLOAD_CODER_MODEL:-true}" == "true" ]]; then
  docker compose exec -T ollama ollama show "${CODER_MODEL}" >/dev/null || { echo "개발 모델 확인 실패: ${CODER_MODEL}"; exit 9; }
fi
