# v0.3.2 변경 사항 (v0.3.1 대비)

## 보안 기본값
- Open WebUI 호스트 포트 제거. Nginx 18081(HTTPS)로만 접근, 공개 가입 기본 차단
- 대시보드 18080, Open WebUI 18081 모두 HTTPS만 열림. 기본 인증(htpasswd) 적용
- Nginx: 허용 경로만 /api 로 전달 (`/api/dashboard`, `/api/items/`, `/api/integrations/status`). 나머지 /api/* 는 404
- FastAPI `/docs`, `/redoc`, `openapi.json` 비활성
- FastAPI 127.0.0.1:18000 은 관리자 SSH 터널 전용
- 백업에서 .env 복사 제거, 7일 자동 삭제 제거 (보존 정책 확정 전)

## 운영 설정
- Ollama 병렬 처리 2 (OLLAMA_NUM_PARALLEL=2), 로드 모델 1
- 설치 기간 WEB_BIND_IP=127.0.0.1, 폐쇄망 전환 시 10.148.216.55
- DEPLOY_MODE: online(설치) / offline(폐쇄망)
- IMAGE_MODE: dev(코드 마운트, 재시작만으로 반영) / release(이미지 고정)

## 설치 스크립트
- 06-init-secrets.sh: DB·ClickHouse·WebUI 비밀값과 대시보드 관리자 계정 자동 생성 (초기 비밀번호는 한 번만 표시)
- 07-gen-cert.sh: 자체 서명 인증서 (SAN에 폐쇄망 IP 포함, IP 전환 후 재발급 불필요)
- 50-deploy-services.sh: DEPLOY_MODE, IMAGE_MODE 분기, 인증서·계정 존재 확인
- build-offline-caches.sh: pip wheelhouse, npm 캐시, Docker 이미지, Ollama 모델, SHA256 생성 (인터넷망)
- verify-offline.sh: 외부 접속 차단 확인 후 폐쇄망 모드 기동 검증

## 빌드
- API Dockerfile: PIP_NO_INDEX=1 이면 wheelhouse만 사용 (폐쇄망 빌드)
- requirements-extra.txt: 폐쇄망에서 설치 가능한 추가 패키지 범위를 미리 정함
- 이미지 태그 aiops-api:0.3.2

## 알려진 한계 (이번 패키지에서 하지 않은 것)
- 실제 연동(ITSM, Jennifer, SIEM) 구현은 샘플 수집 후 진행
- 관찰대상 자동 탐지, 수동분석, 이력관리 화면, 사용자별 권한 연동은 미구현
- 본 패키지는 정적 수정 후 패키징한 상태이며, 실제 GPU PC에서의 설치·기동 검증은 아직 수행하지 않음

- bundle-apt.sh: Ubuntu·Docker·NVIDIA 패키지와 의존성을 로컬 저장소 형태로 미리 받기 (설치 여부와 무관)
- 09-docker-data-root.sh: Docker 저장 경로를 /data/docker로 설정. daemon.json의 다른 항목은 보존하고 백업본을 만듦. MIGRATE=1일 때만 기존 /var/lib/docker를 복사
- 10-prepare-host.sh: Docker 활성화 전에 09 실행
- 30-install-nvidia...: NVIDIA 설정 후 data-root와 runtimes 두 항목이 모두 남았는지 확인
- .env.example: DOCKER_DATA_ROOT=/data/docker 추가
