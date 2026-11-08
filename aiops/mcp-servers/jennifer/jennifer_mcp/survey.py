"""공식 명세(Swagger/OpenAPI) 기준 GET 전수 호출 → 샘플 수집 (매뉴얼 G단계).

  python -m jennifer_mcp.survey --spec swagger.json --server internet \
      --params config/survey-params.json --out /data/collection/jennifer-survey

- 명세의 GET 작업만 대상으로 합니다. POST/PUT/DELETE 는 목록에도 넣지 않습니다.
- guard 차단 규칙(관리·restapi·사용자 목록)은 그대로 적용됩니다. 허용 목록(allowlist)만 우회합니다.
- 응답은 clientIp/clientId 제거, 배열 50건으로 잘라 저장합니다. 토큰은 어디에도 저장하지 않습니다.
- 결과: <out>/<server>/summary.csv, summary.json, samples/*.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from dataclasses import replace
from pathlib import Path

from . import guard
from .client import JenniferClient
from .config import load_settings

TIME_START_NAMES = {"start_time", "starttime", "stime", "start", "from"}
TIME_END_NAMES = {"end_time", "endtime", "etime", "end", "to"}


def load_spec_get_ops(spec: dict) -> list[dict]:
    """OpenAPI 2/3 문서에서 GET 작업만 뽑습니다."""
    base = spec.get("basePath", "") if "swagger" in spec else ""
    ops = []
    for path, item in sorted((spec.get("paths") or {}).items()):
        if not isinstance(item, dict):
            continue
        common = item.get("parameters", [])
        op = item.get("get")
        if not isinstance(op, dict):
            continue
        params = []
        for p in list(common) + list(op.get("parameters", [])):
            if isinstance(p, dict) and p.get("in") in ("query", "path"):
                params.append({"name": p.get("name"), "in": p.get("in"), "required": bool(p.get("required"))})
        full = (base.rstrip("/") + "/" + path.lstrip("/")) if base else path
        ops.append({"path": full, "operationId": op.get("operationId", ""), "summary": op.get("summary", ""),
                    "params": params})
    return ops


def build_call(op: dict, given: dict, now_ms: int, window_ms: int) -> tuple[str, dict, str | None]:
    """(경로, 쿼리 파라미터, 건너뛸 사유) 를 만듭니다."""
    end = now_ms - (now_ms % 60_000)
    start = end - window_ms
    path = op["path"]
    query: dict = {}
    for p in op["params"]:
        name = p["name"]
        key = name.lower()
        if name in given:
            val = given[name]
        elif key in TIME_START_NAMES:
            val = start
        elif key in TIME_END_NAMES:
            val = end
        else:
            val = None
        if p["in"] == "path":
            if val is None:
                return path, {}, f"경로 파라미터 '{name}' 값 없음"
            path = path.replace("{" + name + "}", str(val))
        elif val is not None:
            query[name] = val
        elif p["required"]:
            return path, {}, f"필수 파라미터 '{name}' 값 없음 (--params 에 추가)"
    if re.search(r"{[^}]+}", path):
        return path, {}, "치환되지 않은 경로 파라미터"
    return path, query, None


def _safe_name(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", path.strip("/")) or "root"


def main() -> None:
    ap = argparse.ArgumentParser(description="JENNIFER GET 전수 호출(샘플 수집)")
    ap.add_argument("--spec", required=True, help="Swagger/OpenAPI JSON 파일")
    ap.add_argument("--server", required=True, help="servers.json 의 name (internet|admin|public)")
    ap.add_argument("--params", help="파라미터 기본값 JSON (예: {\"domain_id\":1000,\"instance_id\":10001})")
    ap.add_argument("--out", required=True)
    ap.add_argument("--window-min", type=int, default=5, help="시간 파라미터 자동 구간(분)")
    ap.add_argument("--max-items", type=int, default=50)
    ap.add_argument("--dry-run", action="store_true", help="호출하지 않고 대상·차단 목록만 출력")
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    given = json.loads(Path(args.params).read_text(encoding="utf-8")) if args.params else {}
    settings = replace(load_settings(), enabled=True)  # 운영자가 명시적으로 실행하는 도구
    client = JenniferClient(settings)
    out = Path(args.out) / args.server
    (out / "samples").mkdir(parents=True, exist_ok=True)

    rows = []
    now_ms = int(time.time() * 1000)
    for op in load_spec_get_ops(spec):
        path, query, skip = build_call(op, given, now_ms, args.window_min * 60_000)
        row = {"path": op["path"], "called_path": path, "operationId": op["operationId"],
               "result": "", "detail": "", "bytes": "", "items": ""}
        if skip:
            row.update(result="skipped", detail=skip)
        else:
            try:
                guard.check_call("GET", path, query)
            except guard.BlockedCall as e:
                row.update(result="blocked", detail=str(e))
            else:
                if args.dry_run:
                    row.update(result="dry-run", detail=json.dumps(query, ensure_ascii=False))
                else:
                    res = client.get(args.server, path, query, use_allowlist=False, max_items=args.max_items)
                    if res.get("available"):
                        body = json.dumps(res, ensure_ascii=False, indent=1)
                        (out / "samples" / f"{_safe_name(path)}.json").write_text(body, encoding="utf-8")
                        tr = res.get("truncation") or {}
                        row.update(result="ok", bytes=len(body), items=tr.get("total", ""))
                    else:
                        row.update(result="error", detail=res.get("reason", ""))
        rows.append(row)
        print(f"{row['result']:8} {path} {row['detail']}")

    with (out / "summary.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["path"])
        w.writeheader()
        w.writerows(rows)
    (out / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["result"]] = counts.get(r["result"], 0) + 1
    print("요약:", counts, "→", out)


if __name__ == "__main__":
    main()
