import json
import time
import threading
import urllib.request
import urllib.parse
import urllib.error

class JenniferClient:
    """JENNIFER OpenAPI 코어 클라이언트 (표준 라이브러리 urllib만 사용)"""
    def __init__(self, url, token, domain_id, timeout=30):
        self.base_url = url.rstrip('/')
        self.token = token
        self.domain_id = domain_id
        self.timeout = timeout
        self._lock = threading.Lock()
        # 간단한 호출 간격 제한 (제니퍼 서버 부하 방지용 큐레이팅)
        self._last_call = 0.0

    def call_api(self, endpoint, params=None):
        with self._lock:
            now = time.time()
            if now - self._last_call < 0.5:
                time.sleep(0.5 - (now - self._last_call))
            self._last_call = time.time()

        url = f"{self.base_url}/api/domain/{self.domain_id}/{endpoint}"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"

        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/json")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode('utf-8')
                return json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            return {"error": f"HTTP {e.code}: {e.reason}", "details": body}
        except Exception as e:
            return {"error": str(e)}
