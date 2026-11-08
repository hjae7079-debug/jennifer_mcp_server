"""JENNIFER Open API 읽기 전용 클라이언트 (표준 라이브러리만 사용).

- GET 만 구현합니다. 다른 메서드를 보내는 코드 경로가 없습니다.
- 모든 호출은 guard.check_call 을 통과해야 합니다.
- 인증은 Authorization: Bearer <토큰> 헤더로만 보냅니다.
- 서버마다 타임아웃·토큰·호출 간격을 분리합니다 (D-10).
- 모든 호출(차단 포함)을 JSONL 호출 로그로 남깁니다 (설계 11.2: 쓰기 메서드 미발생 점검용).
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from . import guard
from .config import ServerConf, Settings
from .sanitize import limit_items, strip_pii


class CallLogger:
    def __init__(self, log_dir: Path):
        self.log_dir = log_dir
        self._lock = threading.Lock()

    def write(self, record: dict) -> None:
        record = {"ts": datetime.now(timezone.utc).isoformat(), **record}
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            path = self.log_dir / f"jennifer-calls-{datetime.now().strftime('%Y%m%d')}.jsonl"
            line = json.dumps(record, ensure_ascii=False)
            with self._lock, path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass  # 로그 실패로 조회를 막지 않음


class JenniferClient:
    def __init__(self, settings: Settings, logger: CallLogger | None = None):
        self.settings = settings
        self.logger = logger or CallLogger(settings.log_dir)
        self._locks: dict[str, threading.Lock] = {n: threading.Lock() for n in settings.servers}
        self._last: dict[str, float] = {n: 0.0 for n in settings.servers}
        # 프록시 환경변수를 무시합니다 (폐쇄망 내부 호출)
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def server(self, name: str) -> ServerConf:
        if name not in self.settings.servers:
            raise KeyError(f"알 수 없는 서버: {name} (가능: {', '.join(self.settings.servers)})")
        return self.settings.servers[name]

    def unavailable(self, server: str, reason: str) -> dict:
        label = self.settings.servers[server].label if server in self.settings.servers else server
        return {"server": server, "available": False, "reason": f"조회 불가({label}, {reason})"}

    def get(self, server: str, path: str, params: Mapping[str, Any] | None = None,
            *, use_allowlist: bool = True, max_items: int | None = None) -> dict:
        """결과는 항상 dict: 성공이면 {server, available: True, data, ...}, 실패면 available False."""
        params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        if not self.settings.enabled:
            return self.unavailable(server, "어댑터 비활성(JENNIFER_MCP_ENABLED=false)")
        try:
            conf = self.server(server)
        except KeyError as e:
            return {"server": server, "available": False, "reason": str(e)}
        try:
            norm = guard.check_call("GET", path, params,
                                    self.settings.allowlist if use_allowlist else None)
        except guard.BlockedCall as e:
            self.logger.write({"server": server, "method": "GET", "path": path,
                               "params": _loggable(params), "result": "blocked", "reason": str(e)})
            return {"server": server, "available": False, "blocked": True, "reason": str(e)}
        if not conf.token:
            return self.unavailable(server, f"토큰 미설정({conf.token_env})")

        self._throttle(server, conf.min_interval)
        query = urllib.parse.urlencode(params, doseq=True)
        url = f"{conf.url}{norm}" + (f"?{query}" if query else "")
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {conf.token}")
        req.add_header("Accept", "application/json")
        t0 = time.monotonic()
        status, size, err = None, 0, None
        try:
            with self._opener.open(req, timeout=conf.timeout) as resp:
                status = resp.status
                body = resp.read(self.settings.max_bytes + 1)
                size = len(body)
                if size > self.settings.max_bytes:
                    err = f"응답이 너무 큼(>{self.settings.max_bytes} bytes) — 조회 구간·조건을 줄이세요"
                    return self.unavailable(server, err)
                data = json.loads(body.decode("utf-8")) if body else None
        except urllib.error.HTTPError as e:
            status = e.code
            err = f"HTTP {e.code}"
            return self.unavailable(server, err)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            err = f"연결 실패: {type(e).__name__}"
            return self.unavailable(server, err)
        except (ValueError, UnicodeDecodeError):
            err = "JSON이 아닌 응답"
            return self.unavailable(server, err)
        finally:
            self.logger.write({"server": server, "method": "GET", "path": norm,
                               "params": _loggable(params), "status": status, "bytes": size,
                               "ms": int((time.monotonic() - t0) * 1000),
                               "result": "error" if err else "ok", "error": err})

        data = strip_pii(data)
        data, trunc = limit_items(data, self.settings.max_items if max_items is None else max_items)
        out = {"server": server, "available": True, "path": norm, "data": data}
        if trunc:
            out["truncation"] = trunc
        return out

    def _throttle(self, server: str, min_interval: float) -> None:
        with self._locks[server]:
            wait = min_interval - (time.monotonic() - self._last[server])
            if wait > 0:
                time.sleep(wait)
            self._last[server] = time.monotonic()


def _loggable(params: Mapping[str, Any]) -> dict:
    return {k: (v if not isinstance(v, (bytes, bytearray)) else "<bytes>") for k, v in params.items()}
