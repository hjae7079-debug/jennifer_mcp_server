#!/usr/bin/env bash
# 자체 서명 인증서 생성. 기관 CA 인증서가 있으면 cert.pem / key.pem 을 직접 교체하세요.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
source .env
CERT_DIR="${DATA_ROOT}/certs"; install -d -m 0700 "$CERT_DIR"
if [[ -f "$CERT_DIR/cert.pem" && -f "$CERT_DIR/key.pem" ]]; then
  echo "기존 인증서를 유지합니다: $CERT_DIR"; exit 0
fi
openssl req -x509 -newkey rsa:2048 -nodes -days 730 \
  -keyout "$CERT_DIR/key.pem" -out "$CERT_DIR/cert.pem" -subj "/CN=aiops" \
  -addext "subjectAltName=IP:10.148.216.55,IP:127.0.0.1,DNS:localhost"
chmod 600 "$CERT_DIR/key.pem"; chmod 644 "$CERT_DIR/cert.pem"
echo "인증서 생성 완료. 유효기간 730일 (만료일을 기록하세요)"
openssl x509 -in "$CERT_DIR/cert.pem" -noout -enddate
