"""쓰기 차단 규칙 검증 (설계 4.2: 조회 전용 토큰이 없으므로 코드 차단을 단위 테스트로 검증)."""
import pytest

from jennifer_mcp import guard

ALLOW = ["/api/metrics", "/api/status/*", "/api/dbmetrics/*"]


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "", "get2"])
def test_only_get(method):
    with pytest.raises(guard.BlockedCall):
        guard.check_call(method, "/api/metrics")


@pytest.mark.parametrize("path", [
    "/api-v2/manage/agent", "/api-v2/manage", "/API-V2/MANAGE/x", "/restapi/anything", "/restapi",
    "/api/auth/userlist", "/api/auth/userlist/1", "/api/auth/userlistAll",
    "//api/auth/userlist", "/api//auth/userlist",
])
def test_blocked_prefixes(path):
    with pytest.raises(guard.BlockedCall):
        guard.check_call("GET", path)


@pytest.mark.parametrize("path", [
    "http://evil/api/metrics", "//evil/api/metrics", "/api/../restapi/x", "/api/metrics?token=a",
    "/api/metrics#x", "/api/%2e%2e/restapi", "/api\\metrics", "/other/path", "/", "", "/api/met rics",
])
def test_malformed_paths(path):
    with pytest.raises(guard.BlockedCall):
        guard.check_call("GET", path)


@pytest.mark.parametrize("key", ["token", "TOKEN", "access_token", "api_key", "apikey"])
def test_token_in_query_blocked(key):
    with pytest.raises(guard.BlockedCall):
        guard.check_call("GET", "/api/metrics", {key: "x"})


def test_allowlist():
    assert guard.check_call("GET", "/api/metrics", allowlist=ALLOW) == "/api/metrics"
    assert guard.check_call("get", "/api/status/service/", allowlist=ALLOW) == "/api/status/service"
    with pytest.raises(guard.BlockedCall):
        guard.check_call("GET", "/api/realtime/instance", allowlist=ALLOW)
    with pytest.raises(guard.BlockedCall):
        guard.check_call("GET", "/api/metricsX", allowlist=ALLOW)


def test_no_allowlist_still_blocks():
    assert guard.check_call("GET", "/api-v2/deploy") == "/api-v2/deploy"
    with pytest.raises(guard.BlockedCall):
        guard.check_call("GET", "/api-v2/manage/x", allowlist=None)


def test_client_has_no_write_path():
    """클라이언트 소스에 GET 외 메서드 문자열이 없어야 합니다."""
    import inspect
    from jennifer_mcp import client
    src = inspect.getsource(client)
    for m in ("\"POST\"", "\"PUT\"", "\"DELETE\"", "\"PATCH\"", "'POST'", "'PUT'", "'DELETE'"):
        assert m not in src
