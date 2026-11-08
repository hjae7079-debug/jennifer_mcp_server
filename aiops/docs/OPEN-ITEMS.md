# 현장 확인이 필요한 항목

## 필수 API 정보
- 기관/업무 기준 API URL, 인증 방식, 페이지네이션, 기관/업무 ID와 이름 필드
- 장애 이력 API URL, 장애 ID/기관명/제목/발생시각/상태 필드
- 이벤트 이력 API URL, 이벤트 ID/기관명/제목/발생시각/상태 필드
- 각 API의 조회 제한, 최대 호출 빈도, 타임아웃, 오류/재시도 정책

## Jennifer MCP
- 실제 MCP URL, 인증 헤더, protocol version, Streamable HTTP/SSE/legacy transport 여부
- `tools/list` 결과 원본과 각 read-only 도구의 `inputSchema`
- 실제 호출의 request/response JSON 샘플
- APM에서 먼저 연결할 항목과 호출 제한/비용. 스키마 검증 전 `tools/call`을 임의로 구현하지 않음

## Dify Workflow
- 승인된 Dify 버전과 모든 이미지/플러그인/의존성 목록
- Workflow API Key, 입력 필드, 출력 필드, 사용자/감사 로그 정책
- Dify 서버는 이 패키지에서 자동 설치하지 않으며 별도 공식 Compose 절차와 오프라인 번들이 필요

## 운영 보안
- 사용자 인증/권한(RBAC/SSO), TLS 인증서 및 HTTPS 포트 18443 구성
- UFW/기관 방화벽의 실제 허용 사용자 대역
- 이미지 digest/SBOM/CVE/라이선스 검토
- 백업 암호화 및 복구 리허설

- Dify 서버 이미지 및 플러그인 의존성은 별도 버전 고정·반입 필요.
- Jennifer 실제 tool 호출은 서버의 tools/list 및 응답 스키마 검증 후 구현.
- ITSM MCP의 실제 API 필드, 고유 ID, 변경 감지/재수집 파라미터는 기관 API 확인 후 어댑터 확정.
