#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
[[ $EUID -eq 0 ]] || { echo "sudo scripts/install-all.sh 로 실행하세요."; exit 1; }
if [[ ! -f .env ]]; then
  cp .env.example .env
  printf '\nPOSTGRES_PASSWORD=%s\nCLICKHOUSE_PASSWORD=%s\n' "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" >> .env
  chmod 600 .env; chown root:root .env
  echo ".env를 생성하고 DB 암호를 넣었습니다. 설정과 네트워크 값을 검토한 뒤 다시 실행하세요. 비밀번호는 .env에만 보관됩니다."
  exit 2
fi
chmod 600 .env
# Internet-side preparation only: do not publish dashboard services on the temporary network.
for s in 00-preflight.sh 10-prepare-host.sh 20-setup-storage.sh 30-install-nvidia-container-toolkit.sh 40-build-apps.sh 60-download-models.sh 75-verify-offline-prep.sh 80-package-offline.sh; do
  echo; echo "========== $s =========="; "$ROOT/scripts/$s"
done
echo
echo "인터넷 환경 준비 완료. 이 단계에서는 전체 웹 서비스를 공개하지 않았습니다."
echo "폐쇄망으로 이동해 IP를 설정한 후 sudo bash scripts/55-offline-install.sh 를 실행하세요."
