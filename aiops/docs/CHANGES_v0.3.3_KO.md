# v0.3.3 변경 사항 (v0.3.2 대비)

상세 근거: 저장소 `docs/REVIEW_v4_0_검토결과.md` (E-01 ~ E-19)

## Jennifer MCP 서버 v0.4.0 (새로 작성, `mcp-servers/jennifer/`)
- compose 서비스 `jennifer-mcp` (Streamable HTTP `/mcp`, 호스트 포트 없음, Bearer 인증)
- 서버 3대 격리, GET 전용 차단 규칙과 단위 테스트, clientIp/clientId 제거, 호출 JSONL 로그
- Swagger 기준 GET 전수 호출 도구 `python -m jennifer_mcp.survey`
- 설치 직후 비활성 (`config/jennifer-mcp.env`의 `JENNIFER_MCP_ENABLED=false`)

## 설치·오프라인 (치명 오류 수정)
- `build-offline-caches.sh` 재작성: pip·npm 다운로드를 컨테이너에서 수행(호스트 pip/node 불필요), `package-lock.json` 기반 npm 캐시,
  `node:22-alpine`·`ubuntu:22.04`·`config/extra-images.txt` 이미지 포함, MCP·개발 도구 wheelhouse, git 번들, APT 번들 포함
- `restore-offline-caches.sh` 추가 (새 PC 재구축, D-09)
- `40-build-apps.sh`: `package-lock.json` 생성, 기반 이미지 pull, MCP 이미지 빌드, 태그를 `APP_VERSION`으로 통일
- `75-verify-offline-prep.sh`: 기반 이미지·wheelhouse·lock 파일까지 확인, 태그 불일치(0.3.1) 수정
- `install-all.sh`: 매뉴얼 순서대로 재작성 (06·07 누락으로 실패하던 문제)
- `80-package-offline.sh`, `55-offline-install.sh`: 이전 방식으로 표시

## 호스트·보안
- `15-pin-host.sh` 추가: 자동 업데이트 끄기, 커널·NVIDIA 드라이버 `apt-mark hold` (설치 시작 직후)
- `17-docker-firewall.sh` 추가: Docker 공개 포트(18080/18081)를 DOCKER-USER 체인에서 `ALLOWED_CIDRS`만 허용 (ufw로는 막히지 않음)
- `06-init-secrets.sh`: `JENNIFER_MCP_TOKEN` 생성, `config/jennifer-mcp.env`(600) 생성

## LLM
- `OLLAMA_MAX_LOADED_MODELS=2` (임베딩 호출 때 Qwen3가 내려가던 문제), `OLLAMA_CONTEXT_LENGTH=16384`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`
- 분석·채팅 호출에 `think: false`, `num_ctx` 지정, 분석은 `format: json`
- `docker-compose.dev.yml`: dev 모드에서만 Ollama `127.0.0.1:11434` 공개 (폐쇄망 Qwen Coder 개발용)

## Open WebUI
- 폐쇄망 설정: `OFFLINE_MODE`, `HF_HUB_OFFLINE`, `ENABLE_OPENAI_API=false`, RAG 임베딩을 Ollama `bge-m3`로

## 기타
- `.env.example`: `APP_VERSION`, `ALLOWED_CIDRS`, Ollama 설정, MCP 주소 안내
- `config/mcp.env.example`: `host.docker.internal` 안내 제거 (컨테이너에서 호스트 루프백 접근 불가)
- `config/dev-requirements.txt`, `config/extra-images.txt` 추가
- `70-healthcheck.sh`: MCP 응답, `ollama ps` 확인 추가

## 검증 범위
- MCP 서버 단위 테스트 52개 통과, MCP 클라이언트로 `/mcp` 접속·도구 목록·호출·401 확인
- `docker compose config` 통과, 모든 스크립트 `bash -n` 통과, API 단위 테스트 6개 통과
- 실제 GPU PC 설치, 이미지 빌드, 폐쇄망 동작은 아직 검증하지 않음
