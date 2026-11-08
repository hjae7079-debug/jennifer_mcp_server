"""JENNIFER Open API 클라이언트 (Python 표준 라이브러리만 사용, GET 전용).

설계 근거 (AI-Ops 총정리본 v4.0 4.2절, 2026-11-01 호출 정책):
  - 인증: Authorization: Bearer <토큰>. 쿼리 스트링 토큰은 접근 로그에 남으므로 금지 (params 에 token 이 있으면 거부)
  - 차단: GET 외 모든 메서드, /api-v2/manage/*, /restapi/*, 사용자 목록 /api/auth/userlist*
    → 이 모듈에는 GET 말고 요청을 만드는 코드가 없고, 경로는 check_path() 를 반드시 통과해야 한다 (tests/test_guard.py)
  - 조회 전용 토큰을 받을 수 없어 관리 권한 토큰을 쓰므로, 모든 호출을 logs/calls_YYYYMMDD.jsonl 에 남긴다 (토큰 값은 기록 안 함)
  - 서버 3대(인터넷·행정·대민)마다 토큰·타임아웃을 분리하고, 실패한 서버는 잠시 건너뛴다 (D-10 장애 격리)
  - clientIp·clientId 는 개인정보 → 응답에서 지운 뒤에만 도구·로그·샘플로 넘긴다
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from datetime import datetime

ALLOWED_PREFIXES = ("/api/", "/api-v2/")
# 소문자로 비교. 접두어 일치면 차단 ('/api/auth/userlist' 는 userlistAll 같은 변형도 막힘)
DENY_PREFIXES = ("/api-v2/manage", "/restapi", "/api/auth/userlist")
DENY_PARAMS = ("token", "access_token", "accesstoken", "api_key", "apikey")
_PATH_RE = re.compile(r"^/[A-Za-z0-9_\-/.{}]*$")


class JenniferError(Exception):
    """조회 실패 (서버명·사유를 담아 도구 결과의 '조회 불가'로 보여 줌)."""


class BlockedError(JenniferError):
    """호출 정책 위반 — 서버로 보내지 않음."""


# ---------------------------------------------------------------- 호출 정책
def check_path(path: str) -> str:
    """허용 경로면 정규화된 경로를 돌려주고, 아니면 BlockedError. 서버에 보내기 전에 항상 거친다."""
    if not isinstance(path, str) or not path:
        raise BlockedError("경로가 비어 있음")
    if any(c in path for c in "?#%\\") or any(ord(c) < 33 for c in path):
        raise BlockedError("경로에 쓸 수 없는 문자 (?, #, %%, \\, 공백·제어문자): %r" % path)
    if not _PATH_RE.match(path) or "//" in path or "/../" in path + "/" or "/./" in path + "/":
        raise BlockedError("허용되지 않는 경로 형식: %r" % path)
    low = path.lower()
    if not low.startswith(ALLOWED_PREFIXES):
        raise BlockedError("허용 접두어(/api/, /api-v2/)가 아님: %s" % path)
    for d in DENY_PREFIXES:
        if low == d or low.startswith(d):
            raise BlockedError("차단 경로 (호출 정책): %s" % path)
    if "{" in path or "}" in path:
        raise BlockedError("채워지지 않은 경로 변수: %s" % path)
    return path


def check_params(params: dict | None) -> dict:
    out = {}
    for k, v in (params or {}).items():
        if v is None or v == "":
            continue
        if not isinstance(k, str) or not re.fullmatch(r"[A-Za-z0-9_.\-\[\]]{1,64}", k):
            raise BlockedError("허용되지 않는 파라미터 이름: %r" % (k,))
        if k.lower() in DENY_PARAMS:
            raise BlockedError("토큰은 쿼리 스트링으로 보내지 않음 (Authorization 헤더만): %s" % k)
        if isinstance(v, bool):
            v = "true" if v else "false"
        if isinstance(v, (list, tuple)):
            v = ",".join(str(x) for x in v)
        if not isinstance(v, (str, int, float)):
            raise BlockedError("파라미터 값은 문자열·숫자만: %s" % k)
        out[k] = str(v)
    return out


def strip_fields(obj, drop):
    """응답에서 개인정보 필드(clientIp 등)를 재귀적으로 제거. drop 은 소문자 집합."""
    if isinstance(obj, dict):
        return {k: strip_fields(v, drop) for k, v in obj.items() if str(k).lower() not in drop}
    if isinstance(obj, list):
        return [strip_fields(x, drop) for x in obj]
    return obj


# ---------------------------------------------------------------- 호출 빈도
class RateLimiter:
    """모든 서버를 합친 1분 호출 상한 (넘으면 기다림, 최대 wait 초)."""

    def __init__(self, per_min=120):
        self.per_min = per_min
        self._t = deque()
        self._lock = threading.Lock()

    def acquire(self, wait=60.0):
        deadline = time.time() + wait
        while True:
            with self._lock:
                now = time.time()
                while self._t and now - self._t[0] > 60:
                    self._t.popleft()
                if len(self._t) < self.per_min:
                    self._t.append(now)
                    return
                left = 60 - (now - self._t[0])
            if time.time() + left > deadline:
                raise JenniferError("1분 호출 상한(%d회) 도달" % self.per_min)
            time.sleep(min(max(left, 0.1), 1.0))

    def status(self):
        with self._lock:
            now = time.time()
            return {"calls_last_min": sum(1 for x in self._t if now - x <= 60), "max_calls_per_min": self.per_min}


# ---------------------------------------------------------------- 서버 하나
class JenniferServer:
    def __init__(self, key, url, token, timeout=15, min_interval=0.3, cooldown=30, drop=(), log_fn=None,
                 limiter=None):
        self.key = key
        self.base = url.rstrip("/")
        self.token = token or ""
        self.timeout = timeout
        self.min_interval = min_interval
        self.cooldown = cooldown
        self.drop = {x.lower() for x in drop}
        self.log_fn = log_fn
        self.limiter = limiter
        self._lock = threading.Lock()      # 서버당 동시 1건 (Jennifer 뷰서버 부하 보호)
        self._last = 0.0
        self.last_fail = 0.0
        self.last_error = ""
        # 프록시 환경변수(HTTP_PROXY)가 있어도 뷰서버는 직접 연결
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def get(self, path, params=None, timeout=None):
        path = check_path(path)
        q = check_params(params)
        if not self.token:
            raise JenniferError("%s: 토큰 미설정 (python server.py --set-jennifer-token %s)" % (self.key, self.key))
        if self.last_fail and time.time() - self.last_fail < self.cooldown:
            raise JenniferError("%s: 최근 실패로 %d초간 건너뜀 (%s)" % (
                self.key, int(self.cooldown - (time.time() - self.last_fail)), self.last_error))
        url = self.base + path + ("?" + urllib.parse.urlencode(q) if q else "")
        req = urllib.request.Request(url, method="GET", headers={
            "Authorization": "Bearer " + self.token, "Accept": "application/json"})
        if req.get_method() != "GET":  # 방어: 어떤 경우에도 GET 외 전송 금지
            raise BlockedError("GET 외 메서드")
        if self.limiter:
            self.limiter.acquire()
        rec = {"server": self.key, "path": path, "params": q}
        with self._lock:
            gap = time.time() - self._last
            if gap < self.min_interval:
                time.sleep(self.min_interval - gap)
            t0 = time.monotonic()
            try:
                with self._opener.open(req, timeout=timeout or self.timeout) as resp:
                    raw = resp.read()
                    rec.update(status=resp.status, bytes=len(raw))
            except urllib.error.HTTPError as e:
                body = e.read()[:300].decode("utf-8", "replace") if e.fp else ""
                rec.update(status=e.code, error=body[:200])
                # 4xx·5xx 는 서버는 살아 있음 → 격리하지 않음
                raise JenniferError("%s: HTTP %d %s %s" % (self.key, e.code, e.reason, body[:200].strip()))
            except Exception as e:  # noqa: BLE001 - 타임아웃·연결 거부 → 격리
                rec.update(status=0, error="%s: %s" % (type(e).__name__, e))
                self.last_fail, self.last_error = time.time(), "%s: %s" % (type(e).__name__, e)
                raise JenniferError("%s: 연결 실패 (%s: %s)" % (self.key, type(e).__name__, e))
            finally:
                self._last = time.time()
                rec["ms"] = int((time.monotonic() - t0) * 1000)
                if self.log_fn:
                    self.log_fn(rec)
        self.last_fail, self.last_error = 0.0, ""
        try:
            data = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise JenniferError("%s: 응답이 JSON 이 아님 (%d bytes)" % (self.key, len(raw)))
        return strip_fields(data, self.drop)


# ---------------------------------------------------------------- 호출 기록
class CallLog:
    def __init__(self, log_dir):
        self.dir = log_dir
        self._lock = threading.Lock()

    def __call__(self, rec):
        try:
            os.makedirs(self.dir, exist_ok=True)
            rec = dict({"t": datetime.now().isoformat(timespec="seconds"), "method": "GET"}, **rec)
            with self._lock, open(os.path.join(self.dir, "calls_%s.jsonl" % datetime.now().strftime("%Y%m%d")),
                                  "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass
