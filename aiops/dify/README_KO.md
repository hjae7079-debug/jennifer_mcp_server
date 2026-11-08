# Dify Workflow 연결 안내

FastAPI는 `DIFY_BASE_URL`과 `DIFY_WORKFLOW_API_KEY`로 `/v1/workflows/run`을 호출합니다. 이 패키지에는 Dify 서버 자체와 공식 Compose 이미지 전체는 포함하지 않습니다. Dify의 버전·플러그인·의존성이 바뀌므로 승인된 공식 버전의 Docker Compose와 모든 이미지/플러그인 의존성을 온라인 환경에서 별도 확보해 오프라인 번들로 만들어야 합니다.

Workflow 입력: `kind`, `id`, `institution_name`, `title`, `occurred_at`, `source_payload`, `prompt`.
Workflow 출력: `data.outputs.text`, `answer`, `summary` 중 하나. 실제 Workflow에서 검증한 뒤에만 `ANALYSIS_PROVIDER=dify`로 전환하세요.
