"""Jennifer MCP schema discovery only. This module never invokes tools/call."""
import os, json
import httpx

class JenniferMCPError(Exception): pass

class JenniferMCPAdapter:
    def __init__(self):
        self.url = os.getenv("JENNIFER_MCP_URL", "").strip()
        self.token = os.getenv("JENNIFER_MCP_TOKEN", "").strip()
        self.protocol = os.getenv("JENNIFER_MCP_PROTOCOL_VERSION", "2025-06-18")
        self.session = None
        self.counter = 0
    @property
    def configured(self): return bool(self.url)
    def headers(self):
        h = {"Accept":"application/json, text/event-stream", "Content-Type":"application/json"}
        if self.token: h["Authorization"] = f"Bearer {self.token}"
        if self.session: h["Mcp-Session-Id"] = self.session
        return h
    def next_id(self): self.counter += 1; return self.counter
    @staticmethod
    def parse(resp):
        if resp.status_code >= 400: raise JenniferMCPError(f"MCP HTTP {resp.status_code}")
        raw = resp.text.strip()
        if not raw: return {}
        if "text/event-stream" in resp.headers.get("content-type", ""):
            candidates = [line[5:].strip() for line in raw.splitlines() if line.startswith("data:")]
            for candidate in reversed(candidates):
                try: return json.loads(candidate)
                except Exception: pass
            raise JenniferMCPError("SSE data JSON을 찾지 못했습니다.")
        try: return resp.json()
        except Exception as exc: raise JenniferMCPError("MCP 응답이 JSON이 아닙니다.") from exc
    async def discover_tools(self):
        if not self.configured: raise JenniferMCPError("JENNIFER_MCP_URL 미설정")
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            init = {"jsonrpc":"2.0","id":self.next_id(),"method":"initialize","params":{"protocolVersion":self.protocol,"capabilities":{},"clientInfo":{"name":"aiops-dashboard-discovery","version":"0.3.0"}}}
            try:
                r = await client.post(self.url, headers=self.headers(), json=init)
                self.session = r.headers.get("Mcp-Session-Id") or self.session
                initialized = self.parse(r)
                if initialized.get("error"): raise JenniferMCPError(f"initialize 오류: {initialized['error']}")
                await client.post(self.url, headers=self.headers(), json={"jsonrpc":"2.0","method":"notifications/initialized"})
                r2 = await client.post(self.url, headers=self.headers(), json={"jsonrpc":"2.0","id":self.next_id(),"method":"tools/list","params":{}})
                listed = self.parse(r2)
                if listed.get("error"): raise JenniferMCPError(f"tools/list 오류: {listed['error']}")
                tools = listed.get("result",{}).get("tools")
                if not isinstance(tools,list): raise JenniferMCPError("result.tools 배열 없음. 실제 MCP 프로토콜/응답을 확인하세요.")
                return {"protocol_version":initialized.get("result",{}).get("protocolVersion"),"tool_count":len(tools),"tools":[{"name":t.get("name"),"description":t.get("description"),"inputSchema":t.get("inputSchema")} for t in tools if isinstance(t,dict)],"tool_calls_enabled":False,"note":"탐색 전용. 스키마 검토 후 별도 승인된 allowlist가 필요합니다."}
            except JenniferMCPError: raise
            except Exception as exc: raise JenniferMCPError(f"MCP 탐색 실패({type(exc).__name__}); 서버의 Streamable HTTP 지원 여부를 확인하세요.") from exc
