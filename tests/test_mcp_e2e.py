"""MCP 프로토콜 끝까지 시험 (stdio + Streamable HTTP, 가짜 뷰서버). mcp SDK 가 설치된 venv 에서:
  .venv/bin/python -m unittest tests.test_mcp_e2e -v
임시 폴더에 복사해서 실행 → 이 폴더의 tokens.json·logs 를 건드리지 않음.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ("server.py", "service.py", "jennifer_tools.py", "jennifer_client.py", "mock_jennifer.py", "test_client.py",
         "config.json", "endpoints.json")

try:
    import mcp  # noqa: F401
    HAVE_MCP = True
except ImportError:
    HAVE_MCP = False


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@unittest.skipUnless(HAVE_MCP, "mcp SDK 없음")
class TestE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="jennifer_e2e_")
        for f in FILES:
            shutil.copy(os.path.join(BASE, f), cls.dir)
        cls.port = _free_port()
        with open(os.path.join(cls.dir, "config.local.json"), "w") as f:
            json.dump({"force_mock": True, "http": {"bind": "127.0.0.1", "port": cls.port, "path": "/mcp",
                                                    "require_token": True, "stateless": True, "allow_ips": [],
                                                    "allowed_hosts": [], "ssl_certfile": "", "ssl_keyfile": ""}}, f)
        out = subprocess.run([sys.executable, "server.py", "--gen-token", "e2e"], cwd=cls.dir, capture_output=True,
                             text=True, check=True).stdout
        with open(os.path.join(cls.dir, "tokens.json"), encoding="utf-8") as f:
            cls.token = json.load(f)["e2e"]
        assert cls.token in out
        cls.proc = subprocess.Popen([sys.executable, "server.py", "--http", "--port", str(cls.port)], cwd=cls.dir,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for _ in range(50):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % cls.port, timeout=1).read()
                break
            except OSError:
                time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)
        cls.proc.stderr.close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def _client(self, *args, token=None):
        cmd = [sys.executable, "test_client.py", "--url", "http://127.0.0.1:%d/mcp" % self.port,
               "--token", token or self.token] + list(args)
        return subprocess.run(cmd, cwd=self.dir, capture_output=True, text=True, timeout=60)

    def test_healthz(self):
        h = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/healthz" % self.port).read())
        self.assertTrue(h["ok"] and h["mock"])
        self.assertEqual(h["endpoint"], "/mcp")

    def test_auth_required(self):
        req = urllib.request.Request("http://127.0.0.1:%d/mcp" % self.port, data=b"{}", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 401)

    def test_http_tools(self):
        r = self._client()
        self.assertEqual(r.returncode, 0, r.stderr)
        for t in ("servers_status", "find_instance", "instance_metrics", "transactions", "api_get"):
            self.assertIn("■ " + t, r.stdout)
        r = self._client("find_instance", '{"keyword": "vm00012345"}')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"total": 3', r.stdout)
        r = self._client("api_get", '{"server": "internet", "path": "/api-v2/manage/x"}')
        self.assertIn("차단 경로", r.stdout)
        name = [f for f in os.listdir(os.path.join(self.dir, "logs")) if f.startswith("access_")][0]
        with open(os.path.join(self.dir, "logs", name), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("tools/call:find_instance", log)

    def test_stdio(self):
        r = subprocess.run([sys.executable, "test_client.py", "servers_status"], cwd=self.dir, capture_output=True,
                           text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"mock": true', r.stdout)


if __name__ == "__main__":
    unittest.main()
