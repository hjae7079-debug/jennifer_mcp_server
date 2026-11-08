#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cat > /etc/systemd/system/aiops-backup.service <<UNIT
[Unit]
Description=AIOps daily database/config backup
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
ExecStart=/bin/bash ${ROOT}/scripts/90-backup.sh
UNIT
cat > /etc/systemd/system/aiops-backup.timer <<'UNIT'
[Unit]
Description=Run AIOps backup daily
[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true
RandomizedDelaySec=5m
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now aiops-backup.timer
systemctl list-timers aiops-backup.timer
