#!/usr/bin/env bash
# 백업 범위와 보존 기간은 기관 정책 확정 전까지 자동 삭제하지 않습니다.
# .env(비밀값)는 백업 폴더에 복사하지 않습니다. 별도 안전 위치에 보관하세요.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
source .env
stamp="$(date +%Y%m%d-%H%M%S)"
dest="${BACKUP_ROOT}/aiops-install/backups/${stamp}"
install -d -m 0700 "$dest"
docker compose exec -T postgres sh -lc 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$dest/postgres.sql.gz"
query="BACKUP DATABASE ${CLICKHOUSE_DB} TO Disk('backups', 'aiops_${stamp}')"
docker compose exec -T clickhouse clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query "$query"
cp docker-compose.yml config/clickhouse-backup.xml "$dest/"
echo "백업 완료: $dest"
echo "주의: 자동 삭제 없음(보존 정책 확정 전). .env는 포함하지 않았습니다."
