# 현장 확인이 필요한 항목

## 필수 API 정보
- 기관/업무 기준 API URL, 인증 방식, 페이지네이션, 기관/업무 ID와 이름 필드
- 장애 이력 API URL, 장애 ID/기관명/제목/발생시각/상태 필드
- 이벤트 이력 API URL, 이벤트 ID/기관명/제목/발생시각/상태 필드
- 각 API의 조회 제한, 최대 호출 빈도, 타임아웃, 오류/재시도 정책

## Jennifer (뷰서버 Open API 직접 호출, 벤더 MCP 서버 없음)
- 뷰서버 3대 Open API 경로·파라미터 이름 확정 (Swagger + survey, `mcp-servers/jennifer/config/endpoints.json`의 `verified: false` 항목)
- 서버별 토큰 발급(현재 토큰 사용, 조회 전용 토큰 불가)과 호출 제한
- 응답 래퍼 키·건수 확인 (샘플)

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
- Jennifer는 자체 컨테이너가 뷰서버 Open API를 GET으로 호출. 경로 확정 전 비활성.
- ITSM MCP의 실제 API 필드, 고유 ID, 변경 감지/재수집 파라미터는 기관 API 확인 후 어댑터 확정.
