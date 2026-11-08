"""호출 차단 규칙 (설계 4.2 호출 정책).

- GET 외 메서드는 전부 차단합니다.
- /api-v2/manage/*, /restapi/*, /api/auth/userlist* 는 차단합니다.
- 경로는 /api/ 또는 /api-v2/ 로 시작하는 상대 경로만 허용합니다.
- 토큰은 쿼리 스트링으로 보내지 않습니다(접근 로그에 남음).

이 모듈은 외부 의존성이 없고, tests/test_guard.py 로 검증합니다.
"""
from __future__ import annotations

import re
from typing import Iterable, Mapping

ALLOWED_METHODS = frozenset({"GET"})
ALLOWED_PREFIXES = ("/api/", "/api-v2/")
BLOCKED_PREFIXES = (
    "/api-v2/manage/",
    "/api-v2/manage",
    "/restapi/",
    "/restapi",
    "/api/auth/userlist",
)
# 쿼리 파라미터로 보내면 안 되는 키 (토큰은 Authorization 헤더로만)
BLOCKED_PARAM_KEYS = frozenset({"token", "access_token", "api_key", "apikey"})

_SAFE_PATH = re.compile(r"^/[A-Za-z0-9_\-./{}]*$")


class BlockedCall(Exception):
    """차단 규칙에 걸린 호출."""


def check_call(method: str, path: str, params: Mapping[str, object] | None = None,
               allowlist: Iterable[str] | None = None) -> str:
    """호출이 허용되면 정규화된 경로를 반환하고, 아니면 BlockedCall 을 던집니다.

    allowlist 가 주어지면 그 목록에 있는 경로(또는 '*'로 끝나는 접두사)만 허용합니다.
    """
    m = (method or "").upper()
    if m not in ALLOWED_METHODS:
        raise BlockedCall(f"허용되지 않은 메서드: {m or '(없음)'} — GET만 허용")
    if not isinstance(path, str) or not path:
        raise BlockedCall("경로가 비어 있음")
    if "://" in path or path.startswith("//"):
        raise BlockedCall("절대 URL은 허용하지 않음 — 서버 기준 상대 경로만")
    if "?" in path or "#" in path:
        raise BlockedCall("경로에 쿼리 문자열을 넣지 말고 params로 전달")
    if ".." in path or "\\" in path or "%" in path:
        raise BlockedCall("경로 조작 문자(.., \\, %)는 허용하지 않음")
    if not _SAFE_PATH.match(path):
        raise BlockedCall("경로에 허용되지 않은 문자가 있음")
    norm = re.sub(r"/{2,}", "/", path)
    if norm != "/" and norm.endswith("/"):
        norm = norm.rstrip("/")
    low = norm.lower()
    for b in BLOCKED_PREFIXES:
        if low == b.rstrip("/") or low.startswith(b if b.endswith("/") else b):
            raise BlockedCall(f"차단 경로: {norm}")
    if not any(low.startswith(p) for p in ALLOWED_PREFIXES):
        raise BlockedCall(f"/api/ 또는 /api-v2/ 이외 경로: {norm}")
    for k in (params or {}):
        if str(k).lower() in BLOCKED_PARAM_KEYS:
            raise BlockedCall(f"쿼리 파라미터 '{k}' 금지 — 토큰은 Authorization 헤더로만 전달")
    if allowlist is not None:
        if not _in_allowlist(norm, allowlist):
            raise BlockedCall(f"허용 목록(endpoints.json)에 없는 경로: {norm}")
    return norm


def _in_allowlist(path: str, allowlist: Iterable[str]) -> bool:
    for entry in allowlist:
        e = entry.rstrip("/")
        if e.endswith("*"):
            if path.startswith(e[:-1]):
                return True
        elif path == e:
            return True
    return False
