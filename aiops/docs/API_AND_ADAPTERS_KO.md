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

## Jennifer
제니퍼가 제공하는 MCP 서버는 없습니다. 플랫폼이 제니퍼 뷰서버 Open API(REST, `http://<뷰서버>:7900/api/...`, Bearer 토큰)를 직접 GET으로 호출합니다. `jennifer-mcp`는 이 패키지에 포함된 **자체 컨테이너**(`mcp-servers/jennifer/`)로, 그 REST 호출을 LLM 도구로 감싼 것입니다.

- `apps/api/app/adapters/jennifer_mcp.py`: 자체 `jennifer-mcp` 컨테이너에 `initialize`/`tools/list`만 보내 도구 목록을 확인합니다(연동 상태 화면).
- 실제 조회는 `mcp-servers/jennifer/jennifer_mcp/client.py`가 뷰서버 REST를 GET으로 호출합니다. 허용 목록·차단 규칙·단위 테스트는 그 폴더에 있습니다.
- 경로·파라미터 이름은 Swagger와 전수 GET 호출(survey) 결과로 `config/endpoints.json`에서 확정합니다.

## Dify
`/v1/workflows/run` client를 포함합니다. Workflow 출력은 `data.outputs.text|answer|summary` 중 하나로 확인합니다. 실제 Workflow에서 검증되지 않은 출력 구조를 추정하지 않습니다.
