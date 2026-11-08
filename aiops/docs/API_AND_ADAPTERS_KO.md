# API 및 어댑터 계약

## API
- `GET /api/healthz`
- `GET /api/dashboard`
- `GET /api/items/{incident|event}/{id}`
- `POST /api/chat`
- `POST /api/embeddings`
- `POST /api/integrations/jennifer/discover`
- `GET /api/integrations/status`

Nginx는 `/api/` prefix를 제거하고 내부 FastAPI에 전달합니다. React는 DB/MCP에 직접 연결하지 않습니다.

## 데이터 식별
이력 DB의 PK는 `(kind,id)`입니다. 탐지내역/관찰대상이 장애/이벤트와 연결될 때 `source_kind + source_id`를 사용합니다. 동일 건이 여러 화면에 보여도 원본 이력 ID는 유지합니다.

## 분석 우선순위
- 장애 우선순위 0
- 이벤트 우선순위 1
- 기본 폴링 30초
- 단일 worker가 장애를 먼저 처리합니다. 대량 이벤트가 있으면 장애 분석 지연이 최소화되도록 배치 순서를 유지합니다.

## Jennifer MCP
`initialize`/`notifications/initialized`/`tools/list` 탐색만 구현했습니다. `tools/call`은 의도적으로 구현하지 않았습니다. 실제 `tools/list`와 API 응답 JSON을 확보하고 검토한 뒤 별도 allowlist를 추가해야 합니다.

## Dify
`/v1/workflows/run` client를 포함합니다. Workflow 출력은 `data.outputs.text|answer|summary` 중 하나로 확인합니다. 실제 Workflow에서 검증되지 않은 출력 구조를 추정하지 않습니다.
