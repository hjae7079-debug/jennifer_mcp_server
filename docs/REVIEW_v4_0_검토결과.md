# v4.0 총정리본 · 매뉴얼 v0.3.2 · 패키지 v0.3.2 검토 결과

기준일: 2026-11-08
대상: `AIOps_통합분석_플랫폼_총정리본_v4_0.md`, `AIOps_설치_운영_매뉴얼_v0_3_2.md`, `aiops_integrated_dashboard_v0_3_2.zip`, 이전 `jennifer_mcp_server` (server.py 등)
결과물: 총정리본 v4.1, 매뉴얼 v0.3.3, 패키지 v0.3.3 (`aiops/`), Jennifer MCP 서버 v0.4.0 (`aiops/mcp-servers/jennifer/`)

검토 방법: 문서끼리 대조, 스크립트·compose·소스 정적 검토, `docker compose config` 검증, MCP 서버 단위 테스트(52개)와 실제 MCP 클라이언트 접속 시험. **실제 GPU PC 설치는 하지 않았습니다.**

---

## 1. 틀린 부분 (그대로 설치하면 실패하거나 설계와 다르게 동작)

### 1.1 치명 — 설치·폐쇄망 전환이 막힘

| # | 위치 | 문제 | 수정 |
|---|---|---|---|
| E-01 | `build-offline-caches.sh` [2/4] | `npm ci`는 `package-lock.json`이 있어야 하는데 `apps/web`에 없음. 호스트에 node/npm도 설치되지 않음 → **오프라인 번들 생성 실패** | 40에서 컨테이너로 lock 파일 생성, 번들은 `node:22-alpine` 컨테이너에서 받음 |
| E-02 | `build-offline-caches.sh` [3/4] | 대시보드 빌드용 `node:22-alpine`, GPU 점검용 `ubuntu:22.04`가 저장 목록에 없음 → **폐쇄망에서 대시보드 재빌드 불가** | 저장 목록에 추가, 75에서 존재 확인 |
| E-03 | `build-offline-caches.sh` [1/4] | 호스트 `python3 -m pip` 사용. Ubuntu 24.04 기본에는 pip가 없음 | `python:3.12-slim-bookworm` 컨테이너 안에서 다운로드 |
| E-04 | 이전 Jennifer MCP `server.py` | `--http`에서 `mcp.run_http_server()` 호출 — FastMCP에 없는 함수. 안내는 `/sse`인데 API 어댑터와 `mcp.env.example`은 `/mcp`(Streamable HTTP) 기대 → **연결 불가** | MCP 서버 재작성 (Streamable HTTP `/mcp`) |
| E-05 | `config/mcp.env.example` | `JENNIFER_MCP_URL=http://host.docker.internal:8791/mcp` — MCP 서버를 호스트 `127.0.0.1:8791`에 띄우면 컨테이너에서 접근 불가(host-gateway는 브리지 IP로 들어옴) | MCP 서버를 compose 서비스로 → `http://jennifer-mcp:8791/mcp` |
| E-06 | `install-all.sh` | 06(비밀값) 없이 40 실행 → `WEBUI_SECRET_KEY:?` 때문에 `docker compose pull` 실패. 07(인증서) 없음 | 매뉴얼 순서와 같게 재작성 |
| E-07 | Open WebUI (compose) | 오프라인 설정 없음. 0.6.x는 기본 RAG 임베딩 모델을 HuggingFace에서 받으려 함 → 폐쇄망에서 문서 업로드·RAG 실패 또는 기동 지연 | `OFFLINE_MODE`, `HF_HUB_OFFLINE`, `RAG_EMBEDDING_ENGINE=ollama`(bge-m3) |

### 1.2 중요 — 동작은 하지만 결과가 틀리거나 느림

| # | 위치 | 문제 | 수정 |
|---|---|---|---|
| E-08 | `analyzer.py` | Ollama 기본 컨텍스트 4096 토큰. 프롬프트는 최대 16,000자(한국어 약 8~12k 토큰) → **뒷부분이 잘린 채 분석** | `num_ctx=16384`, `OLLAMA_CONTEXT_LENGTH` |
| E-09 | `analyzer.py`, `main.py /chat` | Qwen3는 기본으로 `<think>` 추론을 출력 → JSON 파싱 실패로 fail-soft 경로, 분석 시간 증가 | `think: false`, `format: json` |
| E-10 | `.env` `OLLAMA_MAX_LOADED_MODELS=1` | 임베딩(bge-m3)도 "모델 1개"로 셈 → 임베딩 호출마다 qwen3 14B가 내려갔다 다시 올라감(수 초~수십 초) | `2`로 변경. 생성 모델 2개(qwen3+coder)는 VRAM이 모자라 Ollama가 자동으로 하나를 내림 |
| E-11 | 설계 9장 "ufw 기본 차단, 허용 대역만" | **Docker가 공개한 포트(18080/18081)는 ufw를 거치지 않음** → 허용 대역 제한이 실제로는 적용되지 않음 | `17-docker-firewall.sh` (DOCKER-USER 체인) |
| E-12 | 설계 12.4 "커널·드라이버 hold, 자동 업데이트 끄기" | 이를 수행하는 스크립트가 없음. 인터넷망 설치 기간에 자동 업데이트가 커널·드라이버를 올릴 수 있음 | `15-pin-host.sh` (00 직후 실행) |
| E-13 | 이전 Jennifer MCP | 경로 `/api/domain/{id}/metric/system`, `xlog` 등은 실측 명세(`/api/dbmetrics`, `/api/status/*` …)와 다름. 서버 1대, 토큰이 `config.json`(git)에 있음, 쓰기 차단·호출 로그·clientIp 제거 없음 | MCP 서버 v0.4.0 재작성 (아래 3장) |

### 1.3 경미 — 불일치

| # | 위치 | 문제 | 수정 |
|---|---|---|---|
| E-14 | `40-build-apps.sh`, `75-verify-offline-prep.sh` | 이미지 태그 `aiops-api:0.3.1`, compose는 `0.3.2` → 75가 엉뚱한 이미지를 확인 | `.env` `APP_VERSION` 하나로 통일 |
| E-15 | 매뉴얼 6장 4~5단계 | `verify-offline.sh`가 이미 50(offline)을 실행하는데 5단계에서 다시 실행 | 5단계 삭제 |
| E-16 | 총정리본 12.3 "Node.js, npm (OS 패키지)" / O-22 | 대시보드는 `node:22-alpine` 컨테이너로 빌드하므로 Ubuntu nodejs 버전과 무관 | O-22 해소, 문구 수정 |
| E-17 | 총정리본 2.2 "Ollama 호스트 포트 없음" vs 폐쇄망에서 Qwen Coder로 개발 | 포트가 없으면 호스트의 코딩 도구가 Ollama에 접근할 수 없음 | `IMAGE_MODE=dev`에서만 `127.0.0.1:11434` 공개 |
| E-18 | `README.md` | 제목·절차가 v0.3.1 기준 | v0.3.3로 갱신 |
| E-19 | 오프라인 경로 2개 | `80-package-offline`+`55-offline-install`과 `build-offline-caches`가 공존, 형식이 다름 | `build-offline-caches` + `restore-offline-caches`로 일원화, 80/55는 이전 방식으로 표시 |

---

## 2. 인터넷망에서 더 받아 두어야 할 것

폐쇄망으로 옮긴 뒤에는 받을 수 없으므로, 아래가 모두 `/backup/aiops-offline/<날짜>/`에 있어야 합니다.

| 구분 | 항목 | 이유 | 처리 |
|---|---|---|---|
| Docker 이미지 | `node:22-alpine` | 대시보드 재빌드 | 40, build-offline-caches |
| | `ubuntu:22.04`, `nvidia/cuda:12.8.1-base-ubuntu24.04` | GPU 점검 (30, 매뉴얼 8.1) | 〃 |
| | `aiops-jennifer-mcp:<버전>` | MCP 서버 실행 | 〃 |
| | `ghcr.io/open-webui/mcpo:main` | Open WebUI MCP 직접 연결이 안 될 때 대안 (O-12) | `config/extra-images.txt` |
| Python | MCP 서버 wheelhouse (`mcp`, `uvicorn` 등) | 폐쇄망 이미지 재빌드 | `mcp-servers/*/wheelhouse` |
| | 개발 도구 wheelhouse (`pytest`, `ruff`, `fastapi`, `mcp` …) | 폐쇄망에서 Qwen Coder로 추가 개발·테스트 | `config/dev-requirements.txt` → `dev-wheelhouse/` |
| npm | `package-lock.json` + npm 캐시 | `npm ci --offline` | 40, build-offline-caches |
| 소스 | git 번들 (`source.bundle`) | 폐쇄망 개발 저장소의 시작점, 이력 유지 | build-offline-caches [5/6] |
| APT | `bundle-apt.sh` 결과를 번들에 포함 | 새 PC 재구축(D-09) | build-offline-caches [6/6] |
| 문서 | Jennifer Swagger JSON, 각 도구 공식 문서(PDF·HTML) | 폐쇄망에서 참고 | 수동 (아래 체크리스트) |
| 개발 도구 (선택) | VS Code `.deb` + Continue 확장 `.vsix` | Qwen2.5-Coder를 IDE에서 사용 | 수동 다운로드 |

**모델 관련 판단**
- `qwen3:14b`(약 9.3GB) + `bge-m3`(약 1.2GB)는 16GB VRAM에 함께 올라갑니다. 병렬 2 × 16k 컨텍스트, KV 캐시 q8_0 기준 약 13~15GB입니다. 실측(O-18)으로 확인하세요.
- `qwen2.5-coder:14b`는 qwen3와 동시에 올라가지 않습니다. 개발 중에는 분석 응답이 느려지므로 **개발은 운영 시간 외** 또는 분석 큐가 빌 때 하세요.
- (선택) 더 나은 코딩 모델이 필요하면 `qwen3-coder:30b`(MoE, 약 19GB)를 받아 두고 GPU+CPU(64GB RAM) 분할로 쓸 수 있습니다. 기본값으로는 넣지 않았습니다.

---

## 3. Jennifer MCP 서버 v0.4.0 (새로 작성)

`aiops/mcp-servers/jennifer/` — 자세한 내용은 같은 폴더의 `README.md`.

- Streamable HTTP `/mcp` (aiops-api 어댑터, Open WebUI 0.6.31+ 기본 MCP 지원과 맞음), stdio 겸용
- 서버 3대(인터넷·행정·대민) 각각 타임아웃·토큰·호출 간격 분리, 응답 없으면 "조회 불가(서버명, 사유)" (D-10)
- GET만. `/api-v2/manage/*`, `/restapi/*`, `/api/auth/userlist*` 차단, 토큰 쿼리 금지, 경로 조작 차단 — 단위 테스트로 검증
- clientIp·clientId 재귀 제거, 건수·바이트 제한
- 실측 제약 강제: dbmetrics 지표 1개, status 분 단위 정시, `responseTime` 정렬 금지, transaction/time 60초 이하
- 모든 호출 JSONL 로그 (`/data/logs/jennifer-mcp/`)
- `JENNIFER_MCP_ENABLED=false`로 설치 (설계 13.6)
- `survey.py`: Swagger 기준 GET 전수 호출 → 샘플·요약 CSV (매뉴얼 G단계의 "준비 중" 해소)
- 경로·파라미터 이름은 `config/endpoints.json`에서만 수정 (미확인 항목은 `verified: false`)

---

## 4. 아직 사람이 확인해야 할 것 (새로 생긴 항목)

| 번호 | 항목 | 확인 방법 |
|---|---|---|
| O-24 | `endpoints.json`의 미확인 경로(`/api/domain`, `/api/instance`, `/api/activeService/list`)와 파라미터 이름 | Swagger + survey |
| O-25 | Open WebUI 0.6.32에서 MCP 서버 등록 시 Bearer 키 전달 방식 | 관리자 설정 → 외부 도구 → MCP(Streamable HTTP) |
| O-26 | 16k 컨텍스트 × 병렬 2에서 VRAM 여유 | `ollama ps`, `nvidia-smi` (O-18과 함께) |
| O-27 | `ALLOWED_CIDRS` 허용 대역 | 현장 (O-21과 함께) |
| O-28 | mcpo 이미지 digest 기록 | 번들 생성 후 `images.list` |
