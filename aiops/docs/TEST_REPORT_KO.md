# 정적 검증 보고서 (패키지 생성 시점)

## 통과한 검사
- Python `compileall`: API/adapter/worker/test 파일 구문 검사 통과
- Shell `bash -n`: 모든 `scripts/*.sh` 구문 검사 통과
- YAML/JSON/XML 파싱: Compose, React package.json, ClickHouse backup config 통과
- React JSX 파싱: TypeScript parser로 `main.jsx` 구문 분석 통과
- 어댑터/분석 테스트: `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=apps/api pytest -q apps/api/tests` → **6 passed**

## 이 생성 환경에서 완료하지 못한 검사
- React/Vite production build: npm registry 설치 시도에서 제한 시간 내 완료되지 않음(네트워크/패키지 다운로드 환경 문제). 대상 GPU PC의 인터넷 준비 단계에서 `40-build-apps.sh`가 실제 빌드를 수행해야 함.
- Docker Compose 구성 검증, 이미지 pull/build, NVIDIA Container Toolkit 설치: 이 생성 환경에 Docker CLI가 없어 실행하지 못함.
- RTX 5080 GPU 추론/VRAM 사용량, 폐쇄망에서 인터넷 차단 상태의 end-to-end: 실행하지 못함.
- 기관/업무/장애/이벤트 API, Jennifer MCP 실제 tool schema, Dify Workflow 입력/출력 매핑: 실제 접속 정보와 응답 JSON이 제공되지 않아 검증하지 못함.
- UFW/기관 방화벽, TLS, 사용자 인증, 백업 복구 리허설: 현장 검증 필요.

정적 검사 통과는 운영 배포 완료를 뜻하지 않습니다. 인터넷 환경에서 설치 스크립트를 실행한 후 각 서비스 헬스체크와 실제 질문·응답을 통과해야 합니다.
