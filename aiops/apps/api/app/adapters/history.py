import os
from typing import Any
import httpx

class HistoryAdapterError(Exception):
    pass

def records_from_json(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = None
        for key in ("items", "records", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                rows = value
                break
            if isinstance(value, dict):
                for nested in ("items", "records"):
                    if isinstance(value.get(nested), list):
                        rows = value[nested]
                        break
                if rows is not None:
                    break
        if rows is None:
            raise HistoryAdapterError("응답 스키마 불일치: 배열 또는 items/records/data 배열이 필요합니다.")
    else:
        raise HistoryAdapterError("응답 형식 오류: JSON 배열/객체가 아닙니다.")
    if not all(isinstance(r, dict) for r in rows):
        raise HistoryAdapterError("응답 스키마 불일치: 각 레코드는 객체여야 합니다.")
    return rows

def normalize_history(kind: str, row: dict) -> dict:
    id_keys = ("incident_id", "id", "key") if kind == "incident" else ("event_id", "id", "key")
    ident = next((row.get(k) for k in id_keys if row.get(k) not in (None, "")), None)
    institution = next((row.get(k) for k in ("institution_name", "institution", "org_name") if row.get(k) not in (None, "")), None)
    title = next((row.get(k) for k in ("title", "subject", "summary_title") if row.get(k) not in (None, "")), None)
    occurred = next((row.get(k) for k in ("occurred_at", "created_at", "event_time", "timestamp") if row.get(k) not in (None, "")), None)
    if ident is None or institution is None or title is None:
        raise HistoryAdapterError(f"{kind} 필수 필드 누락: ID={id_keys}, 기관명(institution_name/institution/org_name), 제목(title/subject/summary_title)")
    return {"kind":kind,"id":str(ident),"institution_name":str(institution),"title":str(title),"occurred_at":str(occurred) if occurred else None,"source_payload":row}

class HistoryApiAdapter:
    def __init__(self, kind: str):
        self.kind = kind
        self.url = os.getenv("HISTORY_INCIDENTS_URL" if kind == "incident" else "HISTORY_EVENTS_URL", "").strip()
        specific = os.getenv("HISTORY_INCIDENTS_TOKEN" if kind == "incident" else "HISTORY_EVENTS_TOKEN", "").strip()
        self.token = specific or os.getenv("HISTORY_API_TOKEN", "").strip()
        self.timeout = float(os.getenv("HISTORY_API_TIMEOUT", "15"))
    @property
    def configured(self): return bool(self.url)
    async def fetch(self):
        if not self.configured: return []
        headers = {"Accept":"application/json"}
        if self.token: headers["Authorization"] = f"Bearer {self.token}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                response = await client.get(self.url, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            raise HistoryAdapterError(f"{self.kind} API 요청 실패({type(exc).__name__})") from exc
        return [normalize_history(self.kind, row) for row in records_from_json(payload)]
