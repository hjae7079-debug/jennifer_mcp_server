#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
echo "== AIOps 사전 점검 =="
. /etc/os-release
echo "OS: $PRETTY_NAME"
[[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == "24.04" ]] || echo "경고: Ubuntu 24.04 기준입니다. 다른 버전은 별도 검증이 필요합니다."
echo "-- Kernel / CPU / RAM"; uname -a; lscpu | grep -E 'Model name|CPU\(s\)' | head -n 4 || true; free -h
echo "-- Disks (이 단계에서는 변경하지 않음)"; lsblk -o NAME,SIZE,MODEL,SERIAL,FSTYPE,MOUNTPOINTS
echo "-- GPU"; command -v nvidia-smi >/dev/null && nvidia-smi || echo "WARN: nvidia-smi 미확인"
echo "-- Network"; ip -brief address || true; ip route || true
echo "-- Mounts"; findmnt /data || true; findmnt /backup || true
mountpoint -q /data || { echo "ERROR: NVMe가 /data에 마운트되지 않았습니다. 먼저 수동 마운트하세요."; exit 2; }
mountpoint -q /backup || { echo "ERROR: HDD가 /backup에 마운트되지 않았습니다. 먼저 수동 마운트하세요."; exit 2; }
echo "완료: 디스크/파티션을 변경하지 않았습니다. OS 디스크 /dev/sda는 보호 대상입니다."
