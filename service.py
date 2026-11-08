"""Jennifer MCP HTTP 서비스 계층 (nsims_mcp service.py 와 같은 구조): 토큰 인증, 접속 IP 제한, /healthz, 접속 로그, uvicorn 실행.

MCP 프로토콜(Streamable HTTP) 자체는 mcp SDK 가 처리하고, 여기서는 그 앞단(ASGI 미들웨어)만 담당한다.
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import os
import secrets
import sys
import threading
import time
from datetime import datetime

import jennifer_tools as T

TOKENS_FILE = os.path.join(T.BASE, "tokens.json")
LOOPBACK = ("127.0.0.1", "localhost", "::1")
_log_lock = threading.Lock()


def http_cfg():
    c = {"bind": "127.0.0.1", "port": 8791, "path": "/mcp", "require_token": True, "stateless": True,
         "allow_ips": [], "allowed_hosts": [], "ssl_certfile": "", "ssl_keyfile": ""}
    c.update(T.CFG.get("http", {}))
    return c


# ---------------------------------------------------------------- 토큰
def load_tokens():
    try:
        with open(TOKENS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_tokens(tokens):
    tmp = TOKENS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=1)
    os.replace(tmp, TOKENS_FILE)
    if os.name == "posix":
        os.chmod(TOKENS_FILE, 0o600)


def manage_token(gen=None, revoke=None):
    tokens = load_tokens()
    if revoke:
        if tokens.pop(revoke, None) is None:
            sys.exit("없는 토큰 이름: %s" % revoke)
        _save_tokens(tokens)
        print("폐기됨: %s (실행 중인 서비스에도 즉시 적용)" % revoke)
        return
    if not __import__("re").fullmatch(r"[A-Za-z0-9_.-]{2,40}", gen):
        sys.exit("토큰 이름은 영문/숫자/_.- 2~40자")
    if gen in tokens:
        print("주의: '%s' 토큰을 새로 발급합니다 (이전 토큰은 무효)" % gen)
    tokens[gen] = "jennifer_" + secrets.token_urlsafe(32)
    _save_tokens(tokens)
    print("토큰 발급: %s\n\n  %s\n" % (gen, tokens[gen]))
    print("이 값은 다시 표시되지 않습니다 (tokens.json 에만 저장). Hermes 쪽 예:")
    print("  ~/.hermes/.env       JENNIFER_MCP_TOKEN=%s" % tokens[gen])
    print('  config.yaml headers  Authorization: "Bearer ${env:JENNIFER_MCP_TOKEN}"')


# ---------------------------------------------------------------- 접근 제어 미들웨어
class Guard:
    """순수 ASGI 미들웨어 (스트리밍 응답을 건드리지 않음)."""

    def __init__(self, app, cfg, info):
        self.app = app
        self.cfg = cfg
        self.info = info
        self.nets = [ipaddress.ip_network(x, strict=False) for x in cfg["allow_ips"]]
        self._tok_mtime = None
        self._tokens = {}

    def _current_tokens(self):
        # tokens.json 이 바뀌면 다시 읽음 → 발급/폐기가 재시작 없이 적용
        try:
            m = os.path.getmtime(TOKENS_FILE)
        except OSError:
            m = None
        if m != self._tok_mtime:
            self._tok_mtime, self._tokens = m, load_tokens()
        return self._tokens

    def _ip_ok(self, ip):
        if not self.nets:
            return True
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in n for n in self.nets)

    def _who(self, scope):
        auth = ""
        for k, v in scope.get("headers", []):
            if k == b"authorization":
                auth = v.decode("latin-1")
                break
        if not auth.lower().startswith("bearer "):
            return None
        given = auth[7:].strip().encode()
        for name, tok in self._current_tokens().items():
            if hmac.compare_digest(given, tok.encode()):
                return name
        return None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":  # lifespan 등은 그대로 (SDK 세션 매니저 기동에 필요)
            return await self.app(scope, receive, send)
        ip = (scope.get("client") or ("?", 0))[0]
        path, method = scope.get("path", ""), scope.get("method", "")

        if not self._ip_ok(ip):
            _access(ip, "-", method, path, 403)
            return await _json(send, 403, {"error": "접속 허용 IP 아님"})
        if path == "/healthz":   # 상태 확인은 접속 기록에 안 남김 (관리자 웹이 10초마다 → 하루 8천 줄이 기록을 덮었음, 2026-10-22)
            body = dict(self.info, ok=True, rate=T.LIMITER.status())
            return await _json(send, 200, body)

        who = "-"
        if self.cfg["require_token"]:
            who = self._who(scope)
            if not who:
                _access(ip, "?", method, path, 401)
                return await _json(send, 401, {"error": "인증 필요 (Authorization: Bearer <토큰>)"},
                                   [(b"www-authenticate", b'Bearer realm="jennifer"')])

        # 요청 본문을 먼저 읽어 JSON-RPC method·도구 이름(tools/call:triage 등)을 접속 기록에 남김 — 사용 통계용 (2026-10-22, 관리자 웹 2차)
        op, receive2 = "", receive
        if method == "POST":
            chunks = []
            while True:
                msg = await receive()
                if msg["type"] == "http.request":
                    chunks.append(msg.get("body") or b"")
                    if not msg.get("more_body"):
                        break
                else:   # http.disconnect — 본문을 다 받기 전에 끊김
                    _access(ip, who, method, path, 0, "disconnect")
                    return
            body = b"".join(chunks)
            op = _rpc_op(body)
            state = {"sent": False}

            async def receive2():
                if not state["sent"]:
                    state["sent"] = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

        status = {}
        t0 = time.monotonic()

        async def send_wrap(msg):
            if msg["type"] == "http.response.start":
                status["code"] = msg["status"]
            await send(msg)

        try:
            await self.app(scope, receive2, send_wrap)
        finally:
            _access(ip, who, method, path, status.get("code", 0), op, int((time.monotonic() - t0) * 1000))


def _rpc_op(body):
    """JSON-RPC 본문 → 'tools/call:도구이름' 또는 method 이름 (묶음 요청은 쉼표로). 본문이 JSON 이 아니면 빈 문자열"""
    try:
        m = json.loads(body.decode("utf-8", "replace")) if body else None
    except ValueError:
        return ""
    ops = []
    for x in (m if isinstance(m, list) else [m]):
        if not isinstance(x, dict):
            continue
        meth = str(x.get("method") or "")
        if meth == "tools/call":
            ops.append("tools/call:" + str((x.get("params") or {}).get("name") or "?")[:40])
        elif meth:
            ops.append(meth[:40])
    return ",".join(ops)[:160]


async def _json(send, code, obj, extra_headers=()):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    await send({"type": "http.response.start", "status": code,
                "headers": [(b"content-type", b"application/json; charset=utf-8"),
                            (b"content-length", str(len(body)).encode())] + list(extra_headers)})
    await send({"type": "http.response.body", "body": body})


def _access(ip, who, method, path, code, op="", ms=0):
    """접속 기록 한 줄: 시각 · IP · 토큰 이름 · 'METHOD 경로' · 응답 코드 · JSON-RPC 동작(tools/call:도구) · 소요 ms  (2026-10-22 부터 7열, 그 전 5열)"""
    try:
        os.makedirs(T.LOG_DIR, exist_ok=True)
        line = "%s\t%s\t%s\t%s %s\t%s\t%s\t%s\n" % (T.now().isoformat(timespec="seconds"), ip, who, method, path, code, op, ms)
        with _log_lock, open(os.path.join(T.LOG_DIR, "access_%s.log" % T.now().strftime("%Y%m%d")),
                             "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


# ---------------------------------------------------------------- 실행
def run_http(mcp, sdk_major, version, bind=None, port=None):
    import uvicorn
    from mcp.server.transport_security import TransportSecuritySettings

    cfg = http_cfg()
    bind = bind or cfg["bind"]
    port = int(port or cfg["port"])
    path = cfg["path"]
    loopback = bind in LOOPBACK

    if not cfg["require_token"] and not loopback:
        sys.exit("[거부] 토큰 없이(require_token=false) 외부 주소(%s)로 열 수 없습니다." % bind)
    if cfg["require_token"] and not load_tokens():
        sys.exit("[중지] 발급된 토큰이 없습니다. 먼저: python server.py --gen-token hermes")

    # DNS 리바인딩 방지: 허용할 Host 헤더 목록. 루프백이면 기본 localhost, 아니면 config 의 allowed_hosts
    hosts = cfg["allowed_hosts"] or (["127.0.0.1:*", "localhost:*", "[::1]:*"] if loopback else [])
    ts = TransportSecuritySettings(enable_dns_rebinding_protection=bool(hosts), allowed_hosts=hosts,
                                   allowed_origins=[])
    if sdk_major >= 2:
        app = mcp.streamable_http_app(streamable_http_path=path, transport_security=ts, host=bind,
                                      stateless_http=cfg["stateless"])
    else:
        mcp.settings.host, mcp.settings.port = bind, port
        mcp.settings.streamable_http_path = path
        mcp.settings.transport_security = ts
        mcp.settings.stateless_http = cfg["stateless"]
        app = mcp.streamable_http_app()

    info = {"name": "jennifer_apm", "version": version, "mcp_sdk": sdk_major, "mock": bool(T.CFG.get("force_mock")),
            "endpoint": path}
    app = Guard(app, cfg, info)

    ssl = {}
    if cfg["ssl_certfile"]:
        ssl = {"ssl_certfile": cfg["ssl_certfile"], "ssl_keyfile": cfg["ssl_keyfile"] or None}
    scheme = "https" if ssl else "http"
    print("jennifer MCP v%s  %s://%s:%d%s" % (version, scheme, bind, port, path), file=sys.stderr)
    print("  인증: %s | 허용 IP: %s | Host 검사: %s | Jennifer: %s%s"
          % ("토큰 %d개" % len(load_tokens()) if cfg["require_token"] else "없음(루프백 전용)",
             ", ".join(cfg["allow_ips"]) or "제한 없음", ", ".join(hosts) or "끔",
             ", ".join("%s=%s" % (k, s.base) for k, s in T.SERVERS.items()), "  [가짜 데이터]" if info["mock"] else ""),
          file=sys.stderr)
    print("  세션: %s" % ("stateless (서버 재시작해도 클라이언트 재연결 불필요)" if cfg["stateless"] else "stateful"),
          file=sys.stderr)
    print("  상태: %s://%s:%d/healthz   로그: %s" % (scheme, bind, port, T.LOG_DIR), file=sys.stderr)
    uvicorn.run(app, host=bind, port=port, log_level="warning", proxy_headers=False, server_header=False, **ssl)
