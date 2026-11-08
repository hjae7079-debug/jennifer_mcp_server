"""JENNIFER APM 조회 도구 로직 (MCP 비의존 — 단독 테스트 가능).

설계 근거 (AI-Ops 총정리본 v4.0 4.2절, 실측 5.6.3.13 2026-10-14):
  - 도메인 51개, 인스턴스 308개 → 목록은 캐시(cache_seconds)하고 LLM 에는 걸러서 넘김
  - dbmetrics 는 지표 1개만 → 지표마다 호출
  - status/* 시작·끝은 분 정시 → 조회 구간을 분 단위로 맞춤
  - transaction/time 은 구간 60초 이하, 1분 약 7,280건 → 요약 + 상위 소량만
  - dbsearch 등의 시각이 Java Date 문자열 → epoch ms 로 바꿔서 넘김
  - 경로·파라미터 이름은 endpoints.json (실서버 확인 전 가정값, survey.py 로 확인)
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)
import jennifer_client as jc  # noqa: E402

LOG_DIR = os.path.join(BASE, "logs")
SECRETS_FILE = os.path.join(BASE, "secrets.json")
SPEC_DIR = os.path.join(BASE, "spec")


class ToolError(Exception):
    pass


def _load(name, default):
    try:
        with open(os.path.join(BASE, name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def load_config():
    cfg = {"servers": {}, "timezone": "Asia/Seoul", "min_interval_sec": 0.3, "max_calls_per_min": 120,
           "cooldown_sec": 30, "max_window_minutes": 1440, "max_rows": 30, "max_output_chars": 16000,
           "cache_seconds": 600, "log_retention_days": 365,
           "drop_fields": ["clientIp", "clientId", "client_ip", "client_id"]}
    cfg.update(_load("config.json", {}))
    # config.local.json: 이 PC 에만 두는 강제 설정 (배포 zip·git 에 없음). 예) {"force_mock": true}
    cfg.update(_load("config.local.json", {}))
    if os.environ.get("JENNIFER_MOCK") == "1":
        cfg["force_mock"] = True
    return cfg


CFG = load_config()
EP = _load("endpoints.json", {})


def load_secrets():
    """서버별 Jennifer API 토큰. 환경변수 JENNIFER_TOKEN_<서버키 대문자> 가 secrets.json 보다 우선."""
    s = _load("secrets.json", {})
    for k in CFG["servers"]:
        v = os.environ.get("JENNIFER_TOKEN_" + k.upper())
        if v:
            s[k] = v
    return s


def set_secret(key, value):
    if key not in CFG["servers"]:
        raise SystemExit("모르는 서버 키: %s (config.json servers: %s)" % (key, ", ".join(CFG["servers"])))
    s = _load("secrets.json", {})
    s[key] = value
    tmp = SECRETS_FILE + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, SECRETS_FILE)


# ---------------------------------------------------------------- 서버 준비 (가짜 모드 포함)
def _start_mock():
    import mock_jennifer
    port = mock_jennifer.serve_background()
    return "http://127.0.0.1:%d" % port


LIMITER = jc.RateLimiter(CFG["max_calls_per_min"])
CALL_LOG = jc.CallLog(LOG_DIR)
SERVERS: dict[str, jc.JenniferServer] = {}


def _build_servers():
    mock_url = _start_mock() if CFG.get("force_mock") else None
    sec = load_secrets()
    SERVERS.clear()
    for k, v in CFG["servers"].items():
        if not isinstance(v, dict) or k.startswith("_"):
            continue
        SERVERS[k] = jc.JenniferServer(
            k, mock_url or v["url"], "mock-token" if mock_url else sec.get(k, ""),
            timeout=v.get("timeout", 15), min_interval=0 if mock_url else CFG["min_interval_sec"],
            cooldown=CFG["cooldown_sec"], drop=CFG["drop_fields"], log_fn=CALL_LOG, limiter=LIMITER)


_build_servers()


def server_title(k):
    return CFG["servers"].get(k, {}).get("title", k)


def _norm(x):
    return str(x or "").strip().lower().replace(" ", "")


def server_keys(name=""):
    """'인터넷'·'행정'·'admin' → [키]. 비우면 전체."""
    if _norm(name) in ("", "all", "전체"):
        return list(SERVERS)
    n = _norm(name)
    for k in SERVERS:
        v = CFG["servers"][k]
        if n in {k.lower(), _norm(v.get("title"))} | {_norm(a) for a in v.get("aliases", [])}:
            return [k]
    raise ToolError("모르는 서버 '%s'. 쓸 수 있는 서버: %s (비우면 전체)" % (
        name, ", ".join("%s(%s)" % (server_title(k), k) for k in SERVERS)))


def one_server(name):
    keys = server_keys(name)
    if len(keys) != 1:
        raise ToolError("이 도구는 서버를 하나 지정해야 함: %s" % ", ".join(
            "%s(%s)" % (server_title(k), k) for k in SERVERS))
    return keys[0]


def _fan_out(server, fn):
    """서버마다 fn(key) 실행. 한 서버가 실패해도 나머지는 계속 (D-10) → 실패는 unavailable 에 사유와 함께."""
    out, bad = {}, []
    for k in server_keys(server):
        try:
            out[k] = fn(k)
        except (jc.JenniferError, ToolError) as e:
            bad.append({"server": k, "title": server_title(k), "reason": str(e)})
    return out, bad


def cleanup_logs():
    """logs/ 의 calls_*·access_* 중 log_retention_days 보다 오래된 파일 삭제 (0 이하 = 지우지 않음). 서비스 시작 때 한 번."""
    days = int(CFG.get("log_retention_days") or 0)
    if days <= 0:
        return 0
    cut = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    n = 0
    for fn in glob.glob(os.path.join(LOG_DIR, "*_*.*")):
        m = re.match(r"^(calls|access)_(\d{8})\.(jsonl|log)$", os.path.basename(fn))
        if m and m.group(2) < cut:
            try:
                os.remove(fn)
                n += 1
            except OSError:
                pass
    return n


# ---------------------------------------------------------------- 시간
def now():
    return datetime.now()


def to_ms(dt):
    return int(dt.timestamp() * 1000)


def from_ms(ms):
    return datetime.fromtimestamp(int(ms) / 1000).strftime("%Y-%m-%d %H:%M:%S")


def parse_time(s, default=None):
    """'2026-11-08 14:30', '2026-11-08 14:30:15', '14:30', '1430', epoch ms(13자리) → datetime. 비우면 default(없으면 지금)."""
    s = str(s or "").strip()
    if not s:
        return default or now()
    if re.fullmatch(r"\d{13}", s):
        return datetime.fromtimestamp(int(s) / 1000)
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y%m%d%H%M%S", "%Y%m%d%H%M"):
        try:
            return datetime.strptime(s, f)
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2}):?(\d{2})", s)
    if m:
        t = now().replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        return t - timedelta(days=1) if t > now() else t
    raise ToolError("시각 형식 오류: '%s' (예 '2026-11-08 14:30', '14:30', epoch ms)" % s)


def minute_window(minutes, end=""):
    """[시작, 끝] 을 분 정시로 맞춘 구간 (status/* 는 초가 0 이어야 함, 실측). 끝 생략 = 지금을 분 단위로 내림."""
    minutes = int(minutes)
    if minutes < 1 or minutes > CFG["max_window_minutes"]:
        raise ToolError("minutes 는 1~%d" % CFG["max_window_minutes"])
    e = parse_time(end).replace(second=0, microsecond=0)
    s = e - timedelta(minutes=minutes)
    return s, e


# ---------------------------------------------------------------- 응답 다루기
_JAVA_DATE = re.compile(r"^[A-Z][a-z]{2} [A-Z][a-z]{2} \d{1,2} \d{2}:\d{2}:\d{2} [A-Z]{2,5} \d{4}$")
_LIST_KEYS = ("result", "results", "data", "list", "items", "rows", "records", "content")


def java_date_ms(s):
    """'Tue Oct 14 10:00:00 KST 2026' → epoch ms (시간대 이름은 무시하고 서버 시간대로 봄). 아니면 None"""
    if isinstance(s, str) and _JAVA_DATE.match(s):
        p = s.split()
        try:
            return to_ms(datetime.strptime(" ".join(p[1:4] + p[5:]), "%b %d %H:%M:%S %Y"))
        except ValueError:
            return None
    return None


def normalize(obj):
    """Java Date 문자열을 epoch ms 로 (원래 키 옆에 <키>_ms 를 두지 않고 값 자체를 바꿈)."""
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize(x) for x in obj]
    ms = java_date_ms(obj)
    return ms if ms is not None else obj


def rows_of(data):
    """응답에서 행 목록을 찾음 (형식 미확정: 최상위 목록 / result·data·list 등 / 첫 번째 목록 값)."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in _LIST_KEYS:
            if isinstance(data.get(k), list):
                return data[k]
        for v in data.values():
            if isinstance(v, list):
                return v
        for k in _LIST_KEYS:
            if isinstance(data.get(k), dict):
                return rows_of(data[k])
        return [data]
    return []


def _trunc(v, n=300):
    if isinstance(v, str) and len(v) > n:
        return v[:n] + "…(%d자)" % len(v)
    if isinstance(v, list) and len(v) > 20:
        return [_trunc(x, n) for x in v[:20]] + ["…(%d개 중 20개)" % len(v)]
    if isinstance(v, dict):
        return {k: _trunc(x, n) for k, x in v.items()}
    if isinstance(v, list):
        return [_trunc(x, n) for x in v]
    return v


def dumps(obj):
    """LLM 에 넘길 JSON. max_output_chars 를 넘으면 목록을 줄여서라도 유효한 JSON 으로."""
    s = json.dumps(obj, ensure_ascii=False, default=str)
    limit = CFG["max_output_chars"]
    if len(s) <= limit:
        return s
    if isinstance(obj, dict):
        obj = dict(obj)
        for k, v in sorted(obj.items(), key=lambda kv: -len(json.dumps(kv[1], ensure_ascii=False, default=str))):
            if isinstance(v, list) and len(v) > 1:
                keep = max(1, len(v) // 2)
                while keep >= 1:
                    obj[k] = v[:keep]
                    obj["_truncated"] = "%s: %d개 중 %d개만 (출력 제한 %d자)" % (k, len(v), keep, limit)
                    s = json.dumps(obj, ensure_ascii=False, default=str)
                    if len(s) <= limit:
                        return s
                    if keep == 1:
                        break
                    keep //= 2
    return json.dumps({"_truncated": "출력 제한 %d자 초과 (%d자) — 조건을 좁히세요" % (limit, len(s)),
                       "head": s[:limit - 200]}, ensure_ascii=False)


def _get(key, name, path_vars=None, **kw):
    """endpoints.json 의 이름(name)으로 호출. kw 는 도구 내부 파라미터 이름 → 설정의 실제 이름으로 바꿔 보냄."""
    ep = EP.get(name)
    if not ep:
        raise ToolError("endpoints.json 에 '%s' 정의 없음" % name)
    path = ep["path"]
    for pk, pv in (path_vars or {}).items():
        if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", str(pv)):
            raise ToolError("경로 변수 값 오류: %s" % pv)
        path = path.replace("{%s}" % pk, str(pv))
    pmap = ep.get("params", {})
    params = {}
    for k, v in kw.items():
        if v in (None, "", 0) and k != "domain":
            continue
        if k not in pmap:
            raise ToolError("endpoints.json '%s' 에 파라미터 '%s' 매핑 없음" % (name, k))
        params[pmap[k]] = v
    return normalize(SERVERS[key].get(path, params))


# ---------------------------------------------------------------- 캐시 (도메인·인스턴스 목록)
_cache: dict = {}
_cache_lock = threading.Lock()


def _cached(ck, fn):
    with _cache_lock:
        hit = _cache.get(ck)
        if hit and time.time() - hit[0] < CFG["cache_seconds"]:
            return hit[1]
    v = fn()
    with _cache_lock:
        _cache[ck] = (time.time(), v)
    return v


def _pick(row, *names):
    """행에서 이름 후보 중 처음 있는 값 (필드 이름 미확정 대비)."""
    if not isinstance(row, dict):
        return None
    low = {str(k).lower(): v for k, v in row.items()}
    for n in names:
        if n.lower() in low and low[n.lower()] not in (None, ""):
            return low[n.lower()]
    return None


def _domains(key):
    return _cached(("domains", key), lambda: rows_of(_get(key, "domains")))


def _domain_ids(key):
    out = []
    for d in _domains(key):
        v = _pick(d, "domainId", "domain_id", "sid", "id")
        if v is not None:
            out.append(v)
    return out


def _instances(key, domain_id):
    return _cached(("inst", key, domain_id), lambda: rows_of(_get(key, "instances", domain=domain_id)))


# ================================================================ 도구
def servers_status():
    """서버마다 연결·응답 시간·도메인 수 + 설정 상태."""
    out = []
    for k, s in SERVERS.items():
        row = {"server": k, "title": server_title(k), "url": s.base, "token": bool(s.token)}
        t0 = time.monotonic()
        try:
            n = len(rows_of(_get(k, "domains")))
            row.update(ok=True, ms=int((time.monotonic() - t0) * 1000), domains=n)
        except (jc.JenniferError, ToolError) as e:
            row.update(ok=False, reason=str(e))
        out.append(row)
    unverified = sorted(k for k, v in EP.items() if isinstance(v, dict) and not v.get("verified"))
    return {"servers": out, "mock": bool(CFG.get("force_mock")), "rate": LIMITER.status(),
            "endpoints_unverified": unverified,
            "note": "endpoints_unverified = 실서버 응답으로 아직 확인 안 한 경로(endpoints.json). 결과 형식이 다를 수 있음"}


def domain_list(server=""):
    res, bad = _fan_out(server, lambda k: [
        {"domain_id": _pick(d, "domainId", "domain_id", "sid", "id"), "name": _pick(d, "domainName", "name", "shortName"),
         **({"instances": _pick(d, "instanceCount", "count")} if _pick(d, "instanceCount", "count") is not None else {})}
        for d in _domains(k)])
    return {"servers": {k: {"title": server_title(k), "count": len(v), "domains": v} for k, v in res.items()},
            "unavailable": bad}


def _compact_instance(key, did, r):
    return {"server": key, "domain_id": did,
            "instance_id": _pick(r, "instanceId", "instance_id", "oid", "id"),
            "name": _pick(r, "instanceName", "name", "shortName"),
            "ip": _pick(r, "ip", "ipAddress", "hostIp", "address"),
            "host": _pick(r, "hostName", "hostname", "host"),
            "state": _pick(r, "status", "state", "agentStatus"),
            "type": _pick(r, "type", "platform", "agentType")}


def _all_instances(key, domain_id=0):
    dids = [domain_id] if domain_id else _domain_ids(key)
    out = []
    for did in dids:
        out += [_compact_instance(key, did, r) for r in _instances(key, did)]
    return out


def instance_list(server="", domain_id=0, keyword="", state="", limit=50):
    """인스턴스 목록 (이름·IP·호스트로 거르기). domain_id 0 이면 그 서버의 모든 도메인 (캐시 10분)."""
    kw, st = _norm(keyword), _norm(state)
    res, bad = _fan_out(server, lambda k: _all_instances(k, int(domain_id or 0)))
    rows = []
    for k, lst in res.items():
        for r in lst:
            if kw and kw not in _norm(" ".join(str(v) for v in r.values() if v is not None)):
                continue
            if st and st not in _norm(r.get("state")):
                continue
            rows.append({x: y for x, y in r.items() if y is not None})
    limit = max(1, min(int(limit), 300))
    return {"total": len(rows), "shown": min(len(rows), limit), "instances": rows[:limit], "unavailable": bad,
            "hint": "instance_metrics·realtime_instance 에는 server·domain_id·instance_id 를 그대로 넘김"}


def find_instance(keyword):
    """VM 이름·IP·호스트명 일부로 세 서버 전체에서 Jennifer 인스턴스 찾기 (매핑 확인용)."""
    if len(_norm(keyword)) < 2:
        raise ToolError("keyword 는 2자 이상 (IP 일부, 호스트명, 인스턴스 이름)")
    return instance_list("", 0, keyword, "", 100)


def metric_names(server="", keyword=""):
    key = one_server(server or next(iter(SERVERS)))
    data = _cached(("metrics", key), lambda: _get(key, "metric_names"))
    rows = rows_of(data)
    names = []
    for r in rows:
        names.append(r if not isinstance(r, dict) else
                     {x: y for x, y in {"name": _pick(r, "name", "metric", "id", "key"),
                                         "desc": _pick(r, "description", "desc", "label", "title"),
                                         "unit": _pick(r, "unit")}.items() if y is not None} or r)
    if keyword:
        names = [n for n in names if _norm(keyword) in _norm(json.dumps(n, ensure_ascii=False))]
    return {"server": key, "count": len(names), "metrics": names[:300]}


def realtime_instance(server, domain_id, instance_id=0):
    """실시간 인스턴스 상태 (실측 4~5초 걸림 → 필요한 인스턴스만)."""
    key = one_server(server)
    data = _get(key, "realtime_instance", domain=int(domain_id), instance=int(instance_id or 0))
    rows = rows_of(data)
    return {"server": key, "domain_id": domain_id, "count": len(rows),
            "rows": [_trunc(r) for r in rows[:CFG["max_rows"]]]}


def _numeric_series(rows):
    """행 목록 → {필드: [값...]} (시각·ID 필드 제외)."""
    skip = {"time", "timestamp", "t", "date", "domainid", "instanceid", "sid", "oid", "id", "interval"}
    out = {}
    for r in rows:
        if isinstance(r, dict):
            for k, v in r.items():
                if str(k).lower() in skip or isinstance(v, bool):
                    continue
                if isinstance(v, (int, float)):
                    out.setdefault(k, []).append(v)
                elif isinstance(v, list) and v and all(isinstance(x, (int, float)) for x in v):
                    out.setdefault(k, []).extend(v)
        elif isinstance(r, (int, float)) and not isinstance(r, bool):
            out.setdefault("value", []).append(r)
    return out


def _stats(vals):
    if not vals:
        return {}
    n = len(vals)
    half = max(1, n // 2)
    first, last = sum(vals[:half]) / half, sum(vals[-half:]) / half
    return {"n": n, "min": min(vals), "max": max(vals), "avg": round(sum(vals) / n, 3), "last": vals[-1],
            "first_half_avg": round(first, 3), "second_half_avg": round(last, 3),
            "trend_pct": round((last - first) / first * 100, 1) if first else None}


def instance_metrics(server, domain_id, instance_id, metrics, minutes=60, end="", interval=0):
    """인스턴스 지표 시계열 요약. metrics 는 쉼표로 여러 개 → 지표마다 1회 호출 (dbmetrics 는 1개만 받음, 실측)."""
    key = one_server(server)
    names = [m.strip() for m in str(metrics).split(",") if m.strip()]
    if not names:
        raise ToolError("metrics 필요 (metric_names 로 이름 확인)")
    if len(names) > 6:
        raise ToolError("metrics 는 한 번에 6개까지 (지표마다 호출 1회)")
    s, e = minute_window(minutes, end)
    out, bad = {}, []
    for m in names:
        try:
            rows = rows_of(_get(key, "instance_metrics", domain=int(domain_id), instance=int(instance_id), metric=m,
                                start=to_ms(s), end=to_ms(e), interval=int(interval or 0)))
            ser = _numeric_series(rows)
            out[m] = {"rows": len(rows), "stats": {k: _stats(v) for k, v in ser.items()}}
            if not ser:
                out[m]["sample"] = [_trunc(r) for r in rows[:3]]
        except jc.JenniferError as ex:
            bad.append({"metric": m, "reason": str(ex)})
    return {"server": key, "domain_id": domain_id, "instance_id": instance_id,
            "window": [s.strftime("%Y-%m-%d %H:%M"), e.strftime("%Y-%m-%d %H:%M")],
            "metrics": out, "failed": bad,
            "note": "trend_pct = 구간 뒤쪽 절반 평균이 앞쪽 절반 대비 몇 % 변했는지 (추세 판단 보조, 판정 아님)"}


def status_summary(server, domain_id, kind="application", minutes=10, end="", sort="", top=10):
    """구간 집계 (애플리케이션·SQL·외부호출·오류 등, kind 는 endpoints.json status.kinds). 시작·끝은 분 정시."""
    key = one_server(server)
    kinds = EP.get("status", {}).get("kinds", [])
    if kinds and kind not in kinds:
        raise ToolError("kind 는 %s 중 하나 (endpoints.json status.kinds)" % ", ".join(kinds))
    s, e = minute_window(minutes, end)
    top = max(1, min(int(top), CFG["max_rows"]))
    data = _get(key, "status", path_vars={"kind": kind}, domain=int(domain_id), start=to_ms(s), end=to_ms(e),
                sort=sort or None, count=top)
    rows = rows_of(data)
    return {"server": key, "domain_id": domain_id, "kind": kind,
            "window": [s.strftime("%Y-%m-%d %H:%M"), e.strftime("%Y-%m-%d %H:%M")],
            "total_rows": len(rows), "rows": [_trunc(r, 200) for r in rows[:top]],
            "note": "sort 는 metric_names 에 있는 이름만 (responseTime 은 500, 실측)"}


def _elapsed(r):
    v = _pick(r, "responseTime", "elapsedTime", "elapsed", "elapseTime", "response_time")
    return v if isinstance(v, (int, float)) else None


def _pct(sorted_vals, p):
    if not sorted_vals:
        return None
    return sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * p))]


TX_FIELDS = ("txid", "txId", "endTime", "startTime", "responseTime", "elapsedTime", "application", "applicationName",
             "instanceId", "instanceName", "sqlTime", "externalCallTime", "fetchTime", "cpuTime", "errorType",
             "errorCode", "exception", "status")


def transactions(server, domain_id, end="", seconds=60, instance_id=0, min_elapsed_ms=0, top=20):
    """트랜잭션 요약 (구간 60초 이하, 실측 1분 약 7천건): 건수·응답시간 분포·오류 수 + 느린 순 상위 top 건."""
    key = one_server(server)
    seconds = int(seconds)
    if not 1 <= seconds <= 60:
        raise ToolError("seconds 는 1~60 (transaction/time 구간 제한, 실측)")
    e = parse_time(end).replace(microsecond=0)
    s = e - timedelta(seconds=seconds)
    rows = rows_of(_get(key, "transactions", domain=int(domain_id), start=to_ms(s), end=to_ms(e),
                        instance=int(instance_id or 0)))
    el = sorted(x for x in (_elapsed(r) for r in rows) if x is not None)
    errs = [r for r in rows if _pick(r, "errorType", "errorCode", "exception")]
    slow = [r for r in rows if (_elapsed(r) or 0) >= int(min_elapsed_ms)]
    slow.sort(key=lambda r: -(_elapsed(r) or 0))
    top = max(1, min(int(top), CFG["max_rows"]))
    keep = {f.lower() for f in TX_FIELDS}
    compact = [{k: _trunc(v, 200) for k, v in r.items() if str(k).lower() in keep} or _trunc(r, 200)
               for r in slow[:top] if isinstance(r, dict)]
    return {"server": key, "domain_id": domain_id,
            "window": [s.strftime("%Y-%m-%d %H:%M:%S"), e.strftime("%Y-%m-%d %H:%M:%S")],
            "count": len(rows), "errors": len(errs),
            "elapsed_ms": {"p50": _pct(el, .5), "p90": _pct(el, .9), "p99": _pct(el, .99),
                           "max": el[-1] if el else None},
            "slowest": compact,
            "next": "느린 건의 txid·endTime 으로 transaction_profile"}


def transaction_profile(server, domain_id, txid, time_ms=""):
    """트랜잭션 프로파일 (구간별 소요). time_ms = 그 트랜잭션의 endTime (epoch ms 또는 '2026-11-08 14:30:15')."""
    key = one_server(server)
    if not re.fullmatch(r"-?\d{1,20}", str(txid).strip()):
        raise ToolError("txid 는 숫자")
    t = to_ms(parse_time(time_ms)) if not re.fullmatch(r"\d{13}", str(time_ms)) else int(time_ms)
    data = _get(key, "transaction_profile", domain=int(domain_id), txid=str(txid).strip(), time=t)
    rows = rows_of(data)
    return {"server": key, "domain_id": domain_id, "txid": str(txid), "count": len(rows),
            "profile": [_trunc(r, 300) for r in rows[:80]],
            "note": "프로파일 GAP = 바로 위 단계가 쓴 시간(실측 해석 규칙). instanceOid 는 서버 버그로 0 → instanceId 로 식별"}


# ---------------------------------------------------------------- 명세 기반 범용 조회
def _spec_files():
    return sorted(glob.glob(os.path.join(SPEC_DIR, "*.json")))


def load_spec_endpoints():
    """spec/*.json (Swagger 2 / OpenAPI 3) 의 GET 엔드포인트 목록. [{path, summary, params:[{name,in,required,type}]}]"""
    out = []
    for fn in _spec_files():
        try:
            with open(fn, encoding="utf-8") as f:
                spec = json.load(f)
        except (OSError, ValueError):
            continue
        base = spec.get("basePath", "") if spec.get("swagger") else ""
        for path, ops in (spec.get("paths") or {}).items():
            op = (ops or {}).get("get")
            if not isinstance(op, dict):
                continue
            prm = []
            for p in (ops.get("parameters") or []) + (op.get("parameters") or []):
                if isinstance(p, dict) and "name" in p:
                    prm.append({"name": p["name"], "in": p.get("in"), "required": bool(p.get("required")),
                                "type": p.get("type") or (p.get("schema") or {}).get("type")})
            full = (base.rstrip("/") + path) if base and base != "/" else path
            out.append({"path": full, "summary": op.get("summary") or op.get("description") or "",
                        "tags": op.get("tags") or [], "params": prm, "spec": os.path.basename(fn)})
    return out


def _policy(path):
    try:
        jc.check_path(re.sub(r"\{[^}]+\}", "x", path))
        return "allowed"
    except jc.BlockedError as e:
        return "blocked: " + str(e)


def api_catalog(keyword="", limit=40):
    """Jennifer Open API 명세(spec/*.json)에서 GET 엔드포인트 찾기 — 경로·설명·파라미터·호출 정책."""
    eps = load_spec_endpoints()
    if not eps:
        return {"count": 0, "note": "spec/ 에 Jennifer Swagger(JSON) 명세 파일이 없음. 뷰서버의 명세를 받아 spec/jennifer.json 으로 저장"}
    kw = _norm(keyword)
    rows = [dict(e, policy=_policy(e["path"])) for e in eps
            if not kw or kw in _norm(e["path"] + " " + e["summary"] + " " + " ".join(e["tags"]))]
    limit = max(1, min(int(limit), 200))
    return {"count": len(rows), "endpoints": rows[:limit]}


def api_get(server, path, params=""):
    """명세에 있는 GET 경로를 직접 조회 (호출 정책·개인정보 제거·출력 제한 적용). params: JSON 객체 문자열."""
    key = one_server(server)
    if isinstance(params, str):
        try:
            params = json.loads(params) if params.strip() else {}
        except ValueError:
            raise ToolError("params 는 JSON 객체 문자열 (예 '{\"domain_id\": 1}')")
    if not isinstance(params, dict):
        raise ToolError("params 는 JSON 객체")
    data = normalize(SERVERS[key].get(path, params))
    rows = rows_of(data)
    return {"server": key, "path": path, "params": params, "rows": len(rows),
            "data": _trunc(data if not isinstance(data, list) else data[:CFG["max_rows"]])}
