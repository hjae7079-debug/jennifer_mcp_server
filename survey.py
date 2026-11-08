"""Jennifer Open API 전수 GET 호출 (샘플 수집) — 매뉴얼 G단계 "제니퍼 전수 호출".

명세(spec/*.json)의 GET 엔드포인트를 하나씩 불러 응답 형식·소요 시간을 기록하고, 마스킹한 샘플을 samples/ 에 저장한다.
- 호출은 jennifer_client 를 거치므로 호출 정책(GET 전용·차단 경로·토큰 쿼리 금지)과 개인정보 제거가 그대로 적용된다
- 파라미터는 이름으로 채움: domain_id→첫 도메인, instance_id→첫 LIVE 인스턴스, start/end→최근 정시 구간(ms), metrics→첫 지표 …
  모르는 필수 파라미터가 있으면 부르지 않고 report 에 '건너뜀(사유)'로 남긴다. --param 이름=값 으로 직접 채울 수 있다
- 샘플은 목록을 20행으로 자르고 IPv4 를 198.18.x.x 로 일관되게 바꿈 (같은 IP → 같은 가짜 IP). 그래도 반출 전에 한 번 열어 볼 것
- --edge: 실측 제약(지표 2개·정시 아님·60초 초과·정렬 이름) 재확인 케이스도 부름

사용:
  python survey.py --server internet --dry-run          # 무엇을 어떤 파라미터로 부를지만 출력
  python survey.py --server internet                    # 실제 호출 → samples/internet/*.json, samples/survey_internet_<시각>.md
  python survey.py --server admin --only status --edge
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jennifer_client as jc  # noqa: E402
import jennifer_tools as T  # noqa: E402

SAMPLES = os.path.join(T.BASE, "samples")
_IPV4 = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")


class Masker:
    def __init__(self):
        self.map = {}

    def ip(self, m):
        s = m.group(1)
        try:
            a = ipaddress.ip_address(s)
        except ValueError:
            return s
        if a.is_loopback or a.is_unspecified or str(a).startswith(("198.18.", "198.19.")):
            return s
        if s not in self.map:
            n = len(self.map) + 1
            self.map[s] = "198.%d.%d.%d" % (18 + (n >> 16 & 1), n >> 8 & 255, n & 255)
        return self.map[s]

    def __call__(self, obj):
        if isinstance(obj, dict):
            return {k: self(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self(x) for x in obj]
        if isinstance(obj, str):
            return _IPV4.sub(self.ip, obj)
        return obj


def cut(obj, n=20):
    if isinstance(obj, list):
        return [cut(x, n) for x in obj[:n]] + (["…(%d개 중 %d개)" % (len(obj), n)] if len(obj) > n else [])
    if isinstance(obj, dict):
        return {k: cut(v, n) for k, v in obj.items()}
    return obj


def shape(obj, depth=0):
    """응답 구조 요약 (키·형식) — 명세 대조 보고서용."""
    if depth > 3:
        return "…"
    if isinstance(obj, dict):
        return {k: shape(v, depth + 1) for k, v in list(obj.items())[:40]}
    if isinstance(obj, list):
        return [shape(obj[0], depth + 1), "len=%d" % len(obj)] if obj else []
    return type(obj).__name__


def build_context(key):
    ctx = {"errors": []}
    end = T.now().replace(second=0, microsecond=0) - timedelta(minutes=1)
    ctx.update(end=T.to_ms(end), start=T.to_ms(end - timedelta(minutes=5)), start60=T.to_ms(end - timedelta(seconds=60)))
    try:
        ids = T._domain_ids(key)
        ctx["domain"] = ids[0] if ids else None
    except (jc.JenniferError, T.ToolError) as e:
        ctx["errors"].append("domain: %s" % e)
    if ctx.get("domain") is not None:
        try:
            insts = T._all_instances(key, ctx["domain"])
            live = [i for i in insts if "live" in str(i.get("state", "")).lower()] or insts
            ctx["instance"] = live[0]["instance_id"] if live else None
        except (jc.JenniferError, T.ToolError) as e:
            ctx["errors"].append("instance: %s" % e)
    try:
        m = T.metric_names(key)["metrics"]
        first = m[0] if m else None
        ctx["metric"] = first.get("name") if isinstance(first, dict) else first
    except (jc.JenniferError, T.ToolError, KeyError, IndexError) as e:
        ctx["errors"].append("metric: %s" % e)
    if ctx.get("domain") is not None:
        try:
            tx = T.transactions(key, ctx["domain"], end=str(ctx["end"]), seconds=60, top=1)["slowest"]
            if tx:
                ctx["txid"] = T._pick(tx[0], "txid", "txId")
                ctx["tx_end"] = T._pick(tx[0], "endTime")
        except (jc.JenniferError, T.ToolError) as e:
            ctx["errors"].append("txid: %s" % e)
    return ctx


def fill(name, ctx, path, overrides):
    n = name.lower().replace("_", "")
    if name in overrides:
        return overrides[name]
    short = "/transaction/time" in path or "/xview" in path
    table = {
        "domainid": ctx.get("domain"), "sid": ctx.get("domain"),
        "instanceid": ctx.get("instance"), "oid": ctx.get("instance"),
        "starttime": ctx["start60"] if short else ctx["start"], "stime": ctx["start60"] if short else ctx["start"],
        "endtime": ctx["end"], "etime": ctx["end"],
        "metrics": ctx.get("metric"), "metric": ctx.get("metric"),
        "time": ctx.get("tx_end") or ctx["end"], "txid": ctx.get("txid"),
        "count": 10, "limit": 10, "size": 10, "top": 10,
    }
    return table.get(n)


def plan(key, ctx, eps, overrides):
    out = []
    for e in eps:
        pol = T._policy(e["path"])
        item = {"path": e["path"], "summary": e["summary"][:80]}
        if pol != "allowed":
            out.append(dict(item, skip=pol))
            continue
        path, params, missing = e["path"], {}, []
        for p in e["params"]:
            v = fill(p["name"], ctx, e["path"], overrides)
            if p.get("in") == "path":
                if v is None:
                    missing.append(p["name"])
                else:
                    path = path.replace("{%s}" % p["name"], str(v))
            elif p.get("in") in ("query", None):
                if v is not None:
                    params[p["name"]] = v
                elif p["required"]:
                    missing.append(p["name"])
            elif p.get("in") == "header" and p["name"].lower() == "authorization":
                continue
            elif p["required"]:
                missing.append("%s(%s)" % (p["name"], p.get("in")))
        if missing:
            out.append(dict(item, skip="필수 파라미터 미상: " + ", ".join(missing)))
        else:
            out.append(dict(item, call=path, params=params))
    return out


def edge_cases(ctx):
    """실측 제약 재확인 (v4.0 4.2절). (이름, endpoints.json 항목, kw, path_vars)"""
    d, i, m = ctx.get("domain"), ctx.get("instance"), ctx.get("metric") or "heap_used"
    e = ctx["end"]
    return [
        ("dbmetrics 지표 2개 (기대: 500)", "instance_metrics",
         dict(domain=d, instance=i, metric="%s,%s" % (m, m), start=ctx["start"], end=e), None),
        ("status 시작이 정시 아님 (기대: 500)", "status", dict(domain=d, start=ctx["start"] + 15000, end=e), {"kind": "application"}),
        ("status sort=responseTime (기대: 500)", "status", dict(domain=d, start=ctx["start"], end=e, sort="responseTime"),
         {"kind": "application"}),
        ("status sort=averageResponseTime (O-06)", "status", dict(domain=d, start=ctx["start"], end=e,
                                                                  sort="averageResponseTime"), {"kind": "application"}),
        ("status sort=elapseSum (O-06)", "status", dict(domain=d, start=ctx["start"], end=e, sort="elapseSum"),
         {"kind": "application"}),
        ("transaction/time 61초 (기대: 오류)", "transactions", dict(domain=d, start=e - 61000, end=e), None),
    ]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", required=True, help="internet|admin|public (별명 가능)")
    ap.add_argument("--only", default="", help="경로에 이 글자가 들어간 것만")
    ap.add_argument("--param", action="append", default=[], help="이름=값 (여러 번)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--edge", action="store_true", help="실측 제약 재확인 케이스도")
    ap.add_argument("--sleep", type=float, default=1.0, help="호출 사이 대기(초), 뷰서버 부하 보호")
    a = ap.parse_args()

    key = T.one_server(a.server)
    eps = [e for e in T.load_spec_endpoints() if a.only.lower() in e["path"].lower()]
    if not eps:
        sys.exit("spec/*.json 에 GET 엔드포인트가 없음 (명세 파일을 spec/ 에 두세요)")
    overrides = dict(x.split("=", 1) for x in a.param)
    print("[%s] 문맥 준비 (도메인·인스턴스·지표·txid) …" % key, file=sys.stderr)
    ctx = build_context(key)
    print("  domain=%s instance=%s metric=%s txid=%s %s" % (ctx.get("domain"), ctx.get("instance"), ctx.get("metric"),
                                                         ctx.get("txid"), ctx["errors"] or ""), file=sys.stderr)
    items = plan(key, ctx, eps, overrides)
    if a.dry_run:
        print(json.dumps(items, ensure_ascii=False, indent=1))
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = os.path.join(SAMPLES, key)
    os.makedirs(outdir, mode=0o700, exist_ok=True)
    mask = Masker()
    report = []
    for it in items:
        if "skip" in it:
            report.append(it)
            continue
        t0 = time.monotonic()
        try:
            data = T.normalize(T.SERVERS[key].get(it["call"], it["params"]))
            fn = re.sub(r"[^A-Za-z0-9]+", "_", it["call"]).strip("_") + ".json"
            path = os.path.join(outdir, fn)
            with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
                json.dump({"path": it["path"], "call": mask(it["call"]), "params": mask(it["params"]),
                           "collected": stamp, "data": mask(cut(data))}, f, ensure_ascii=False, indent=1)
            it.update(ok=True, rows=len(T.rows_of(data)), shape=shape(data), sample=os.path.relpath(path, T.BASE))
        except jc.JenniferError as e:
            it.update(ok=False, error=str(e)[:300])
        it["ms"] = int((time.monotonic() - t0) * 1000)
        print("  %-4s %6dms %s" % ("OK" if it.get("ok") else "FAIL", it["ms"], it["call"]), file=sys.stderr)
        report.append(it)
        time.sleep(a.sleep)

    if a.edge:
        for name, ep, kw, pv in edge_cases(ctx):
            t0 = time.monotonic()
            try:
                data = T._get(key, ep, path_vars=pv, **kw)
                r = {"edge": name, "ok": True, "rows": len(T.rows_of(data))}
            except (jc.JenniferError, T.ToolError) as e:
                r = {"edge": name, "ok": False, "error": str(e)[:200]}
            r["ms"] = int((time.monotonic() - t0) * 1000)
            print("  EDGE %-5s %s" % (r["ok"], name), file=sys.stderr)
            report.append(r)
            time.sleep(a.sleep)

    base = os.path.join(SAMPLES, "survey_%s_%s" % (key, stamp))
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(mask({"server": key, "context": {k: v for k, v in ctx.items() if k != "errors"},
                        "context_errors": ctx["errors"], "items": report}), f, ensure_ascii=False, indent=1)
    ok = sum(1 for r in report if r.get("ok"))
    fail = sum(1 for r in report if r.get("ok") is False)
    skip = sum(1 for r in report if "skip" in r)
    lines = ["# Jennifer 전수 GET 호출 — %s (%s)" % (T.server_title(key), stamp), "",
             "성공 %d · 실패 %d · 건너뜀 %d · IP 마스킹 %d개" % (ok, fail, skip, len(mask.map)), "",
             "| 결과 | 경로 | 행 | ms | 비고 |", "|---|---|---|---|---|"]
    for r in report:
        if "edge" in r:
            lines.append("| %s | (경계) %s | %s | %s | %s |" % ("정상 응답" if r["ok"] else "오류 응답", r["edge"], r.get("rows", ""),
                                                            r["ms"], r.get("error", "")[:80]))
        elif "skip" in r:
            lines.append("| 건너뜀 | `%s` | | | %s |" % (r["path"], r["skip"][:80]))
        else:
            lines.append("| %s | `%s` | %s | %s | %s |" % ("성공" if r["ok"] else "실패", r["path"], r.get("rows", ""), r["ms"],
                                                       r.get("error", "")[:80].replace("|", "/")))
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(mask("\n".join(lines)) + "\n")
    print("보고서: %s.md / .json  샘플: %s/" % (base, outdir), file=sys.stderr)


if __name__ == "__main__":
    main()
