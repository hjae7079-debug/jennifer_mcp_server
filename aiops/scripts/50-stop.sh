#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
docker compose stop
echo "컨테이너를 중지했습니다. /data 및 /backup 데이터는 삭제하지 않았습니다."
