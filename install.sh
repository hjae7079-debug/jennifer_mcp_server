#!/bin/bash
# Jennifer MCP 설치 (GPU PC, 폐쇄망 가능) — sudo bash install.sh
# 하는 일:
#   1) /opt/jennifer_mcp_server 로 복사 + 전용 계정 jennifer-mcp
#   2) 가상환경 + 패키지 (wheels/ 에서만, 인터넷 안 씀)
#   3) 클라이언트 토큰 hermes·aiops 발급 (값은 tokens.json 에만, 화면에 안 보임)
#   4) systemd 등록 → /healthz 확인
# Jennifer API 토큰은 설치 후 직접: sudo -u jennifer-mcp /opt/jennifer_mcp_server/.venv/bin/python \
#   /opt/jennifer_mcp_server/server.py --set-jennifer-token internet   (admin, public 도)
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "sudo bash $0 로 실행하세요"; exit 1; }
SRC=$(cd "$(dirname "$0")" && pwd)
D=${JENNIFER_MCP_DIR:-/opt/jennifer_mcp_server}
U=jennifer-mcp
[ -d "$SRC/wheels" ] || { echo "wheels/ 없음 — 인터넷 PC 에서 bash download_wheels.sh 후 반입"; exit 1; }

echo "[1/4] 복사 → $D"
id "$U" >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin "$U"
mkdir -p "$D"
if [ "$SRC" != "$D" ]; then
  # 비밀값·실행 산출물은 덮어쓰지 않음
  rsync -a --exclude .venv --exclude logs --exclude tokens.json --exclude secrets.json \
        --exclude config.local.json --exclude samples "$SRC"/ "$D"/
fi
chown -R "$U:$U" "$D"; chmod 750 "$D"

echo "[2/4] 가상환경 + 패키지 (wheels/ 에서)"
dpkg -s python3.12-venv >/dev/null 2>&1 || apt-get install -y -q python3.12-venv >/dev/null
[ -x "$D/.venv/bin/python" ] || sudo -u "$U" python3 -m venv "$D/.venv"
sudo -u "$U" "$D/.venv/bin/pip" install -q --no-index --find-links "$D/wheels" -r "$D/requirements.lock"
sudo -u "$U" "$D/.venv/bin/python" -c "import importlib.metadata as m; print('      mcp', m.version('mcp'))"

echo "[3/4] 클라이언트 토큰"
for name in hermes aiops; do
  if sudo -u "$U" "$D/.venv/bin/python" -c "import json,sys; sys.exit(0 if '$name' in json.load(open('$D/tokens.json')) else 1)" 2>/dev/null; then
    echo "      $name: 기존 유지"
  else
    sudo -u "$U" "$D/.venv/bin/python" "$D/server.py" --gen-token "$name" >/dev/null
    echo "      $name: 발급 (값 확인: sudo cat $D/tokens.json)"
  fi
done

echo "[4/4] systemd"
install -m 644 "$D/jennifer-mcp.service" /etc/systemd/system/jennifer-mcp.service
systemctl daemon-reload
systemctl enable --now jennifer-mcp >/dev/null 2>&1
systemctl restart jennifer-mcp
sleep 3
systemctl is-active jennifer-mcp
curl -s http://127.0.0.1:8791/healthz; echo
echo "완료. Jennifer 토큰 저장(--set-jennifer-token) 후: sudo systemctl restart jennifer-mcp"
