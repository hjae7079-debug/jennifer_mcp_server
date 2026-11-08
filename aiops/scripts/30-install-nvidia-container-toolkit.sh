#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[[ $EUID -eq 0 ]] || { echo "sudo로 실행하세요."; exit 1; }
command -v nvidia-smi >/dev/null || { echo "NVIDIA 드라이버가 보이지 않습니다. 드라이버 설치/재부팅 후 재실행하세요."; exit 1; }
if docker info 2>/dev/null | grep -qi nvidia; then echo "NVIDIA runtime이 이미 보입니다. GPU 테스트를 진행합니다."; else
  install -m 0755 -d /usr/share/keyrings
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' >/etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y nvidia-container-toolkit
  nvidia-ctk runtime configure --runtime=docker
  bash "$ROOT/scripts/09-docker-data-root.sh"
  grep -q '"data-root"' /etc/docker/daemon.json || { echo "ERROR: data-root 항목이 사라졌습니다"; exit 3; }
  grep -q '"runtimes"' /etc/docker/daemon.json || { echo "ERROR: nvidia runtime 항목이 없습니다"; exit 3; }
fi
docker run --rm --gpus all ubuntu:22.04 nvidia-smi
echo "NVIDIA Container Toolkit 확인 완료."
