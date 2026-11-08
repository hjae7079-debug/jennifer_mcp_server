from jennifer_mcp.survey import build_call, load_spec_get_ops

SPEC = {
    "swagger": "2.0", "basePath": "/",
    "paths": {
        "/api/metrics": {"get": {"operationId": "metrics"}},
        "/api/dbmetrics/instance": {"get": {"parameters": [
            {"name": "domain_id", "in": "query", "required": True},
            {"name": "start_time", "in": "query", "required": True},
            {"name": "end_time", "in": "query", "required": True}]}},
        "/api/agent/{id}": {"get": {"parameters": [{"name": "id", "in": "path", "required": True}]},
                            "delete": {}},
        "/api-v2/manage/x": {"post": {}},
    },
}


def test_only_get_ops():
    ops = load_spec_get_ops(SPEC)
    assert [o["path"] for o in ops] == ["/api/agent/{id}", "/api/dbmetrics/instance", "/api/metrics"]


def test_build_call():
    ops = {o["path"]: o for o in load_spec_get_ops(SPEC)}
    path, q, skip = build_call(ops["/api/dbmetrics/instance"], {"domain_id": 1000}, 1791939630000, 300000)
    assert skip is None and q["start_time"] == 1791939300000 and q["end_time"] == 1791939600000
    path, q, skip = build_call(ops["/api/dbmetrics/instance"], {}, 1791939630000, 300000)
    assert "domain_id" in skip
    path, q, skip = build_call(ops["/api/agent/{id}"], {"id": 7}, 0, 1)
    assert path == "/api/agent/7" and skip is None
