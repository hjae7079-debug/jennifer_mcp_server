#!/usr/bin/env bash
# 설치·검증 결과를 모아 보고서 ZIP을 만듭니다. 비밀값(PASSWORD, TOKEN, SECRET, KEY)은 가려집니다.
# 결과: /backup/aiops-install/report/<시각>.zip  → 이 ZIP을 대화에 보내 주세요.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="/backup/aiops-install/report/${STAMP}"
install -d -m 0700 "$OUT"

{ echo "## uname"; uname -a; echo "## os"; lsb_release -a 2>/dev/null; echo "## mounts"; findmnt /data /backup 2>/dev/null; df -h /data /backup 2>/dev/null; echo "## block"; lsblk -f; echo "## fstab"; cat /etc/fstab; echo "## ip"; ip -br addr; } > "$OUT/host.txt" 2>&1 || true
nvidia-smi > "$OUT/nvidia-smi.txt" 2>&1 || true
dpkg -l | grep -E 'nvidia|linux-image|docker|containerd' > "$OUT/packages.txt" 2>&1 || true
docker version > "$OUT/docker-version.txt" 2>&1 || true
docker compose ps -a > "$OUT/compose-ps.txt" 2>&1 || true
docker images > "$OUT/images.txt" 2>&1 || true
docker compose logs --tail=300 > "$OUT/compose-logs.txt" 2>&1 || true
bash scripts/70-healthcheck.sh > "$OUT/healthcheck.txt" 2>&1 || true
bash scripts/85-test-llm.sh > "$OUT/test-llm.txt" 2>&1 || true
[[ -f .env ]] && sed -E 's/^([A-Z_]+)=.*/\1=<값 제외>/' .env > "$OUT/env-keys.txt"
cp docker-compose.yml config/nginx.conf "$OUT/" 2>/dev/null || true
find "$OUT" -type f -name '*.txt' -exec sed -i -E 's/((PASSWORD|TOKEN|SECRET|KEY)[A-Z_]*)[=: ]+[^ ,"]+/\1=<가림>/gI' {} +
( cd "$(dirname "$OUT")" && zip -qr "${STAMP}.zip" "$STAMP" )
echo "보고서 생성: $(dirname "$OUT")/${STAMP}.zip"
echo "이 파일을 대화에 첨부해 주세요. 비밀값은 가려져 있지만, 첨부 전에 한 번 열어 확인하세요."
