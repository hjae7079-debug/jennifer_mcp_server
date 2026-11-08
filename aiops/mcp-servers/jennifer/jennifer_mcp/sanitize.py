"""개인정보 제거와 응답 크기 제한.

설계 4.2: clientIp, clientId 는 저장하지 않고 MCP 응답에서도 제외합니다.
"""
from __future__ import annotations

from typing import Any

# 대소문자·구분자 무시하고 비교합니다 (clientIp, client_ip, CLIENT-IP ...)
PII_KEYS = frozenset({"clientip", "clientid"})


def _norm(key: str) -> str:
    return "".join(ch for ch in str(key).lower() if ch.isalnum())


def strip_pii(obj: Any) -> Any:
    """dict/list 를 재귀적으로 돌며 PII 키를 제거한 사본을 반환합니다."""
    if isinstance(obj, dict):
        return {k: strip_pii(v) for k, v in obj.items() if _norm(k) not in PII_KEYS}
    if isinstance(obj, list):
        return [strip_pii(v) for v in obj]
    return obj


def limit_items(obj: Any, max_items: int) -> tuple[Any, dict | None]:
    """최상위(또는 흔한 래퍼 키 아래) 배열이 너무 길면 잘라 내고 잘림 정보를 돌려줍니다.

    LLM 컨텍스트 보호용입니다. 원시 트랜잭션 대량 수집 금지(설계 4.2)와 같은 취지입니다.
    """
    if max_items <= 0:
        return obj, None
    if isinstance(obj, list):
        if len(obj) > max_items:
            return obj[:max_items], {"truncated": True, "total": len(obj), "returned": max_items}
        return obj, None
    if isinstance(obj, dict):
        for key in ("result", "data", "list", "items", "records"):
            v = obj.get(key)
            if isinstance(v, list) and len(v) > max_items:
                out = dict(obj)
                out[key] = v[:max_items]
                return out, {"truncated": True, "field": key, "total": len(v), "returned": max_items}
    return obj, None
