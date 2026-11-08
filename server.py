"""JENNIFER APM MCP 서버 (조회 전용, nsims_mcp 와 같은 구조).

운영 (Streamable HTTP 서비스 — 상시 실행, 여러 클라이언트가 URL 로 접속):
  python server.py --gen-token hermes              # 클라이언트별 토큰 발급 → tokens.json
  python server.py --set-jennifer-token internet   # Jennifer API 토큰 저장 (화면에 안 보이게 입력) → secrets.json
  python server.py --http                          # config.json http.bind:port (기본 127.0.0.1:8791/mcp)

시험:
  python server.py                                 # stdio (클라이언트가 자식 프로세스로 실행)
  python server.py --selftest                      # MCP 없이 세 뷰서버 연결만 확인

로직은 jennifer_tools.py, 호출 정책(GET 전용·차단 경로)은 jennifer_client.py, HTTP 인증은 service.py.
mcp SDK v1(FastMCP)/v2(MCPServer) 모두 지원.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anyio  # noqa: E402  (mcp SDK 의존성)
import jennifer_client as jc  # noqa: E402
import jennifer_tools as T  # noqa: E402

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
    SDK_MAJOR = 2
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    SDK_MAJOR = 1

VERSION = "0.1.0"  # 0.1.0 (11/08): 첫 판 — 서버 3대 분리·GET 전용 호출 정책·개인정보 제거·명세 기반 범용 조회·가짜 뷰서버
INSTRUCTIONS = """JENNIFER APM(WAS 성능) 조회 도구. 읽기 전용이며 쓰기·관리 API 는 호출할 수 없다.
뷰서버 3대: 인터넷 업무(internet)·행정 업무(admin)·대민 업무(public). server 인자로 고르고, 비우면 가능한 도구는 3대 전체를 본다.
한 서버가 응답하지 않으면 그 서버만 unavailable 에 사유와 함께 나오고 나머지 결과는 정상이다 — 결론에 '조회 불가(서버, 사유)'를 적는다.
분석 순서: 대상 찾기(find_instance: VM 이름·IP·호스트명, instance_list) → 지표 이름 확인(metric_names) →
지표 추세(instance_metrics, 지표마다 호출 1회) → 구간 집계(status_summary) → 느린 트랜잭션(transactions, 60초 이하) → 원인 구간(transaction_profile).
지표·집계 수치는 도구가 계산한 값만 근거로 쓰고, 근거마다 server·domain_id·instance_id·구간을 적는다. 수치가 없으면 추측하지 말고 '근거 부족'.
위 도구에 없는 조회는 api_catalog(명세 검색) → api_get(GET 경로 직접 조회). 차단 경로(관리·사용자 목록 등)는 policy 에 blocked 로 나온다.
시각 형식: '2026-11-08 14:30', '14:30', epoch ms. end 생략 = 지금. 개인정보(clientIp·clientId)는 응답에서 이미 지워져 있다."""

try:  # 서버 버전을 initialize 응답(serverInfo.version)에 노출 (v1 FastMCP 는 version 인자가 없음)
    mcp = _Server("jennifer_apm", instructions=INSTRUCTIONS, version=VERSION)
except TypeError:
    mcp = _Server("jennifer_apm", instructions=INSTRUCTIONS)
    if hasattr(mcp, "_mcp_server"):
        mcp._mcp_server.version = VERSION


def _call_sync(fn, *a, **kw):
    try:
        return T.dumps(fn(*a, **kw))
    except (T.ToolError, jc.JenniferError) as e:
        return T.dumps({"error": str(e)})
    except Exception as e:  # noqa: BLE001 - LLM 에게 원인을 돌려준다
        return T.dumps({"error": "%s: %s" % (type(e).__name__, e)})


async def _call(fn, *a, **kw):
    # 뷰서버 조회는 블로킹 → 작업 스레드에서 (HTTP 서비스에서 다른 클라이언트가 멈추지 않게)
    return await anyio.to_thread.run_sync(lambda: _call_sync(fn, *a, **kw))


@mcp.tool(structured_output=False)
async def servers_status() -> str:
    """[JENNIFER] 뷰서버 3대의 연결 상태·응답 시간·도메인 수, 호출 빈도, 아직 실서버로 확인 안 된 경로 목록. 처음에 한 번."""
    return await _call(T.servers_status)


@mcp.tool(structured_output=False)
async def domain_list(server: str = "") -> str:
    """[JENNIFER] 도메인 목록 (domain_id·이름). server 비우면 3대 전체."""
    return await _call(T.domain_list, server)


@mcp.tool(structured_output=False)
async def instance_list(server: str = "", domain_id: int = 0, keyword: str = "", state: str = "", limit: int = 50) -> str:
    """[JENNIFER] 인스턴스(WAS 에이전트) 목록: server·domain_id·instance_id·이름·IP·호스트·상태.
    domain_id 0 이면 모든 도메인(목록은 10분 캐시). keyword 로 이름·IP·호스트 일부 거르기, state 예 'STOPPED'.
    server 비우면 3대 전체."""
    return await _call(T.instance_list, server, domain_id, keyword, state, limit)


@mcp.tool(structured_output=False)
async def find_instance(keyword: str) -> str:
    """[JENNIFER] VM 이름(vm00012345)·IP·호스트명·인스턴스 이름 일부로 3대 전체에서 인스턴스 찾기.
    장애 대상 VM 이 어느 서버·도메인·인스턴스인지 확인할 때. 여러 개 나오면 모두 후보로 다룬다."""
    return await _call(T.find_instance, keyword)


@mcp.tool(structured_output=False)
async def metric_names(server: str = "", keyword: str = "") -> str:
    """[JENNIFER] 조회 가능한 지표 이름 (/api/metrics). instance_metrics 의 metrics, status_summary 의 sort 에 이 이름만 쓴다.
    keyword 예 'heap', 'gc', 'pool'. server: 뷰서버 — '인터넷'(internet)·'행정'(admin)·'대민'(public) (비우면 첫 서버)."""
    return await _call(T.metric_names, server, keyword)


@mcp.tool(structured_output=False)
async def realtime_instance(server: str, domain_id: int, instance_id: int = 0) -> str:
    """[JENNIFER] 인스턴스 실시간 상태 (액티브 서비스·CPU·힙 등). 실측 4~5초 걸리므로 필요한 인스턴스만.
    server: 뷰서버 — '인터넷'(internet)·'행정'(admin)·'대민'(public)."""
    return await _call(T.realtime_instance, server, domain_id, instance_id)


@mcp.tool(structured_output=False)
async def instance_metrics(server: str, domain_id: int, instance_id: int, metrics: str, minutes: int = 60,
                           end: str = "", interval: int = 0) -> str:
    """[JENNIFER] 인스턴스 지표 시계열 요약 (최소·최대·평균·마지막·앞뒤 절반 평균·trend_pct).
    metrics: 쉼표 구분 최대 6개 (지표마다 호출 1회 — 한 번에 2개 보내면 서버 500, 실측). 이름은 metric_names 로 확인.
    minutes: 구간(분, 최대 1440). end 생략 = 지금. 구간은 분 정시로 맞춤. server: 뷰서버 — '인터넷'(internet)·'행정'(admin)·'대민'(public)."""
    return await _call(T.instance_metrics, server, domain_id, instance_id, metrics, minutes, end, interval)


@mcp.tool(structured_output=False)
async def status_summary(server: str, domain_id: int, kind: str = "application", minutes: int = 10, end: str = "",
                         sort: str = "", top: int = 10) -> str:
    """[JENNIFER] 도메인의 구간 집계 상위 top 건. kind: application·sql·externalcall·error (endpoints.json status.kinds).
    sort 는 metric_names 에 있는 이름만 (예 averageResponseTime, elapseSum — responseTime 은 500). 구간은 분 정시.
    인스턴스 필터는 이 API 에서 동작하지 않음(실측) → 인스턴스 단위는 instance_metrics. server: 뷰서버 — '인터넷'(internet)·'행정'(admin)·'대민'(public)."""
    return await _call(T.status_summary, server, domain_id, kind, minutes, end, sort, top)


@mcp.tool(structured_output=False)
async def transactions(server: str, domain_id: int, end: str = "", seconds: int = 60, instance_id: int = 0,
                       min_elapsed_ms: int = 0, top: int = 20) -> str:
    """[JENNIFER] 짧은 구간(최대 60초)의 트랜잭션 요약: 건수·오류 수·응답시간 p50/p90/p99/max + 느린 순 상위 top 건(txid·endTime 포함).
    1분에 수천 건이라 원문 대량 조회는 하지 않는다. 장애 시각 주변 1분을 end 로 지정. server: 뷰서버 — '인터넷'(internet)·'행정'(admin)·'대민'(public)."""
    return await _call(T.transactions, server, domain_id, end, seconds, instance_id, min_elapsed_ms, top)


@mcp.tool(structured_output=False)
async def transaction_profile(server: str, domain_id: int, txid: str, end_time: str) -> str:
    """[JENNIFER] 트랜잭션 하나의 프로파일 (SQL·외부호출 등 구간별 소요). end_time = transactions 결과의 endTime (epoch ms).
    GAP = 바로 위 단계가 쓴 시간. server: 뷰서버 — '인터넷'(internet)·'행정'(admin)·'대민'(public)."""
    return await _call(T.transaction_profile, server, domain_id, txid, end_time)


@mcp.tool(structured_output=False)
async def api_catalog(keyword: str = "", limit: int = 40) -> str:
    """[JENNIFER] Open API 명세(spec/*.json)에서 GET 엔드포인트 검색: 경로·설명·파라미터·호출 정책(allowed/blocked).
    전용 도구에 없는 조회가 필요할 때 api_get 전에."""
    return await _call(T.api_catalog, keyword, limit)


@mcp.tool(structured_output=False)
async def api_get(server: str, path: str, params: str = "") -> str:
    """[JENNIFER] 명세에 있는 GET 경로 직접 조회. path 예 '/api/domain', params 는 JSON 객체 문자열 예 '{"domain_id": 1000}'.
    시각 파라미터는 epoch ms. 관리·사용자 목록·쓰기 경로는 차단되고, 토큰을 params 에 넣을 수 없다. server: 뷰서버 — '인터넷'(internet)·'행정'(admin)·'대민'(public)."""
    return await _call(T.api_get, server, path, params)


def main():
    ap = argparse.ArgumentParser(description="JENNIFER APM MCP 서버 v%s" % VERSION)
    ap.add_argument("--http", action="store_true", help="Streamable HTTP 서비스로 실행 (운영)")
    ap.add_argument("--bind", help="HTTP 바인드 주소 (config.json http.bind 대신)")
    ap.add_argument("--port", type=int, help="HTTP 포트 (config.json http.port 대신)")
    ap.add_argument("--gen-token", metavar="NAME", help="클라이언트 토큰 발급 후 종료")
    ap.add_argument("--revoke-token", metavar="NAME", help="클라이언트 토큰 폐기 후 종료")
    ap.add_argument("--set-jennifer-token", metavar="SERVER", help="Jennifer API 토큰 저장 (internet|admin|public)")
    ap.add_argument("--selftest", action="store_true", help="뷰서버 연결만 확인")
    a = ap.parse_args()

    if a.gen_token or a.revoke_token:
        import service
        service.manage_token(gen=a.gen_token, revoke=a.revoke_token)
    elif a.set_jennifer_token:
        val = sys.stdin.readline().strip() if not sys.stdin.isatty() else getpass.getpass(
            "%s 토큰 (화면에 안 보임): " % a.set_jennifer_token).strip()
        if not val:
            sys.exit("빈 값")
        T.set_secret(a.set_jennifer_token, val)
        print("저장됨: secrets.json [%s] (권한 600). 실행 중인 서비스는 재시작해야 적용" % a.set_jennifer_token)
    elif a.selftest:
        print(json.dumps(T.servers_status(), ensure_ascii=False, indent=1))
    elif a.http:
        import service
        T.cleanup_logs()
        service.run_http(mcp, SDK_MAJOR, VERSION, bind=a.bind, port=a.port)
    else:
        mcp.run()  # stdio


if __name__ == "__main__":
    main()
