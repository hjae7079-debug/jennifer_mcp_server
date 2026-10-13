import os
import json
from jennifer_client import JenniferClient

def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

CFG = load_config()
CLIENT = JenniferClient(
    url=CFG.get("jennifer_url", "http://127.0.0.1:7900"),
    token=CFG.get("jennifer_token", ""),
    domain_id=CFG.get("domain_id", 1),
    timeout=CFG.get("timeout", 30)
)

def get_active_service():
    result = CLIENT.call_api("realtime/activeService")
    if isinstance(result, dict) and "error" in result:
        return f"제니퍼 API 호출 실패: {result['error']}"
    return json.dumps(result, ensure_ascii=False)

def get_system_resource(stime, etime):
    params = {"stime": stime, "etime": etime}
    result = CLIENT.call_api("metric/system", params=params)
    if isinstance(result, dict) and "error" in result:
        return f"제니퍼 API 호출 실패: {result['error']}"
    return json.dumps(result, ensure_ascii=False)

def get_xlog(stime, etime, min_response_time=3000):
    params = {"stime": stime, "etime": etime, "minResTime": min_response_time}
    result = CLIENT.call_api("xlog", params=params)
    if isinstance(result, dict) and "error" in result:
        return f"제니퍼 API 호출 실패: {result['error']}"
    return json.dumps(result, ensure_ascii=False)
