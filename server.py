import argparse
import anyio
from mcp.server.fastmcp import FastMCP
import jennifer_tools as J

# FastMCP 서버 생성
mcp = FastMCP(
    "jennifer_apm",
    instructions="JENNIFER APM 성능 데이터를 조회하여 시스템 장애 및 지연 원인을 분석하는 도구입니다. CPU, Memory, Active Service, XLog 데이터를 활용하여 종합적으로 판단하세요."
)

@mcp.tool()
async def active_service() -> str:
    """[JENNIFER APM] 현재 활성화된 액티브 서비스 수를 확인하여 시스템 병목 여부를 1차 판단합니다."""
    return await anyio.to_thread.run_sync(J.get_active_service)

@mcp.tool()
async def system_resource(stime: str, etime: str) -> str:
    """[JENNIFER APM] 특정 시간대의 CPU 및 Heap Memory 사용량 데이터를 조회합니다. (포맷: yyyy-MM-dd HH:mm)"""
    return await anyio.to_thread.run_sync(J.get_system_resource, stime, etime)

@mcp.tool()
async def slow_xlog(stime: str, etime: str, min_ms: int = 3000) -> str:
    """[JENNIFER APM] 특정 시간대에 발생한 느린 트랜잭션(Slow XLog)을 조회하여 지연 원인(SQL, 외부 API 등)을 추적합니다."""
    return await anyio.to_thread.run_sync(J.get_xlog, stime, etime, min_ms)

def main():
    parser = argparse.ArgumentParser(description="JENNIFER MCP Server for Qwen")
    parser.add_argument("--http", action="store_true", help="HTTP(SSE) 모드로 실행")
    args = parser.parse_args()

    if args.http:
        host = J.CFG.get("mcp_host", "127.0.0.1")
        port = J.CFG.get("mcp_port", 8791)
        print(f"Starting HTTP SSE Server on http://{host}:{port}/sse")
        mcp.run_http_server(host=host, port=port)
    else:
        print("Starting stdio Server...")
        mcp.run()

if __name__ == "__main__":
    main()
