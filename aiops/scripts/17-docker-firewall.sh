#!/usr/bin/env bash
# Docker 가 공개한 포트(18080, 18081)는 ufw 규칙을 거치지 않습니다 (Docker 가 iptables 에 직접 규칙을 넣음).
# 그래서 "허용 대역에서만 접근"은 DOCKER-USER 체인에서 막아야 합니다. 폐쇄망 전환 때 실행합니다.
#   sudo bash scripts/17-docker-firewall.sh            # .env 의 ALLOWED_CIDRS 적용 + 부팅 시 자동 적용 등록
#   sudo bash scripts/17-docker-firewall.sh --remove   # 규칙 제거
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
source .env
PORTS="${WEB_PORT:-18080}:${WEBUI_PORT:-18081}"
CHAIN=AIOPS-ALLOW

remove_rules() {
  while iptables -C DOCKER-USER -p tcp -m conntrack --ctorigdstport "$PORTS" --ctdir ORIGINAL -j "$CHAIN" 2>/dev/null; do
    iptables -D DOCKER-USER -p tcp -m conntrack --ctorigdstport "$PORTS" --ctdir ORIGINAL -j "$CHAIN"
  done
  iptables -F "$CHAIN" 2>/dev/null || true
  iptables -X "$CHAIN" 2>/dev/null || true
}

if [[ "${1:-}" == "--remove" ]]; then
  remove_rules; systemctl disable --now aiops-docker-firewall.service 2>/dev/null || true
  echo "제거 완료"; exit 0
fi
[[ -n "${ALLOWED_CIDRS:-}" ]] || { echo "ALLOWED_CIDRS 가 비어 있습니다. .env 에 허용 대역을 넣은 뒤 실행하세요 (O-21)."; exit 2; }
iptables -L DOCKER-USER -n >/dev/null 2>&1 || { echo "DOCKER-USER 체인이 없습니다. Docker 기동 후 실행하세요."; exit 3; }

remove_rules
iptables -N "$CHAIN"
IFS=',' read -ra CIDRS <<< "$ALLOWED_CIDRS"
for c in "${CIDRS[@]}"; do
  c="$(echo "$c" | xargs)"; [[ -n "$c" ]] || continue
  iptables -A "$CHAIN" -s "$c" -j RETURN
  echo "허용: $c → TCP $PORTS"
done
iptables -A "$CHAIN" -j DROP
iptables -I DOCKER-USER 1 -p tcp -m conntrack --ctorigdstport "$PORTS" --ctdir ORIGINAL -j "$CHAIN"

# 부팅 후 Docker 가 체인을 다시 만들면 재적용
cat > /etc/systemd/system/aiops-docker-firewall.service <<UNIT
[Unit]
Description=AIOps DOCKER-USER allow-list for ${PORTS}
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
ExecStartPre=/bin/sleep 5
ExecStart=/bin/bash ${ROOT}/scripts/17-docker-firewall.sh
RemainAfterExit=yes
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable aiops-docker-firewall.service >/dev/null 2>&1 || true
iptables -L "$CHAIN" -n -v
echo "완료. 허용 대역 밖 PC에서 https://<IP>:18080 접속이 막히는지 확인하세요."
