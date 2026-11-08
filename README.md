# jennifer_mcp_server — JENNIFER APM MCP 서버 (조회 전용)

Hermes Agent·AI-Ops 플랫폼(FastAPI)·기타 MCP 클라이언트가 JENNIFER 뷰서버 3대의 WAS 성능 데이터를 **읽기만** 하도록 해 주는 MCP 서버.
구조는 [`vicory777/nsims_mcp`](https://github.com/vicory777/nsims_mcp)(nSIMS SIEM MCP)를 따랐다. 설계 기준은 「AI-Ops 통합분석 플랫폼 총정리본 v4.0」 4.2절.

- **운영: Streamable HTTP 서비스** — systemd 상시 실행, `http://<주소>:8791/mcp` (AI-Ops `.env` 의 `JENNIFER_MCP_URL` 과 같은 포트·경로)
  - 클라이언트별 토큰, 접속 IP 제한, Host 헤더 검사, `/healthz`, 접속 기록 (nsims_mcp `service.py` 와 같은 코드)
- 시험: stdio (`python server.py`)
- mcp SDK **1.30.0(고정본)**·2.3.0 모두 시험 통과 (stdio·HTTP 둘 다), AI-Ops `jennifer_mcp.py` 어댑터의 도구 탐색(12개) 확인

```
[Hermes / AI-Ops API] ──HTTP(Bearer 토큰)──> jennifer MCP :8791/mcp ──GET 전용──> 인터넷 업무 10.148.222.57:7900
                                              │                     ├──────────> 행정 업무   10.148.232.57:7900
                                              │                     └──────────> 대민 업무   10.148.232.59:7900
                          logs/access_*.log (누가·어떤 도구), logs/calls_*.jsonl (어떤 API 를 어떤 파라미터로)
```

## 안전 장치 (v4.0 호출 정책)

| 항목 | 구현 | 시험 |
|---|---|---|
| GET 만 호출 | `jennifer_client.py` 에 GET 외 요청을 만드는 코드 자체가 없음 (요청 본문 없음, `method="GET"` 고정) | `test_client_source_only_get` (소스 정적 검사), 가짜 서버에 쓰기 요청 0건 확인 |
| 차단 경로 | `/api-v2/manage*`, `/restapi*`, `/api/auth/userlist*` (대소문자 무시) + `/api/`·`/api-v2/` 밖, `..`·`//`·`%`·`?`·공백 등 | `test_denied_*` — 차단된 요청이 서버에 **도착하지 않음** 확인 |
| 토큰 | `Authorization: Bearer` 헤더만. 파라미터에 `token`·`access_token`·`apiKey` 가 있으면 거부 | `test_token_never_in_query` |
| 서버 3대 격리 (D-10) | 서버마다 토큰·타임아웃 분리, 동시 1건, 연결 실패 시 30초간 건너뜀 → 결과의 `unavailable` 에 서버·사유 | `test_isolation` |
| 개인정보 | `clientIp`·`clientId`(설정 `drop_fields`)를 응답에서 지운 뒤에만 도구·샘플로 | `test_transactions`, `test_strip_fields` |
| 호출 기록 | 모든 호출을 `logs/calls_YYYYMMDD.jsonl` (서버·경로·파라미터·상태·ms, **토큰 값 없음**) | — |
| 부하 | 서버당 최소 간격 0.3초, 전체 1분 120회 상한 (넘으면 대기), 목록 10분 캐시 | — |

> 조회 전용 토큰을 받을 수 없어 관리 권한 토큰을 쓰므로, 위 차단은 **코드에서만** 이뤄진다. 정기적으로 `logs/calls_*.jsonl` 에 GET 외 기록·차단 경로가 없는지 확인할 것 (`"method": "GET"` 만 있어야 함).

## 도구 (Hermes 에서는 `mcp__jennifer__<이름>`)

| 도구 | 하는 일 | API 호출 수 |
|---|---|---|
| `servers_status` | 3대 연결·응답 시간·도메인 수, 호출 빈도, **아직 실서버로 확인 안 된 경로** | 3 |
| `domain_list` | 도메인 목록 (server 비우면 3대) | 서버당 1 (캐시) |
| `instance_list` | 인스턴스 목록 + 이름·IP·호스트·상태 거르기 | 도메인당 1 (캐시) |
| `find_instance` | VM 이름·IP·호스트명 일부로 3대 전체 검색 (URL→VM→인스턴스 매핑 확인용) | 캐시 후 0 |
| `metric_names` | 조회 가능한 지표 이름 (`/api/metrics`) | 1 (캐시) |
| `realtime_instance` | 실시간 인스턴스 상태 (실측 4~5초) | 1 |
| `instance_metrics` | 지표 시계열 요약: 최소·최대·평균·마지막·앞뒤 절반 평균·`trend_pct` (관찰대상 탐지 보조) | **지표마다 1** (최대 6) |
| `status_summary` | 도메인 구간 집계 상위 (application·sql·externalcall·error), 구간은 분 정시 | 1 |
| `transactions` | 60초 이하 구간 트랜잭션: 건수·오류·p50/p90/p99/max + 느린 순 상위 | 1 |
| `transaction_profile` | 트랜잭션 하나의 구간별 소요 (txid + endTime) | 1 |
| `api_catalog` | 명세(`spec/*.json`)에서 GET 엔드포인트 검색 + 정책(allowed/blocked) | 0 |
| `api_get` | 명세의 GET 경로 직접 조회 (정책·개인정보 제거·출력 제한 적용) | 1 |

`server` 인자: `인터넷`(internet)·`행정`(admin)·`대민`(public). 시각: `'2026-11-08 14:30'`, `'14:30'`, epoch ms. 응답의 Java Date 문자열은 epoch ms 로 바꿔서 넘긴다.

## ⚠️ 실서버 확인 전 (가정값)

Jennifer 응답 형식과 일부 경로·파라미터 이름은 실서버로 확인하지 못했다. 그래서 **코드가 아니라 `endpoints.json` 에서 고친다**.

1. 뷰서버의 Swagger 명세 JSON 을 `spec/jennifer.json` 으로 둔다 (git 에는 안 올라감)
2. 폐쇄망에서 `survey.py` 로 전수 GET 호출 → `samples/survey_<서버>_<시각>.md` 에 성공·실패·응답 구조
3. 결과를 보고 `endpoints.json` 의 `path`·`params` 를 고치고 `"verified": true` 로 바꾼다 → `servers_status` 의 `endpoints_unverified` 가 빈다
4. 응답 필드 이름이 다르면 `jennifer_tools.py` 의 `_pick(...)` 후보 이름에 추가 (예: 인스턴스 IP 필드)

도구는 형식을 모를 때도 깨지지 않게 만들었다 (행 목록을 `result`·`data`·`list` 등에서 찾고, 필드 이름 후보 여러 개). 형식이 다르면 요약 대신 `sample` 이 나온다.

## 설치 — 인터넷망에서 준비 → 폐쇄망 반입

```bash
# [인터넷 PC] 저장소 받기 + 리눅스 py3.12 용 설치 파일 (29개, mcp 1.30.0 고정)
git clone https://github.com/hjae7079-debug/jennifer_mcp_server.git
cd jennifer_mcp_server
bash download_wheels.sh                 # → wheels/ + wheels/SHA256SUMS
cp <받은 Jennifer Swagger 명세>.json spec/jennifer.json
cd .. && zip -r jennifer_mcp_server.zip jennifer_mcp_server -x '*/.git/*'
```

```bash
# [GPU PC, 인터넷 없이] 설치 → /opt/jennifer_mcp_server, 계정 jennifer-mcp, systemd jennifer-mcp
unzip jennifer_mcp_server.zip && cd jennifer_mcp_server
sudo bash install.sh
# Jennifer API 토큰 저장 (서버마다, 화면에 안 보이게 입력 → secrets.json 600)
for s in internet admin public; do
  sudo -u jennifer-mcp /opt/jennifer_mcp_server/.venv/bin/python /opt/jennifer_mcp_server/server.py --set-jennifer-token $s
done
sudo systemctl restart jennifer-mcp
curl http://127.0.0.1:8791/healthz
```

- 토큰은 환경변수 `JENNIFER_TOKEN_INTERNET`·`_ADMIN`·`_PUBLIC` 로도 줄 수 있음 (`secrets.json` 보다 우선)
- 클라이언트 토큰: `install.sh` 가 `hermes`·`aiops` 두 개 발급. 추가 `server.py --gen-token 이름`, 폐기 `--revoke-token 이름` (재시작 불필요)
- `secrets.json`·`tokens.json`·`config.local.json`·`logs/`·`samples/`·`spec/*.json`·`wheels/` 는 git 에 안 올라감

### 접속 범위 (`config.json` → `http`)

| 상황 | 설정 |
|---|---|
| Hermes·test_client 가 같은 PC (기본) | `"bind": "127.0.0.1"` |
| **AI-Ops 컨테이너**(api·worker)에서 `http://host.docker.internal:8791/mcp` 로 접속 | `"bind": "172.17.0.1"`(docker0 IP, `ip -4 addr show docker0` 로 확인), `"allow_ips": ["172.16.0.0/12"]`, `"allowed_hosts": ["host.docker.internal:8791"]` |
| TLS | `"ssl_certfile"`, `"ssl_keyfile"` |

127.0.0.1 로 띄우면 컨테이너에서 `host.docker.internal` 로 **접속할 수 없다** (host-gateway 는 루프백이 아니라 브리지 IP). 토큰 없이 외부 주소로 여는 설정은 실행이 거부된다.

### 클라이언트 등록

Hermes (`~/.hermes/config.yaml`):
```yaml
mcp_servers:
  jennifer:
    url: "http://127.0.0.1:8791/mcp"
    headers:
      Authorization: "Bearer ${env:JENNIFER_MCP_TOKEN}"   # ~/.hermes/.env 에 JENNIFER_MCP_TOKEN=<tokens.json 의 hermes 값>
    timeout: 120
```

AI-Ops (`/opt/aiops/.env`): `JENNIFER_MCP_URL=http://host.docker.internal:8791/mcp`, `JENNIFER_MCP_TOKEN=<tokens.json 의 aiops 값>` → 설정 화면의 연동 상태에서 도구 12개가 보이면 정상 (현재 어댑터는 탐색 전용, `tools/call` 은 아직 안 함).

## 시험 순서

```bash
# 인터넷망(뷰서버 없음) — 가짜 뷰서버로 흐름만
echo '{"force_mock": true}' > config.local.json        # 이 PC 는 항상 가짜 데이터 (반입 zip 에서 뺄 것)
python3 -m venv .venv && .venv/bin/pip install --no-index --find-links wheels -r requirements.lock
.venv/bin/python -m unittest discover -s tests -v     # 28개 (호출 정책·도구·전수 호출 계획·MCP stdio/HTTP)
.venv/bin/python server.py --gen-token me && .venv/bin/python server.py --http &
.venv/bin/python test_client.py --url http://127.0.0.1:8791/mcp --token <토큰>                      # 도구 목록
.venv/bin/python test_client.py --url http://127.0.0.1:8791/mcp --token <토큰> find_instance '{"keyword":"vm000"}'
```

```bash
# 폐쇄망(뷰서버 연결) — config.local.json 없어야 함
.venv/bin/python server.py --selftest                                  # ① 3대 직접 연결
.venv/bin/python survey.py --server internet --dry-run                 # ② 무엇을 부를지 확인
.venv/bin/python survey.py --server internet --edge                    # ③ 전수 GET + 실측 제약 재확인 → samples/
curl http://127.0.0.1:8791/healthz                                     # ④ 서비스 ("mock": false)
```
⑤ Hermes 에서: "행정 업무 서버에서 vm00012345 인스턴스의 최근 1시간 힙과 GC 추세 봐줘"

가짜 뷰서버(`mock_jennifer.py`)의 응답 형식은 **가정**이다. 도구 호출 흐름·차단 규칙·개인정보 제거 확인용이지 결과 해석용이 아니다.

## 전수 GET 호출 (`survey.py`, 매뉴얼 G단계)

- 명세의 GET 엔드포인트를 하나씩 부르며 파라미터를 이름으로 채움: `domain_id`→첫 도메인, `instance_id`→첫 LIVE 인스턴스, `start_time`/`end_time`→최근 5분 정시(ms, `transaction/time` 은 60초), `metrics`→첫 지표, `txid`·`time`→최근 트랜잭션
- 모르는 필수 파라미터는 부르지 않고 보고서에 `건너뜀(사유)`. `--param 이름=값` 으로 채움
- 차단 경로(관리·사용자 목록·restapi)는 부르지 않고 `blocked` 로 기록
- 샘플은 목록 20행으로 자르고 **IPv4 를 198.18.x.x 로 일관 치환**, `clientIp`·`clientId` 제거. 그래도 반출 전에 직접 열어 볼 것 (호스트명·업무명은 그대로)
- `--edge`: dbmetrics 지표 2개, status 정시 아님, `sort_by_metrics=responseTime`·`averageResponseTime`·`elapseSum`(O-06), transaction/time 61초
- 호출 사이 1초 대기 (`--sleep`), 서버당 동시 1건 → 뷰서버 부하 최소화

## 파일

| 파일 | 역할 | 수정 |
|---|---|---|
| `server.py` | 진입점, MCP 도구 등록, CLI (`--http`, `--gen-token`, `--set-jennifer-token`, `--selftest`) | 도구 추가 시 |
| `service.py` | HTTP 앞단: 토큰 인증, IP 제한, Host 검사, `/healthz`, 접속 기록 (nsims_mcp 와 같음) | - |
| `jennifer_client.py` | **호출 정책**(GET 전용·차단 경로·토큰 쿼리 금지), 서버별 격리, 개인정보 제거, 호출 기록 | 정책 바뀔 때만 |
| `jennifer_tools.py` | 도구 로직 (시간 정시 맞춤, 지표별 호출, 요약, 명세 읽기) | 필드 이름 후보 |
| `endpoints.json` | 도구가 부르는 경로·파라미터 이름 (**실측 후 고치는 곳**) | **survey 후** |
| `config.json` | 서버 3대 주소·타임아웃, 상한, `drop_fields`, `http` | 필요 시 |
| `config.local.json` | 이 PC 전용 강제 설정 (`{"force_mock": true}`), git·zip 제외 | - |
| `secrets.json` / `tokens.json` | Jennifer API 토큰 / 클라이언트 토큰 (600, git·zip 제외) | 명령으로만 |
| `survey.py` | 전수 GET 호출, 마스킹 샘플·보고서 | - |
| `mock_jennifer.py` | 가짜 뷰서버 (실측 제약 흉내) | - |
| `test_client.py` | Hermes 없이 시험 (stdio / HTTP) | - |
| `tests/` | 단위·끝까지 시험 28개, `fixtures/spec_sample.json` (가짜 명세) | 샘플 받으면 fixtures 추가 |
| `requirements.lock`, `download_wheels.sh`, `wheels/` | 시험한 버전 고정 목록 (nsims_mcp 와 같음) + 리눅스 py3.12 오프라인 설치 파일 | - |
| `install.sh`, `jennifer-mcp.service` | 폐쇄망 설치 (/opt, 전용 계정, systemd 하드닝) | 경로 |
| `spec/` | Jennifer Swagger 명세 (git 제외) | - |

## ⚠️ 에이전트 권한 (nsims_mcp 실측 교훈)

- 분석용 Hermes 에 **터미널 도구가 열려 있으면** 에이전트가 MCP 를 거치지 않고 뷰서버를 직접 부를 수 있다 → 차단 규칙·호출 기록이 무력화. 터미널은 끄거나 승인제로
- 인터넷망 PC 는 `config.local.json` 에 `{"force_mock": true}` → 어떤 방법으로 실행해도 실제 API 를 못 부름
- 실데이터 MCP 는 **로컬 모델(Ollama)로만**. 클라우드 모델이 설정된 클라이언트에 등록하지 말 것
