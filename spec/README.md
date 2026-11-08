# spec/ — Jennifer Open API 명세

뷰서버의 Swagger(OpenAPI) 명세 JSON 을 이 폴더에 `jennifer.json` 같은 이름으로 둔다 (여러 개 가능).

- `api_catalog` 도구와 `survey.py`(전수 GET 호출)가 이 파일을 읽는다
- 명세는 내부 자료라 git 에 올리지 않는다 (`.gitignore` 의 `spec/*.json`). 반입 zip 에만 넣는다
- 형식: Swagger 2.0 또는 OpenAPI 3.x (JSON). YAML 이면 JSON 으로 바꿔서 둔다
