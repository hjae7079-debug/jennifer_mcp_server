"""호출 정책(쓰기 차단) 시험 — v4.0 "쓰기 차단 규칙은 단위 테스트로 검증".

  cd jennifer_mcp_server && python -m unittest discover -s tests -v
뷰서버 불필요 (가짜 뷰서버를 띄워 실제 HTTP 로 확인).
"""
from __future__ import annotations

import ast
import os
import sys
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.environ["JENNIFER_MOCK"] = "1"

import jennifer_client as jc  # noqa: E402
import jennifer_tools as T  # noqa: E402
import mock_jennifer as M  # noqa: E402


class TestPathPolicy(unittest.TestCase):
    def test_allowed(self):
        for p in ("/api/domain", "/api/instance", "/api/dbmetrics/instance", "/api/status/application",
                  "/api/transaction/txid", "/api-v2/deploy", "/api/auth/check"):
            self.assertEqual(jc.check_path(p), p)

    def test_denied_prefixes(self):
        for p in ("/api-v2/manage", "/api-v2/manage/agent", "/API-V2/MANAGE/x", "/restapi", "/restapi/a/b",
                  "/RestApi/x", "/api/auth/userlist", "/api/auth/userlistAll", "/api/auth/USERLIST/1"):
            with self.assertRaises(jc.BlockedError, msg=p):
                jc.check_path(p)

    def test_denied_shapes(self):
        for p in ("", "api/domain", "/", "/other/x", "/api/../api-v2/manage", "/api/./x", "//api/domain",
                  "/api/domain?x=1", "/api/domain#a", "/api/%2e%2e/restapi", "/api\\x", "/api/ domain",
                  "http://evil/api/domain", "/api/status/{kind}", "/api/\nx", "/api/x/.."):
            with self.assertRaises(jc.BlockedError, msg=repr(p)):
                jc.check_path(p)

    def test_token_never_in_query(self):
        for k in ("token", "TOKEN", "access_token", "apiKey"):
            with self.assertRaises(jc.BlockedError):
                jc.check_params({k: "x"})
        with self.assertRaises(jc.BlockedError):
            jc.check_params({"a b": 1})
        self.assertEqual(jc.check_params({"domain_id": 1, "x": None, "y": "", "f": True, "l": [1, 2]}),
                         {"domain_id": "1", "f": "true", "l": "1,2"})

    def test_client_source_only_get(self):
        """jennifer_client.py 에 GET 외 메서드로 요청을 만드는 코드가 없음 (정적 검사)."""
        with open(os.path.join(BASE, "jennifer_client.py"), encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "method":
                self.assertIsInstance(node.value, ast.Constant)
                self.assertEqual(node.value.value, "GET")
            if isinstance(node, ast.keyword) and node.arg == "data":
                self.fail("요청 본문(data=)을 만드는 코드가 있음")
        for word in ("urlopen(", "http.client", "requests."):
            self.assertNotIn(word, src)


class TestOverHttp(unittest.TestCase):
    def setUp(self):
        M.WRITE_ATTEMPTS.clear()
        self.srv = T.SERVERS["internet"]

    def test_blocked_never_reaches_server(self):
        before = len(M.REQUESTS)
        for p in ("/api-v2/manage/agent", "/restapi/x", "/api/auth/userlist"):
            with self.assertRaises(jc.BlockedError):
                self.srv.get(p)
        with self.assertRaises(jc.BlockedError):
            self.srv.get("/api/domain", {"token": "leak"})
        self.assertEqual(len(M.REQUESTS), before, "차단된 요청이 서버에 도착함")

    def test_api_get_tool_blocks(self):
        for p in ("/api-v2/manage/agent", "/api/auth/userlist", "/api/../restapi/x"):
            with self.assertRaises(jc.BlockedError):
                T.api_get("internet", p, "")
        with self.assertRaises(jc.BlockedError):
            T.api_get("internet", "/api/domain", '{"token": "x"}')

    def test_all_tools_no_write(self):
        T.servers_status()
        T.domain_list()
        T.instance_list()
        T.find_instance("vm0001")
        T.metric_names("internet")
        T.realtime_instance("internet", 1000, 1)
        T.instance_metrics("internet", 1000, 1, "heap_used,gc_time", 30)
        T.status_summary("internet", 1000, "sql", 10)
        T.transactions("internet", 1000, seconds=60)
        T.transaction_profile("internet", 1000, "7000000000000000000", "1762579200000")
        self.assertEqual(M.WRITE_ATTEMPTS, [])

    def test_auth_header_not_query(self):
        before = len(M.REQUESTS)
        T.SERVERS["internet"].get("/api/domain")
        self.assertNotIn("token", M.REQUESTS[before].lower())

    def test_strip_fields(self):
        d = {"a": 1, "clientIp": "x", "n": [{"CLIENTID": 2, "b": {"client_ip": 3, "c": 4}}]}
        self.assertEqual(jc.strip_fields(d, {"clientip", "clientid", "client_ip"}), {"a": 1, "n": [{"b": {"c": 4}}]})


if __name__ == "__main__":
    unittest.main()
