#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[[ -f "$ROOT/.env" ]] || { echo ".env가 없습니다. 먼저 cp .env.example .env 후 값을 확인하세요."; exit 1; }
# shellcheck disable=SC1091
source "$ROOT/.env"
mountpoint -q "${DATA_ROOT:-/data}" || { echo "ERROR: ${DATA_ROOT:-/data} 마운트 필요"; exit 2; }
mountpoint -q "${BACKUP_ROOT:-/backup}" || { echo "ERROR: ${BACKUP_ROOT:-/backup} 마운트 필요"; exit 2; }
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl gnupg lsb-release jq git unzip rsync openssl build-essential
timedatectl set-timezone "${TZ:-Asia/Seoul}" || true
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" >/etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
bash "$ROOT/scripts/09-docker-data-root.sh"
systemctl enable --now docker
docker version
docker compose version
install -d -m 0750 "${INSTALL_ROOT:-/opt/aiops}"
install -d -m 0755 "${DATA_ROOT:-/data}"
install -d -m 0700 "${BACKUP_ROOT:-/backup}/aiops-install"
install -d -m 0700 "${BACKUP_ROOT:-/backup}/aiops-install/logs" "${BACKUP_ROOT:-/backup}/aiops-install/backups"
chmod 0700 "${BACKUP_ROOT:-/backup}/aiops-install"
# Service data directories: set ownership only when empty; never recursively chown existing data.
ensure_dir() {
  local path="$1" uid="$2" gid="$3"
  mkdir -p "$path"
  if [[ -z "$(find "$path" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    chown "$uid:$gid" "$path"; chmod 0750 "$path"
  else
    echo "기존 데이터 보존: $path (소유권 자동 변경 안 함; 필요 시 컨테이너 UID와 수동 비교)"
  fi
}
ensure_dir "$DATA_ROOT/postgresql" 999 999
ensure_dir "$DATA_ROOT/clickhouse" 101 101
ensure_dir "$DATA_ROOT/redis" 999 999
ensure_dir "$DATA_ROOT/models/ollama" 0 0
ensure_dir "$DATA_ROOT/open-webui" 0 0
ensure_dir "$DATA_ROOT/logs/clickhouse" 101 101
ensure_dir "$BACKUP_ROOT/aiops-install/clickhouse" 101 101
ensure_dir "$DATA_ROOT/collection" 0 0
ensure_dir "$DATA_ROOT/logs/jennifer-mcp" 10002 10002
chmod 600 "$ROOT/.env"
if ! grep -q '^POSTGRES_PASSWORD=' "$ROOT/.env"; then printf '\nPOSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 32)" >> "$ROOT/.env"; fi
if ! grep -q '^CLICKHOUSE_PASSWORD=' "$ROOT/.env"; then printf '\nCLICKHOUSE_PASSWORD=%s\n' "$(openssl rand -hex 32)" >> "$ROOT/.env"; fi
chmod 600 "$ROOT/.env"
chown root:root "$ROOT/.env"
echo "호스트 준비 완료. 관리자 웹 계정은 자동 생성하지 않았습니다."
