"""MCP 서버 단독 시험 (Hermes 없이).

  HTTP 서비스 (운영 방식 — 서비스가 떠 있어야 함):
    python test_client.py --url http://127.0.0.1:8791/mcp --token <토큰>
    python test_client.py --url http://127.0.0.1:8791/mcp --token <토큰> find_instance '{"keyword":"vm000"}'
    (--token 대신 환경변수 JENNIFER_MCP_TOKEN 도 됨)

  stdio (server.py 를 자식 프로세스로 띄움):
    python test_client.py
    python test_client.py servers_status
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

if hasattr(sys.stdout, "reconfigure"):  # Windows 콘솔 한글 깨짐 방지
    sys.stdout.reconfigure(encoding="utf-8")


def show_tools(tools):
    for t in tools:
        props = (t.get("inputSchema") or {}).get("properties", {})
        print("\n■ %s(%s)\n  %s" % (t["name"], ", ".join(props),
                                   (t.get("description") or "").strip().replace("\n", "\n  ")))


def show_result(content):
    for c in content:
        if c.get("type") == "text":
            try:
                print(json.dumps(json.loads(c["text"]), ensure_ascii=False, indent=1))
            except ValueError:
                print(c["text"])


def run_stdio(tool, args):
    """표준 라이브러리만으로 JSON-RPC 를 직접 주고받음 (SDK 버전과 무관하게 프로토콜 자체를 시험)."""
    proc = subprocess.Popen([sys.executable, os.path.join(HERE, "server.py")], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=sys.stderr, cwd=HERE)
    seq = [0]

    def send(method, params=None, notify=False):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            seq[0] += 1
            msg["id"] = seq[0]
        proc.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        proc.stdin.flush()
        if notify:
            return None
        while True:
            line = proc.stdout.readline()
            if not line:
                raise SystemExit("서버가 종료됨 (위 stderr 확인)")
            resp = json.loads(line)
            if resp.get("id") == msg["id"]:
                return resp

    info = send("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                               "clientInfo": {"name": "test_client", "version": "1"}}).get("result", {})
    print("서버:", info.get("serverInfo"), "프로토콜:", info.get("protocolVersion"))
    send("notifications/initialized", notify=True)
    if not tool:
        show_tools(send("tools/list", {})["result"]["tools"])
    else:
        resp = send("tools/call", {"name": tool, "arguments": args})
        print("오류:", resp["error"]) if "error" in resp else show_result(resp["result"].get("content", []))
    proc.stdin.close()
    proc.wait(timeout=10)


def run_http(url, token, tool, args):
    """공식 mcp SDK 클라이언트로 Streamable HTTP 접속 (실제 MCP 클라이언트와 같은 경로)."""
    import asyncio
    from mcp import ClientSession
    try:
        from mcp.client.streamable_http import streamablehttp_client as _client  # v1
        opener = lambda: _client(url, headers={"Authorization": "Bearer " + token}, timeout=60,  # noqa: E731
                                 sse_read_timeout=600)
    except ImportError:  # v2: 헤더는 HTTP 클라이언트 객체로 전달 (v2 SDK 는 httpx2 사용)
        try:
            import httpx2 as httpx
        except ImportError:
            import httpx
        from mcp.client.streamable_http import streamable_http_client as _client
        opener = lambda: _client(url, http_client=httpx.AsyncClient(  # noqa: E731
            headers={"Authorization": "Bearer " + token}, timeout=httpx.Timeout(60, read=600)))

    async def main():
        async with opener() as streams:
            async with ClientSession(streams[0], streams[1]) as s:
                init = await s.initialize()
                si = getattr(init, "server_info", None) or init.serverInfo  # v2 는 snake_case
                pv = getattr(init, "protocol_version", None) or getattr(init, "protocolVersion", "")
                print("서버:", si.name, si.version, "프로토콜:", pv)
                if not tool:
                    show_tools([t.model_dump(by_alias=True) for t in (await s.list_tools()).tools])
                else:
                    res = await s.call_tool(tool, args)
                    show_result([c.model_dump() for c in res.content])

    asyncio.run(main())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="HTTP 서비스 주소 (없으면 stdio)")
    ap.add_argument("--token", default=os.environ.get("JENNIFER_MCP_TOKEN", ""))
    ap.add_argument("tool", nargs="?")
    ap.add_argument("args", nargs="?", default="{}")
    a = ap.parse_args()
    args = json.loads(a.args)
    if a.url:
        if not a.token:
            sys.exit("--token 또는 JENNIFER_MCP_TOKEN 필요")
        run_http(a.url, a.token, a.tool, args)
    else:
        run_stdio(a.tool, args)


if __name__ == "__main__":
    main()
