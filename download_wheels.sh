#!/bin/bash
# 인터넷 되는 PC 에서 실행: 리눅스 x86_64 / Python 3.12 (Ubuntu 24.04) 용 설치 파일을 wheels/ 에 받는다.
#   bash download_wheels.sh            → wheels/*.whl (약 30개)
# 받는 PC 의 OS·파이썬 버전과 상관없이 대상(리눅스 py3.12) 기준으로 받는다. 폐쇄망 설치는 install.sh 가 wheels/ 만 쓴다.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
mkdir -p wheels
"$PY" -m pip download -r requirements.lock -d wheels --no-deps --only-binary=:all: \
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
  --python-version 3.12 --implementation cp
ls wheels | wc -l | xargs echo "wheels:"
( cd wheels && sha256sum *.whl > SHA256SUMS )
echo "완료: wheels/SHA256SUMS 함께 반입"
