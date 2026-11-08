# AIOps 통합분석 대시보드 패키지 v0.3.3

> v0.3.3 변경: `docs/CHANGES_v0.3.3_KO.md`. 설치 절차는 `docs/MANUAL_KO.md`(= 저장소 `docs/AIOps_설치_운영_매뉴얼_v0_3_3.md`)를 따르세요. 아래 빠른 시작은 요약입니다.

Ubuntu 24.04 폐쇄망 GPU PC용 React 대시보드와 초기 설치·오프라인 번들 스크립트입니다.

## 화면/기능
- 밝은/어두운 테마 전환
- 그래프 없이 KPI 카드와 표 중심
- 상단 KPI: 기관 수, 업무 수, 장애 건 수, 이벤트 건 수
- 기관/업무 기준 API 미연동 시 `30 / 140 (임시)`로 표시
- 장애/이벤트 최근 3건, 탐지내역/관찰대상 최근 5건(내부 스크롤)
- 항목 클릭 시 상세 화면(개요, 타임라인, WEB, WAS, DB, AI 분석, 조치 이력, 보고서 탭)
- 실제 장애/이벤트 API 미설정 시 가짜 운영 데이터를 표시하지 않음
- `DATA_MODE=mock`를 명시적으로 켠 경우에만 `DEMO-` ID의 테스트 데이터를 표시하고 모의 모드 배너를 표시
- React는 Nginx를 거쳐 FastAPI만 호출. DB/MCP 직접 접근 없음

## 서비스 구성
- Ollama: `qwen3:14b` 기본 LLM
- Ollama: `bge-m3` 임베딩 모델, pgvector 1024차원 저장 테이블
- PostgreSQL/pgvector, Redis, ClickHouse
- React 정적 UI + Nginx reverse proxy
- FastAPI + 별도 Worker 컨테이너
- Open WebUI는 별도 포트/UI
- Dify Workflow API client 포함(단, Dify 서버 자체의 버전별 공식 Compose 배포는 별도 승인·오프라인 번들 작업 필요)
- Jennifer MCP adapter는 `initialize`/`tools/list` 탐색만 구현. 실제 tool 호출은 실제 서버 도구 스키마 확인 전까지 차단
- Jennifer MCP 서버(`mcp-servers/jennifer/`, compose 서비스 `jennifer-mcp`): 읽기 전용, 설치 직후 비활성

## 빠른 시작
1. NVMe `/data`, HDD `/backup`을 먼저 마운트합니다. 스크립트는 포맷/파티션 변경을 하지 않습니다.
2. 저장소를 받아 `/opt/aiops`로 연결합니다: `sudo git clone <저장소> /opt/aiops-src && sudo ln -sfn /opt/aiops-src/aiops /opt/aiops && cd /opt/aiops && sudo cp .env.example .env`
3. 인터넷(NAT) 환경에서 `sudo bash scripts/install-all.sh` (00 → 15 → 10 → 20 → 30 → 06 → 07 → 40 → 60 → 50 → 70 → 85). `WEB_BIND_IP=127.0.0.1`이라 외부에 공개되지 않습니다.
4. `sudo bash scripts/build-offline-caches.sh` → `sudo bash scripts/75-verify-offline-prep.sh` (실패하면 NAT를 끊지 않습니다).
5. `.env`를 `DEPLOY_MODE=offline`, `WEB_BIND_IP=10.148.216.55`로 바꾸고 IP를 `10.148.216.55/26`, 게이트웨이 `10.148.216.1`로 설정, NAT 차단.
6. `sudo bash scripts/verify-offline.sh` → `ALLOWED_CIDRS` 입력 후 `sudo bash scripts/17-docker-firewall.sh`.

## 접속
- 대시보드: `https://10.148.216.55:18080` (기본 인증 계정 필요)
- Open WebUI: `https://10.148.216.55:18081` (Open WebUI 로그인)
- FastAPI: 운영에서 `/docs` 비활성. 관리자는 SSH 터널로 `127.0.0.1:18000` 접근
- HTTPS `18443`은 인증서 및 TLS 설정을 추가하기 전까지 사용하지 않습니다.

## 실제 연동이 필요한 항목
- 기관/업무 기준 API의 URL·인증·응답 필드 매핑
- 장애 이력 API와 이벤트 이력 API의 실제 URL·인증·응답 JSON
- Jennifer MCP 실 서버의 protocol/tool schema/arguments/response envelope
- Dify Workflow ID, API Key, 입력·출력 필드 매핑 및 Dify 서버 오프라인 설치
- 사용자 인증/RBAC/기관 SSO, TLS 인증서, 실제 방화벽 정책

이 패키지는 생성 시점의 소스 정적 검사만 수행할 수 있습니다. 실제 RTX 5080 GPU, Docker 이미지 pull, 폐쇄망에서의 end-to-end 동작, 기관 API/MCP/Dify 연결을 이 환경에서 실행해 검증한 것은 아닙니다. `docs/TEST_REPORT_KO.md`를 확인하세요.


## v0.3.1 변경
- ITSM 기본 수집 주기 5분(300초) 반영
- 개발 지원 모델 기본 다운로드 활성화
- 오프라인 이미지·모델 사전검증 스크립트 추가
- 오프라인 번들에 Ollama 모델 압축본 포함
