#!/usr/bin/env bash
# Docker 저장 경로(data-root)를 DOCKER_DATA_ROOT(기본 /data/docker)로 설정합니다.
# /etc/docker/daemon.json 의 다른 항목(runtimes 등)은 그대로 보존합니다.
# 기존 /var/lib/docker 에 데이터가 있을 때 옮기려면: sudo MIGRATE=1 bash scripts/09-docker-data-root.sh
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then source "$ROOT/.env"; fi
TARGET="${DOCKER_DATA_ROOT:-/data/docker}"
DATA="${DATA_ROOT:-/data}"
mountpoint -q "$DATA" || { echo "ERROR: $DATA 마운트 필요"; exit 2; }

install -d -m 0710 "$TARGET"
install -d -m 0755 /etc/docker
DJ=/etc/docker/daemon.json
[[ -f "$DJ" ]] || echo '{}' > "$DJ"
cp "$DJ" "$DJ.bak.$(date +%Y%m%d-%H%M%S)"

python3 - "$DJ" "$TARGET" <<'PY'
import json, sys
path, target = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as f:
    d = json.load(f)
d["data-root"] = target
with open(path, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
echo "daemon.json 설정 완료 (기존 항목 보존, 백업본 생성)"

OLD=/var/lib/docker
if [[ "$OLD" != "$TARGET" && -d "$OLD" && -n "$(ls -A "$OLD" 2>/dev/null)" ]]; then
  if [[ "${MIGRATE:-0}" == "1" ]]; then
    systemctl stop docker docker.socket || true
    rsync -aHAX "$OLD/" "$TARGET/"
    echo "복사 완료. 확인 후 $OLD 는 수동으로 정리하세요."
  else
    echo "주의: $OLD 에 기존 데이터가 있습니다. 새 경로만 사용합니다. 옮기려면 MIGRATE=1 로 다시 실행하세요."
  fi
fi

systemctl restart docker
if docker info 2>/dev/null | grep -q "Docker Root Dir: $TARGET"; then
  echo "확인: Docker Root Dir = $TARGET"
else
  echo "ERROR: data-root 적용을 확인하지 못했습니다. docker info 출력을 확인하세요."; exit 3
fi
