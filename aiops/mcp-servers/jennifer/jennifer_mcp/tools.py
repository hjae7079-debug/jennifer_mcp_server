"""MCP 도구 로직 (mcp 패키지와 분리해 단위 테스트 가능).

설계 4.2 실측 제약을 코드로 강제합니다.
- dbmetrics: 지표 1개만 (2개면 서버 500)
- status/*: 분 단위 정시, sort_by_metrics=responseTime 금지
- transaction/time: 구간 60초 이하, 결과 건수 제한 (원시 트랜잭션 대량 수집 금지)
- 서버 3대는 각각 격리: 한 서버가 응답 없으면 '조회 불가(서버명, 사유)'로 표시하고 나머지는 진행
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from .client import JenniferClient
from .timeutil import MINUTE_MS, align_minute_range, check_max_window, to_epoch_ms

BAD_SORT_METRICS = frozenset({"responsetime"})
_STATUS_KIND = re.compile(r"^[A-Za-z][A-Za-z0-9_\-/]{0,60}$")


class Tools:
    def __init__(self, client: JenniferClient):
        self.c = client
        self.s = client.settings
        self.p = client.settings.params

    # ---------- 공통 ----------
    def _ep(self, key: str) -> str:
        if key not in self.s.endpoints:
            raise ValueError(f"endpoints.json 에 '{key}' 경로가 없습니다")
        return self.s.endpoints[key]

    def _targets(self, server: str) -> list[str]:
        if not server or server == "all":
            return list(self.s.servers)
        return [server]

    def _fanout(self, server: str, fn) -> dict:
        targets = self._targets(server)
        if len(targets) == 1:
            return {"results": [fn(targets[0])]}
        with ThreadPoolExecutor(max_workers=len(targets)) as ex:
            return {"results": list(ex.map(fn, targets))}

    # ---------- 도구 ----------
    def servers(self) -> dict:
        return {
            "enabled": self.s.enabled,
            "servers": [{"name": c.name, "label": c.label, "url": c.url,
                         "token_configured": bool(c.token), "timeout_s": c.timeout}
                        for c in self.s.servers.values()],
            "note": "토큰 값은 표시하지 않습니다. enabled=false 이면 모든 조회가 비활성입니다.",
        }

    def domains(self, server: str = "all") -> dict:
        return self._fanout(server, lambda n: self.c.get(n, self._ep("domains")))

    def instances(self, server: str, domain_id: int) -> dict:
        return self.c.get(server, self._ep("instances"), {self.p["domain_id"]: int(domain_id)})

    def metric_catalog(self, server: str) -> dict:
        return self.c.get(server, self._ep("metrics"), max_items=0)

    def dbmetrics_instance(self, server: str, domain_id: int, instance_id: int, metric: str,
                           start: str, end: str) -> dict:
        metric = _single_metric(metric)
        s, e = align_minute_range(start, end)
        return self.c.get(server, self._ep("dbmetrics_instance"), {
            self.p["domain_id"]: int(domain_id), self.p["instance_id"]: int(instance_id),
            self.p["metrics"]: metric, self.p["start_time"]: s, self.p["end_time"]: e})

    def dbmetrics_domain(self, server: str, domain_id: int, metric: str, start: str, end: str) -> dict:
        metric = _single_metric(metric)
        s, e = align_minute_range(start, end)
        return self.c.get(server, self._ep("dbmetrics_domain"), {
            self.p["domain_id"]: int(domain_id), self.p["metrics"]: metric,
            self.p["start_time"]: s, self.p["end_time"]: e})

    def realtime_instance(self, server: str, domain_id: int) -> dict:
        # realtime/instance 는 4~5초 걸리므로 업무에 연결된 인스턴스 조회에만 사용 (5분 전수 호출 금지)
        return self.c.get(server, self._ep("realtime_instance"), {self.p["domain_id"]: int(domain_id)})

    def status(self, server: str, kind: str, domain_id: int, start: str, end: str,
               sort_by_metrics: str = "", limit: int = 50) -> dict:
        if not _STATUS_KIND.match(kind or "") or ".." in kind:
            raise ValueError("kind 는 status/ 아래 하위 경로 이름입니다 (예: service, sql, external)")
        if sort_by_metrics and sort_by_metrics.strip().lower() in BAD_SORT_METRICS:
            raise ValueError("sort_by_metrics=responseTime 은 서버 500 — /api/metrics 에 있는 지표 이름만 사용")
        s, e = align_minute_range(start, end)
        params: dict[str, Any] = {self.p["domain_id"]: int(domain_id),
                                  self.p["start_time"]: s, self.p["end_time"]: e}
        if sort_by_metrics:
            params["sort_by_metrics"] = sort_by_metrics.strip()
        return self.c.get(server, f"/api/status/{kind.strip('/')}", params, max_items=max(1, min(limit, 500)))

    def transaction_sample(self, server: str, domain_id: int, start: str, end: str, limit: int = 20) -> dict:
        s = to_epoch_ms(start)
        e = to_epoch_ms(end)
        check_max_window(s, e, MINUTE_MS)
        return self.c.get(server, self._ep("transaction_time"), {
            self.p["domain_id"]: int(domain_id), self.p["start_time"]: s, self.p["end_time"]: e},
            max_items=max(1, min(limit, 100)))

    def transaction_txid(self, server: str, domain_id: int, txid: str, end: str) -> dict:
        # 실측: txid 조회에도 endTime 필요. instanceOid 는 서버 버그로 0 → 인스턴스는 instanceId 로 식별
        return self.c.get(server, self._ep("transaction_txid"), {
            self.p["domain_id"]: int(domain_id), self.p["txid"]: str(txid),
            self.p["end_time"]: to_epoch_ms(end)})

    def get(self, server: str, path: str, params_json: str = "{}") -> dict:
        """허용 목록(endpoints.json allowlist) 안의 GET 경로만 호출하는 범용 도구."""
        try:
            params = json.loads(params_json or "{}")
        except json.JSONDecodeError as e:
            raise ValueError(f"params_json 이 JSON 객체가 아님: {e}") from e
        if not isinstance(params, dict):
            raise ValueError("params_json 은 JSON 객체여야 합니다")
        return self.c.get(server, path, params)


def _single_metric(metric: str) -> str:
    m = (metric or "").strip()
    if not m:
        raise ValueError("metric 이 비어 있음")
    if "," in m or " " in m:
        raise ValueError("dbmetrics 는 지표 1개만 받습니다 (2개 이상이면 서버 500). 지표마다 따로 호출하세요")
    return m
