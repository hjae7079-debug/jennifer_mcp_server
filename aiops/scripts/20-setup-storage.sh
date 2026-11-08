#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
mountpoint -q /data || { echo "ERROR: NVMe를 /data에 먼저 마운트하세요."; exit 2; }
mountpoint -q /backup || { echo "ERROR: HDD를 /backup에 먼저 마운트하세요."; exit 2; }
echo "안전 모드: 포맷/파티션/마운트 변경을 하지 않습니다."
lsblk -o NAME,SIZE,MODEL,SERIAL,FSTYPE,MOUNTPOINTS
findmnt /data; findmnt /backup
df -h /data /backup
echo "OS 디스크 /dev/sda는 절대 수정하지 않습니다."
