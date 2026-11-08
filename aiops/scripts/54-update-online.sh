#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
echo "안전한 업데이트 절차: 온라인 준비 환경에서 버전 검토 → DB/설정 백업 → 승인된 이미지 pull 및 앱 재빌드 → offline bundle 재생성 → SHA256 검증 → 폐쇄망 반입."
echo "폐쇄망에서 docker compose pull/build를 실행하지 마세요. 이 스크립트는 자동으로 서비스를 변경하지 않습니다."
