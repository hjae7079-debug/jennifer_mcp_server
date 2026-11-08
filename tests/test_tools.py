"""도구 로직 시험 (가짜 뷰서버):  python -m unittest discover -s tests -v"""
from __future__ import annotations

import json
import os
import sys
import unittest
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
os.environ["JENNIFER_MOCK"] = "1"

import jennifer_client as jc  # noqa: E402
import jennifer_tools as T  # noqa: E402
import survey as S  # noqa: E402


class TestTime(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(T.parse_time("2026-11-08 14:30"), datetime(2026, 11, 8, 14, 30))
        self.assertEqual(T.parse_time("2026-11-08 14:30:15"), datetime(2026, 11, 8, 14, 30, 15))
        self.assertEqual(T.parse_time(str(T.to_ms(datetime(2026, 11, 8, 1, 2, 3)))), datetime(2026, 11, 8, 1, 2, 3))
        self.assertLessEqual(T.parse_time("23:59"), datetime.now())
        with self.assertRaises(T.ToolError):
            T.parse_time("어제")

    def test_minute_window(self):
        s, e = T.minute_window(10, "2026-11-08 14:30:45")
        self.assertEqual((s.second, e.second), (0, 0))
        self.assertEqual(T.to_ms(e) % 60000, 0)
        self.assertEqual((e - s).total_seconds(), 600)
        with self.assertRaises(T.ToolError):
            T.minute_window(0)
        with self.assertRaises(T.ToolError):
            T.minute_window(99999)

    def test_java_date(self):
        self.assertEqual(T.java_date_ms("Tue Oct 14 10:00:00 KST 2026"), T.to_ms(datetime(2026, 10, 14, 10, 0)))
        self.assertIsNone(T.java_date_ms("2026-10-14"))
        r = T.api_get("internet", "/api/thrown", "")
        self.assertIsInstance(r["data"]["result"][0]["time"], int)
        self.assertNotIn("clientId", json.dumps(r))


class TestTools(unittest.TestCase):
    def test_status(self):
        r = T.servers_status()
        self.assertTrue(all(s["ok"] for s in r["servers"]), r)
        self.assertTrue(r["mock"])
        self.assertIn("instance_metrics", r["endpoints_unverified"])

    def test_server_alias(self):
        self.assertEqual(T.server_keys("행정"), ["admin"])
        self.assertEqual(T.server_keys("대민 업무"), ["public"])
        self.assertEqual(len(T.server_keys("")), 3)
        with self.assertRaises(T.ToolError):
            T.server_keys("없는서버")
        with self.assertRaises(T.ToolError):
            T.one_server("")

    def test_instances(self):
        r = T.instance_list("internet")
        self.assertEqual(r["total"], 12)
        self.assertEqual({"server", "domain_id", "instance_id", "name", "ip", "host", "state", "type"},
                         set(r["instances"][0]))
        f = T.find_instance("vm00012346")
        self.assertEqual(f["total"], 3)  # 세 서버 모두 같은 가짜 데이터
        self.assertEqual(T.instance_list("", 0, "", "stopped")["total"], 3)
        with self.assertRaises(T.ToolError):
            T.find_instance("v")

    def test_metrics_one_per_call(self):
        r = T.instance_metrics("internet", 1000, 1, "heap_used, cpu", minutes=60)
        self.assertEqual(r["failed"], [])
        self.assertGreater(r["metrics"]["heap_used"]["stats"]["value"]["trend_pct"], 20)  # 가짜 힙은 상승
        with self.assertRaises(T.ToolError):
            T.instance_metrics("internet", 1000, 1, "a,b,c,d,e,f,g")

    def test_status_summary(self):
        r = T.status_summary("admin", 1000, "application", 10, "2026-11-08 14:30:45", "elapseSum", 5)
        self.assertEqual(len(r["rows"]), 5)
        with self.assertRaises(jc.JenniferError):   # 실측 제약을 가짜 서버가 흉내 → 오류가 그대로 전달
            T.status_summary("admin", 1000, "application", 10, "", "responseTime")
        with self.assertRaises(T.ToolError):
            T.status_summary("admin", 1000, "없는종류")

    def test_transactions(self):
        r = T.transactions("public", 1001, seconds=60, top=5)
        self.assertEqual(r["count"], 200)
        self.assertGreater(r["errors"], 0)
        self.assertEqual(len(r["slowest"]), 5)
        txt = json.dumps(r, ensure_ascii=False)
        self.assertNotIn("clientIp", txt)
        self.assertNotIn("clientId", txt)
        self.assertNotIn("198.51.100", txt)
        with self.assertRaises(T.ToolError):
            T.transactions("public", 1001, seconds=61)
        p = T.transaction_profile("public", 1001, r["slowest"][0]["txid"], str(r["slowest"][0]["endTime"]))
        self.assertEqual(p["count"], 4)
        self.assertNotIn("clientIp", json.dumps(p))

    def test_isolation(self):
        """한 서버가 죽어도 나머지 결과는 나오고 사유가 표시됨 (D-10)."""
        good = T.SERVERS["admin"]
        T._cache.clear()   # 도메인 목록 캐시가 있으면 서버에 안 가므로
        T.SERVERS["admin"] = jc.JenniferServer("admin", "http://127.0.0.1:9", "x", timeout=1, cooldown=30)
        try:
            r = T.domain_list()
            self.assertEqual(set(r["servers"]), {"internet", "public"})
            self.assertEqual(r["unavailable"][0]["server"], "admin")
            r2 = T.domain_list()   # 두 번째는 연결 시도 없이 바로 건너뜀
            self.assertIn("건너뜀", r2["unavailable"][0]["reason"])
        finally:
            T.SERVERS["admin"] = good

    def test_dumps_limit(self):
        big = {"rows": [{"x": "a" * 500} for _ in range(200)], "n": 1}
        s = T.dumps(big)
        self.assertLessEqual(len(s), T.CFG["max_output_chars"])
        self.assertIn("_truncated", json.loads(s))

    def test_catalog(self):
        old = T.SPEC_DIR
        T.SPEC_DIR = os.path.join(BASE, "tests", "fixtures")
        try:
            r = T.api_catalog()
            paths = {e["path"]: e["policy"] for e in r["endpoints"]}
            self.assertNotIn("/api/event", paths)          # POST 전용은 목록에 없음
            self.assertEqual(paths["/api/domain"], "allowed")
            self.assertTrue(paths["/api/auth/userlist"].startswith("blocked"))
            self.assertTrue(paths["/api-v2/manage/agent"].startswith("blocked"))
            self.assertEqual(T.api_catalog("지표")["count"], 2)
        finally:
            T.SPEC_DIR = old


class TestSurvey(unittest.TestCase):
    def test_plan(self):
        old = T.SPEC_DIR
        T.SPEC_DIR = os.path.join(BASE, "tests", "fixtures")
        try:
            ctx = S.build_context("internet")
            self.assertEqual(ctx["errors"], [])
            items = {i["path"]: i for i in S.plan("internet", ctx, T.load_spec_endpoints(), {"kind": "sql"})}
        finally:
            T.SPEC_DIR = old
        self.assertEqual(items["/api/instance"]["params"], {"domain_id": 1000})
        self.assertEqual(items["/api/status/{kind}"]["call"], "/api/status/sql")
        self.assertIn("mystery", items["/api/thrown"]["skip"])
        self.assertTrue(items["/restapi/legacy"]["skip"].startswith("blocked"))
        dm = items["/api/dbmetrics/instance"]["params"]
        self.assertEqual(dm["end_time"] - dm["start_time"], 300000)

    def test_mask(self):
        m = S.Masker()
        out = m({"a": "10.148.222.57:7900", "b": ["10.148.222.57", "1.2.3.4 and 10.0.0.1"], "c": "v1.2.3"})
        self.assertEqual(out["a"], "198.18.0.1:7900")
        self.assertEqual(out["b"][0], "198.18.0.1")
        self.assertNotIn("1.2.3.4", json.dumps(out))
        self.assertEqual(out["c"], "v1.2.3")


if __name__ == "__main__":
    unittest.main()
