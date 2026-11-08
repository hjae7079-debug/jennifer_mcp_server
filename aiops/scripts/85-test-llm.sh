#!/usr/bin/env bash
set -Eeuo pipefail
API="${API_URL:-http://127.0.0.1:18000}"
echo '== API health =='; curl -fsS "$API/healthz"; echo
echo '== Qwen3-14B chat =='; curl -fsS -X POST "$API/chat" -H 'Content-Type: application/json' -d '{"question":"폐쇄망 로컬 모델 연결 확인. 한 문장으로 답하세요."}'; echo
echo '== BGE-M3 embedding + pgvector write =='; curl -fsS -X POST "$API/embeddings" -H 'Content-Type: application/json' -d '{"source_ref":"manual-test","content":"폐쇄망 임베딩 검증 데이터"}'; echo
