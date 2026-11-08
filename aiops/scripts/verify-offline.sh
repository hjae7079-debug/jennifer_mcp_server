#!/usr/bin/env bash
# 인터넷을 차단한 상태에서 실행합니다. 외부 접속이 되면 실패로 처리합니다.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
if curl -s -m 5 -o /dev/null https://pypi.org/simple/ ; then
  echo "FAIL: 외부 접속이 가능합니다. 인터넷 차단 후 다시 실행하세요."; exit 1
fi
echo "OK: 외부 접속 차단 확인"
DEPLOY_MODE=offline bash scripts/50-deploy-services.sh
bash scripts/70-healthcheck.sh || true
echo "검증 완료. 결과를 기록하세요."
