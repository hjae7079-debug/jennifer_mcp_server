#!/usr/bin/env bash
# 인터넷망 설치 "초기"에 실행합니다 (00-preflight 직후).
# 설치 중 unattended-upgrades 가 커널·NVIDIA 드라이버를 올려 GPU가 깨지는 것을 막습니다 (설계 12.4, 위험표).
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
echo "== 현재 커널: $(uname -r) (O-19 기록용)"
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null || echo "WARN: nvidia-smi 미확인"

echo "== 자동 업데이트 끄기"
for u in unattended-upgrades.service apt-daily.timer apt-daily-upgrade.timer; do
  systemctl disable --now "$u" 2>/dev/null && echo "  비활성: $u" || echo "  없음: $u"
done
cat > /etc/apt/apt.conf.d/99aiops-no-auto-upgrade <<'CONF'
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Unattended-Upgrade "0";
APT::Periodic::Download-Upgradeable-Packages "0";
CONF

echo "== 커널·드라이버 고정 (apt-mark hold)"
mapfile -t PKGS < <(dpkg-query -W -f='${Package} ${Status}\n' \
  'linux-image-*' 'linux-headers-*' 'linux-modules-*' 'linux-generic*' 'linux-image-generic*' 'linux-headers-generic*' \
  'nvidia-*' 'libnvidia-*' 'xserver-xorg-video-nvidia*' 2>/dev/null \
  | awk '$NF=="installed"{print $1}' | grep -v -E '^nvidia-container|^libnvidia-container' | sort -u)
if ((${#PKGS[@]})); then
  apt-mark hold "${PKGS[@]}" >/dev/null
  echo "  고정 ${#PKGS[@]}개"
fi
apt-mark showhold | tee /backup/aiops-install/held-packages.txt 2>/dev/null || apt-mark showhold
echo "완료. 해제가 필요하면: sudo apt-mark unhold <패키지>"
