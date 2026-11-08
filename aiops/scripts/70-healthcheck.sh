#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .env
echo "== 컨테이너 상태 =="; docker compose ps
echo "== API health =="; curl -fsS "http://127.0.0.1:${API_PORT}/healthz"; echo
echo "== 대시보드 HTTP =="; curl -kfsSI --max-time 10 "https://${WEB_BIND_IP}:${WEB_PORT}/" || true
echo "== Open WebUI HTTP =="; curl -kfsSI --max-time 10 "https://${WEB_BIND_IP}:${WEBUI_PORT}/" || true
echo "== Ollama models =="; docker compose exec -T ollama ollama list
echo "== GPU =="; nvidia-smi
echo "== PostgreSQL =="; docker compose exec -T postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
echo "== Redis =="; docker compose exec -T redis redis-cli ping
echo "== ClickHouse =="; docker compose exec -T clickhouse clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query 'SELECT 1'
echo "== API dashboard payload =="; curl -fsS "http://127.0.0.1:${API_PORT}/dashboard" || true
echo "검증 완료 여부는 모든 위 명령의 실제 결과로 판단하세요."
