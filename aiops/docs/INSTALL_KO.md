# 설치·운영 매뉴얼 (한국어)

## 1. 목표
인터넷이 되는 환경에서 같은 GPU PC에 필요한 이미지·패키지·모델을 다운로드한 뒤 PC를 폐쇄망으로 이동합니다. 폐쇄망에서는 추가 인터넷 다운로드 없이 React 대시보드, FastAPI, Ollama, PostgreSQL/pgvector, Redis, ClickHouse, Open WebUI를 실행합니다.

## 2. 디스크·권한 전제
- 사용자가 미리 NVMe `/data`, HDD `/backup`을 마운트합니다.
- `00-preflight.sh`는 두 경로가 실제 마운트 포인트인지 검사합니다.
- 모든 설치 스크립트는 root로 실행합니다.
- `/dev/sda`는 절대 포맷/재파티션하지 않습니다.
- 데이터 디렉터리가 비어 있을 때만 스크립트가 서비스별 UID/GID 소유권을 설정합니다. 기존 데이터가 있으면 재귀 `chown`을 하지 않고 경고만 출력합니다.
- `.env`는 root 소유, 권한 600으로 유지합니다. Docker 그룹은 사실상 root 권한이므로 일반 사용자에게 부여하지 않습니다.

## 3. 인터넷 환경에서 준비
압축을 `/opt/aiops`에 풉니다(백업 타이머가 이 경로를 참조하므로 이후 경로를 바꾸지 않는 것을 권장합니다).
```bash
sudo unzip aiops_integrated_dashboard_v0.3.1.zip -d /opt
cd /opt/aiops
sudo bash scripts/install-all.sh
```
첫 실행 시 `.env`를 만들고 DB 암호를 생성한 후 종료할 수 있습니다. `.env`의 IP, 모델, API URL을 검토하고 같은 명령을 다시 실행하세요.

이 스크립트는 다음을 수행합니다.
1. Ubuntu/Docker/디스크/GPU 사전 검사
2. Docker Engine/Compose 및 NVIDIA Container Toolkit 준비
3. 서비스별 데이터 디렉터리 준비(디스크 포맷 없음)
4. FastAPI 이미지와 React 정적 UI 빌드
5. PostgreSQL/pgvector, ClickHouse, Redis, Ollama, Open WebUI, Nginx 이미지 다운로드
6. ``qwen3:14b`, `bge-m3`, `qwen2.5-coder:14b` 모델 다운로드
7. Docker 이미지 tar, manifest, SHA256이 포함된 `/data` 오프라인 번들 및 `/backup/aiops-install/` 압축본 생성

인터넷 준비 단계에서는 전체 웹 UI를 임시 네트워크에 공개하지 않습니다. Ollama는 모델 다운로드를 위해 실행될 수 있습니다.

## 4. 폐쇄망으로 이동
1. 같은 PC를 폐쇄망에 연결합니다.
2. Netplan 파일과 NIC 이름을 직접 확인하고 기존 설정을 백업합니다.
3. IP `10.148.216.55/26`, gateway `10.148.216.1`을 적용합니다. DNS는 폐쇄망 DNS를 확인한 경우에만 입력합니다.
4. `netplan generate`와 로컬 콘솔의 `netplan try`로 확인한 후 `netplan apply` 합니다.
5. `/data`, `/backup`이 같은 데이터와 함께 마운트되는지 확인합니다.
6. 프로젝트 루트에서:
```bash
sudo bash scripts/75-verify-offline-prep.sh
sudo bash scripts/55-offline-install.sh
sudo bash scripts/70-healthcheck.sh
sudo bash scripts/85-test-llm.sh
```
오프라인 설치는 `docker compose pull` 또는 `build`를 실행하지 않습니다. 이미지가 빠졌다면 외부 연결을 임의로 열지 말고 온라인 준비 단계에서 번들을 보완하세요.

## 5. 접속·테스트
- 대시보드: `http://10.148.216.55:18080`
- Open WebUI: `http://10.148.216.55:18081`
- FastAPI 문서: 서버 로컬 `http://127.0.0.1:18000/docs`
- Health: `curl http://127.0.0.1:18000/healthz`
- LLM: `POST /chat`, JSON `{"question":"폐쇄망 연결 확인"}`
- BGE-M3: `POST /embeddings`, JSON `{"source_ref":"test-1","content":"검증 문서"}`
- PostgreSQL/Redis/ClickHouse 상태는 `70-healthcheck.sh` 결과를 확인합니다.

## 6. 데이터 API 설정
`.env`에 다음을 설정합니다.
- `HISTORY_INCIDENTS_URL`: 장애 이력 GET API
- `HISTORY_EVENTS_URL`: 이벤트 이력 GET API
- `HISTORY_API_TOKEN`: 필요한 경우 Bearer token
- `INSTITUTIONS_API_URL`: 기관/업무 기준 API의 설정 자리표시자

이력 API 응답은 JSON 배열 또는 `items`/`records`/`data` 배열을 지원합니다. 각 행에는 ID(`incident_id`/`event_id`/`id`/`key`), 기관명(`institution_name`/`institution`/`org_name`), 제목(`title`/`subject`/`summary_title`)이 필요합니다. 발생 시각은 ISO 8601 권장입니다. 응답 형식이 다르면 `apps/api/app/adapters/history.py`를 실제 JSON에 맞춰 수정하고 테스트합니다. 스키마가 불명확하면 레코드를 추정하지 않습니다.

`HISTORY_POLL_SECONDS=300`(5분) 기본값으로 주기 조회합니다. 신규 장애는 우선순위 0, 이벤트는 1로 큐 처리합니다. 따라서 실제 지연은 폴링 주기와 API 응답시간에 따라 달라집니다.

## 7. Jennifer MCP
`.env`에서 `JENNIFER_MCP_URL`과 필요 시 `JENNIFER_MCP_TOKEN`을 설정합니다. Docker 안에서 호스트의 MCP 서버를 부를 때는 예를 들어 `http://host.docker.internal:8791/mcp`를 사용하며 Compose의 `extra_hosts` 설정이 필요할 수 있습니다(현 패키지의 실제 네트워크 구성을 확인).

연동 상태 화면에서 Jennifer 도구 스키마 탐색을 실행하면 `initialize`/`tools/list`만 시도합니다. **실제 Jennifer 서버에 연결해 tool schema와 반환 JSON을 확인한 상태가 아니므로 tool call은 구현하지 않았습니다.** 서버가 Streamable HTTP가 아니면 탐색이 실패할 수 있습니다. `tools/list`와 실제 응답을 확보한 후 읽기 전용 allowlist 및 인자 검증을 추가하세요.

## 8. Dify Workflow
클라이언트는 포함되어 있지만 Dify 서버 자체는 이 패키지에서 설치하지 않습니다. Dify 공식 버전별 Compose와 모든 이미지/플러그인 의존성을 별도로 승인·다운로드·봉인해야 합니다.
- `DIFY_BASE_URL`
- `DIFY_WORKFLOW_API_KEY`
- `ANALYSIS_PROVIDER=dify`

Workflow는 입력 `kind`, `id`, `institution_name`, `title`, `occurred_at`, `source_payload`, `prompt`를 받고 `data.outputs.text`, `answer`, `summary` 중 하나를 반환하도록 매핑합니다. 실제 Dify Workflow에서 검증하기 전에는 `ANALYSIS_PROVIDER=ollama`를 유지하세요.

## 9. 시작/중지/상태/로그/업데이트/백업
```bash
sudo bash scripts/51-start.sh
sudo bash scripts/50-stop.sh
bash scripts/52-status.sh
bash scripts/53-logs.sh api
bash scripts/53-logs.sh worker
sudo bash scripts/90-backup.sh
sudo bash scripts/95-install-backup-timer.sh
sudo bash scripts/54-update-online.sh
```
백업 타이머는 매일 02:30 실행하며 7일보다 오래된 백업을 정리하도록 구성됩니다. `.env` 백업에는 비밀정보가 있으므로 `/backup` 암호화/접근통제를 적용하세요.

## 10. 보안·미완료 사항
- API 18000은 loopback에만 바인딩합니다. Ollama, DB, Redis, ClickHouse 포트는 호스트에 공개하지 않습니다.
- 18080/18081은 지정된 내부 IP에 바인딩합니다. 기관 방화벽에서 실제 사용자 대역만 허용하세요.
- 현재 대시보드에 사용자별 RBAC/SSO와 TLS가 완성되어 있지 않습니다. 운영 반입 전에 인증/HTTPS(18443)와 보안 검토가 필요합니다.
- Jennifer MCP tool calls, 실제 장애/이벤트/기관 API 매핑, Dify 서버/Workflow는 미완료입니다.
- 현 생성 환경에서는 GPU 추론, 이미지 다운로드, 폐쇄망 end-to-end를 실행하지 못했습니다. `TEST_REPORT_KO.md` 참조.


## 11. v0.3.1 준비 사항
- ITSM 기본 수집 주기를 사용자 결정에 따라 300초(5분)로 설정했습니다. 변경은 `.env`의 `HISTORY_POLL_SECONDS`를 수정하고 서비스를 재기동하는 방식이며, 관리자 권한으로만 파일을 변경하도록 운영합니다.
- 오프라인 준비 시 주 분석 모델, 임베딩 모델, 개발 지원 모델을 모두 다운로드하도록 기본값을 변경했습니다.
- `75-verify-offline-prep.sh`가 이미지·모델 확보 여부를 검사합니다.
- 오프라인 번들에는 Ollama 모델 디렉터리의 별도 압축본을 포함합니다. 모델 크기에 따라 저장공간과 압축 시간이 크게 달라집니다.
- Dify 서버 전체와 기관별 ITSM/Jennifer/SIEM MCP 서버 구현은 이 번들에 포함된 것으로 간주하지 않습니다. 실제 서버 버전·이미지·도구 스키마 확인 후 별도 반입 패키지로 준비해야 합니다.
