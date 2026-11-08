#!/usr/bin/env bash
# 빈 비밀값을 채우고 대시보드 기본 인증 계정을 만듭니다. 이미 값이 있으면 건드리지 않습니다.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
[[ -f .env ]] || cp .env.example .env
chmod 600 .env && chown root:root .env

set_if_empty() {
  local key="$1" val="$2"
  if grep -q "^${key}=$" .env; then sed -i "s|^${key}=\$|${key}=${val}|" .env; echo "생성: ${key}"; fi
}
set_if_empty POSTGRES_PASSWORD "$(openssl rand -hex 24)"
set_if_empty CLICKHOUSE_PASSWORD "$(openssl rand -hex 24)"
set_if_empty WEBUI_SECRET_KEY "$(openssl rand -hex 32)"
set_if_empty JENNIFER_MCP_TOKEN "$(openssl rand -hex 32)"
# 이전 버전 .env 에 키가 없으면 추가
grep -q '^JENNIFER_MCP_TOKEN=' .env || { printf '\nJENNIFER_MCP_TOKEN=%s\n' "$(openssl rand -hex 32)" >> .env; echo "생성: JENNIFER_MCP_TOKEN"; }

# Jennifer MCP: 뷰서버 토큰 파일(빈 값, 비활성)과 서버 목록
if [[ ! -f config/jennifer-mcp.env ]]; then
  install -m 0600 -o root -g root mcp-servers/jennifer/jennifer-mcp.env.example config/jennifer-mcp.env
  echo "생성: config/jennifer-mcp.env (토큰 비어 있음, JENNIFER_MCP_ENABLED=false)"
fi
chmod 600 config/jennifer-mcp.env
[[ -f config/jennifer-servers.json ]] || cp mcp-servers/jennifer/config/servers.example.json config/jennifer-servers.json

source .env
CERT_DIR="${DATA_ROOT}/certs"; install -d -m 0700 "$CERT_DIR"
if [[ ! -f "$CERT_DIR/htpasswd" ]]; then
  pw="$(openssl rand -base64 18 | tr -dc 'A-Za-z0-9' | head -c 16)"
  printf 'admin:%s\n' "$(openssl passwd -apr1 "$pw")" > "$CERT_DIR/htpasswd"
  chmod 600 "$CERT_DIR/htpasswd"
  echo "=============================================="
  echo " 대시보드 관리자 계정: admin"
  echo " 초기 비밀번호: ${pw}"
  echo " (이 화면에서만 표시됩니다. 즉시 안전한 곳에 보관하세요)"
  echo "=============================================="
fi
echo "비밀값 초기화 완료. 다음: scripts/07-gen-cert.sh"
