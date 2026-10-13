# JENNIFER APM MCP Server for Qwen & Hermes Agent

이 프로젝트는 JENNIFER APM의 OpenAPI를 호출하여 로컬 Qwen 모델(LLM) 및 Hermes Agent에 성능 데이터를 제공하는 MCP 서버입니다.

---

## 📂 파일 구조
```text
jennifer_mcp_server/
├── README.md              # 설치 및 연동 가이드 (본 문서)
├── requirements.txt       # 파이썬 필수 패키지 (mcp, anyio)
├── config.json            # JENNIFER 뷰서버 연결 설정 파일
├── server.py              # MCP 서버 접수창구 (stdio / HTTP 모드 지원)
├── jennifer_tools.py      # 비즈니스 로직 (Active Service, 시스템 자원, XLog)
└── jennifer_client.py     # 표준 라이브러리(urllib) 기반 코어 통신 클라이언트
```

---

## ⚙️ 1. 설정 방법 (`config.json`)
`config.json` 파일을 열어 실제 운영 중인 JENNIFER 뷰서버 환경에 맞게 수정합니다.
```json
{
  "jennifer_url": "http://127.0.0.1:7900",
  "jennifer_token": "YOUR_OPEN_API_TOKEN_HERE",
  "domain_id": 1,
  "mcp_host": "127.0.0.1",
  "mcp_port": 8791,
  "timeout": 30
}
```

---

## 📦 2. 설치 방법 (폐쇄망 / 에어갭 환경 지원)  : 필요시 !!!

인터넷이 차단된 폐쇄망 서버에서는 의존성 패키지(`.whl`)를 외부에서 미리 다운로드하여 반입해야 합니다.

1. **외부망(인터넷 가능) PC에서 패키지 다운로드:**
   ```bash
   pip download -r requirements.txt -d ./offline_packages
   ```
2. **폐쇄망 서버로 폴더 이동 후 로컬 설치:**
   ```bash
   pip install --no-index --find-links=./offline_packages -r requirements.txt
   ```

---

## 🚀 3. 실행 방법

- **Stdio 모드 (Hermes Agent / Open WebUI 직접 연동용):**
  ```bash
  python server.py
  ```
- **HTTP (SSE) 모드 (데몬 백그라운드 서비스용):**
  ```bash
  python server.py --http
  ```

---

## 🤖 4. Hermes Agent 환경 연동 가이드 (`~/.hermes/config.yaml`)

Hermes Agent가 본 MCP 서버를 도구(Tool)로 인식하여 Qwen 모델과 연동할 수 있도록 설정 파일에 등록합니다.

`~/.hermes/config.yaml` 파일을 열고 아래와 같이 `mcp_servers` 항목에 추가하세요.

```yaml
mcp_servers:
  # 기존에 사용 중인 다른 MCP 서버 (예: nSIMS 등)
  nsims:
    url: "http://127.0.0.1:8790/mcp"
    headers:
      Authorization: "Bearer ${env:NSIMS_MCP_TOKEN}"

###############################################
stdio / HTTP 선택
  # 새로 추가하는 JENNIFER APM MCP 서버 (stdio 모드 연동)
  jennifer_apm:
    command: "python"
    args:
      - "/home/사용자계정명/jennifer_mcp_server/server.py"

  # 새로 추가하는 JENNIFER APM MCP 서버 (HTTP 서버 모드)
  jennifer_apm:
    url: "[http://127.0.0.1:8791/sse](http://127.0.0.1:8791/sse)"
###############################################
```

> **💡 팁:** `args`에 지정하는 `server.py`의 경로는 반드시 시스템 상의 **절대 경로(Absolute Path)**를 입력하셔야 에러 없이 정상 구동됩니다.
