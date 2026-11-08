#!/usr/bin/env bash
# 인터넷망 설치 전체 실행 (매뉴얼 5장 순서와 같음). 각 단계 로그는 /backup/aiops-install/logs/ 에 남습니다.
# WEB_BIND_IP=127.0.0.1 상태이므로 서비스를 띄워도 외부에 공개되지 않습니다.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
[[ $EUID -eq 0 ]] || { echo "sudo scripts/install-all.sh 로 실행하세요."; exit 1; }
[[ -f .env ]] || { cp .env.example .env; chmod 600 .env; chown root:root .env; }
LOG=/backup/aiops-install/logs; install -d -m 0750 "$LOG"
for s in 00-preflight.sh 15-pin-host.sh 10-prepare-host.sh 20-setup-storage.sh 30-install-nvidia-container-toolkit.sh \
         06-init-secrets.sh 07-gen-cert.sh 40-build-apps.sh 60-download-models.sh 50-deploy-services.sh \
         70-healthcheck.sh 85-test-llm.sh; do
  echo; echo "========== $s =========="
  bash "$ROOT/scripts/$s" 2>&1 | tee "$LOG/${s%.sh}.log"
done
echo
echo "설치·검증 완료. 06 로그의 초기 비밀번호를 옮겨 적은 뒤 지우세요: sudo sed -i '/초기 비밀번호/d' $LOG/06-init-secrets.log"
echo "다음: sudo bash scripts/build-offline-caches.sh → sudo bash scripts/75-verify-offline-prep.sh → sudo bash scripts/collect-report.sh"
