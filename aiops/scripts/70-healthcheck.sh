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
echo "== Jennifer MCP (401=토큰 불일치, 200/400/405/406=서버 동작 중) =="
docker compose exec -T jennifer-mcp python - <<'PY' || true
import os, urllib.request, urllib.error
req = urllib.request.Request("http://127.0.0.1:8791/mcp", method="GET")
req.add_header("Authorization", "Bearer " + os.environ.get("MCP_AUTH_TOKEN", ""))
try:
    print("응답 코드:", urllib.request.urlopen(req, timeout=5).status)
except urllib.error.HTTPError as e:
    print("응답 코드:", e.code)
except Exception as e:
    print("연결 실패:", type(e).__name__)
PY
echo "== Ollama 로드 상태 =="; docker compose exec -T ollama ollama ps || true
echo "== API dashboard payload =="; curl -fsS "http://127.0.0.1:${API_PORT}/dashboard" || true
echo "검증 완료 여부는 모든 위 명령의 실제 결과로 판단하세요."
