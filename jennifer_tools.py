import os
import json
from jennifer_client import JenniferClient

# 설정 불러오기
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
    """현재 WAS의 액티브 서비스(Active Service) 수치를 조회합니다."""
    result = CLIENT.call_api("realtime/activeService")
    if "error" in result:
        return f"제니퍼 API 호출 실패: {result['error']}"
    return json.dumps(result, ensure_ascii=False)

def get_system_resource(stime, etime):
    """특정 시간대의 WAS CPU 및 Heap Memory 사용률을 조회합니다."""
    params = {"stime": stime, "etime": etime}
    result = CLIENT.call_api("metric/system", params=params)
    if "error" in result:
        return f"제니퍼 API 호출 실패: {result['error']}"
    return json.dumps(result, ensure_ascii=False)

def get_xlog(stime, etime, min_response_time=3000):
    """특정 시간대에 발생한 지연 트랜잭션(XLog) 목록을 조회합니다."""
    params = {"stime": stime, "etime": etime, "minResTime": min_response_time}
    result = CLIENT.call_api("xlog", params=params)
    if "error" in result:
        return f"제니퍼 API 호출 실패: {result['error']}"
    return json.dumps(result, ensure_ascii=False)
