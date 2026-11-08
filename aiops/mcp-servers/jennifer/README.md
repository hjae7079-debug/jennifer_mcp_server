# JENNIFER APM 읽기 전용 MCP 서버 (v0.4.0)

AI-Ops 통합분석 플랫폼(총정리본 v4.1)의 Jennifer 연동 계층입니다. 이전 `server.py / jennifer_tools.py` 버전을 대체합니다.

## 이전 버전과 달라진 점

| 이전 (v1.0.0) | 지금 (v0.4.0) | 이유 |
|---|---|---|
| `/api/domain/{id}/realtime/activeService`, `metric/system`, `xlog` 호출 | 경로를 `config/endpoints.json`에 두고 Swagger로 확인 | 이전 경로는 실측 명세(5.6.3.13)의 `/api/dbmetrics`, `/api/status/*` 형식과 다름 |
| 서버 1대, `config.json`에 토큰 | 서버 3대(인터넷·행정·대민), 토큰은 환경 변수 | D-10 서버별 격리, 토큰을 git에 넣지 않음 |
| `--http` 시 `/sse` 안내, `run_http_server` 호출(존재하지 않는 함수) | Streamable HTTP `/mcp` | aiops-api 어댑터와 Open WebUI가 `/mcp`(2025-06-18)를 사용 |
| 쓰기 차단 없음 | GET만, 관리·restapi·사용자 목록 차단, 단위 테스트 | 조회 전용 토큰이 없어 코드로 차단 (설계 4.2) |
| 응답 원본 그대로 | clientIp/clientId 제거, 건수·크기 제한 | 개인정보 미저장, LLM 컨텍스트 보호 |
| 호출 기록 없음 | `/logs/jennifer-calls-YYYYMMDD.jsonl` | 쓰기 메서드 미발생 점검 (설계 11.2) |
| 시간 `yyyy-MM-dd HH:mm` 그대로 전달 | epoch ms 변환, status는 분 단위 정시 맞춤 | 실측 제약 |

## 구성

```
jennifer_mcp/
  guard.py      차단 규칙 (GET만, 차단 경로, 토큰 쿼리 금지, 허용 목록)
  client.py     표준 라이브러리 HTTP 클라이언트 (서버별 타임아웃·토큰·간격, 호출 로그)
  sanitize.py   개인정보 제거, 건수 제한
  timeutil.py   epoch ms, 분 단위 정렬, Java Date 변환
  tools.py      도구 로직 (dbmetrics 지표 1개, transaction 60초, responseTime 정렬 금지)
  server.py     MCP 서버 (Streamable HTTP /mcp, stdio)
  survey.py     Swagger 기준 GET 전수 호출 → 샘플 수집 (매뉴얼 G단계)
config/
  servers.example.json   뷰서버 3대 (토큰 없음)
  endpoints.json         도구 경로·허용 목록·파라미터 이름 (Swagger 확인 후 여기만 수정)
  survey-params.example.json
jennifer-mcp.env.example 토큰·활성화 스위치 (root 600)
tests/                   52개 단위 테스트 (가짜 제니퍼 서버 포함)
```

## 도구 목록

| 도구 | 설명 |
|---|---|
| `jennifer_servers` | 서버 목록, 활성 여부, 토큰 설정 여부 |
| `jennifer_domains` | 도메인 목록 (all이면 3대 병렬, 서버별 격리) |
| `jennifer_instances` | 도메인의 인스턴스 목록 |
| `jennifer_metric_catalog` | `/api/metrics` 지표 이름 |
| `jennifer_dbmetrics_instance` / `_domain` | 지표 시계열 (지표 1개만) |
| `jennifer_realtime_instance` | 실시간 인스턴스 상태 (4~5초, 반복 전수 호출 금지) |
| `jennifer_status` | `/api/status/{kind}` 집계 (분 단위 정시, responseTime 정렬 금지) |
| `jennifer_transaction_sample` | 대표 트랜잭션 소량 (60초 이하, 최대 100건) |
| `jennifer_transaction_txid` | txid 상세 (end 필요) |
| `jennifer_get` | 허용 목록 안의 GET 범용 조회 |

## 실행

플랫폼에서는 `aiops/docker-compose.yml`의 `jennifer-mcp` 서비스로 실행합니다.
API와 Open WebUI는 `http://jennifer-mcp:8791/mcp` 로 접근하고, 헤더 `Authorization: Bearer <MCP_AUTH_TOKEN>`을 보냅니다.

```bash
# 설정 (최초 1회)
sudo cp mcp-servers/jennifer/config/servers.example.json config/jennifer-servers.json
sudo cp mcp-servers/jennifer/jennifer-mcp.env.example config/jennifer-mcp.env
sudo chmod 600 config/jennifer-mcp.env
```

개발 PC에서 직접 실행할 때(stdio):
```bash
cd aiops/mcp-servers/jennifer
python3 -m venv .venv && .venv/bin/pip install --no-index --find-links wheelhouse -r requirements.txt
JENNIFER_CALL_LOG_DIR=./logs .venv/bin/python -m jennifer_mcp.server --stdio
```

## 활성화 순서 (설계 13.6: 설치 직후 꺼진 상태)

1. 단위 테스트 통과 확인: `python -m pytest -q tests`
2. 토큰 입력, `JENNIFER_MCP_ENABLED=false` 유지
3. Swagger JSON을 받아 전수 호출 dry-run:
   `python -m jennifer_mcp.survey --spec swagger.json --server internet --params config/survey-params.json --out /data/collection/jennifer-survey --dry-run`
4. dry-run 목록에서 `blocked` 항목(관리·사용자 목록)을 확인한 뒤 실제 호출 (`--dry-run` 제거)
5. `summary.csv`와 샘플로 `config/endpoints.json` 경로·파라미터 이름을 확정하고 `verified`를 true로 바꿈
6. `JENNIFER_MCP_ENABLED=true` 후 재기동, 호출 로그에서 GET 외 메서드가 없는지 확인:
   `grep -h '"method"' /data/logs/jennifer-mcp/*.jsonl | grep -v '"method": "GET"' | wc -l` → 0

## 확인이 필요한 부분 (실측 전)

- `endpoints.json`에서 `verified: false`인 경로(`/api/domain`, `/api/instance`, `/api/activeService/list`)와 파라미터 이름(`domain_id`, `start_time` 등)은 Swagger로 확인해야 합니다.
- 응답 래퍼 키(`result` 등)는 샘플을 보고 `sanitize.limit_items`의 키 목록을 조정합니다.
