#!/usr/bin/env bash
# 인터넷망에서 실행: 폐쇄망 재빌드·재구축에 필요한 자원을 한 폴더로 묶습니다.
#   pip wheelhouse (API, MCP 서버, 개발 도구), npm 캐시, Docker 이미지, Ollama 모델, git 번들, SHA256
# 호스트에 pip·node 가 없어도 되도록 모두 컨테이너 안에서 받습니다.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
source .env
OUT="${BACKUP_ROOT}/aiops-offline/$(date +%Y%m%d)"; install -d -m 0750 "$OUT"
PY_IMAGE=python:3.12-slim-bookworm
NODE_IMAGE="${NODE_IMAGE:-node:22-alpine}"

pip_download() {  # $1=작업 디렉터리(ROOT 기준)  $2..=requirements 파일
  local dir="$1"; shift
  local reqs=(); for r in "$@"; do reqs+=(-r "$r"); done
  docker run --rm -v "$ROOT/$dir:/w" -w /w "$PY_IMAGE" \
    pip download "${reqs[@]}" -d wheelhouse --only-binary=:all: \
      --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
      --python-version 3.12 --implementation cp
}

echo "[1/6] pip wheelhouse (API)"
pip_download apps/api requirements.txt requirements-extra.txt
echo "[1/6] pip wheelhouse (MCP 서버: mcp-servers/*)"
for d in mcp-servers/*/; do
  [[ -f "$d/requirements.txt" ]] || continue
  extra=(); [[ -f "$d/requirements-dev.txt" ]] && extra=(requirements-dev.txt)
  pip_download "${d%/}" requirements.txt "${extra[@]}"
done
echo "[1/6] pip wheelhouse (폐쇄망 개발 도구: config/dev-requirements.txt)"
if [[ -f config/dev-requirements.txt ]]; then
  install -d "$ROOT/dev-wheelhouse"
  docker run --rm -v "$ROOT/config:/c:ro" -v "$ROOT/dev-wheelhouse:/w" "$PY_IMAGE" \
    pip download -r /c/dev-requirements.txt -d /w --only-binary=:all: \
      --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
      --python-version 3.12 --implementation cp
fi
tar -czf "$OUT/wheelhouse.tgz" apps/api/wheelhouse mcp-servers/*/wheelhouse $( [[ -d dev-wheelhouse ]] && echo dev-wheelhouse )
{ ls apps/api/wheelhouse mcp-servers/*/wheelhouse; if [[ -d dev-wheelhouse ]]; then ls dev-wheelhouse; fi; } > "$OUT/wheelhouse.list"

echo "[2/6] npm 캐시 (package-lock.json 기준)"
[[ -f apps/web/package-lock.json ]] || { echo "apps/web/package-lock.json 없음. 40-build-apps.sh 를 먼저 실행하세요."; exit 3; }
rm -rf "$ROOT/.npm-cache"
docker run --rm -v "$ROOT/apps/web:/app" -v "$ROOT/.npm-cache:/npm-cache" -w /app "$NODE_IMAGE" \
  sh -lc 'npm ci --no-audit --no-fund --cache /npm-cache && rm -rf node_modules'
tar -czf "$OUT/npm-cache.tgz" -C "$ROOT" .npm-cache apps/web/package-lock.json

echo "[3/6] Docker 이미지"
images="$(docker compose -f docker-compose.yml config --images | sort -u)"
images="$images $PY_IMAGE $NODE_IMAGE ubuntu:22.04"
[[ -f config/extra-images.txt ]] && images="$images $(grep -v -E '^\s*(#|$)' config/extra-images.txt | xargs)"
for img in $images; do
  if ! docker image inspect "$img" >/dev/null 2>&1; then docker pull "$img"; fi
done
echo "$images" | tr ' ' '\n' | sort -u > "$OUT/images.list"
# shellcheck disable=SC2046
docker save -o "$OUT/images.tar" $(cat "$OUT/images.list")

echo "[4/6] Ollama 모델"
docker compose stop ollama
tar -czf "$OUT/ollama-models.tgz" -C "${DATA_ROOT}/models/ollama" .
docker compose start ollama

echo "[5/6] 소스 git 번들 (폐쇄망 개발 저장소 시작점)"
if git -C "$ROOT/.." rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C "$ROOT/.." bundle create "$OUT/source.bundle" --all
  git -C "$ROOT/.." log -1 --format='%H %cd' > "$OUT/source.commit"
else
  tar --exclude='./.env' --exclude='./config/jennifer-mcp.env' --exclude='./apps/web/node_modules' \
      -czf "$OUT/source.tgz" -C "$ROOT" .
fi

echo "[6/6] 오프라인 APT 저장소 복사 (bundle-apt.sh 결과가 있으면)"
[[ -d "${BACKUP_ROOT}/aiops-offline/apt" ]] && tar -czf "$OUT/apt-repo.tgz" -C "${BACKUP_ROOT}/aiops-offline" apt || echo "  apt 번들 없음 (bundle-apt.sh 미실행)"

( cd "$OUT" && sha256sum -- * | grep -v ' SHA256SUMS$' > SHA256SUMS )
du -sh "$OUT"
echo "번들 완료: $OUT  (.env, 인증서 키, jennifer-mcp.env 는 넣지 않았습니다)"
