import argparse
import os
import sys
import json
import anyio

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jennifer_tools as J

try:
    from mcp.server.mcpserver import MCPServer as _Server
    SDK_MAJOR = 2
except ImportError:
    from mcp.server.fastmcp import FastMCP as _Server
    SDK_MAJOR = 1

VERSION = "1.0.0"
INSTRUCTIONS = "JENNIFER APM 성능 데이터를 조회하여 시스템 장애 및 지연 원인을 분석하는 도구입니다. CPU, Memory, Active Service, XLog 데이터를 활용하여 종합적으로 판단하세요."

try:
    mcp = _Server("jennifer_apm", instructions=INSTRUCTIONS, version=VERSION)
except TypeError:
    mcp = _Server("jennifer_apm", instructions=INSTRUCTIONS)
    if hasattr(mcp, "_mcp_server"):
        mcp._mcp_server.version = VERSION

def _call_sync(fn, *a, **kw):
    try:
        res = fn(*a, **kw)
        if isinstance(res, str):
            return res
        return json.dumps(res, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False)

async def _call(fn, *a, **kw):
    return await anyio.to_thread.run_sync(lambda: _call_sync(fn, *a, **kw))

@mcp.tool()
async def active_service() -> str:
    """[JENNIFER APM] 현재 활성화된 액티브 서비스 수를 확인하여 시스템 병목 여부를 1차 판단합니다."""
    return await _call(J.get_active_service)

@mcp.tool()
async def system_resource(stime: str, etime: str) -> str:
    """[JENNIFER APM] 특정 시간대의 CPU 및 Heap Memory 사용량 데이터를 조회합니다. (포맷: yyyy-MM-dd HH:mm)"""
    return await _call(J.get_system_resource, stime, etime)

@mcp.tool()
async def slow_xlog(stime: str, etime: str, min_ms: int = 3000) -> str:
    """[JENNIFER APM] 특정 시간대에 발생한 느린 트랜잭션(Slow XLog)을 조회하여 지연 원인(SQL, 외부 API 등)을 추적합니다."""
    return await _call(J.get_xlog, stime, etime, min_ms)

def main():
    parser = argparse.ArgumentParser(description="JENNIFER MCP Server for Qwen")
    parser.add_argument("--http", action="store_true", help="HTTP(SSE) 모드로 실행")
    parser.add_argument("--bind", help="HTTP 바인드 주소")
    parser.add_argument("--port", type=int, help="HTTP 포트")
    args = parser.parse_args()

    if args.http:
        host = args.bind or J.CFG.get("mcp_host", "127.0.0.1")
        port = args.port or J.CFG.get("mcp_port", 8791)
        print(f"Starting HTTP Server on http://{host}:{port}/sse")
        if SDK_MAJOR == 1:
            mcp.run_http_server(host=host, port=port)
        else:
            mcp.run(transport="sse")
    else:
        print("Starting stdio Server...", file=sys.stderr)
        mcp.run()

if __name__ == "__main__":
    main()
