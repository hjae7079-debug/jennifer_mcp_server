# AIOps 운영 매뉴얼

## 주요 포트
| 용도 | 주소/포트 | 공개 범위 |
|---|---|---|
| React 대시보드 | `10.148.216.55:18080` | 지정된 내부망에서만 허용 |
| Open WebUI | `10.148.216.55:18081` | 지정된 내부망에서만 허용 |
| FastAPI | `127.0.0.1:18000` | 호스트 loopback 전용 |
| Ollama | 컨테이너 내부 `11434` | 호스트 포트 공개 안 함 |
| PostgreSQL | 컨테이너 내부 `5432` | 호스트 포트 공개 안 함 |
| Redis | 컨테이너 내부 `6379` | 호스트 포트 공개 안 함 |
| ClickHouse | 컨테이너 내부 `8123/9000` | 호스트 포트 공개 안 함 |

## 운영 명령
프로젝트 루트에서 root 권한으로 실행합니다.
```bash
sudo bash scripts/51-start.sh
sudo bash scripts/50-stop.sh
bash scripts/52-status.sh
sudo bash scripts/53-logs.sh api
sudo bash scripts/53-logs.sh worker
sudo bash scripts/53-logs.sh ollama
sudo bash scripts/70-healthcheck.sh
sudo bash scripts/85-test-llm.sh
sudo bash scripts/90-backup.sh
sudo bash scripts/95-install-backup-timer.sh
```

## 데이터 경로와 권한
- `/data/models/ollama`: 모델 파일
- `/data/postgresql`: PostgreSQL/pgvector
- `/data/clickhouse`: ClickHouse 데이터
- `/data/redis`: Redis AOF
- `/data/open-webui`: Open WebUI 설정/대화 데이터
- `/data/logs/clickhouse`: ClickHouse 로그
- `/backup/aiops-install/backups`: PostgreSQL dump, ClickHouse backup 호출 메타데이터, 비밀 설정 백업
- `/backup/aiops-install/clickhouse`: ClickHouse native backup 저장 위치

설치 스크립트는 빈 디렉터리에만 서비스 UID/GID 소유권을 설정합니다. 기존 데이터 디렉터리에 재귀 `chown`을 수행하지 않습니다. 권한 오류가 발생하면 먼저 `docker image inspect`의 컨테이너 UID, 호스트 경로 소유자, 로그를 확인하고 무조건 `chmod 777` 하지 마세요.

## 백업과 복구
`95-install-backup-timer.sh`는 매일 02:30에 백업을 실행하는 systemd timer를 등록합니다. `90-backup.sh`는 PostgreSQL logical dump와 ClickHouse native backup을 만들고 7일보다 오래된 백업을 정리합니다. `.env`에는 암호와 API 토큰이 있을 수 있으므로 root-only 백업이며, 운영 시 `/backup`의 암호화/접근 통제를 권장합니다.

복구 전에는 서비스 중지/복구 시나리오를 운영 절차로 승인받고 별도 테스트 환경에서 검증하세요. 단순 백업 파일 존재만으로 복구 가능성이 보장되지는 않습니다.

## 업데이트
폐쇄망에서 이미지 pull/build를 하지 않습니다. 승인된 인터넷 환경에서 이미지 태그/버전/취약점/라이선스를 검토하고 앱 빌드 → 모델/이미지 확보 → `80-package-offline.sh` → SHA256 확인 → 승인된 매체로 반입합니다. 기존 DB 백업 후 계획된 점검 시간에 교체하세요.

## 보안
- `.env`: root 소유, mode 600
- Docker 그룹은 사실상 root 권한이므로 일반 사용자에게 부여하지 않음
- 사용자 PC에 공개되는 포트는 18080/18081만 필요한 대역에 제한
- 18000, 11434, 5432, 6379, 8123/9000은 직접 공개하지 않음
- 현재 앱은 사용자별 RBAC/SSO/TLS를 완성하지 않았으므로 기관 인증·HTTPS 설정 전 운영 배포 금지
- 장애/이벤트 API 토큰은 읽기 전용 최소 권한을 사용
- Jennifer MCP tool schema를 검증하기 전 도구를 호출하지 않음

## 장애 대응 순서
1. `docker compose ps`
2. `sudo bash scripts/53-logs.sh <service>`
3. `nvidia-smi`, `docker compose exec ollama ollama list`
4. `/data`·`/backup` 마운트와 여유 공간 확인
5. API URL/인증/응답 스키마 확인
6. 실제 JSON과 오류 종류를 기록하되 토큰/비밀번호는 제거한 뒤 어댑터를 수정
