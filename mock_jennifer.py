"""가짜 Jennifer 뷰서버 — 뷰서버에 못 붙는 곳(인터넷망 PC)에서 MCP·Hermes·AIOps 연동 흐름을 시험하는 용도.

config.local.json {"force_mock": true} 또는 JENNIFER_MOCK=1 이면 jennifer_tools 가 이것을 띄워 세 서버를 모두 여기로 돌린다.
- 응답 형식은 **가정** (실서버 형식 미확인). 도구 호출 흐름·호출 정책·개인정보 제거 시험용이지 결과 해석용이 아님
- 실측 제약을 흉내 냄: dbmetrics 지표 2개 → 500, status/* 시작·끝이 분 정시 아님 → 500, sort_by_metrics=responseTime → 500,
  transaction/time 구간 60초 초과 → 500, 토큰 틀림 → 401, GET 외 메서드 → 405 (그리고 WRITE_ATTEMPTS 에 기록)
- IP 는 문서용 예약 대역(192.0.2.x, 198.51.100.x) → 실제 IP 와 섞이지 않음
단독 실행: python mock_jennifer.py [포트]  (기본 127.0.0.1:17900, 토큰 mock-token)
"""
from __future__ import annotations

import json
import random
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "mock-token"
WRITE_ATTEMPTS: list = []   # 시험에서 "쓰기 요청이 서버에 한 번도 도착하지 않았다"를 확인
REQUESTS: list = []
DOMAINS = [{"domainId": 1000 + i, "domainName": n, "instanceCount": 3}
           for i, n in enumerate(["포털", "민원", "인증", "통계"])]
METRICS = [{"name": n, "description": d, "unit": u} for n, d, u in [
    ("heap_used", "힙 사용량", "MB"), ("gc_time", "GC 시간", "ms"), ("cpu", "CPU 사용률", "%"),
    ("active_service", "액티브 서비스 수", "개"), ("db_pool_active", "DB 풀 사용 수", "개"),
    ("service_rate", "초당 처리 건수", "tps"), ("error_count", "오류 건수", "건"),
    ("averageResponseTime", "평균 응답시간", "ms"), ("elapseSum", "응답시간 합", "ms")]]


def _instances(did):
    base = (did - 1000) * 3
    return [{"instanceId": base + j + 1, "instanceName": "was%02d_%d" % (base + j + 1, did),
             "ip": "192.0.2.%d" % (10 + base + j), "hostName": "vm%08d" % (12345 + base + j),
             "status": "STOPPED" if (base + j) % 7 == 6 else "LIVE", "type": "JAVA"} for j in range(3)]


def _q(qs, k, default=None):
    v = qs.get(k)
    return v[0] if v else default


def _num(qs, k, default=0):
    try:
        return int(_q(qs, k, default))
    except (TypeError, ValueError):
        return default


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 조용히
        pass

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write(self):
        WRITE_ATTEMPTS.append((self.command, self.path))
        self._send(405, {"error": "mock: write method"})

    do_POST = do_PUT = do_DELETE = do_PATCH = _write

    def do_GET(self):  # noqa: C901 - 경로별 가짜 응답
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        REQUESTS.append(self.path)
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self._send(401, {"error": "unauthorized"})
        p = u.path
        if p == "/api/domain":
            return self._send(200, {"result": DOMAINS})
        if p == "/api/instance":
            did = _num(qs, "domain_id")
            if did not in [d["domainId"] for d in DOMAINS]:
                return self._send(200, {"result": []})
            return self._send(200, {"result": _instances(did)})
        if p == "/api/metrics":
            return self._send(200, {"result": METRICS})
        if p == "/api/realtime/instance":
            did = _num(qs, "domain_id")
            iid = _num(qs, "instance_id")
            rows = [dict(i, activeService=random.randint(0, 30), cpu=round(random.uniform(5, 80), 1),
                         heap_used=random.randint(300, 1800), clientIp="198.51.100.7")
                    for i in _instances(did) if not iid or i["instanceId"] == iid]
            return self._send(200, {"result": rows})
        if p == "/api/dbmetrics/instance":
            m = _q(qs, "metrics", "")
            if "," in m:
                return self._send(500, {"error": "Internal Server Error"})
            s, e = _num(qs, "start_time"), _num(qs, "end_time")
            step = 60_000
            n = max(1, min(240, (e - s) // step))
            rise = m == "heap_used"
            rows = [{"time": s + k * step, "domainId": _num(qs, "domain_id"), "instanceId": _num(qs, "instance_id"),
                     "value": round((500 + k * 8 if rise else 100) + random.uniform(-20, 20), 1)} for k in range(n)]
            return self._send(200, {"result": rows})
        if p.startswith("/api/status/"):
            s, e = _num(qs, "start_time"), _num(qs, "end_time")
            if s % 60_000 or e % 60_000:
                return self._send(500, {"error": "start/end must be on the minute"})
            if _q(qs, "sort_by_metrics") == "responseTime":
                return self._send(500, {"error": "Internal Server Error"})
            kind = p.rsplit("/", 1)[-1]
            rows = [{"name": "/%s/item%02d.do" % (kind, k), "callCount": random.randint(10, 5000),
                     "averageResponseTime": random.randint(20, 4000), "errorCount": random.randint(0, 20),
                     "elapseSum": random.randint(1000, 900000)} for k in range(_num(qs, "count", 10) or 10)]
            return self._send(200, {"result": rows})
        if p == "/api/transaction/time":
            s, e = _num(qs, "start_time"), _num(qs, "end_time")
            if e - s > 60_000:
                return self._send(500, {"error": "range over 60s"})
            did = _num(qs, "domain_id")
            rows = []
            for k in range(200):
                inst = random.choice(_instances(did) or [{"instanceId": 0, "instanceName": "-"}])
                rt = int(random.expovariate(1 / 300))
                rows.append({"txid": str(7_000_000_000_000_000 + k), "startTime": e - rt - 1000, "endTime": e - 1000,
                             "responseTime": rt, "application": "/board/view%d.do" % (k % 9),
                             "instanceId": inst["instanceId"], "instanceOid": 0, "sqlTime": rt // 3,
                             "errorType": "SQLException" if k % 37 == 0 else "",
                             "clientIp": "198.51.100.%d" % (k % 250), "clientId": "user%04d" % k})
            return self._send(200, {"result": rows})
        if p == "/api/transaction/txid":
            if not _q(qs, "time"):
                return self._send(500, {"error": "time(endTime) required"})
            return self._send(200, {"result": [
                {"seq": 0, "type": "START", "message": "/board/view1.do", "elapsed": 0, "gap": 0},
                {"seq": 1, "type": "SQL", "message": "SELECT * FROM board WHERE id = ?", "elapsed": 820, "gap": 5},
                {"seq": 2, "type": "EXTERNAL_CALL", "message": "http://192.0.2.200/api", "elapsed": 1500, "gap": 12},
                {"seq": 3, "type": "END", "elapsed": 0, "gap": 3, "instanceOid": 0, "clientIp": "198.51.100.9"}]})
        if p == "/api/thrown":
            return self._send(200, {"result": [{"time": "Tue Oct 14 10:00:00 KST 2026", "clientId": "x"}]})
        return self._send(404, {"error": "not found: " + p})


def serve_background(port=0):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 17900
    print("가짜 Jennifer 뷰서버 http://127.0.0.1:%d (토큰 %s)" % (port, TOKEN))
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
