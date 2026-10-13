import json
import time
import threading
import urllib.request
import urllib.parse
import urllib.error

class JenniferClient:
    def __init__(self, url, token, domain_id, timeout=30):
        self.base_url = url.rstrip('/')
        self.token = token
        self.domain_id = domain_id
        self.timeout = timeout
        self._lock = threading.Lock()
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
            handlers = [urllib.request.ProxyHandler({})]
            opener = urllib.request.build_opener(*handlers)
            with opener.open(req, timeout=self.timeout) as resp:
                body = resp.read().decode('utf-8')
                return json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8') if e.fp else ""
            return {"error": f"HTTP {e.code}: {e.reason}", "details": body}
        except Exception as e:
            return {"error": str(e)}
