import pytest

from jennifer_mcp.sanitize import limit_items, strip_pii
from jennifer_mcp.timeutil import align_minute_range, check_max_window, java_date_to_epoch_ms, to_epoch_ms


def test_strip_pii_recursive():
    data = {"result": [{"txid": 1, "clientIp": "1.2.3.4", "clientId": "u", "nested": {"client_ip": "x", "ok": 1}}],
            "CLIENTIP": "y"}
    out = strip_pii(data)
    assert out == {"result": [{"txid": 1, "nested": {"ok": 1}}]}
    assert data["CLIENTIP"] == "y"  # 원본은 변경하지 않음


def test_limit_items():
    obj, info = limit_items({"result": list(range(10))}, 3)
    assert obj["result"] == [0, 1, 2] and info["total"] == 10
    obj, info = limit_items(list(range(2)), 3)
    assert info is None
    obj, info = limit_items(list(range(5)), 0)
    assert info is None and len(obj) == 5


def test_to_epoch_ms():
    assert to_epoch_ms("2026-10-14 10:00") == 1791939600000
    assert to_epoch_ms(1791939600) == 1791939600000
    assert to_epoch_ms("1791939600000") == 1791939600000
    with pytest.raises(ValueError):
        to_epoch_ms("어제")


def test_align_minute():
    s, e = align_minute_range(1791939630000, 1791939690000)
    assert s == 1791939600000 and e == 1791939720000
    s, e = align_minute_range("2026-10-14 10:00", "2026-10-14 10:00")
    assert e - s == 60000
    with pytest.raises(ValueError):
        align_minute_range("2026-10-14 10:05", "2026-10-14 10:00")


def test_window():
    check_max_window(0, 60000, 60000)
    with pytest.raises(ValueError):
        check_max_window(0, 60001, 60000)


def test_java_date():
    assert java_date_to_epoch_ms("Tue Oct 14 10:00:00 KST 2026") == 1791939600000
    with pytest.raises(ValueError):
        java_date_to_epoch_ms("2026-10-14")
