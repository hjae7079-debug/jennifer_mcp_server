"""가짜 제니퍼 서버로 클라이언트·도구 동작 확인."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from jennifer_mcp.client import CallLogger, JenniferClient
from jennifer_mcp.config import DEFAULT_PARAMS, ServerConf, Settings
from jennifer_mcp.tools import Tools

SEEN = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        SEEN.append({"method": "GET", "path": self.path, "auth": self.headers.get("Authorization")})
        if self.path.startswith("/api/slow"):
            import time
            time.sleep(2)
        body = json.dumps({"result": [{"name": f"r{i}", "clientIp": "10.0.0.1"} for i in range(5)]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        SEEN.append({"method": "POST", "path": self.path})
        self.send_response(500)
        self.end_headers()


@pytest.fixture(scope="module")
def fake():
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def tools(fake, tmp_path, monkeypatch):
    monkeypatch.setenv("T_A", "secret-a")
    monkeypatch.setenv("T_B", "")
    servers = {
        "a": ServerConf("a", "A서버", fake, "T_A", timeout=1, min_interval=0),
        "b": ServerConf("b", "B서버", fake, "T_B", timeout=1, min_interval=0),
        "dead": ServerConf("dead", "죽은서버", "http://127.0.0.1:9", "T_A", timeout=1, min_interval=0),
    }
    endpoints = {"domains": "/api/domain", "metrics": "/api/metrics", "transaction_time": "/api/transaction/time",
                 "dbmetrics_instance": "/api/dbmetrics/instance"}
    st = Settings(servers=servers, endpoints=endpoints,
                  allowlist=["/api/domain", "/api/metrics", "/api/transaction/time", "/api/dbmetrics/*",
                             "/api/status/*", "/api/slow"],
                  params=dict(DEFAULT_PARAMS), enabled=True, log_dir=tmp_path, max_items=3)
    SEEN.clear()
    return Tools(JenniferClient(st, CallLogger(tmp_path))), tmp_path


def test_bearer_header_and_no_token_in_query(tools):
    t, logdir = tools
    res = t.metric_catalog("a")
    assert res["available"] is True
    assert SEEN[-1]["auth"] == "Bearer secret-a"
    assert "secret-a" not in SEEN[-1]["path"]
    log = "".join(p.read_text() for p in Path(logdir).glob("*.jsonl"))
    assert "secret-a" not in log and '"method": "GET"' in log


def test_pii_removed_and_truncated(tools):
    t, _ = tools
    res = t.c.get("a", "/api/domain")
    assert all("clientIp" not in r for r in res["data"]["result"])
    assert res["truncation"]["total"] == 5 and len(res["data"]["result"]) == 3


def test_isolation_fanout(tools):
    t, _ = tools
    out = t.domains("all")["results"]
    by = {r["server"]: r for r in out}
    assert by["a"]["available"] is True
    assert by["b"]["available"] is False and "토큰 미설정" in by["b"]["reason"]
    assert by["dead"]["available"] is False and "죽은서버" in by["dead"]["reason"]


def test_timeout_reported(tools):
    t, _ = tools
    res = t.c.get("a", "/api/slow")
    assert res["available"] is False and "조회 불가(A서버" in res["reason"]


def test_blocked_never_sent(tools):
    t, logdir = tools
    res = t.get("a", "/api-v2/manage/agent")
    assert res.get("blocked") is True
    res = t.get("a", "/api/realtime/instance")  # 허용 목록 밖
    assert res.get("blocked") is True
    assert SEEN == []
    assert "blocked" in "".join(p.read_text() for p in Path(logdir).glob("*.jsonl"))
    assert all(s["method"] == "GET" for s in SEEN)


def test_disabled(tools):
    t, _ = tools
    t.s.enabled = False
    res = t.metric_catalog("a")
    assert res["available"] is False and "비활성" in res["reason"] and SEEN == []


def test_tool_constraints(tools):
    t, _ = tools
    with pytest.raises(ValueError):
        t.dbmetrics_instance("a", 1, 2, "tps,cpu", "2026-10-14 10:00", "2026-10-14 10:05")
    with pytest.raises(ValueError):
        t.transaction_sample("a", 1, "2026-10-14 10:00", "2026-10-14 10:02")
    with pytest.raises(ValueError):
        t.status("a", "service", 1, "2026-10-14 10:00", "2026-10-14 10:05", sort_by_metrics="responseTime")
    with pytest.raises(ValueError):
        t.status("a", "../restapi", 1, "2026-10-14 10:00", "2026-10-14 10:05")
    res = t.dbmetrics_instance("a", 1, 2, "tps", "2026-10-14 10:00:30", "2026-10-14 10:04:10")
    assert res["available"] is True
    assert "start_time=1791939600000" in SEEN[-1]["path"] and "end_time=1791939900000" in SEEN[-1]["path"]
