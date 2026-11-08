# AI-Ops 통합분석 플랫폼 (PoC) — 설치 패키지 + Jennifer MCP 서버

폐쇄망 GPU PC(Ubuntu 24.04.5, RTX 5080)에서 로컬 LLM(Qwen3 14B)으로 ITSM·Jennifer·SIEM 데이터를 분석하는 플랫폼의 설치 패키지입니다.
**인터넷망에서 이 저장소를 받아 설치·번들을 만든 뒤, 같은 PC를 폐쇄망으로 옮깁니다.**

| 경로 | 내용 |
|---|---|
| `docs/AIOps_통합분석_플랫폼_총정리본_v4_1.md` | 설계 총정리본 (최신, v4.0을 대체) |
| `docs/AIOps_설치_운영_매뉴얼_v0_3_3.md` | 설치·운영 매뉴얼 (최신) |
| `docs/REVIEW_v4_0_검토결과.md` | v4.0·v0.3.2에서 틀린 부분과 인터넷망에서 더 받아야 할 것 |
| `aiops/` | 설치 패키지 v0.3.3 (`/opt/aiops`로 연결해 사용) |
| `aiops/mcp-servers/jennifer/` | Jennifer APM 읽기 전용 MCP 서버 v0.4.0 (이전 `server.py` 대체) |

## 흐름

```
[인터넷망]  git clone → install-all.sh → build-offline-caches.sh → 75-verify-offline-prep.sh
                                         (이미지·모델·wheel·npm·git 번들 → /backup/aiops-offline/<날짜>/)
[폐쇄망]    IP 변경·NAT 차단 → verify-offline.sh → 17-docker-firewall.sh
            → 제니퍼 차단 테스트 → survey(전수 GET) → endpoints.json 확정 → MCP 활성화
            → Qwen2.5-Coder로 추가 개발 (git 번들 + dev-wheelhouse), 추가 MCP는 aiops/mcp-servers/<이름>/ 로 반입
```

빠른 시작:
```bash
sudo git clone https://github.com/hjae7079-debug/jennifer_mcp_server.git /opt/aiops-src
sudo ln -sfn /opt/aiops-src/aiops /opt/aiops
cd /opt/aiops && sudo cp .env.example .env
sudo bash scripts/install-all.sh
```

## 테스트

```bash
cd aiops/mcp-servers/jennifer && python3 -m pytest -q tests   # 52개 (차단 규칙, 개인정보 제거, 시간 변환, 서버 격리, survey)
cd aiops/apps/api && python3 -m pytest -q tests               # 6개
```
