# JENNIFER APM MCP Server for Qwen

이 프로젝트는 JENNIFER APM의 OpenAPI를 호출하여 로컬 Qwen 모델(LLM)에 성능 데이터를 제공하는 MCP 서버의 기본 뼈대입니다.

## 설치 방법
```bash
pip install -r requirements.txt
```

## 설정
`config.json` 파일을 열어 실제 JENNIFER 뷰서버 주소와 발급받은 OpenAPI 토큰, 도메인 ID를 입력하세요.

## 실행 방법
- **테스트(stdio 모드):** `python server.py` (Hermes/Open WebUI 클라이언트가 직접 프로세스를 띄울 때 사용)
- **HTTP 서버 모드:** `python server.py --http` (별도 데몬으로 띄워놓고 여러 클라이언트가 URL로 접근할 때 사용)
