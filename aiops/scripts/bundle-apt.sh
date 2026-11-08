#!/usr/bin/env bash
# 인터넷(NAT) 상태에서 실행. 이미 설치된 패키지도 받아 둡니다(다운로드만 수행, 설치 안 함).
# 결과: ${BACKUP_ROOT}/aiops-offline/apt/ 에 .deb 전체 + 로컬 저장소 인덱스
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
source /opt/aiops/.env 2>/dev/null || source "$(dirname "$0")/../.env"
OUT="${BACKUP_ROOT:-/backup}/aiops-offline/apt"
install -d "$OUT/pool"

# 1) 외부 저장소 등록 (Docker, NVIDIA). 이미 있으면 덮어씀
install -d -m 0755 /etc/apt/keyrings
apt-get update
apt-get install -y ca-certificates curl gnupg apt-rdepends apt-utils dpkg-dev
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /etc/apt/keyrings/nvidia-container.gpg --yes
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/etc/apt/keyrings/nvidia-container.gpg] https://#g' > /etc/apt/sources.list.d/nvidia-container-toolkit.list
apt-get update

# 2) 프로젝트 패키지 목록 (설치 여부와 무관하게 전부 포함)
PKGS=(
  # 기본 도구
  curl wget ca-certificates gnupg openssl jq chrony ufw git rsync zip unzip
  apt-transport-https lsb-release python3-pip python3-venv
  # Docker
  docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  # GPU 컨테이너
  nvidia-container-toolkit nvidia-container-toolkit-base libnvidia-container1 libnvidia-container-tools
  # 대시보드 빌드
  nodejs npm
  # 장애 복구용 (현재 설치 버전과 같아야 함, 설치하지 않고 보관만)
  "linux-image-$(uname -r)" "linux-headers-$(uname -r)"
)

# 4-1) OS 기본 운영 도구 (설치 여부와 무관하게 포함)
PKGS+=(
  # 네트워크
  net-tools iproute2 iputils-ping iputils-tracepath dnsutils traceroute tcpdump ethtool
  netplan.io nftables iptables bind9-host whois mtr-tiny telnet nmap
  # 시스템 모니터링·진단
  htop iotop sysstat lsof strace pciutils usbutils lshw dmidecode
  smartmontools nvme-cli psmisc procps
  # 디스크·파일시스템
  parted gdisk e2fsprogs xfsprogs lvm2 util-linux
  # 편집·쉘·압축
  vim-tiny nano tmux less tree bash-completion ncurses-term
  p7zip-full zip unzip gzip bzip2 xz-utils
  # 서버·보안·로그
  openssh-server openssh-client sudo cron rsyslog logrotate
  auditd apparmor-utils fail2ban
  # 기타
  locales tzdata software-properties-common unattended-upgrades
  ca-certificates gnupg
)

# 3) 의존성까지 해석
apt-rdepends "${PKGS[@]}" 2>/dev/null | grep -v '^ ' | grep -v -E '^(Reading|Build|Pre-Depend|Depends|Suggests)' | sort -u > "$OUT/pkglist.txt"
echo "대상 패키지 수: $(wc -l < "$OUT/pkglist.txt")"

# 4) 다운로드 (가상 패키지·저장소에 없는 항목은 건너뛰고 기록)
cd "$OUT/pool"
: > "$OUT/skipped.txt"
while read -r p; do
  apt-get download "$p" >/dev/null 2>&1 || echo "$p" >> "$OUT/skipped.txt"
done < "$OUT/pkglist.txt"

# 5) 로컬 저장소 인덱스
cd "$OUT"
apt-ftparchive packages pool > Packages
gzip -kf Packages
apt-ftparchive release . > Release
sha256sum pool/*.deb > SHA256SUMS
echo "완료: $(ls pool/*.deb | wc -l)개 .deb, 건너뜀 $(wc -l < skipped.txt)개 (skipped.txt 확인)"
echo "주의: 폐쇄망에서는 apt-mark hold 로 커널·드라이버를 고정하고, 자동 업데이트를 끄세요."
